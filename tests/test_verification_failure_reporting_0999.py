"""Interrupted or broken checks must not create successful release evidence."""

import json
import subprocess
import sys
from unittest.mock import patch

import pytest

from tools import verify


@pytest.mark.parametrize(
    ("error", "expected_code", "message"),
    [
        (KeyboardInterrupt(), 130, "Verification interrupted"),
        (ValueError("malformed browser response"), 1, "ValueError"),
        (ImportError("missing session module"), 1, "ImportError"),
    ],
)
def test_unexpected_exit_cannot_certify_success(tmp_path, error, expected_code, message):
    report = tmp_path / "verification.json"
    with (
        patch.object(sys, "argv", ["verify", "--report", str(report)]),
        patch.object(verify.shutil, "which", return_value="test-runtime"),
        patch.object(verify.subprocess, "run", side_effect=error),
    ):
        assert verify.main() == expected_code
    result = json.loads(report.read_text())
    assert result["passed"] is False
    assert result["complete"] is False
    assert message in result["failure"]


def test_check_timeout_is_recorded_and_stops_following_checks(tmp_path):
    report = tmp_path / "verification.json"
    with (
        patch.object(sys, "argv", ["verify", "--check-timeout", "7", "--report", str(report)]),
        patch.object(verify.shutil, "which", return_value="test-runtime"),
        patch.object(
            verify.subprocess, "run", side_effect=subprocess.TimeoutExpired("check", 7)
        ) as run,
    ):
        assert verify.main() == 1
    assert run.call_count == 1
    assert run.call_args.kwargs["timeout"] == 7
    result = json.loads(report.read_text())
    assert result["passed"] is False
    assert result["complete"] is False
    assert result["checks"][0]["timed_out"] is True
    assert result["checks"][0]["exit_code"] is None
    assert "exceeded 7 seconds" in result["failure"]


def test_partial_run_remains_incomplete_even_when_checks_pass(tmp_path):
    report = tmp_path / "verification.json"
    with (
        patch.object(sys, "argv", ["verify", "--skip-browser", "--report", str(report)]),
        patch.object(verify.shutil, "which", return_value="test-runtime"),
        patch.object(verify.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)),
    ):
        assert verify.main() == 0
    result = json.loads(report.read_text())
    assert result["passed"] is True
    assert result["complete"] is False
    assert result["failure"] is None


def test_uncaught_control_flow_exit_is_fail_closed(tmp_path):
    report = tmp_path / "verification.json"
    with (
        patch.object(sys, "argv", ["verify", "--report", str(report)]),
        patch.object(verify.shutil, "which", return_value="test-runtime"),
        patch.object(verify.subprocess, "run", side_effect=SystemExit(2)),
        pytest.raises(SystemExit),
    ):
        verify.main()
    result = json.loads(report.read_text())
    assert result["passed"] is False
    assert result["complete"] is False


def test_check_timeout_must_be_positive():
    with patch.object(sys, "argv", ["verify", "--check-timeout", "0"]), pytest.raises(SystemExit):
        verify.main()
