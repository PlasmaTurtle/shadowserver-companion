"""Browser startup and cancellation preserve owned process/profile lifetime."""

from pathlib import Path
import threading

import pytest

from modules.tools.components.website_capture import browser


def test_startup_failure_removes_temporary_profile(monkeypatch, tmp_path):
    profile = tmp_path / "capture-profile"

    def create(**kwargs):
        profile.mkdir()
        return str(profile)

    def fail(*args, **kwargs):
        raise OSError("Synthetic browser launch failure")

    monkeypatch.setattr(browser.tempfile, "mkdtemp", create)
    monkeypatch.setattr(browser.subprocess, "Popen", fail)
    with pytest.raises(OSError, match="launch failure"):
        browser.capture_website("http://localhost/", executable="synthetic-browser")
    assert not profile.exists()


def test_pre_cancelled_capture_does_not_start_browser(monkeypatch):
    cancel = threading.Event()
    cancel.set()

    def forbidden(*args, **kwargs):
        pytest.fail("Cancelled capture started a browser")

    monkeypatch.setattr(browser.subprocess, "Popen", forbidden)
    with pytest.raises(ValueError, match="cancelled"):
        browser.capture_website("https://example.com/", cancel_event=cancel)


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
    with pytest.raises(ValueError, match="could not start"):
        browser.capture_website("http://localhost/", executable="synthetic-browser")
    assert closed == [True] and not profile.exists()
