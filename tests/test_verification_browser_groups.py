"""CI browser groups own their setup and cannot certify a partial run as complete."""

import io
import json
from pathlib import Path
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
                patch.dict(sys.modules, {"workbench.local_session": session}),
            ):
                code = verify.main()
            result = json.loads(report.read_text())
        for _, server in servers:
            server.terminate.assert_called_once()
            server.wait.assert_called_once_with(timeout=10)
        self.assertFalse(result["complete"])
        return code, result, executed, servers, launch_tokens

    def test_separate_groups_cover_the_full_browser_run(self):
        groups = {}
        for group in ("core", "observatory", "setup", "all"):
            with self.subTest(group=group):
                code, result, executed, servers, tokens = self.run_group(group)
                self.assertEqual(code, 0)
                self.assertTrue(result["passed"])
                self.assertEqual(result["browser_suite"], group)
                self.assertEqual(len(servers), 3 if group == "all" else 1)
                groups[group] = [name for name, _ in executed]
                if group in ("all", "core"):
                    self.assertEqual(len(tokens), 4)
                    self.assertEqual(len(set(tokens)), 4)
                else:
                    self.assertEqual(tokens, [])
                    self.assertEqual(len(executed), 1)
        self.assertEqual(groups["all"], groups["core"] + groups["observatory"] + groups["setup"])
        self.assertEqual(len(set(groups["all"])), 6)

    def test_failed_group_is_reported_and_server_is_stopped(self):
        code, result, executed, servers, _ = self.run_group("setup", fail=True)
        self.assertEqual(code, 1)
        self.assertFalse(result["passed"])
        self.assertIn("test_setup_release_browser.cjs failed", result["failure"])
        self.assertEqual(len(executed), 1)
        self.assertEqual(len(servers), 1)


if __name__ == "__main__":
    unittest.main()
