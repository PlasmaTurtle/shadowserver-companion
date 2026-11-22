"""Browser startup and cancellation preserve owned process/profile lifetime."""

from pathlib import Path
import threading

import pytest

from modules.tools.components.website_capture import CaptureBrowserStartupError, browser
from modules.tools.components.website_capture.diagnostics import network_error


def test_startup_failure_removes_temporary_profile(monkeypatch, tmp_path):
    profile = tmp_path / "capture-profile"

    def create(**kwargs):
        profile.mkdir()
        return str(profile)

    def fail(*args, **kwargs):
        raise PermissionError(13, "Synthetic private profile path")

    monkeypatch.setattr(browser.tempfile, "mkdtemp", create)
    monkeypatch.setattr(browser.subprocess, "Popen", fail)
    with pytest.raises(CaptureBrowserStartupError, match="OS error 13") as failure:
        browser.capture_website("http://localhost/", executable="synthetic-browser")
    assert str(failure.value) == network_error(failure.value)
    assert "private" not in str(failure.value)
    assert not profile.exists()


def test_pre_cancelled_capture_does_not_start_browser(monkeypatch):
    cancel = threading.Event()
    cancel.set()

    def forbidden(*args, **kwargs):
        pytest.fail("Cancelled capture started a browser")

    monkeypatch.setattr(browser.subprocess, "Popen", forbidden)
    with pytest.raises(ValueError, match="cancelled") as failure:
        browser.capture_website("https://example.com/", cancel_event=cancel)
    assert not isinstance(failure.value, CaptureBrowserStartupError)


def test_early_browser_exit_closes_owned_guard_and_profile(monkeypatch, tmp_path):
    profile = tmp_path / "capture-profile"
    closed = []

    def create(**kwargs):
        profile.mkdir()
        return str(profile)

    class Process:
        def poll(self):
            return 1

        def wait(self, **kwargs):
            return 1

    class Guard:
        def __init__(self, process):
            pass

        def close(self):
            closed.append(True)

    monkeypatch.setattr(browser.tempfile, "mkdtemp", create)
    monkeypatch.setattr(browser.subprocess, "Popen", lambda *a, **k: Process())
    monkeypatch.setattr(browser, "BrowserProcessGuard", Guard)
    with pytest.raises(CaptureBrowserStartupError, match=r"exit code 1\)") as failure:
        browser.capture_website("http://localhost/", executable="synthetic-browser")
    assert network_error(failure.value) == str(failure.value)
    assert closed == [True] and not profile.exists()


@pytest.mark.parametrize(
    ("failed_method", "error", "diagnostic"),
    [
        ("Page.enable", ConnectionResetError(10054, "A private local path"), "OS error 10054"),
        (
            "Browser.setDownloadBehavior",
            ValueError("Capture browser could not complete Browser.setDownloadBehavior"),
            "could not complete Browser.setDownloadBehavior",
        ),
    ],
)
def test_browser_setup_failure_prevents_navigation(
    monkeypatch, tmp_path, failed_method, error, diagnostic
):
    from unittest.mock import Mock

    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "DevToolsActivePort").write_text("1234\n/devtools/browser/test\n", encoding="ascii")
    client = Mock()

    def call(method, *args, **kwargs):
        if method == failed_method:
            raise error
        return {
            "Browser.getVersion": {"product": "Edge"},
            "Target.createTarget": {"targetId": "target"},
            "Target.attachToTarget": {"sessionId": "session"},
        }.get(method, {})

    client.call.side_effect = call
    monkeypatch.setattr(browser.tempfile, "mkdtemp", lambda **kwargs: str(profile))
    monkeypatch.setattr(browser.subprocess, "Popen", Mock())
    monkeypatch.setattr(browser, "BrowserProcessGuard", Mock())
    monkeypatch.setattr(browser, "CDP", Mock(return_value=client))
    with pytest.raises(CaptureBrowserStartupError, match=diagnostic):
        browser.capture_website("http://localhost/", executable="synthetic-browser")
    calls = client.call.call_args_list
    methods = [entry.args[0] for entry in calls]
    policy = calls[methods.index("Browser.setDownloadBehavior")]
    assert policy.args == (
        "Browser.setDownloadBehavior",
        {"behavior": "deny", "eventsEnabled": True},
    )
    assert policy.kwargs == {"browser": True}
    assert "Page.navigate" not in methods
    if failed_method == "Browser.setDownloadBehavior":
        assert "Target.createTarget" not in methods
    client.close.assert_called_once()
    assert not profile.exists()
