"""Run the repeatable developer release checks against synthetic workspaces.

Install requirements-dev.txt, run npm ci, and install Playwright Chromium first.
Use --skip-browser only when recording an explicitly incomplete verification.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-browser", action="store_true")
    parser.add_argument(
        "--only-browser",
        action="store_true",
        help="Run registered browser acceptance with fresh sessions; records partial verification",
    )
    parser.add_argument(
        "--skip-backend",
        action="store_true",
        help="Run frontend/tooling checks only; records incomplete verification",
    )
    parser.add_argument(
        "--browser-suite",
        choices=("all", "core", "observatory", "setup"),
        default="all",
        help="Select one isolated browser fixture group with --only-browser",
    )
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--check-timeout",
        type=int,
        default=1800,
        help="Maximum seconds for each check process (default: 1800)",
    )
    args = parser.parse_args()
    if args.only_browser and args.skip_browser:
        parser.error("--only-browser cannot be combined with --skip-browser")
    if args.browser_suite != "all" and not args.only_browser:
        parser.error("--browser-suite requires --only-browser")
    if args.check_timeout <= 0:
        parser.error("--check-timeout must be positive")
    results = []
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT), str(ROOT / "components/attribution/src"), env.get("PYTHONPATH", "")]
    )
    env.pop("WORKBENCH_PREVIEW", None)
    node = shutil.which("node")
    npm = shutil.which("npm")
    if not node or not npm:
        parser.error("Node.js and npm are required for developer verification.")

    def run(label, command, child_env=None):
        print(f"\n[{label}]", flush=True)
        started = time.monotonic()
        try:
            result = subprocess.run(
                command, cwd=ROOT, env=child_env or env, timeout=args.check_timeout
            )
        except subprocess.TimeoutExpired as error:
            results.append(
                {
                    "check": label,
                    "exit_code": None,
                    "seconds": round(time.monotonic() - started, 3),
                    "timed_out": True,
                }
            )
            raise RuntimeError(f"{label} exceeded {args.check_timeout} seconds") from error
        results.append(
            {
                "check": label,
                "exit_code": result.returncode,
                "seconds": round(time.monotonic() - started, 3),
            }
        )
        if result.returncode:
            raise RuntimeError(f"{label} failed (exit {result.returncode})")

    failure = None
    completed = False
    interrupted = False
    try:
        if not args.only_browser:
            run("Release identity and validation gate", [sys.executable, "tools/check_release.py"])
            run("Module boundaries and map", [sys.executable, "tools/program_map.py", "--check"])
            run("Python format", [sys.executable, "-m", "ruff", "format", "--check", "."])
            run("Python lint", [sys.executable, "-m", "ruff", "check", "."])
            run("Frontend format", [npm, "run", "format:check"])
            run("Frontend syntax", [npm, "run", "lint"])
            run("Frontend module contracts", [npm, "test"])
        if not args.skip_browser:
            with tempfile.TemporaryDirectory(prefix="companion-verification-") as directory:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                if args.browser_suite in ("all", "core"):
                    with socket.socket() as probe:
                        probe.bind(("127.0.0.1", 0))
                        port = probe.getsockname()[1]
                    base = f"http://127.0.0.1:{port}"
                    with open(Path(directory) / "server.log", "w+", encoding="utf-8") as log:
                        server = subprocess.Popen(
                            [
                                sys.executable,
                                "run.py",
                                "--demo",
                                "--no-browser",
                                "--port",
                                str(port),
                                "--data-dir",
                                str(Path(directory) / "workspace"),
                            ],
                            cwd=ROOT,
                            env=env,
                            stdout=log,
                            stderr=subprocess.STDOUT,
                        )
                        try:
                            deadline = time.monotonic() + 45
                            while time.monotonic() < deadline:
                                if server.poll() is not None:
                                    log.seek(0)
                                    raise RuntimeError("Test server exited: " + log.read()[-4000:])
                                try:
                                    with opener.open(base + "/api/health", timeout=1) as response:
                                        if response.status == 200:
                                            break
                                except OSError:
                                    time.sleep(0.2)
                            else:
                                raise RuntimeError("Test server did not become ready")
                            browser_env = {**env, "ECLIPSE_BASE_URL": base}
                            if str(ROOT) not in sys.path:
                                sys.path.insert(0, str(ROOT))
                            from workbench.local_session import read_instance

                            launcher_key = read_instance(Path(directory) / "workspace", port, True)
                            for name in (
                                "test_local_session_browser_072.cjs",
                                "test_frontend_browser_070.cjs",
                                "test_frontend_accessibility_070.cjs",
                                "test_frontend_workspace_080.cjs",
                            ):
                                request = urllib.request.Request(
                                    base + "/api/session/launch",
                                    method="POST",
                                    headers={"X-Workbench-Launcher": launcher_key},
                                )
                                with opener.open(request, timeout=2) as response:
                                    launch = json.load(response)["launch"]
                                browser_env["ECLIPSE_LAUNCH_URL"] = base + "/#launch=" + launch
                                run(name, [node, "tests/" + name], browser_env)
                        finally:
                            server.terminate()
                            try:
                                server.wait(timeout=10)
                            except subprocess.TimeoutExpired:
                                server.kill()
                                server.wait()
                # Each specialized suite owns fresh data: Observatory needs its
                # multientity source universe; first-run setup needs an empty workspace.
                for fixture_name, fixture_script, test_script, metadata_env in (
                    (
                        "observatory",
                        "eclipse_browser_fixture_0981.py",
                        "test_observatory_browser_0995.cjs",
                        "ECLIPSE_FIXTURE",
                    ),
                    (
                        "setup",
                        "setup_release_browser_fixture.py",
                        "test_setup_release_browser.cjs",
                        "SETUP_BROWSER_FIXTURE",
                    ),
                ):
                    if args.browser_suite not in ("all", fixture_name):
                        continue
                    fixture_workspace = Path(directory) / fixture_name
                    metadata_path = fixture_workspace / "browser.json"
                    with open(
                        Path(directory) / (fixture_name + "-server.log"), "w+", encoding="utf-8"
                    ) as log:
                        server = subprocess.Popen(
                            [
                                sys.executable,
                                "tests/" + fixture_script,
                                "--workspace",
                                str(fixture_workspace),
                            ],
                            cwd=ROOT,
                            env=env,
                            stdout=log,
                            stderr=subprocess.STDOUT,
                        )
                        try:
                            deadline = time.monotonic() + 45
                            while time.monotonic() < deadline:
                                if server.poll() is not None:
                                    log.seek(0)
                                    raise RuntimeError(
                                        fixture_name + " test server exited: " + log.read()[-4000:]
                                    )
                                try:
                                    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                                    with opener.open(
                                        metadata["base"] + "/api/health", timeout=1
                                    ) as response:
                                        if response.status == 200:
                                            break
                                except (OSError, ValueError, KeyError):
                                    time.sleep(0.2)
                            else:
                                raise RuntimeError(
                                    fixture_name + " test server did not become ready"
                                )
                            run(
                                test_script,
                                [node, "tests/" + test_script],
                                {**env, metadata_env: str(metadata_path)},
                            )
                        finally:
                            server.terminate()
                            try:
                                server.wait(timeout=10)
                            except subprocess.TimeoutExpired:
                                server.kill()
                                server.wait()
        # Browser acceptance is fast; expose UI regressions before the longer
        # backend suite. Full verification still requires both to succeed.
        if not (args.only_browser or args.skip_backend):
            run(
                "Backend and attribution regression",
                [sys.executable, "-m", "pytest", "-v", "--maxfail=1"],
            )
        completed = True
    except KeyboardInterrupt:
        interrupted = True
        failure = "Verification interrupted."
        print(failure, file=sys.stderr)
    except Exception as error:
        failure = f"{type(error).__name__}: {error}"
        print(failure, file=sys.stderr)
    finally:
        # Unhandled control-flow exceptions must never leave a successful report.
        if not completed and failure is None:
            failure = "Verification did not complete."
        report = {
            "version": (ROOT / "VERSION").read_text().strip(),
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "python": sys.version,
            "platform": sys.platform,
            "browser_checks_requested": not args.skip_browser,
            "browser_suite": args.browser_suite if not args.skip_browser else None,
            "backend_checks_requested": not (args.skip_backend or args.only_browser),
            "portable_frontend_checks_requested": not args.only_browser,
            "complete": completed
            and failure is None
            and not (args.skip_browser or args.skip_backend or args.only_browser),
            "native_windows_acceptance": False,
            "passed": completed and failure is None,
            "failure": failure,
            "checks": results,
        }
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 130 if interrupted else 1 if failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
