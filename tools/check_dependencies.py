"""Verify release locks and optionally audit exact public package versions.

Offline verification uses only the repository's wheels and lock files. --audit
requires pip-audit in the selected tool interpreter and sends only public
package names/versions to its advisory service; it never opens a case workspace.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
INTERNAL = "outreach-attribution"


def canonical(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def pins(path, *, hashed):
    result = {}
    pattern = r"([A-Za-z0-9_.-]+)==([^\s]+)"
    if hashed:
        pattern += r" --hash=sha256:([0-9a-f]{64})"
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        match = re.fullmatch(pattern, raw)
        if not match:
            raise ValueError(f"Noncanonical dependency pin: {path.name}:{number}")
        name = canonical(match[1])
        if name in result:
            raise ValueError(f"Duplicate dependency pin: {name}")
        result[name] = {"version": match[2], "sha256": match[3] if hashed else None}
    return result


def wheel_inventory(root):
    expected = json.loads((root / "wheelhouse-sha256.json").read_text(encoding="utf-8"))
    actual = {p.name for p in (root / "wheelhouse").glob("*.whl")}
    if set(expected) != actual:
        raise ValueError(f"Wheel inventory differs from manifest: {root}")
    lock = pins(root / "requirements-windows.txt", hashed=True)
    records = {}
    for filename, digest in sorted(expected.items()):
        if Path(filename).name != filename or not filename.endswith(".whl"):
            raise ValueError("Unsafe wheel manifest member")
        path = root / "wheelhouse" / filename
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Changed wheel: {filename}")
        with zipfile.ZipFile(path) as wheel:
            metadata = [n for n in wheel.namelist() if n.endswith(".dist-info/METADATA")]
            if len(metadata) != 1 or wheel.testzip():
                raise ValueError(f"Invalid wheel: {filename}")
            parsed = BytesParser().parsebytes(wheel.read(metadata[0]))
        name, version = canonical(parsed["Name"]), parsed["Version"]
        if name in records or lock.get(name) != {"version": version, "sha256": digest}:
            raise ValueError(f"Wheel metadata/hash does not match requirements: {filename}")
        records[name] = {"name": name, "version": version, "artifact": filename, "sha256": digest}
    if set(records) != set(lock):
        raise ValueError("Requirements contain an unbundled dependency")
    return records


def verify_source_requirements(root, records):
    """Keep the source installer on the same exact application versions.

    Deliberately accept only the repository's documented requirements format;
    an added index, include, unpinned dependency or alternate local project must
    be reviewed instead of silently escaping the release integrity check.
    """
    path = root / "requirements.txt"
    references = {"-c requirements-constraints.txt", "./components/attribution"}
    seen = set()
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        if raw in references:
            name = raw
        else:
            match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^\s]+)", raw)
            if not match:
                raise ValueError(f"Noncanonical source requirement: {path.name}:{number}")
            name = canonical(match[1])
            if name == INTERNAL or records.get(name, {}).get("version") != match[2]:
                raise ValueError(f"Source requirement differs from Windows lock: {name}")
        if name in seen:
            raise ValueError(f"Duplicate source requirement: {name}")
        seen.add(name)
    if not references.issubset(seen):
        raise ValueError("Source requirements must retain constraints and local attribution source")


def verify(root=ROOT):
    records = wheel_inventory(root)
    verify_source_requirements(root, records)
    module = root / "components" / "attribution"
    standalone = wheel_inventory(module)
    for name, value in standalone.items():
        if records.get(name) != value:
            raise ValueError(f"Standalone and application wheels disagree: {name}")
    constraints = pins(root / "requirements-constraints.txt", hashed=False)
    if set(constraints) != set(records) - {INTERNAL}:
        raise ValueError("Constraint set differs from bundled public packages")
    for name, pin in constraints.items():
        if pin["version"] != records[name]["version"]:
            raise ValueError(f"Constraint version differs from Windows lock: {name}")
    project = tomllib.loads((module / "pyproject.toml").read_text())["project"]
    if project["version"] != records[INTERNAL]["version"]:
        raise ValueError("Attribution source version differs from bundled wheel")
    source_root = module / "src"
    source_files = {
        p.relative_to(source_root).as_posix(): p
        for p in (source_root / "attribution").rglob("*.py")
    }
    with zipfile.ZipFile(root / "wheelhouse" / records[INTERNAL]["artifact"]) as wheel:
        members = {
            n for n in wheel.namelist() if n.startswith("attribution/") and n.endswith(".py")
        }
        if members != set(source_files):
            raise ValueError("Bundled attribution Python files differ from current source")
        if any(wheel.read(name) != path.read_bytes() for name, path in source_files.items()):
            raise ValueError("Bundled attribution wheel is stale; rebuild it from current source")
    return list(records.values())


def audit(packages, interpreter=sys.executable):
    public = [p for p in packages if p["name"] != INTERNAL]
    with tempfile.TemporaryDirectory(prefix="companion-dependency-audit-") as folder:
        request = Path(folder) / "requirements.txt"
        output = Path(folder) / "audit.json"
        request.write_text("".join(f"{p['name']}=={p['version']}\n" for p in public))
        completed = subprocess.run(
            [
                str(interpreter),
                "-m",
                "pip_audit",
                "--no-deps",
                "--disable-pip",
                "-r",
                str(request),
                "-f",
                "json",
                "-o",
                str(output),
                "--timeout",
                "20",
            ],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if completed.returncode not in (0, 1) or not output.is_file():
            raise ValueError("Advisory audit failed; no successful audit can be recorded")
        report = json.loads(output.read_text())
    rows = report.get("dependencies", [])
    if (
        len(rows) != len(public)
        or {canonical(p.get("name", "")) for p in rows} != {p["name"] for p in public}
        or any(p.get("skip_reason") for p in rows)
        or any(not isinstance(p.get("vulns"), list) for p in rows)
    ):
        raise ValueError("Advisory audit did not cover every pinned public package")
    expected = {p["name"]: p["version"] for p in public}
    if any(expected[canonical(p["name"])] != p.get("version") for p in rows):
        raise ValueError("Advisory audit versions differ from the release")
    count = sum(len(p.get("vulns", [])) for p in rows)
    if completed.returncode == 1 and not count:
        raise ValueError("Advisory scanner failed without reporting a vulnerability")
    return {
        "status": "vulnerabilities_found" if count else "passed",
        "advisory_count": count,
        "public_packages": len(public),
        "excluded_internal_package": INTERNAL,
        "report": report,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--audit-python", type=Path, default=Path(sys.executable))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        packages = verify()
        result = {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "release": (ROOT / "VERSION").read_text().strip(),
            "lock_integrity": "passed",
            "packages": packages,
            "advisory_audit": audit(packages, args.audit_python)
            if args.audit
            else {"status": "not_run"},
            "scope": "Python wheel advisories only; native codecs and CPython require separate review.",
        }
        if args.output:
            args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 1 if result["advisory_audit"]["status"] == "vulnerabilities_found" else 0
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired, zipfile.BadZipFile) as error:
        print(f"Dependency check failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
