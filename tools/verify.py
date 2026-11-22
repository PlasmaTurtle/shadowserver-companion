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
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]


# One disposition for every executable browser script. Focused groups are opt-in;
# the full verifier runs every routine group in this order on fresh workspaces.
BROWSER_GROUPS = {
    "core": {
        "fixture": None,
        "scripts": (
            "modules/workspace/tests/test_local_session_browser_072.cjs",
            "modules/ui/tests/test_frontend_browser_070.cjs",
            "modules/ui/tests/test_frontend_accessibility_070.cjs",
            "modules/workspace/tests/test_frontend_workspace_080.cjs",
        ),
    },
    "observatory": {
        "fixture": "modules/observatory/tests/eclipse_browser_fixture_0981.py",
        "metadata_env": "ECLIPSE_FIXTURE",
        "scripts": ("modules/observatory/tests/test_observatory_browser_0995.cjs",),
    },
    "setup": {
        "fixture": "tests/setup_release_browser_fixture.py",
        "metadata_env": "SETUP_BROWSER_FIXTURE",
        "scripts": ("tests/test_setup_release_browser.cjs",),
    },
    "navigation": {
        "fixture": "modules/ui/tests/navigation_browser_fixture_098.py",
        "metadata_env": "NAVIGATION_FIXTURE",
        "port_argument": True,
        # DNS begins uncached; navigation then creates its first case; palette
        # may add an explainer after those initial-state assertions finish.
        "scripts": (
            "modules/entities/tests/test_entity_dns_browser_0984.cjs",
            "modules/ui/tests/test_navigation_browser_098.cjs",
            "modules/ui/tests/test_command_palette_browser_0981.cjs",
        ),
    },
    "library": {
        "fixture": "modules/ui/tests/navigation_browser_fixture_098.py",
        "port_argument": True,
        "scripts": (
            "modules/library/tests/test_cve_catalog_browser_0983.cjs",
            "modules/library/tests/test_catalog_library_browser_0984.cjs",
            "modules/library/tests/test_content_lifecycle_browser.cjs",
        ),
    },
    "contacts": {
        "fixture": "modules/entities/tests/contacts_browser_fixture_090.py",
        "metadata_env": "CONTACT_BROWSER_FIXTURE",
        "port_argument": True,
        "scripts": ("modules/entities/tests/test_contacts_browser_098.cjs",),
    },
    "api": {
        "fixture": "modules/accretion/tests/api_acquisition_browser_fixture_098.py",
        "metadata_env": "API_BROWSER_FIXTURE",
        "scripts": ("modules/accretion/tests/test_api_acquisition_browser_098.cjs",),
    },
    "investigations": {
        "fixture": "modules/investigations/tests/investigations_browser_fixture_0982.py",
        "metadata_env": "INVESTIGATIONS_FIXTURE",
        "scripts": ("modules/investigations/tests/test_investigations_browser_0982.cjs",),
    },
    "sources": {
        "fixture": "modules/investigations/tests/source_adoption_browser_fixture_0984.py",
        "metadata_env": "SOURCE_FIXTURE_METADATA",
        "scripts": ("modules/investigations/tests/test_source_adoption_browser_0984.cjs",),
    },
    "catalog-scope": {
        "fixture": "modules/library/tests/catalog_observatory_fixture_0984.py",
        "metadata_env": "ECLIPSE_FIXTURE",
        "port_argument": True,
        "scripts": ("modules/library/tests/test_catalog_observatory_0984.cjs",),
    },
    "contacts-lifecycle": {
        "fixture": "modules/entities/tests/contacts_browser_fixture_090.py",
        "metadata_env": "CONTACT_BROWSER_FIXTURE",
        "port_argument": True,
        "focused": "Discovery budgets, cancellation and detached polling on current contact UI; run when contact acquisition/lifecycle changes. Replaces obsolete confirmation-gate browser scenarios; current handoff remains routine and historical route decisions retain module regression coverage.",
        "scripts": ("modules/entities/tests/test_contact_lifecycle_browser.cjs",),
    },
    "keyboard": {
        "fixture": None,
        "focused": "Detailed keyboard/manual-tab, focus restoration and dirty-form navigation checks; run for UI accessibility or keyboard changes in addition to routine accessibility.",
        "scripts": ("modules/ui/tests/test_interaction_browser_095.cjs",),
    },
    "workflow": {
        "fixture": "modules/investigations/tests/workflow_browser_fixture_095.py",
        "metadata_env": "WORKFLOW_BROWSER_FIXTURE",
        "focused": "Reasoned hold/re-enable outreach and policy-event search; run for outreach/workday changes. Uses a deliberately overdue synthetic case.",
        "scripts": ("modules/investigations/tests/test_workflow_browser_095.cjs",),
    },
    "queue-polish": {
        "fixture": "modules/investigations/tests/workflow_browser_fixture_095.py",
        "metadata_env": "WORKFLOW_BROWSER_FIXTURE",
        "focused": "Queue/directory recovery, deferred-date validation and Activity filters; run for queue/policy interaction changes on a fresh overdue case.",
        "scripts": ("modules/workspace/tests/test_queue_polish_browser_095.cjs",),
    },
    "package-shell": {
        "fixture": "modules/ui/tests/shell_browser_fixture_0982.py",
        "manual": True,
        "focused": "Certified-package download bytes and visual shell matrix; needs a prepared synthetic demo template with certified report files. Does not certify a native installation.",
        "setup": "Create a fresh demo with python run.py --demo --no-browser --data-dir <new-demo> and stop it after startup; then python modules/ui/tests/shell_browser_fixture_0982.py --template <new-demo> --workspace <new-output>. The fixture copies only synthetic demo records, adds pagination events and runs its browser script.",
        "scripts": ("modules/ui/tests/test_shell_browser_0982.cjs",),
    },
    "evidence-reader": {
        "fixture": "modules/investigations/tests/evidence_reader_fixture_0981.py",
        "manual": True,
        "focused": "Portable file:// evidence reader, folder hash verification and print/mobile rendering; generated artifacts are outside the live app shell and do not prove PDF certification.",
        "setup": "python modules/investigations/tests/evidence_reader_fixture_0981.py --workspace <new-output>; set EVIDENCE_READER_FILE=<new-output>/Evidence_Record.html and optionally EVIDENCE_QA_OUTPUT=<screenshots>; node modules/investigations/tests/test_evidence_reader_browser_0981.cjs. No app server or user evidence is used.",
        "scripts": ("modules/investigations/tests/test_evidence_reader_browser_0981.cjs",),
    },
    "field-density": {
        "fixture": "modules/observatory/tests/field_browser_fixture_0998.py",
        "manual": True,
        "focused": "Exploratory 96-entity Field fixture with dense assets, long history and dark matter. Fixture generation is not an automated acceptance result; use it for density/performance investigation.",
        "setup": "python modules/observatory/tests/field_browser_fixture_0998.py --workspace <new-output> --port <unused-loopback-port>; open the one-use launch_url in <new-output>/browser.json, then stop the fixture when finished. Uses synthetic records only; no timing threshold is certified.",
        "scripts": (),
    },
}


def validate_browser_suites(root=ROOT, groups=None):
    """New, stale or duplicate browser checks need an explicit maintained disposition."""
    groups = BROWSER_GROUPS if groups is None else groups
    discovered = {
        file.relative_to(root).as_posix()
        for directory in (root / "tests", root / "modules")
        for file in directory.rglob("test_*.cjs")
        if "_browser" in file.stem or "chromium.launch(" in file.read_text(encoding="utf-8")
    }
    registered = set()
    for name, group in groups.items():
        if group.get("fixture") and not (root / group["fixture"]).is_file():
            raise ValueError(f"Missing browser fixture for {name}: {group['fixture']}")
        if group.get("manual") and not group.get("setup"):
            raise ValueError(f"Manual browser group needs concrete setup: {name}")
        for script in group["scripts"]:
            if script in registered:
                raise ValueError(f"Duplicate browser disposition: {script}")
            if script not in discovered:
                raise ValueError(f"Missing or non-browser script: {script}")
            registered.add(script)
    if discovered - registered:
        raise ValueError(
            "Browser scripts need a disposition: " + ", ".join(sorted(discovered - registered))
        )


def browser_checks(args, env, node, run):
    """Run selected browser groups, issuing a fresh launcher token for every script."""
    from modules.workspace.components.local_session import read_instance

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with tempfile.TemporaryDirectory(prefix="companion-verification-") as directory:
        temporary = Path(directory)
        artifacts = (
            args.report.parent / (args.report.stem + "-browser")
            if args.report
            else temporary / "artifacts"
        )
        artifacts.mkdir(parents=True, exist_ok=True)
        for name, group in BROWSER_GROUPS.items():
            if group.get("manual") or (args.browser_suite == "all" and group.get("focused")):
                continue
            if args.browser_suite not in ("all", name):
                continue
            workspace = temporary / name
            metadata_path = workspace / "browser.json"
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            base = f"http://127.0.0.1:{port}"
            if group["fixture"]:
                command = [sys.executable, group["fixture"], "--workspace", str(workspace)]
                if group.get("port_argument"):
                    command += ["--port", str(port)]
            else:
                command = [
                    sys.executable,
                    "run.py",
                    "--demo",
                    "--no-browser",
                    "--port",
                    str(port),
                    "--data-dir",
                    str(workspace),
                ]
            with (artifacts / (name + "-server.log")).open("w+", encoding="utf-8") as log:
                server = subprocess.Popen(
                    command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT
                )
                try:
                    deadline = time.monotonic() + 90
                    while time.monotonic() < deadline:
                        if server.poll() is not None:
                            log.seek(0)
                            raise RuntimeError(name + " fixture exited: " + log.read()[-4000:])
                        try:
                            metadata = (
                                json.loads(metadata_path.read_text(encoding="utf-8"))
                                if group["fixture"]
                                else {"base": base}
                            )
                            base = metadata["base"]
                            with opener.open(base + "/api/health", timeout=1) as response:
                                if response.status == 200:
                                    break
                        except (OSError, ValueError, KeyError):
                            time.sleep(0.2)
                    else:
                        raise RuntimeError(
                            name
                            + " fixture did not become ready; see "
                            + str(artifacts / (name + "-server.log"))
                        )
                    port = urllib.parse.urlsplit(base).port
                    launcher = read_instance(workspace, port, not bool(group["fixture"]))
                    for script in group["scripts"]:
                        request = urllib.request.Request(
                            base + "/api/session/launch",
                            method="POST",
                            headers={"X-Workbench-Launcher": launcher},
                        )
                        with opener.open(request, timeout=2) as response:
                            launch_url = base + "/#launch=" + json.load(response)["launch"]
                        metadata["launch_url"] = launch_url
                        if group["fixture"]:
                            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
                        output = artifacts / Path(script).stem
                        output.mkdir(exist_ok=True)
                        browser_env = {
                            **env,
                            "ECLIPSE_BASE_URL": base,
                            "ECLIPSE_LAUNCH_URL": launch_url,
                            "BASE_URL": base,
                            "LAUNCH_URL": launch_url,
                        }
                        for variable in (
                            "QA_DIR",
                            "QA_OUT",
                            "ECLIPSE_SCREENSHOTS",
                            "CONTACT_SCREENSHOTS",
                            "DNS_SCREENSHOTS",
                            "NAVIGATION_SCREENSHOTS",
                            "INVESTIGATIONS_SCREENSHOTS",
                            "SOURCE_QA_DIR",
                        ):
                            browser_env[variable] = str(output)
                        if group.get("metadata_env"):
                            browser_env[group["metadata_env"]] = str(metadata_path)
                        run(script, [node, script], browser_env)
                finally:
                    server.terminate()
                    try:
                        server.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        server.kill()
                        server.wait(timeout=10)


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
        choices=(
            "all",
            *(name for name, group in BROWSER_GROUPS.items() if not group.get("manual")),
        ),
        default="all",
        help="Select one isolated browser fixture group with --only-browser",
    )
    parser.add_argument(
        "--list-browser",
        action="store_true",
        help="Show every browser check, fixture and routine/focused disposition",
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
    if args.list_browser:
        validate_browser_suites()
        print(json.dumps(BROWSER_GROUPS, indent=2))
        return 0
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    results = []
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [
            str(ROOT),
            str(ROOT / "modules/attribution/components/engine/src"),
            env.get("PYTHONPATH", ""),
        ]
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
        validate_browser_suites()
        if not (args.only_browser or args.skip_backend):
            missing = [
                name
                for name in ("pdftotext", "pdftoppm", "pdffonts", "pdfinfo")
                if not shutil.which(name)
            ]
            if missing:
                raise RuntimeError(
                    "Missing Poppler tools on PATH: "
                    + ", ".join(missing)
                    + ". Install complete Poppler utilities or add their bin directory "
                    "to PATH; see docs/DEVELOPMENT.md."
                )
        if not args.only_browser:
            run("Release identity and validation gate", [sys.executable, "tools/check_release.py"])
            run("Module boundaries and map", [sys.executable, "tools/program_map.py", "--check"])
            run("Python format", [sys.executable, "-m", "ruff", "format", "--check", "."])
            run("Python lint", [sys.executable, "-m", "ruff", "check", "."])
            run("Frontend format", [npm, "run", "format:check"])
            run("Frontend syntax", [npm, "run", "lint"])
            run("Frontend module contracts", [npm, "test"])
        if not args.skip_browser:
            browser_checks(args, env, node, run)
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
            "version": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
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
