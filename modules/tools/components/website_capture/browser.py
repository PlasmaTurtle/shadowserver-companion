"""Capture the selected loaded page in an isolated installed Edge/Chrome session."""

import base64
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import time

from .cdp import CDP
from .diagnostics import network_error
from .downloads import DownloadObservations
from .process_guard import BrowserProcessGuard
from .transport import web_url
from .navigation import (
    WebsiteLoadError,
    extract_root_domain as extract_root_domain,
    load_page,
)
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


def browser_arguments(executable, profile):
    return [
        executable,
        "--headless=new",
        "--remote-debugging-port=0",
        "--remote-debugging-address=127.0.0.1",
        "--user-data-dir=" + str(profile),
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=1440,900",
        "about:blank",
    ]


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
    requested_url = web_url(url)
    cancel_event = cancel_event or threading.Event()
    start = time.monotonic()
    if cancel_event.is_set():
        raise ValueError("Website capture cancelled")
    operation_deadline = deadline if deadline is not None else float("inf")
    deadline = min(start + STARTUP_SECONDS, operation_deadline)
    if start >= deadline:
        raise TimeoutError("The website capture time budget has expired")
    profile = None
    process = client = guard = target = None
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
        "resource_bytes": 0,
        "policy": "native-browser-viewport-v3",
        "browser": "",
        "resource_failures": [],
        "content_scans": {},
        "content_scanning": "not_performed",
        "fetched_requests": 0,
    }

    def open_page():
        nonlocal target
        client.deadline = deadline
        # The first target is still about:blank. Failures configuring it precede
        # any navigation; a later fallback target follows a site attempt.
        metadata["browser_stage"] = "startup" if target is None else "page_setup"
        if target is not None:
            client.call("Target.closeTarget", {"targetId": target}, browser=True)
            client.session = None
        target = client.call("Target.createTarget", {"url": "about:blank"}, browser=True)[
            "targetId"
        ]
        client.session = client.call(
            "Target.attachToTarget", {"targetId": target, "flatten": True}, browser=True
        )["sessionId"]
        client.call("Page.enable")
        client.call("Page.setLifecycleEventsEnabled", {"enabled": True})
        client.call("Emulation.setDeviceMetricsOverride", VIEWPORT)
        client.call("Network.enable")
        metadata["browser_stage"] = "navigation"
        return client

    try:
        metadata["browser_stage"] = "startup"
        profile = Path(tempfile.mkdtemp(prefix="companion-website-"))
        process = subprocess.Popen(
            browser_arguments(executable or find_browser(), profile),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        guard = BrowserProcessGuard(process)
        port_file = profile / "DevToolsActivePort"
        while not port_file.is_file():
            if cancel_event.wait(0.05):
                raise ValueError("Website capture cancelled")
            if time.monotonic() >= deadline:
                raise ValueError("Capture browser did not become ready in time")
            exit_code = process.poll()
            if exit_code is not None:
                raise ValueError(f"Capture browser exited before startup (exit code {exit_code})")
        lines = port_file.read_text(encoding="ascii").splitlines()
        if (
            len(lines) < 2
            or not lines[0].isdigit()
            or not lines[1].startswith("/devtools/browser/")
        ):
            raise ValueError("Invalid capture browser endpoint")
        client = CDP("ws://127.0.0.1:" + lines[0] + lines[1], deadline, downloads=downloads)
        client.cancel_event = cancel_event
        metadata["browser"] = client.call("Browser.getVersion", browser=True).get("product", "")[
            :160
        ]
        # All capture tabs share this context. Require its policy before visiting a site.
        client.call(
            "Browser.setDownloadBehavior", {"behavior": "deny", "eventsEnabled": True}, browser=True
        )
        metadata["browser_stage"] = "candidate_selection"
        deadline = min(time.monotonic() + MAX_SECONDS, operation_deadline)
        load_page(
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
        if cancel_event.is_set():
            raise ValueError("Website capture cancelled")
        metadata["browser_stage"] = "screenshot"
        screenshot = client.call(
            "Page.captureScreenshot",
            {
                "format": "png",
                "fromSurface": True,
                "captureBeyondViewport": False,
                "clip": {"x": 0, "y": 0, "width": 1440, "height": 900, "scale": 1},
            },
        )
        png = base64.b64decode(screenshot["data"], validate=True)
        metadata["captured_at"] = now()
        metadata["browser_stage"] = "complete"
    except WebsiteLoadError:
        raise
    except (OSError, ValueError) as error:
        if downloads.attempts:
            raise CaptureOperationError(network_error(error), metadata) from error
        if metadata["browser_stage"] != "startup" or cancel_event.is_set():
            raise
        native_code = getattr(error, "winerror", None) or getattr(error, "errno", None)
        detail = f"OS error {native_code}" if isinstance(native_code, int) else network_error(error)
        raise CaptureBrowserStartupError(f"Capture browser startup failed: {detail}") from error
    finally:
        if client:
            try:
                if not cancel_event.is_set():
                    client.finish_downloads()
            except (OSError, ValueError):
                pass  # Preserve observations and the original capture outcome on disconnect.
            metadata.update(downloads.snapshot())
            try:
                client.send("Browser.close", browser=True)
            except (OSError, ValueError):
                pass
            client.close()
        if guard:
            guard.close()
        if process:
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
        if profile is not None:
            shutil.rmtree(profile, ignore_errors=True)
    metadata["elapsed_seconds"] = round(time.monotonic() - start, 2)
    return png, metadata
