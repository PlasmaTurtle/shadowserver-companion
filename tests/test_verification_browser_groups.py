"""CI browser groups own their setup and cannot certify a partial run as complete."""

import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from tools import verify


class BrowserGroupTests(unittest.TestCase):
    def run_group(self, group, fail=False):
        executed, servers, launch_tokens = [], [], []

        def start(command, **kwargs):
            server = MagicMock()
            server.poll.return_value = None
            servers.append((command, server))
            if "--workspace" in command:
                workspace = Path(command[command.index("--workspace") + 1])
                workspace.mkdir()
                (workspace / "browser.json").write_text(
                    json.dumps({"base": "http://127.0.0.1:8888"}), encoding="utf-8"
                )
            return server

        def open_request(request, **kwargs):
            if isinstance(request, verify.urllib.request.Request):
                token = f"synthetic-launch-{len(launch_tokens)}"
                launch_tokens.append(token)
                response = io.BytesIO(json.dumps({"launch": token}).encode())
            else:
                response = io.BytesIO(b"{}")
            response.status = 200
            return response

        def run(command, **kwargs):
            executed.append((command[-1], dict(kwargs["env"])))
            return subprocess.CompletedProcess(command, 1 if fail else 0)

        opener = SimpleNamespace(open=open_request)
        probe = MagicMock()
        probe.__enter__.return_value.getsockname.return_value = ("127.0.0.1", 8888)
        session = SimpleNamespace(read_instance=lambda *args: "synthetic-launcher")
        with TemporaryDirectory() as temporary:
            report = Path(temporary) / "verification.json"
            with (
                patch.object(
                    sys,
                    "argv",
                    ["verify", "--only-browser", "--browser-suite", group, "--report", str(report)],
                ),
                patch.object(verify.shutil, "which", return_value="test-runtime"),
                patch.object(verify.subprocess, "Popen", side_effect=start),
                patch.object(verify.subprocess, "run", side_effect=run),
                patch.object(verify.socket, "socket", return_value=probe),
                patch.object(verify.urllib.request, "build_opener", return_value=opener),
                patch.dict(sys.modules, {"modules.workspace.components.local_session": session}),
            ):
                code = verify.main()
            result = json.loads(report.read_text(encoding="utf-8"))
        for _, server in servers:
            server.terminate.assert_called_once()
            server.wait.assert_called_once_with(timeout=10)
        self.assertFalse(result["complete"])
        return code, result, executed, servers, launch_tokens

    def test_separate_groups_cover_the_full_browser_run(self):
        groups = {}
        routine = [name for name, spec in verify.BROWSER_GROUPS.items() if not spec.get("focused")]
        for group in (*routine, "all"):
            with self.subTest(group=group):
                code, result, executed, servers, tokens = self.run_group(group)
                self.assertEqual(code, 0)
                self.assertTrue(result["passed"])
                self.assertEqual(result["browser_suite"], group)
                self.assertEqual(len(servers), len(routine) if group == "all" else 1)
                groups[group] = [name for name, _ in executed]
                self.assertEqual(len(tokens), len(executed))
                self.assertEqual(len(set(tokens)), len(executed))
        self.assertEqual(groups["all"], [script for group in routine for script in groups[group]])
        self.assertIn("modules/library/tests/test_content_lifecycle_browser.cjs", groups["library"])
        self.assertEqual(len(groups["all"]), 17)
        self.assertEqual(len(set(groups["all"])), len(groups["all"]))

    def test_focused_group_is_explicit_and_still_partial(self):
        code, result, executed, servers, tokens = self.run_group("contacts-lifecycle")
        self.assertEqual(code, 0)
        self.assertTrue(result["passed"])
        self.assertEqual(len(servers), 1)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(
            executed[0][0], "modules/entities/tests/test_contact_lifecycle_browser.cjs"
        )

    def test_failed_group_is_reported_and_server_is_stopped(self):
        code, result, executed, servers, _ = self.run_group("setup", fail=True)
        self.assertEqual(code, 1)
        self.assertFalse(result["passed"])
        self.assertIn("test_setup_release_browser.cjs failed", result["failure"])
        self.assertEqual(len(executed), 1)
        self.assertEqual(len(servers), 1)


class BrowserInventoryTests(unittest.TestCase):
    def test_every_current_browser_script_has_one_disposition(self):
        verify.validate_browser_suites()

    def test_browser_name_requires_disposition_even_with_custom_launcher(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "tests").mkdir()
            (root / "tests/test_added_browser.cjs").write_text("launchCustomBrowser();\n")
            with self.assertRaisesRegex(ValueError, "need a disposition"):
                verify.validate_browser_suites(root, {})

    def test_new_duplicate_stale_and_unprepared_manual_checks_are_rejected(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "tests").mkdir()
            script = "tests/test_browser.cjs"
            (root / script).write_text("chromium.launch({});\n", encoding="utf-8")
            for groups, message in (
                ({}, "need a disposition"),
                ({"a": {"scripts": (script,)}, "b": {"scripts": (script,)}}, "Duplicate"),
                ({"a": {"scripts": ("tests/test_missing.cjs",)}}, "Missing or non-browser"),
                ({"a": {"scripts": (script,), "manual": True}}, "concrete setup"),
                ({"a": {"scripts": (script,), "fixture": "missing.py"}}, "Missing browser fixture"),
            ):
                with self.subTest(groups=groups), self.assertRaisesRegex(ValueError, message):
                    verify.validate_browser_suites(root, groups)


@unittest.skipUnless(shutil.which("node"), "Node is required to validate DOM registration")
class FrontendRegistrationTests(unittest.TestCase):
    def validate(self, files, registered):
        runner = Path(__file__).resolve().parent / "run_frontend.cjs"
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in files:
                file = root / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text("// Synthetic suite; validation must not execute it.\n")
            return subprocess.run(
                [
                    shutil.which("node"),
                    "-e",
                    "const {validateSuites} = require(process.argv[1]); "
                    "validateSuites(process.argv[2], JSON.parse(process.argv[3]));",
                    str(runner),
                    str(root),
                    json.dumps(registered),
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )

    def test_registered_portable_suites_exclude_browsers_and_helpers(self):
        result = self.validate(
            [
                "tests/test_shared.cjs",
                "modules/entities/tests/nested/test_review.cjs",
                "modules/entities/tests/dom_helpers.cjs",
                "tests/test_setup_release_browser.cjs",
                "modules/entities/tests/test_review_browser_0120.cjs",
                "modules/ui/tests/test_frontend_accessibility_070.cjs",
                "modules/workspace/tests/test_frontend_workspace_080.cjs",
            ],
            ["test_shared.cjs", "../modules/entities/tests/nested/test_review.cjs"],
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unregistered_portable_suite_fails(self):
        result = self.validate(["modules/entities/tests/nested/test_review.cjs"], [])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "Unregistered DOM suites: modules/entities/tests/nested/test_review.cjs", result.stderr
        )

    def test_duplicate_stale_and_browser_registrations_fail(self):
        for files, registered, message in (
            (
                ["tests/test_shared.cjs"],
                ["test_shared.cjs", "test_shared.cjs"],
                "Duplicate DOM suite registration: tests/test_shared.cjs",
            ),
            (
                [],
                ["test_stale.cjs"],
                "Registered DOM suite is missing or browser-only: tests/test_stale.cjs",
            ),
            (
                ["tests/test_review_browser.cjs"],
                ["test_review_browser.cjs"],
                "Registered DOM suite is missing or browser-only: tests/test_review_browser.cjs",
            ),
        ):
            with self.subTest(registered=registered):
                result = self.validate(files, registered)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)


if __name__ == "__main__":
    unittest.main()
