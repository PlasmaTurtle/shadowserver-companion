"""Playwright-managed browser lifetime and viewport capture for shared callers."""

import asyncio
from contextlib import suppress
import os
from pathlib import Path
import re
import shutil
import threading
import time

from playwright.async_api import (
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeout,
    async_playwright,
)

from .diagnostics import network_error
from .downloads import DownloadObservations
from .transport import web_url
from .navigation import WebsiteLoadError, extract_root_domain as extract_root_domain, load_page
from modules.workspace.components.primitives import now

VIEWPORT = {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False}
MAX_SECONDS = 90
STARTUP_SECONDS = 20


class CaptureBrowserStartupError(ValueError):
    """The local browser could not initialize before attempting a website."""


class CaptureOperationError(ValueError):
    """An interrupted capture with observations made before the interruption."""

    def __init__(self, message, metadata):
        super().__init__(message)
        self.metadata = metadata


def find_browser():
    if os.name == "nt":
        for variable, suffix in [
            ("PROGRAMFILES(X86)", "Microsoft/Edge/Application/msedge.exe"),
            ("PROGRAMFILES", "Microsoft/Edge/Application/msedge.exe"),
            ("LOCALAPPDATA", "Microsoft/Edge/Application/msedge.exe"),
            ("PROGRAMFILES", "Google/Chrome/Application/chrome.exe"),
            ("PROGRAMFILES(X86)", "Google/Chrome/Application/chrome.exe"),
            ("LOCALAPPDATA", "Google/Chrome/Application/chrome.exe"),
        ]:
            folder = os.environ.get(variable)
            if folder and (Path(folder) / suffix).is_file():
                return str(Path(folder) / suffix)
    else:
        for name in ("microsoft-edge", "google-chrome", "chromium", "chromium-browser"):
            if found := shutil.which(name):
                return found
    raise ValueError(
        "Website capture needs Microsoft Edge or Google Chrome installed. Manual attachment is still available."
    )


def browser_options(executable=None):
    """Prefer supported installed browser channels; explicit paths are caller-owned."""
    if executable is not None:
        return {"executable_path": str(executable)}
    name = Path(find_browser()).name.lower()
    if name in {"msedge.exe", "microsoft-edge"}:
        return {"channel": "msedge"}
    if name in {"chrome.exe", "google-chrome"}:
        return {"channel": "chrome"}
    return {"executable_path": find_browser()}


def classify_page(info, http_status, loaded, document_failed):
    text = (info.get("title", "") + " " + info.get("text", "")).casefold()
    if (
        document_failed
        or not http_status
        or not info.get("url", "").startswith(("https://", "http://"))
    ):
        return "load_failed"
    if http_status in (403, 429) or any(
        s in text
        for s in (
            "verify you are human",
            "checking your browser",
            "just a moment...",
            "enable javascript and cookies to continue",
            "access denied",
            "attention required! | cloudflare",
            "captcha",
        )
    ):
        return "challenge"
    if http_status >= 400 and http_status not in {401, 407}:
        return "load_failed"
    if not loaded or not info.get("visible", bool(info.get("text", "").strip())):
        return "partial"
    if (
        http_status in (401, 407)
        or info.get("password")
        or re.search(r"/(?:login|signin|sign-in)(?:/|\?|$)", info.get("url", ""), re.I)
    ):
        return "login_required"
    return "captured"


def capture_website(
    url,
    *,
    cancel_event=None,
    executable=None,
    skip_urls=(),
    require_usable=False,
    page_check=None,
    deadline=None,
):
    """Capture synchronously from a worker; Playwright stays on this owning thread."""
    requested = web_url(url)
    cancel_event = cancel_event or threading.Event()
    if cancel_event.is_set():
        raise ValueError("Website capture cancelled")
    if deadline is not None and time.monotonic() >= deadline:
        raise TimeoutError("The website capture time budget has expired")
    return asyncio.run(
        _capture(
            requested,
            cancel_event=cancel_event,
            executable=executable,
            skip_urls=skip_urls,
            require_usable=require_usable,
            page_check=page_check,
            operation_deadline=deadline,
        ),
        loop_factory=asyncio.ProactorEventLoop if os.name == "nt" else asyncio.new_event_loop,
    )


async def _capture(
    requested_url,
    *,
    cancel_event,
    executable,
    skip_urls,
    require_usable,
    page_check,
    operation_deadline,
):
    start = time.monotonic()
    operation_deadline = operation_deadline if operation_deadline is not None else float("inf")
    deadline = min(start + STARTUP_SECONDS, operation_deadline)
    native = context = page = close_task = None
    finished = asyncio.Event()
    expired = False
    downloads = DownloadObservations()
    metadata = {
        "requested_url": requested_url,
        "root_domain": extract_root_domain(requested_url),
        "final_url": "",
        "title": "",
        "captured_at": now(),
        "viewport": dict(VIEWPORT),
        "capture_status": "load_failed",
        "http_status": None,
        "redirects": [],
        "attempted_urls": [],
        "attempts": [],
        "fallback_used": False,
        "blocked_requests": 0,
        "policy": "playwright-viewport-v1",
        "browser": "",
        "resource_failures": [],
        "content_scans": {},
        "content_scanning": "not_performed",
        "fetched_requests": 0,
        "browser_stage": "startup",
    }

    async def release():
        try:
            with suppress(PlaywrightError):
                if context is not None:
                    await context.close()
        finally:
            with suppress(PlaywrightError):
                if native is not None:
                    await native.close()

    async def close():
        nonlocal close_task
        if close_task is None and native is not None:
            close_task = asyncio.create_task(release())
        if close_task is not None:
            await close_task

    async def watch():
        nonlocal expired
        while not finished.is_set():
            expired = time.monotonic() >= deadline
            if (cancel_event.is_set() or expired) and native is not None:
                await close()
                return
            await asyncio.sleep(0.05)

    async def open_page():
        nonlocal page
        metadata["browser_stage"] = "startup" if page is None else "page_setup"
        if page is not None:
            await page.close()
        page = await context.new_page()
        metadata["browser_stage"] = "navigation"
        return page

    monitor = asyncio.create_task(watch())
    try:
        async with async_playwright() as playwright:
            try:
                options = browser_options(executable)
                native = await playwright.chromium.launch(
                    **options,
                    headless=True,
                    chromium_sandbox=True,
                    timeout=max(1, (deadline - time.monotonic()) * 1000),
                )
                metadata["browser"] = options.get("channel", "Chromium") + "/" + native.version
                context = await native.new_context(
                    viewport={"width": 1440, "height": 900},
                    device_scale_factor=1,
                    accept_downloads=False,
                )
                await downloads.attach(native)
                deadline = min(time.monotonic() + MAX_SECONDS, operation_deadline)
                page = await load_page(
                    requested_url,
                    open_page=open_page,
                    deadline=deadline,
                    cancel_event=cancel_event,
                    metadata=metadata,
                    classify=classify_page,
                    skip_urls=skip_urls,
                    require_usable=require_usable,
                    page_check=page_check,
                )
                metadata["browser_stage"] = "screenshot"
                png = await page.screenshot(
                    type="png",
                    full_page=False,
                    timeout=max(1, (deadline - time.monotonic()) * 1000),
                )
                metadata["captured_at"] = now()
                metadata["browser_stage"] = "complete"
            finally:
                finished.set()
                await monitor
                await close()
    except (PlaywrightError, OSError, ValueError) as error:
        if cancel_event.is_set():
            raise CaptureOperationError("Website capture cancelled", metadata) from error
        if metadata["browser_stage"] == "startup":
            # Playwright diagnostics can contain paths and command lines. Retain
            # only the safe native failure information at the application boundary.
            match = re.search(r"exitCode=(-?\d+)", str(error))
            detail = (
                f"Capture browser exited before startup (exit code {match[1]})"
                if match
                else "Capture browser did not become ready in time"
                if expired or isinstance(error, PlaywrightTimeout)
                else network_error(error)
            )
            raise CaptureBrowserStartupError(f"Capture browser startup failed: {detail}") from error
        if expired:
            raise CaptureOperationError("Website capture timed out", metadata) from error
        if isinstance(error, WebsiteLoadError):
            raise
        raise CaptureOperationError(network_error(error), metadata) from error
    finally:
        finished.set()
        await monitor
        metadata.update(downloads.snapshot())
    if cancel_event.is_set():
        raise CaptureOperationError("Website capture cancelled", metadata)
    metadata["elapsed_seconds"] = round(time.monotonic() - start, 2)
    return png, metadata
