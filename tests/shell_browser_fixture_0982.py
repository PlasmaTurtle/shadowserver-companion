"""Run shell interaction checks against a fresh copy of a synthetic demo workspace."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "components/attribution/src")]

from workbench.local_session import read_instance
from workbench.store import Store


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    if args.workspace.exists():
        raise SystemExit("Use a new scratch output directory")
    args.workspace.mkdir(parents=True)
    data = args.workspace / "workspace"
    shutil.copytree(args.template, data)
    store = Store(data)
    if store.one("SELECT COUNT(*) AS count FROM leads WHERE demo=0")["count"]:
        raise SystemExit("This fixture only accepts synthetic demo records")
    with store.transaction() as db:
        for number in range(65):
            store.log(db, "shell_browser_qa", f"Shell browser pagination {number:02d}")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    with (args.workspace / "server.log").open("w") as log:
        server = subprocess.Popen(
            [
                sys.executable,
                "run.py",
                "--demo",
                "--no-browser",
                "--data-dir",
                str(data),
                "--port",
                str(port),
            ],
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if server.poll() is not None:
                    raise RuntimeError("Synthetic server exited")
                try:
                    with opener.open(base + "/api/health", timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("Synthetic server did not start")
            key = read_instance(data, port, True)
            request = urllib.request.Request(
                base + "/api/session/launch",
                method="POST",
                headers={"X-Workbench-Launcher": key},
            )
            with opener.open(request) as response:
                launch = json.load(response)["launch"]
            env = dict(
                os.environ,
                BASE_URL=base,
                LAUNCH_URL=base + "/#launch=" + launch,
                QA_DIR=str(args.workspace),
            )
            result = subprocess.run(
                ["node", "tests/test_shell_browser_0982.cjs"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
            )
            (args.workspace / "browser-result.txt").write_text(result.stdout + result.stderr)
            print(result.stdout + result.stderr)
            raise SystemExit(result.returncode)
        finally:
            server.terminate()
            try:
                server.wait(timeout=8)
            except subprocess.TimeoutExpired:
                server.kill()


if __name__ == "__main__":
    main()
