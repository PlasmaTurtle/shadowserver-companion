"""Build the navigable source map and enforce explicit import boundaries.

No application imports, workspace reads, network calls or third-party tooling.
The graph includes local/deferred Python imports and literal ES module imports;
it does not infer dynamic calls, SQL access or browser action-registry dispatch.
"""

from __future__ import annotations

import argparse
import ast
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]


def module_name(path):
    value = path.as_posix()
    if value.startswith("components/attribution/src/"):
        value = value.removeprefix("components/attribution/src/")
    if value.endswith(".py"):
        return value[:-3].replace("/", ".").removesuffix(".__init__")
    return value


def inventory(root):
    paths = {root / "run.py", root / "excel_intake.py"}
    for folder, pattern in [
        ("workbench", "*.py"),
        ("components/attribution/src", "*.py"),
        ("tools", "*.py"),
        ("static", "*.js"),
    ]:
        paths.update((root / folder).rglob(pattern))
    return sorted(
        p.relative_to(root)
        for p in paths
        if "__pycache__" not in p.parts and "vendor" not in p.parts
    )


def imports(path, text):
    if path.suffix == ".js":
        result = []
        for target in re.findall(
            r"\b(?:import|export)\s+(?:[^;]*?\s+from\s+)?[\'\"]([^\'\"]+)[\'\"]", text
        ):
            if target.startswith("."):
                parts = []
                for part in (path.parent / target).parts:
                    if part == "..":
                        parts.pop()
                    elif part != ".":
                        parts.append(part)
                result.append("/".join(parts))
        return result
    module = module_name(path)
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    found = []
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            found.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = (
                ".".join(package.split(".")[: len(package.split(".")) - node.level + 1])
                if node.level
                else ""
            )
            base = ".".join(p for p in (prefix, node.module) if p)
            found.append(base)
            found.extend(base + "." + a.name for a in node.names)
    return sorted(set(found))


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
    return any(name == prefix or name.startswith(prefix + ".") for prefix in prefixes)


def analyze(root=ROOT):
    registry = json.loads((root / "docs/components.json").read_text())
    components = registry["components"]
    paths = inventory(root)
    modules = {module_name(p): p for p in paths}
    errors, files, edges, referenced_by_module = [], [], {}, {}
    for module, path in modules.items():
        owners = [c for c in components if any(path.match(pattern) for pattern in c["paths"])]
        if len(owners) != 1:
            errors.append(f"{path}: expected one owner, found {[c['id'] for c in owners]}")
        text = (root / path).read_text(encoding="utf-8")
        referenced = imports(path, text)
        referenced_by_module[module] = referenced
        # Include imported package init and explicit submodule imports when both exist.
        resolved = set()
        for name in referenced:
            if name in modules:
                resolved.add(name)
            elif path.parts[0] == "tools":
                sibling = ".".join(path.parent.parts) + "." + name
                if sibling in modules:
                    resolved.add(sibling)
        internal = sorted(resolved - {module})
        edges[module] = set(internal)
        symbols = []
        if path.suffix == ".py":
            for node in ast.parse(text).body:
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
            for target in dependencies:
                if within(target, rule.get("deny", [])):
                    errors.append(f"{rule['name']}: {module} -> {target}")
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
        for target in component["tests"]:
            if target.startswith(("tests/", "components/")) and not (root / target).exists():
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
        "release": (root / "VERSION").read_text().strip(),
        "release_channel": json.loads((root / "RELEASE.json").read_text()).get("channel")
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
    template = (root / "tools/program_map_template.html").read_text()
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
        if not path.exists() or path.read_text() != expected:
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
            path.write_text(value, encoding="utf-8")
    if args.check:
        for path, value in outputs.items():
            if not path.exists() or path.read_text() != value:
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
