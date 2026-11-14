"""Prepare the source edition from the same runtime and wheel locks as setup.

This bootstrap deliberately needs only the standard library. Any installed
Python 3 may invoke it; it selects the required interpreter before creating the
application environment. Existing workspaces are never touched.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def runtime_version(root: Path = ROOT) -> tuple[int, int]:
    lock = json.loads(
        (root / "tools/windows_installer/runtime-lock.json").read_text(encoding="utf-8")
    )
    return tuple(int(part) for part in lock["version"].split(".")[:2])


def compatible(executable: list[str], version: tuple[int, int]) -> bool:
    command = (
        "import sys,struct; "
        f'assert sys.version_info[:2] == {version!r} and struct.calcsize("P") == 8'
    )
    try:
        return (
            subprocess.run(
                [*executable, "-c", command],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            ).returncode
            == 0
        )
    except OSError:
        return False


def select_interpreter(version: tuple[int, int]) -> list[str]:
    if sys.version_info[:2] == version and struct.calcsize("P") == 8:
        return [sys.executable]
    candidate = ["py", "-" + ".".join(map(str, version))]
    if compatible(candidate, version):
        return candidate
    raise RuntimeError(
        "Python "
        + ".".join(map(str, version))
        + " 64-bit is required. Install it with the Python launcher, then run Setup.cmd."
    )


def main() -> int:
    if os.name != "nt":
        raise RuntimeError(
            "Setup.cmd prepares the bundled Windows x64 dependencies. Use requirements-dev.txt for development on other platforms."
        )
    version = runtime_version(ROOT)
    app_version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    print(f"Setting up Shadowserver Companion {app_version}...")
    environment = ROOT / ".venv"
    executable = environment / "Scripts/python.exe"
    if environment.exists():
        if not executable.is_file() or not compatible([str(executable)], version):
            raise RuntimeError(
                "This .venv uses a different or incomplete Python environment. "
                "Close the app, rename .venv, and run Setup.cmd again. Keep your data folder."
            )
    else:
        subprocess.run([*select_interpreter(version), "-m", "venv", str(environment)], check=True)
    subprocess.run(
        [
            str(executable),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--find-links",
            str(ROOT / "wheelhouse"),
            "--require-hashes",
            "-r",
            str(ROOT / "requirements-windows.txt"),
        ],
        check=True,
        cwd=ROOT,
    )
    (environment / "workbench-version.txt").write_text(app_version + "\n", encoding="utf-8")
    print("Setup complete. Open Start Workbench.cmd to begin.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Setup failed: {error}", file=sys.stderr)
        raise SystemExit(1)
