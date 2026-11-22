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


def wheel_inventory(root, *, folder=None):
    """Derive exact artifact inventory from the approved lock and wheel metadata.

    Every wheel must have an approved hash before its ZIP is inspected, and every
    locked package must occur exactly once. Staged installer directories use the
    same checks as the source wheelhouse; no second hash manifest is required.
    """
    lock = pins(root / "requirements-windows.txt", hashed=True)
    approved = {pin["sha256"] for pin in lock.values()}
    folder = root / "wheelhouse" if folder is None else folder
    records = {}
    for path in sorted(folder.glob("*.whl")):
        filename = path.name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Changed wheel: {filename}")
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest not in approved:
            raise ValueError(f"Changed wheel: {filename}")
        with zipfile.ZipFile(path) as wheel:
            metadata = [n for n in wheel.namelist() if n.endswith(".dist-info/METADATA")]
            if len(metadata) != 1 or wheel.testzip():
                raise ValueError(f"Invalid wheel: {filename}")
            parsed = BytesParser().parsebytes(wheel.read(metadata[0]))
            wheel_info = BytesParser().parsebytes(
                wheel.read(metadata[0].removesuffix("METADATA") + "WHEEL")
            )
        if not parsed.get("Name") or not parsed.get("Version"):
            raise ValueError(f"Invalid wheel metadata: {filename}")
        name, version = canonical(parsed["Name"]), parsed["Version"]
        if name in records or lock.get(name) != {"version": version, "sha256": digest}:
            raise ValueError(f"Wheel metadata/hash does not match requirements: {filename}")
        stem = metadata[0].removesuffix(".dist-info/METADATA")
        declared_name, separator, declared_version = stem.rpartition("-")
        if not separator or canonical(declared_name) != name or declared_version != version:
            raise ValueError(f"Wheel metadata directory differs from its identity: {filename}")
        prefix = stem + ("-" + wheel_info["Build"] if wheel_info.get("Build") else "")
        parts = filename.removesuffix(".whl").rsplit("-", 3)
        # pip validates target compatibility from the filename during installation.
        # Upstream wheels can bundle a platform driver while retaining pure-Python
        # WHEEL tags; reproducing pip's compatibility rules here rejects those wheels.
        if len(parts) != 4 or parts[0] != prefix:
            raise ValueError(f"Wheel filename differs from its metadata identity: {filename}")
        records[name] = {"name": name, "version": version, "artifact": filename, "sha256": digest}
    if set(records) != set(lock):
        raise ValueError("Requirements contain an unbundled dependency")
    return records


def verify_source_requirements(root, records):
    """Keep the source installer on the same exact application versions.

    Deliberately accept only the repository's documented requirements format;
    an added index, include, duplicate version pin or alternate local project must
    be reviewed instead of silently escaping the release integrity check.
    """
    path = root / "requirements.txt"
    references = {"-c requirements-constraints.txt", "./modules/attribution/components/engine"}
    seen = set()
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        if raw in references:
            name = raw
        else:
            match = re.fullmatch(r"[A-Za-z0-9_.-]+", raw)
            if not match:
                raise ValueError(f"Noncanonical source requirement: {path.name}:{number}")
            name = canonical(raw)
            if name == INTERNAL or name not in records:
                raise ValueError(f"Source requirement differs from Windows lock: {name}")
        if name in seen:
            raise ValueError(f"Duplicate source requirement: {name}")
        seen.add(name)
    if not references.issubset(seen):
        raise ValueError("Source requirements must retain constraints and local attribution source")


def sync_constraints(root, records, *, write=False):
    """Maintain pip's portable version projection of the canonical Windows lock."""
    expected = (
        "# Generated from requirements-windows.txt; do not edit versions here.\n"
        "# Refresh with: python tools/check_dependencies.py --write\n"
        + "".join(
            f"{name}=={record['version']}\n"
            for name, record in sorted(records.items())
            if name != INTERNAL
        )
    )
    path = root / "requirements-constraints.txt"
    if write:
        path.write_text(expected, encoding="utf-8", newline="\n")
    elif not path.is_file() or path.read_text(encoding="utf-8") != expected:
        raise ValueError(
            "Generated constraints are stale; run python tools/check_dependencies.py --write"
        )


def verify(root=ROOT, *, write=False):
    records = wheel_inventory(root)
    verify_source_requirements(root, records)
    module = root / "modules/attribution/components/engine"
    standalone = wheel_inventory(module)
    # The independently shipped engine retains its own filename manifest.
    expected = json.loads((module / "wheelhouse-sha256.json").read_text(encoding="utf-8"))
    if expected != {row["artifact"]: row["sha256"] for row in standalone.values()}:
        raise ValueError("Standalone wheel inventory differs from its manifest")
    for name, value in standalone.items():
        if records.get(name) != value:
            raise ValueError(f"Standalone and application wheels disagree: {name}")
    project = tomllib.loads((module / "pyproject.toml").read_text(encoding="utf-8"))["project"]
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
    sync_constraints(root, records, write=write)
    return list(records.values())


def audit(packages, interpreter=sys.executable):
    public = [p for p in packages if p["name"] != INTERNAL]
    with tempfile.TemporaryDirectory(prefix="companion-dependency-audit-") as folder:
        request = Path(folder) / "requirements.txt"
        output = Path(folder) / "audit.json"
        request.write_text(
            "".join(f"{p['name']}=={p['version']}\n" for p in public), encoding="utf-8"
        )
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
        report = json.loads(output.read_text(encoding="utf-8"))
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
    parser.add_argument(
        "--write", action="store_true", help="Refresh common constraints from the verified lock"
    )
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--audit-python", type=Path, default=Path(sys.executable))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        packages = verify(write=args.write)
        result = {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "release": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
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
