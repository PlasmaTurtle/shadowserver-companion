"""The security gate must cover current boundaries without becoming full pytest."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("security_gate_0996", ROOT / "tools/security_gate.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def create_suites(root, names):
    for name in names:
        path = root / "tests" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Synthetic test file\n", encoding="utf-8")


def test_current_gate_keeps_baseline_and_covers_new_security_boundaries():
    selected = set(gate.security_suites(ROOT))
    baseline = {p.relative_to(ROOT).as_posix() for p in (ROOT / "tests").glob("test_*_072.py")}
    assert baseline and baseline <= selected
    assert {
        "tests/test_security_stability_0985.py",
        "tests/test_website_capture_0985.py",
        "tests/test_api_acquisition_routes_098.py",
        "tests/test_workspace_data_captures.py",
        "tests/test_workspace_data_080.py",
        "tests/test_release_privacy_070.py",
        "tests/shadowserver_api_module/test_network.py",
        "tests/shadowserver_api_module/test_download.py",
        "tests/shadowserver_api_module/test_cli_credentials.py",
    } <= selected
    assert "tests/test_eclipse.py" not in selected
    assert all((ROOT / name).is_file() for name in selected)


def test_selection_is_version_independent_unique_and_python_only(tmp_path):
    included = [
        "test_security_capture_1100.py",  # Matches multiple families only once.
        "test_local_session_1100.py",
        "test_request_limits_1100.py",
        "test_http_body_limits_1100.py",
        "test_citation_integrity_072.py",
        "shadowserver_api_module/test_download.py",
    ]
    excluded = [
        "test_security_capture_1100.cjs",
        "security_capture_fixture_1100.py",
        "test_observatory_1100.py",
    ]
    create_suites(tmp_path, included + excluded)
    (tmp_path / "tests/test_security_directory.py").mkdir()
    assert gate.security_suites(tmp_path) == sorted("tests/" + name for name in included)


@pytest.mark.parametrize("exit_codes", [(0, 0), (0, 1), (1,)])
def test_gate_executes_and_records_selected_suites_and_preserves_failure(
    tmp_path, monkeypatch, exit_codes
):
    create_suites(tmp_path, ["test_security_stability_1100.py", "test_local_session_072.py"])
    (tmp_path / "VERSION").write_text("0.9.96\n", encoding="utf-8")
    output = tmp_path / "gate-result"
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    monkeypatch.setattr(gate.sys, "argv", ["security_gate.py", "--output", str(output)])
    monkeypatch.setenv("WORKBENCH_PREVIEW", "1")
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        assert "WORKBENCH_PREVIEW" not in kwargs["env"]
        assert kwargs["cwd"] == tmp_path
        return SimpleNamespace(returncode=exit_codes[len(calls) - 1])

    monkeypatch.setattr(gate.subprocess, "run", run)
    expected_pass = exit_codes == (0, 0)
    assert gate.main() == (0 if expected_pass else 1)
    report = json.loads((output / "security-gate.json").read_text())
    assert report["passed"] is expected_pass
    assert report["native_windows_acceptance"] is False
    assert report["suites"] == gate.security_suites(tmp_path)
    assert len(calls) == len(exit_codes)
    if len(calls) == 2:
        assert calls[1][1:4] == ["-m", "pytest", "-q"]
        assert calls[1][4:] == report["suites"]


def test_empty_selection_fails_before_audit_or_test_execution(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    monkeypatch.setattr(
        gate.sys, "argv", ["security_gate.py", "--output", str(tmp_path / "gate-result")]
    )

    def unexpected(*args, **kwargs):
        pytest.fail("An empty security gate must not execute commands")

    monkeypatch.setattr(gate.subprocess, "run", unexpected)
    with pytest.raises(SystemExit) as error:
        gate.main()
    assert error.value.code == 2
