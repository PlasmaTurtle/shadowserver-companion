"""Build the navigable source map and enforce explicit import boundaries.

No application imports, workspace reads, network calls or third-party tooling.
The graph includes local/deferred Python imports and literal ES module imports,
including import('...'). It does not infer computed imports, Python imported
symbols, dynamic calls, SQL access or browser action-registry dispatch.
"""

from __future__ import annotations

import argparse
import ast
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
MODULE_FOLDERS = {
    "components",
    "tools",
    "helpers",
    "databases",
    "static",
    "tests",
    "docs",
    "fonts",
    "schemas",
    "resources",
}


def module_name(path):
    value = path.as_posix()
    if value.startswith("modules/attribution/components/engine/src/"):
        value = value.removeprefix("modules/attribution/components/engine/src/")
    if value.endswith(".py"):
        return value[:-3].replace("/", ".").removesuffix(".__init__")
    return value


def inventory(root):
    """Find owned source and accidental loose programs without scanning dependencies."""
    paths = []
    excluded = {
        "tests",
        "node_modules",
        "vendor",
        "wheelhouse",
        "build",
        "dist",
        "__pycache__",
        "data",
        "data-demo",
    }
    for directory, folders, filenames in os.walk(root):
        folders[:] = [
            name
            for name in folders
            if not name.startswith(".") and name not in excluded and not name.endswith(".egg-info")
        ]
        for filename in filenames:
            if filename == "conftest.py":
                continue
            path = Path(directory) / filename
            if path.suffix in {".py", ".js"}:
                paths.append(path.relative_to(root))
    return sorted(paths)


_JS_TOKENS = re.compile(
    r"(?P<comment>//[^\n]*|/\*[\s\S]*?\*/)"
    r"|(?P<string>'(?:\\[\s\S]|[^'\\])*'|\"(?:\\[\s\S]|[^\"\\])*\")"
    r"|(?P<template>`(?:\\[\s\S]|[^`\\])*`)"
    r"|(?P<word>[A-Za-z_$][\w$]*)|(?P<operator>=>|\?\.)|(?P<other>[^\s])"
)
_JS_REGEX = re.compile(r"/(?![/*])(?:\\.|\[(?:\\.|[^\]\\])*\]|[^/\\\n])+/[a-z]*")


def javascript_targets(text):
    """Read literal ES imports without matching comments or quoted examples.

    This is a lexical scanner, not a JavaScript parser. Template strings (including
    their interpolations), computed imports and CommonJS calls are outside scope.
    """
    tokens, offset = [], 0
    while match := _JS_TOKENS.search(text, offset):
        kind, value = match.lastgroup, match.group()
        offset = match.end()
        if kind == "comment":
            continue
        if value == "/" and (
            not tokens
            or tokens[-1][1] in {"=", "(", "[", "{", ",", ":", ";", "!", "?", "return", "=>"}
        ):
            literal = _JS_REGEX.match(text, match.start())
            if literal:
                offset = literal.end()
                tokens.append(("regex", literal.group(), match.start()))
                continue
        tokens.append((kind, value, match.start()))
    for index, (kind, value, start) in enumerate(tokens):
        if kind != "word" or value not in {"import", "export"}:
            continue
        if index and tokens[index - 1][1] in {".", "?."}:
            continue
        tail = tokens[index + 1 :]
        candidate = None
        if value == "import" and tail and tail[0][0] == "string":
            candidate = tail[0]
        elif value == "import" and len(tail) >= 3 and tail[0][1] == "(":
            if tail[1][0] == "string" and tail[2][1] in {")", ","}:
                candidate = tail[1]
        elif tail and (tail[0][1] in {"{", "*"} or (value == "import" and tail[0][0] == "word")):
            binding_depth = 0
            for left, right in zip(tail, tail[1:]):
                if left[1] == "{":
                    binding_depth += 1
                elif left[1] == "}":
                    binding_depth -= 1
                if not binding_depth and left[1] in {
                    ";",
                    "import",
                    "export",
                    "const",
                    "let",
                    "var",
                    "function",
                    "class",
                    "return",
                }:
                    break
                if not binding_depth and left[1] == "from" and right[0] == "string":
                    candidate = right
                    break
        if candidate:
            # JSON-style escapes and ordinary JS string escapes used in paths.
            # JS permits \/; Python retains it. Replace by escape-pair so an
            # escaped backslash followed by a slash is not changed accidentally.
            literal = re.sub(
                r"\\[\s\S]",
                lambda match: "/" if match.group() == r"\/" else match.group(),
                candidate[1],
            )
            try:
                target = ast.literal_eval(literal)
            except (SyntaxError, ValueError):
                continue
            yield target, text.count("\n", 0, start) + 1


def import_details(path, text):
    """Return graph candidates, actual module bases and source diagnostics."""
    found, targets, diagnostics = [], [], []
    if path.suffix == ".js":
        for target, line in javascript_targets(text):
            if not target.startswith(("./", "../", "/modules/")):
                continue
            try:
                target_path = unquote(urlsplit(target).path)
            except ValueError:
                diagnostics.append(
                    f"{path.as_posix()}:{line}: invalid local JavaScript import {target}"
                )
                continue
            if "\\" in target_path:
                diagnostics.append(
                    f"{path.as_posix()}:{line}: local JavaScript imports must use URL path separators: {target}"
                )
                continue
            parts = [] if target_path.startswith("/") else list(path.parent.parts)
            for part in target_path.split("/"):
                if part == "..":
                    if not parts:
                        diagnostics.append(
                            f"{path.as_posix()}:{line}: JavaScript import escapes source root: {target}"
                        )
                        break
                    parts.pop()
                elif part not in {"", "."}:
                    parts.append(part)
            else:
                name = "/".join(parts)
                found.append(name)
                targets.append((name, line, True))
        return sorted(set(found)), targets, diagnostics
    module = module_name(path)
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    package_parts = package.split(".") if package else []
    try:
        tree = ast.parse(text)
    except SyntaxError as error:
        return [], [], [f"{path.as_posix()}:{error.lineno}: invalid Python syntax: {error.msg}"]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(a.name for a in node.names)
            targets.extend((a.name, node.lineno, False) for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level > len(package_parts):
                diagnostics.append(
                    f"{path.as_posix()}:{node.lineno}: relative Python import escapes package root"
                )
                continue
            prefix = (
                ".".join(package_parts[: len(package_parts) - node.level + 1]) if node.level else ""
            )
            base = ".".join(p for p in (prefix, node.module) if p)
            found.append(base)
            targets.append((base, node.lineno, bool(node.level)))
            found.extend(base + "." + a.name for a in node.names)
    return sorted(set(found)), targets, diagnostics


def imports(path, text):
    return import_details(path, text)[0]


def missing_imports(root, path, targets, python_roots):
    """Check local module bases, without importing code or guessing symbols.

    Existing directories may be namespace packages; files outside the graph (for
    example generated/vendor code) remain valid targets. Unknown absolute Python
    roots may be third-party packages and are deliberately not checked here.
    """
    errors = []
    for name, line, relative in targets:
        if path.suffix == ".js":
            try:
                candidate = (root / name).resolve()
                if not candidate.is_relative_to(root.resolve()):
                    errors.append(
                        f"{path.as_posix()}:{line}: JavaScript import escapes source root: {name}"
                    )
                    continue
                exists = candidate.is_file()
            except (OSError, ValueError):
                errors.append(f"{path.as_posix()}:{line}: invalid local JavaScript import {name}")
                continue
            language = "JavaScript"
        else:
            first, *rest = name.split(".")
            if first not in python_roots and not relative:
                continue
            base = python_roots.get(first, root / first).joinpath(*rest)
            exists = base.is_dir() or base.with_suffix(".py").is_file()
            language = "Python"
        if not exists:
            errors.append(f"{path.as_posix()}:{line}: missing local {language} module {name}")
    return errors


def cycles(edges):
    # Tarjan strongly connected components; no runtime imports are required.
    index, stack, active, indexes, low, result = 0, [], set(), {}, {}, []

    def visit(node):
        nonlocal index
        indexes[node] = low[node] = index
        index += 1
        stack.append(node)
        active.add(node)
        for target in sorted(edges[node]):
            if target not in indexes:
                visit(target)
                low[node] = min(low[node], low[target])
            elif target in active:
                low[node] = min(low[node], indexes[target])
        if low[node] == indexes[node]:
            group = []
            while True:
                item = stack.pop()
                active.remove(item)
                group.append(item)
                if item == node:
                    break
            if len(group) > 1:
                result.append(sorted(group))

    for node in sorted(edges):
        if node not in indexes:
            visit(node)
    return sorted(result)


def within(name, prefixes):
    return any(
        name == prefix or name.startswith((prefix + ".", prefix + "/")) for prefix in prefixes
    )


def analyze(root=ROOT):
    registry = json.loads((root / "docs/components.json").read_text(encoding="utf-8"))
    components = registry["components"]
    layout_errors = []
    if registry.get("project_paths"):
        expected = {component["id"] for component in components}
        present = {
            path.name
            for path in (root / "modules").iterdir()
            if path.is_dir() and not path.name.startswith((".", "__"))
        }
        for name in sorted(present - expected):
            layout_errors.append(f"modules/{name}: module has no registered owner")
        for name in sorted(expected):
            for folder in sorted(MODULE_FOLDERS):
                if not (root / "modules" / name / folder).is_dir():
                    layout_errors.append(f"modules/{name}/{folder}: missing module folder")
        components = [
            *components,
            {
                "id": "project",
                "name": "Project infrastructure",
                "kind": "Top-level integration",
                "paths": registry["project_paths"],
                "entry": "run.py",
                "contract": "Application launch, release packaging and project-wide verification.",
                "tests": ["tests"],
                "next_work": "Keep feature implementations inside their module.",
            },
        ]
    paths = inventory(root)
    modules = {module_name(p): p for p in paths}
    python_roots = {
        name.split(".")[0]: root / name.split(".")[0]
        for name, path in modules.items()
        if path.suffix == ".py"
    }
    engine = root / "modules/attribution/components/engine/src/attribution"
    if engine.is_dir():
        python_roots["attribution"] = engine
    errors, files, edges, referenced_by_module = layout_errors, [], {}, {}
    for module, path in modules.items():
        owners = [c for c in components if any(path.full_match(pattern) for pattern in c["paths"])]
        if len(owners) != 1:
            errors.append(f"{path}: expected one owner, found {[c['id'] for c in owners]}")
        text = (root / path).read_text(encoding="utf-8")
        referenced, targets, diagnostics = import_details(path, text)
        errors.extend(diagnostics)
        errors.extend(missing_imports(root, path, targets, python_roots))
        referenced_by_module[module] = referenced
        # Include imported package init and explicit submodule imports when both exist.
        resolved = set()
        for name in referenced:
            if name in modules:
                resolved.add(name)
            elif "tools" in path.parts:
                sibling = ".".join(path.parent.parts) + "." + name
                if sibling in modules:
                    resolved.add(sibling)
        internal = sorted(resolved - {module})
        edges[module] = set(internal)
        symbols = []
        if path.suffix == ".py":
            try:
                body = ast.parse(text).body
            except SyntaxError:
                body = []  # import_details already reports the source diagnostic.
            for node in body:
                if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                ) and not node.name.startswith("_"):
                    symbols.append(
                        {
                            "name": node.name,
                            "line": node.lineno,
                            "kind": "class" if isinstance(node, ast.ClassDef) else "function",
                        }
                    )
        else:
            symbols = [
                {"name": m.group(1), "line": text[: m.start()].count("\n") + 1, "kind": "export"}
                for m in re.finditer(r"export\s+(?:async\s+)?function\s+(\w+)", text)
            ]
        files.append(
            {
                "path": path.as_posix(),
                "module": module,
                "owner": owners[0]["id"] if len(owners) == 1 else "unassigned",
                "lines": len(text.splitlines()),
                "sha256": hashlib.sha256(text.encode()).hexdigest(),
                "imports": internal,
                "symbols": symbols,
            }
        )
    for rule in registry["rules"]:
        for module, dependencies in edges.items():
            if not within(module, rule["source"]):
                continue
            for target in referenced_by_module[module]:
                if (
                    rule.get("stdlib_only")
                    and not within(target, rule.get("allow_internal", []))
                    and target.split(".", 1)[0] not in sys.stdlib_module_names
                ):
                    errors.append(f"{rule['name']}: non-stdlib import {module} -> {target}")
                if within(target, rule.get("deny_external", [])):
                    errors.append(
                        f"{rule['name']}: prohibited provider/persistence import {module} -> {target}"
                    )
                if within(target, rule.get("deny", [])):
                    errors.append(f"{rule['name']}: {module} -> {target}")
            for target in dependencies:
                if (
                    "allow_internal" in rule
                    and not within(target, rule["allow_internal"])
                    and target not in rule.get("allow_exact", [])
                ):
                    errors.append(f"{rule['name']}: {module} -> {target}")
    found_cycles = cycles(edges)
    for group in found_cycles:
        if not any(set(group) <= set(known) for known in registry["known_cycles"]):
            errors.append("New dependency cycle: " + " -> ".join(group))
    for component in components:
        if component.get("entry") and not (root / component["entry"]).is_file():
            errors.append(f"{component['id']}: missing component entry {component['entry']}")
        for target in component["tests"]:
            if target.startswith(("tests/", "modules/")) and not (root / target).exists():
                errors.append(f"{component['id']}: missing test entry {target}")
    owner = {f["module"]: f["owner"] for f in files}
    grouped = defaultdict(list)
    for source, targets in edges.items():
        for target in targets:
            if owner[source] != owner[target]:
                grouped[(owner[source], owner[target])].append({"from": source, "to": target})
    links = [
        {"from": a, "to": b, "imports": sorted(v, key=lambda x: (x["from"], x["to"]))}
        for (a, b), v in sorted(grouped.items())
    ]
    return {
        "schema": 1,
        "release": (root / "VERSION").read_text(encoding="utf-8").strip(),
        "release_channel": json.loads((root / "RELEASE.json").read_text(encoding="utf-8")).get(
            "channel"
        )
        if (root / "RELEASE.json").exists()
        else "unspecified",
        "scope": registry["description"],
        "components": components,
        "files": files,
        "links": links,
        "cycles": found_cycles,
        "rules": registry["rules"],
        "errors": sorted(set(errors)),
    }


def render(data, root=ROOT):
    template = (root / "tools/program_map_template.html").read_text(encoding="utf-8")
    payload = (
        json.dumps(data, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    return template.replace("/*PROGRAM_DATA*/null", payload)


def verify(root=ROOT):
    """Fail a build for boundary violations or documentation drift."""
    data = analyze(root)
    errors = list(data["errors"])
    outputs = {
        root / "docs/program-map.json": json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        root / "docs/program-map.html": render(data, root),
    }
    for path, expected in outputs.items():
        if not path.exists() or path.read_text(encoding="utf-8") != expected:
            errors.append(
                f"{path.relative_to(root)} is stale; run python tools/program_map.py --write"
            )
    if errors:
        raise ValueError("Program boundaries/map check failed: " + "; ".join(errors))
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Regenerate docs/program-map.json and docs/program-map.html",
    )
    parser.add_argument(
        "--check", action="store_true", help="Fail for boundary violations or stale generated maps"
    )
    args = parser.parse_args()
    data = analyze()
    outputs = {
        ROOT / "docs/program-map.json": json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        ROOT / "docs/program-map.html": render(data),
    }
    errors = list(data["errors"])
    if args.write and not errors:
        for path, value in outputs.items():
            path.write_text(value, encoding="utf-8", newline="\n")
    if args.check:
        for path, value in outputs.items():
            if not path.exists() or path.read_text(encoding="utf-8") != value:
                errors.append(
                    f"{path.relative_to(ROOT)} is stale; run python tools/program_map.py --write"
                )
    print(
        json.dumps(
            {
                "release": data["release"],
                "components": len(data["components"]),
                "owned_modules": len(data["files"]),
                "known_cycles": data["cycles"],
                "errors": errors,
            },
            indent=2,
        )
    )
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
