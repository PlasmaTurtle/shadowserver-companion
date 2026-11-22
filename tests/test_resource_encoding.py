"""UTF-8 tool artifacts retain text without relying on the host locale."""

import json
import os
from pathlib import Path
import subprocess
import sys


def test_dependency_audit_preserves_utf8_advisory_text_under_locale_defaults():
    root = Path(__file__).resolve().parents[1]
    program = r"""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from tools import check_dependencies as gate

assert sys.flags.utf8_mode == 0
description = "Synthetic \u010d advisory; retained \u6f22\u5b57 text"
report = {"dependencies": [{"name": "example", "version": "1.0",
          "vulns": [{"id": "SYNTHETIC-1", "description": description}]}]}
def scan(command, **kwargs):
    # No advisory service or subprocess: model its documented JSON file output.
    path = Path(command[command.index("-o") + 1])
    path.write_bytes(json.dumps(report, ensure_ascii=False).encode("utf-8"))
    return SimpleNamespace(returncode=1)
gate.subprocess.run = scan
result = gate.audit([{"name": "example", "version": "1.0"}])
assert result["status"] == "vulnerabilities_found" and result["advisory_count"] == 1
assert result["report"] == report
print(json.dumps(result["report"]))
"""
    run = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8=0",
            "-X",
            "warn_default_encoding",
            "-W",
            "error::EncodingWarning",
            "-c",
            program,
        ],
        cwd=root,
        env={**os.environ, "PYTHONUTF8": "0", "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        encoding="utf-8",
        timeout=30,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    description = json.loads(run.stdout)["dependencies"][0]["vulns"][0]["description"]
    assert description == "Synthetic č advisory; retained 漢字 text"
