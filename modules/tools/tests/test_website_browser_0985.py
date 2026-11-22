"""Capture failures preserve caller control and owned browser cleanup."""

from contextlib import asynccontextmanager
import asyncio
import threading
import time
from unittest.mock import AsyncMock, Mock

import pytest
from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeout

from modules.tools.components.website_capture import (
    CaptureBrowserStartupError,
    WebsiteLoadError,
    browser,
)
from modules.tools.components.website_capture.diagnostics import network_error


@pytest.fixture
def session(monkeypatch):
    page = Mock()
    page.screenshot = AsyncMock(return_value=b"PNG")
    context = Mock()
    context.new_page = AsyncMock(return_value=page)
    context.close = AsyncMock()
    native = Mock(version="158")
    native.new_context = AsyncMock(return_value=context)
    native.close = AsyncMock()
    events = Mock()
    events.send = AsyncMock(return_value={"browserContextIds": ["isolated"]})
    callbacks = {}
    events.on.side_effect = lambda name, callback: callbacks.__setitem__(name, callback)
    native.new_browser_cdp_session = AsyncMock(return_value=events)
    driver = Mock()
    driver.chromium.launch = AsyncMock(return_value=native)
    stopped = []

    @asynccontextmanager
    async def runtime():
        try:
            yield driver
        finally:
            stopped.append(True)

    monkeypatch.setattr(browser, "async_playwright", runtime)
    monkeypatch.setattr(browser, "browser_options", lambda executable: {"channel": "msedge"})
    return driver, native, context, page, callbacks, stopped


def test_pre_cancelled_capture_does_not_start_browser(monkeypatch):
    cancel = threading.Event()
    cancel.set()
    start = Mock(side_effect=AssertionError("Cancelled capture started a browser"))
    monkeypatch.setattr(browser, "async_playwright", start)
    with pytest.raises(ValueError, match="cancelled") as failure:
        browser.capture_website("https://example.com/", cancel_event=cancel)
    assert not isinstance(failure.value, CaptureBrowserStartupError)
    start.assert_not_called()


def test_startup_failure_retains_exit_code_without_command_line(session):
    driver, native, context, page, callbacks, stopped = session
    driver.chromium.launch.side_effect = PlaywrightError(
        "BrowserType.launch: private profile and token URL <process did exit: exitCode=0, signal=null>"
    )
    with pytest.raises(CaptureBrowserStartupError, match="exit code 0") as failure:
        browser.capture_website("https://example.com/")
    assert network_error(failure.value) == str(failure.value)
    assert "private" not in str(failure.value)
    context.new_page.assert_not_called()
    assert stopped == [True]


def test_failed_context_setup_never_visits_website_and_closes_browser(session):
    driver, native, context, page, callbacks, stopped = session
    native.new_context.side_effect = PlaywrightError("context setup failed with private path")
    with pytest.raises(CaptureBrowserStartupError):
        browser.capture_website("https://example.com/")
    assert native.new_context.call_args.kwargs["accept_downloads"] is False
    context.new_page.assert_not_called()
    native.close.assert_awaited_once()
    assert stopped == [True]


@pytest.mark.parametrize("result", ["screenshot", "load_failure", "connection_lost"])
def test_capture_preserves_download_observations_and_closes_resources(session, monkeypatch, result):
    driver, native, context, page, callbacks, stopped = session

    async def load(url, *, metadata, **kwargs):
        metadata["browser_stage"] = "navigation"
        callbacks["Browser.downloadWillBegin"]({"frameId": "sub", "guid": "fixture"})
        if result == "connection_lost":
            raise PlaywrightError("browser disconnected with private URL")
        callbacks["Browser.downloadProgress"]({"guid": "fixture", "state": "canceled"})
        if result == "load_failure":
            raise WebsiteLoadError("No rendered page", metadata)
        return page

    monkeypatch.setattr(browser, "load_page", load)
    if result == "screenshot":
        png, metadata = browser.capture_website("https://localhost/")
        assert png == b"PNG"
    else:
        expected = WebsiteLoadError if result == "load_failure" else browser.CaptureOperationError
        with pytest.raises(expected) as failure:
            browser.capture_website("https://localhost/")
        metadata = failure.value.metadata
    assert [row["outcome"] for row in metadata["download_activity"]["attempts"]] == [
        "unconfirmed" if result == "connection_lost" else "canceled"
    ]
    context.close.assert_awaited_once()
    native.close.assert_awaited_once()
    assert stopped == [True]


def test_already_expired_deadline_does_not_launch(session):
    driver, *_ = session
    with pytest.raises(TimeoutError, match="budget"):
        browser.capture_website("https://example.com/", deadline=time.monotonic() - 1)
    driver.chromium.launch.assert_not_called()


def test_launch_timeout_always_stops_the_batch_as_a_startup_failure(session, monkeypatch):
    driver, *_ = session

    async def fail(**kwargs):
        await asyncio.sleep(0.08)
        raise PlaywrightTimeout("Timed out launching with private profile")

    driver.chromium.launch.side_effect = fail
    monkeypatch.setattr(browser, "STARTUP_SECONDS", 0.01)
    with pytest.raises(CaptureBrowserStartupError, match="did not become ready"):
        browser.capture_website("https://example.com/")


def test_disconnected_cleanup_preserves_the_original_capture_failure(session, monkeypatch):
    driver, native, context, page, callbacks, stopped = session
    context.close.side_effect = PlaywrightError("Target page, context or browser has been closed")
    native.close.side_effect = PlaywrightError("Target page, context or browser has been closed")

    async def fail(url, *, metadata, **kwargs):
        metadata["browser_stage"] = "navigation"
        raise WebsiteLoadError("Website could not be loaded: DNS resolution failed", metadata)

    monkeypatch.setattr(browser, "load_page", fail)
    with pytest.raises(WebsiteLoadError, match="DNS resolution failed"):
        browser.capture_website("https://example.com/")
    native.close.assert_awaited_once()
    assert stopped == [True]


def test_first_page_failure_is_local_startup_failure(session):
    driver, native, context, page, callbacks, stopped = session
    context.new_page.side_effect = PlaywrightError("Browser closed before first tab")
    with pytest.raises(CaptureBrowserStartupError):
        browser.capture_website("https://example.com/")
    page.screenshot.assert_not_called()
    native.close.assert_awaited_once()
