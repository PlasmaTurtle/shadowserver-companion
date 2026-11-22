"""Check exact release dependencies and security/citation regression tests.

This is a release engineering gate, not a workstation acceptance test. Advisory
requests contain public package names and versions only. No workspace is opened.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

# Keep the original release regressions, then follow security boundaries rather
# than a release suffix. Browser acceptance remains in tools/verify.py.
SUITE_PATTERNS = (
    "test_*_072.py",
    "test_security*.py",
    "test_*session*.py",
    "test_*capture*.py",
    "test_request_limit*.py",
    "test_*body_limit*.py",
    "test_api_acquisition*.py",
    "test_workspace_data*.py",
    "test_backup_snapshot_decode*.py",
    "test_release_privacy*.py",
    "test_admission*.py",
    "test_evidence_registry*.py",
    "test_entity_lifecycle*.py",
    "test_ownership_matrix*.py",
    "test_workspace_health*.py",
    "test_certification_concurrency*.py",
    "shadowserver_api_module/test_cli_credentials.py",
    "shadowserver_api_module/test_network.py",
    "shadowserver_api_module/test_download.py",
)


def security_suites(root: Path) -> list[str]:
    """Return existing Python boundary suites once, in stable path order."""
    return sorted(
        {
            path.relative_to(root).as_posix()
            for folder in (root / "tests", *sorted((root / "modules").glob("*/tests")))
            for pattern in SUITE_PATTERNS
            for path in folder.glob(pattern)
            if path.is_file() and not path.is_symlink()
        }
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-python", type=Path, default=Path(sys.executable))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    suites = security_suites(ROOT)
    if not suites:
        parser.error("Security regression suites are missing")
    env = dict(os.environ)
    env.pop("WORKBENCH_PREVIEW", None)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT), str(ROOT / "modules/attribution/components/engine/src")]
    )
    commands = [
        (
            "Dependencies",
            [
                sys.executable,
                "tools/check_dependencies.py",
                "--audit",
                "--audit-python",
                str(args.audit_python),
                "--output",
                str(output / "dependencies.json"),
            ],
        ),
        ("Security and citation regressions", [sys.executable, "-m", "pytest", "-q", *suites]),
    ]
    results = []
    for index, (label, command) in enumerate(commands):
        with (output / f"check-{index + 1}.log").open("w", encoding="utf-8") as log:
            process = subprocess.run(
                command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=False
            )
        results.append({"check": label, "exit_code": process.returncode})
        print(f"{label}: {'passed' if process.returncode == 0 else 'failed'}", flush=True)
        if process.returncode:
            break
    passed = len(results) == len(commands) and all(r["exit_code"] == 0 for r in results)
    report = {
        "release": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "checks": results,
        "suites": suites,
        "native_windows_acceptance": False,
        "scope": "Exact Python dependency advisories and targeted Python security/citation regressions, including session, capture, import and restore boundaries; run tools/verify.py separately for full regressions and browser acceptance.",
    }
    (output / "security-gate.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
