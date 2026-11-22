"""Immutable bootstrap build identity and native synthetic launch lifecycle."""

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from tools.windows_installer import build


def test_bootstrap_is_content_addressed_outside_mutable_payload(tmp_path, monkeypatch):
    commands = []

    def compile(command, **kwargs):
        commands.append(command)
        output = next(value.split("=", 1)[1] for value in command if "DOUTPUT=" in value)
        Path(output).write_bytes(b"MZ synthetic immutable bootstrap")

    monkeypatch.setattr(build.subprocess, "run", compile)
    source, descriptor = build.build_bootstrap(tmp_path, "SyntheticProbe", "makensis")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    assert source.parent == tmp_path / "bootstrap"
    assert descriptor == {"protocol": 1, "path": f"bootstrap/launch-{digest}.exe", "sha256": digest}
    original_time = source.stat().st_mtime_ns
    assert build.build_bootstrap(tmp_path, "SyntheticProbe", "makensis") == (source, descriptor)
    assert source.stat().st_mtime_ns == original_time
    assert all(any("DAPP_ID=SyntheticProbe" in arg for arg in command) for command in commands)
    source.write_bytes(b"unexpected replacement")
    with pytest.raises(ValueError, match="does not match"):
        build.build_bootstrap(tmp_path, "SyntheticProbe", "makensis")
    assert source.read_bytes() == b"unexpected replacement"


@pytest.mark.skipif(os.name != "nt", reason="Native Windows launch protocol")
def test_native_bootstrap_lifecycle(tmp_path):
    compiler = shutil.which("makensis")
    if compiler is None:
        pytest.skip("NSIS compiler is not installed or selected on PATH")
    python_home = Path(sys.base_prefix)
    if not (python_home / "python314.dll").is_file():
        pytest.skip("Python 3.14 native runtime fixture is unavailable")
    result = subprocess.run(
        [
            sys.executable,
            str(build.HERE / "verify_bootstrap.py"),
            "--output",
            str(tmp_path / "native"),
            "--makensis",
            compiler,
            "--python-home",
            str(python_home),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    assert result.returncode == 0, result.stdout + result.stderr
