"""Installed edition launcher. Uses a workspace outside the program directory."""

from __future__ import annotations

import argparse
import atexit
import ctypes
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import tempfile
import time
import urllib.request
import webbrowser

from workbench.release import installation_identity, load_release, validate_workspace_identity

RELEASE = load_release()
IDENTITY = installation_identity(RELEASE["edition"], RELEASE.get("variant", ""))
RUNNING_MUTEX = IDENTITY["running_mutex"]
INSTALL_GATE = f"Local\\{IDENTITY['app_id']}.Installed.StartInstall"
APP_NAME = IDENTITY["app_name"]
MAX_RESPONSE = 64 * 1024
REOPEN_SECONDS = 30
_installation_handle = None


def default_workspace(demo: bool = False) -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if not local or not Path(local).is_absolute():
        raise RuntimeError(
            "Windows did not provide LOCALAPPDATA. Start the application from your Windows account."
        )
    return Path(local) / IDENTITY["app_id"] / ("data-demo" if demo else "data")


def read_local_json(url: str, *, launcher_key: str | None = None, timeout: float = 1) -> dict:
    # Workstation proxy settings must not send localhost traffic to a proxy.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *_args):
            return None

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request(url, method="POST" if launcher_key else "GET")
    if launcher_key:
        request.add_header("X-Workbench-Launcher", launcher_key)
    with opener.open(request, timeout=timeout) as response:
        raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ValueError("Local response exceeded the limit")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Unexpected local response")
    return value


def existing_instance(port: int, workspace: Path, demo: bool, *, timeout: float = 1) -> str | None:
    try:
        from workbench.local_session import read_instance

        deadline = time.monotonic() + timeout
        health = read_local_json(f"http://127.0.0.1:{port}/api/health", timeout=timeout)
        if health.get("app") != "notification-workbench" or health.get("demo") is not demo:
            return None
        key = read_instance(workspace, port, demo)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        response = read_local_json(
            f"http://127.0.0.1:{port}/api/session/launch", launcher_key=key, timeout=remaining
        )
        token = response.get("launch")
        if (
            not isinstance(token, str)
            or not 30 <= len(token) <= 100
            or not all(c.isascii() and (c.isalnum() or c in "-_") for c in token)
        ):
            return None
        return f"http://127.0.0.1:{port}/#launch=" + token
    except OSError, ValueError, TypeError, KeyError:
        return None


def wait_for_existing_instance(port: int, workspace: Path, demo: bool) -> str | None:
    """A workspace lock is not proof of identity; only authenticated reuse is."""
    deadline = time.monotonic() + REOPEN_SECONDS
    while (remaining := deadline - time.monotonic()) > 0:
        url = existing_instance(port, workspace, demo, timeout=min(1, remaining))
        if url:
            return url
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(0.2, remaining))
    return None


def open_existing_session(url: str, *, no_browser: bool) -> None:
    if no_browser:
        print("Open: " + url)
    else:
        webbrowser.open(url)
    print(f"Opened the existing {APP_NAME} session.")


def hold_installation_mutex() -> None:
    """Atomically register a running process against setup's exclusive gate.

    The gate is held only while publishing the legacy running handle, allowing
    Demo and independent workspaces to run together. Setup holds the same gate
    throughout file replacement, after checking for all running handles.
    """
    global _installation_handle
    if sys.platform != "win32" or _installation_handle is not None:
        return
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    kernel32.CloseHandle.restype = ctypes.c_int
    kernel32.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_ulong)
    kernel32.WaitForSingleObject.restype = ctypes.c_ulong
    kernel32.ReleaseMutex.argtypes = (ctypes.c_void_p,)
    kernel32.ReleaseMutex.restype = ctypes.c_int
    gate = kernel32.CreateMutexW(None, False, INSTALL_GATE)
    if not gate:
        raise ctypes.WinError(ctypes.get_last_error())
    owned = False
    try:
        # Another launcher owns this only for a few calls. A short wait avoids
        # mistaking simultaneous launches for an installation in progress.
        result = kernel32.WaitForSingleObject(gate, 5000)
        if result == 0xFFFFFFFF:
            raise ctypes.WinError(ctypes.get_last_error())
        if result not in (0, 0x80):  # WAIT_OBJECT_0 / WAIT_ABANDONED both grant ownership.
            raise RuntimeError(
                "Installation or removal is in progress. Reopen the application when setup finishes."
            )
        owned = True
        handle = kernel32.CreateMutexW(None, False, RUNNING_MUTEX)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        _installation_handle = handle
        atexit.register(kernel32.CloseHandle, handle)
    finally:
        if owned:
            kernel32.ReleaseMutex(gate)
        kernel32.CloseHandle(gate)


def runtime_self_test() -> None:
    """Offline import/export smoke test for the exact installed Windows runtime."""
    import ssl
    import sqlite3
    import attribution
    import dns.resolver
    import pydantic_core
    import pillow_heif
    from PIL import Image
    from docx import Document
    from lxml import etree
    from reportlab.pdfgen.canvas import Canvas
    from workbench.api import create_app

    with tempfile.TemporaryDirectory(prefix="outreach-self-test-") as folder:
        root = Path(folder)
        app = create_app(root / "workspace", worker=False)
        assert any(getattr(route, "path", "") == "/api/health" for route in app.routes)
        Image.new("RGB", (20, 20), "white").save(root / "image.png")
        doc = Document()
        doc.add_paragraph("Shadowserver Companion installation test")
        doc.save(root / "test.docx")
        pdf = Canvas(str(root / "test.pdf"))
        pdf.drawString(40, 740, "Shadowserver Companion installation test")
        pdf.save()
        assert etree.fromstring(b"<test/>").tag == "test"
        assert (root / "test.docx").stat().st_size > 1000
        assert (root / "test.pdf").stat().st_size > 500
    print(
        f"Runtime test passed: Python {sys.version.split()[0]}, SQLite {sqlite3.sqlite_version}, {ssl.OPENSSL_VERSION}"
    )


def configure_logging(workspace: Path | None = None):
    # Logs must exist before port/session checks and stay outside a replaceable
    # workspace. A fallback also records failures before LOCALAPPDATA is known.
    from workbench.runtime_logging import configure_runtime_logging

    return configure_runtime_logging(
        workspace,
        app_id=IDENTITY["app_id"],
        fallback_folder=Path(tempfile.gettempdir()) / (IDENTITY["app_id"] + "-startup"),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--port", type=int)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        configure_logging()
        hold_installation_mutex()
        runtime_self_test()
        if sys.platform == "win32":
            ctypes.windll.user32.MessageBoxW(
                None,
                "Bundled runtime checks passed. No working records were used.",
                APP_NAME,
                0x40,
            )
        return 0
    workspace = (args.data_dir or default_workspace(args.demo)).resolve()
    validate_workspace_identity(
        workspace,
        os.environ.get("LOCALAPPDATA"),
        edition=RELEASE["edition"],
        variant=RELEASE.get("variant", ""),
    )
    configure_logging(workspace)
    hold_installation_mutex()
    port = args.port if args.port is not None else IDENTITY["demo_port" if args.demo else "port"]
    if not 1 <= port <= 65535:
        parser.error("Port must be between 1 and 65535.")
    launch_url = existing_instance(port, workspace, args.demo)
    if launch_url:
        open_existing_session(launch_url, no_browser=args.no_browser)
        return 0
    # Only the server's actual bind determines availability. Client connection
    # probes can time out on an unused Windows port; raw binds reject TIME_WAIT.
    # The workspace may be atomically replaced during run.main startup. Keep
    # open log handles outside it so the rename also works on Windows.
    # Prevent installed source directories accumulating bytecode between upgrades.
    sys.dont_write_bytecode = True
    os.environ.pop("WORKBENCH_PREVIEW", None)
    from run import main as run_workbench

    saved_args = sys.argv
    sys.argv = [
        str(Path(__file__).with_name("run.py")),
        "--data-dir",
        str(workspace),
        "--port",
        str(port),
    ]
    if args.demo:
        sys.argv.append("--demo")
    if args.no_browser:
        sys.argv.append("--no-browser")
    try:
        run_workbench()
    except SystemExit as error:
        if not isinstance(error.code, str) or not error.code.startswith(
            "This workspace is already open."
        ):
            raise
        # A simultaneous launch can acquire the workspace before it is ready
        # to authenticate a browser. Never start a second server or guess a URL.
        launch_url = wait_for_existing_instance(port, workspace, args.demo)
        if not launch_url:
            raise RuntimeError(
                "This workspace is already open, but its matching browser session is not ready. "
                "Reopen the same application shortcut shortly, or check its application log."
            ) from None
        open_existing_session(launch_url, no_browser=args.no_browser)
    finally:
        sys.argv = saved_args
    return 0


def entrypoint() -> int:
    try:
        return main()
    except KeyboardInterrupt:
        return 0
    except SystemExit as error:
        if not isinstance(error.code, str):
            raise
        message = error.code
    except Exception as error:
        if not any(
            isinstance(handler, RotatingFileHandler) for handler in logging.getLogger().handlers
        ):
            try:
                configure_logging()
            except OSError:
                pass
        logging.exception("%s could not start", APP_NAME)
        message = str(error)
    from workbench.runtime_logging import safe_write

    safe_write(sys.stderr, f"\n{APP_NAME} could not start: {message}\n")
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, message, APP_NAME, 0x10)
    return 1


if __name__ == "__main__":
    raise SystemExit(entrypoint())
