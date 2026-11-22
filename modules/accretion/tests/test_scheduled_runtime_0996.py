"""Windowless scheduler failures remain visible without exposing credentials."""

from contextlib import contextmanager
import importlib.util
import io
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys

import pytest

from modules.workspace.components import runtime_logging


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    logger = logging.getLogger()
    previous_handlers, previous_level = logger.handlers[:], logger.level
    logger.handlers = []
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    path = Path(__file__).resolve().parents[3] / "modules/accretion/tools/run_scheduled.py"
    spec = importlib.util.spec_from_file_location("scheduled_runner_0996", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        yield module, tmp_path
    finally:
        for handler in logger.handlers:
            handler.close()
        logger.handlers = previous_handlers
        logger.setLevel(previous_level)


def log_text(folder):
    return "\n".join(path.read_text(encoding="utf-8") for path in folder.rglob("*.log*"))


def test_pythonw_pre_job_failure_records_stack_without_secret_arguments(runtime, monkeypatch):
    runner, folder = runtime
    secret = "private-provider-credential"

    def fail_before_job(_args):
        print("incidental output containing " + secret)
        sys.stdout.buffer.write(secret.encode())
        raise RuntimeError(secret)

    monkeypatch.setattr(runner, "main", fail_before_job)
    with monkeypatch.context() as patch:
        patch.setattr(sys, "stdout", None)
        patch.setattr(sys, "stderr", None)
        assert runner.entrypoint(["--data-dir", str(folder / "data")]) == 1
        assert sys.stdout is None and sys.stderr is None
    content = log_text(folder)
    assert "Scheduled runner failed before completion: RuntimeError" in content
    assert "fail_before_job" in content and "test_scheduled_runtime_0996.py" in content
    assert secret not in content


def test_release_validation_failure_is_logged_before_a_job_or_workspace_open(runtime, monkeypatch):
    from modules.workspace.components import workspace_session as workspace_lifecycle
    import modules.workspace.components.release

    runner, folder = runtime
    workspace = folder / "data"

    def invalid_release():
        raise ValueError("untrusted release message api_key=private-value")

    def never_open(_root):
        raise AssertionError("The workspace must not open after release validation failed")

    monkeypatch.setattr(modules.workspace.components.release, "load_release", invalid_release)
    monkeypatch.setattr(workspace_lifecycle, "workspace_session", never_open)
    with monkeypatch.context() as patch:
        patch.setattr(sys, "stdout", None)
        patch.setattr(sys, "stderr", None)
        assert runner.entrypoint(["--data-dir", str(workspace)]) == 1
    log = folder / "data-logs" / "scheduled.log"
    assert log.is_file() and not workspace.exists()
    content = log.read_text(encoding="utf-8")
    assert "ValueError" in content and "invalid_release" in content
    assert "private-value" not in content


def test_pythonw_bad_arguments_retain_nonzero_exit_in_bootstrap_log(runtime, monkeypatch):
    runner, folder = runtime
    with monkeypatch.context() as patch:
        patch.setattr(sys, "stdout", None)
        patch.setattr(sys, "stderr", None)
        assert runner.entrypoint([]) == 2
    assert "SystemExit" in log_text(folder)
    assert (folder / "local/ShadowserverCompanion/logs/scheduled.log").is_file()


@pytest.mark.parametrize("code", [None, 0, 2, 7, "untrusted secret value"])
def test_system_exit_status_is_preserved_without_logging_its_arguments(runtime, monkeypatch, code):
    runner, folder = runtime

    def exit_early(_args):
        raise SystemExit(code)

    monkeypatch.setattr(runner, "main", exit_early)
    assert runner.entrypoint([]) == (code if isinstance(code, int) else 0 if code is None else 1)
    assert "untrusted secret value" not in log_text(folder)


def test_scheduler_preserves_workspace_session_and_busy_exit(runtime, monkeypatch):
    from modules.workspace.components import workspace_session as workspace_lifecycle

    runner, folder = runtime
    events = []

    @contextmanager
    def owned(root):
        events.append(("acquired", root))
        try:
            yield
        finally:
            events.append(("released", root))

    def pending(root):
        events.append(("run", root))
        return 2

    monkeypatch.setattr(workspace_lifecycle, "workspace_session", owned)
    monkeypatch.setattr(runner, "run", pending)
    workspace = (folder / "data").resolve()
    assert runner.entrypoint(["--data-dir", str(workspace)]) == 2
    assert events == [("acquired", workspace), ("run", workspace), ("released", workspace)]
    assert "exit status 2" in log_text(folder)


def test_existing_owner_is_successful_yield_not_a_second_writer(runtime, monkeypatch):
    from modules.workspace.components import workspace_session as workspace_lifecycle

    runner, folder = runtime

    @contextmanager
    def already_owned(_root):
        raise SystemExit("This workspace is already open.")
        yield

    monkeypatch.setattr(workspace_lifecycle, "workspace_session", already_owned)
    monkeypatch.setattr(runner, "run", lambda _root: pytest.fail("Opened an owned workspace"))
    assert runner.entrypoint(["--data-dir", str(folder / "data")]) == 0
    assert "yielded without opening it" in log_text(folder)


def test_uninstaller_task_removal_never_takes_installation_or_workspace_ownership(
    runtime, monkeypatch
):
    import modules.workspace.components.release
    import modules.accretion.components.windows_schedule

    runner, folder = runtime
    calls = []
    monkeypatch.setattr(
        modules.accretion.components.windows_schedule,
        "configure",
        lambda root, value: calls.append((root, value)),
    )
    monkeypatch.setattr(
        modules.workspace.components.release,
        "load_release",
        lambda: pytest.fail("Removal must return before install/workspace ownership"),
    )
    assert runner.entrypoint(["--data-dir", str(folder / "data"), "--remove-task"]) == 0
    assert calls == [(folder / "data", False)]


def test_rotating_logs_redact_credential_fields_urls_and_exception_text(runtime):
    _, folder = runtime
    workspace = folder / "data"
    logs = runtime_logging.configure_runtime_logging(workspace, name="scheduled", console=False)
    handler = next(
        item for item in logging.getLogger().handlers if isinstance(item, RotatingFileHandler)
    )
    assert handler.maxBytes == 2_000_000 and handler.backupCount == 3
    # Exercise rollover with a smaller test-only bound, using the real handler.
    handler.maxBytes = 350
    for _ in range(7):
        logging.warning(
            "provider headers={'apiKey': 'private-api-value', 'secret': 'private-secret-value'}; url=http://127.0.0.1/#launch=private-launch-value"
        )
    try:
        raise ValueError("Authorization: Bearer private-bearer-value")
    except ValueError:
        logging.exception("Diagnostic failure")
    handler.flush()
    assert logs == folder / "data-logs" and not workspace.exists()
    assert len(list(logs.glob("scheduled.log*"))) <= 4
    content = log_text(logs)
    assert "Diagnostic failure" in content and "[redacted]" in content
    for value in (
        "private-api-value",
        "private-secret-value",
        "private-launch-value",
        "private-bearer-value",
    ):
        assert value not in content


def test_closed_console_does_not_prevent_file_logging(runtime, monkeypatch):
    _, folder = runtime
    closed = io.StringIO()
    closed.close()
    monkeypatch.setattr(sys, "stderr", closed)
    logs = runtime_logging.configure_runtime_logging(folder / "data", name="scheduled")
    logging.error("Persistent diagnostic survives a closed console")
    assert "survives a closed console" in log_text(logs)
    assert runtime_logging.safe_write(closed, "ignored") is False


def test_desktop_can_keep_existing_bootstrap_folder(runtime):
    _, folder = runtime
    expected = folder / "legacy-startup"
    assert runtime_logging.configure_runtime_logging(fallback_folder=expected) == expected


def test_unwritable_workspace_log_folder_falls_back_outside_workspace(runtime, monkeypatch):
    _, folder = runtime
    original = runtime_logging.QuietRotatingFileHandler

    def reject_primary(path, **kwargs):
        if Path(path).parent == folder / "data-logs":
            raise PermissionError("Read-only workspace parent")
        return original(path, **kwargs)

    monkeypatch.setattr(runtime_logging, "QuietRotatingFileHandler", reject_primary)
    result = runtime_logging.configure_runtime_logging(
        folder / "data", name="scheduled", console=False
    )
    assert result == folder / "local/ShadowserverCompanion/logs"
    logging.error("Fallback persistent diagnostic")
    assert "Fallback persistent diagnostic" in log_text(result)


def test_log_write_failure_does_not_dump_unredacted_arguments(runtime, monkeypatch):
    _, folder = runtime
    console = io.StringIO()
    monkeypatch.setattr(sys, "stderr", console)
    runtime_logging.configure_runtime_logging(folder / "data", name="scheduled", console=False)
    handler = logging.getLogger().handlers[0]

    class BrokenFile:
        closed = False

        def seek(self, *args):
            return 0

        def tell(self):
            return 0

        def write(self, _value):
            raise OSError("Disk unavailable")

        def flush(self):
            return None

        def close(self):
            self.closed = True

    handler.stream.close()
    handler.stream = BrokenFile()
    logging.error("Provider rejected %s", "opaque-private-credential")
    assert "could not write its diagnostic log" in console.getvalue()
    assert "opaque-private-credential" not in console.getvalue()


def test_unavailable_logging_and_console_still_produce_failure_exit(runtime, monkeypatch):
    runner, _ = runtime

    def no_log_destination(*args, **kwargs):
        raise PermissionError("no log destination")

    monkeypatch.setattr(runner, "configure_runtime_logging", no_log_destination)
    monkeypatch.setattr(runner, "main", lambda _args: pytest.fail("Cannot start silently"))
    with monkeypatch.context() as patch:
        patch.setattr(sys, "stdout", None)
        patch.setattr(sys, "stderr", None)
        assert runner.entrypoint([]) == 1
