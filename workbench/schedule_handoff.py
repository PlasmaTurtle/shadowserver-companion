"""Cooperative handoff from a scheduled workspace owner to the foreground."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
import threading
import time


def _paths(root):
    root = Path(root).resolve()
    return root.parent / ("." + root.name + "-scheduled.json"), root.parent / (
        "." + root.name + "-scheduled-stop.json"
    )


def _load(path):
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 4096:
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write(path, value):
    if path.is_symlink():
        raise ValueError("Scheduled handoff path must not be a link")
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=".companion-handoff-", delete=False
    ) as handle:
        temporary = Path(handle.name)
        json.dump(value, handle)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _alive(pid):
    if os.name == "nt":
        import ctypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = (ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_ulong)
        kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
        handle = kernel.OpenProcess(0x00100000, False, pid)
        if not handle:
            return ctypes.get_last_error() != 87  # Access denied is not proof of exit.
        try:
            return kernel.WaitForSingleObject(handle, 0) != 0
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def request_handoff(root, *, timeout=30):
    """Return True when a scheduled owner yields; False means no live marker.

    Never terminates a process or removes its workspace lock. The caller still
    acquires the ordinary workspace_session lock after this returns.
    """
    root = Path(root).resolve()
    marker, request = _paths(root)
    value = _load(marker)
    if (
        not isinstance(value, dict)
        or value.get("workspace") != str(root)
        or not re.fullmatch(r"[a-f0-9]{32}", str(value.get("nonce", "")))
        or type(value.get("pid")) is not int
        or value["pid"] <= 0
    ):
        return False
    if not _alive(value["pid"]):
        if _load(marker) == value:
            marker.unlink(missing_ok=True)
        return False
    _write(request, {"nonce": value["nonce"]})
    deadline = time.monotonic() + max(0, min(timeout, 60))
    while time.monotonic() < deadline:
        if _load(marker) != value or not _alive(value["pid"]):
            from .workspace_lock import acquire_lock

            try:
                probe = acquire_lock(root.parent, "." + root.name + "-companion.lock")
            except SystemExit:
                pass
            else:
                probe.close()
                return True
        time.sleep(0.1)
    raise RuntimeError(
        "Scheduled intake is finishing its current request. Reopen the application shortly; saved work is retained."
    )


@contextmanager
def scheduled_ownership(root, cancel_event):
    """Enter only while holding workspace_session; marker is never a lock."""
    marker, request = _paths(root)
    value = {
        "pid": os.getpid(),
        "nonce": secrets.token_hex(16),
        "workspace": str(Path(root).resolve()),
    }
    _write(marker, value)
    stopped = threading.Event()

    def watch():
        while not stopped.wait(0.1):
            incoming = _load(request)
            if isinstance(incoming, dict) and incoming.get("nonce") == value["nonce"]:
                cancel_event.set()
                return

    worker = threading.Thread(target=watch, name="scheduled-handoff", daemon=True)
    worker.start()
    try:
        yield
    finally:
        stopped.set()
        worker.join(timeout=1)
        if _load(marker) == value:
            marker.unlink(missing_ok=True)
        incoming = _load(request)
        if isinstance(incoming, dict) and incoming.get("nonce") == value["nonce"]:
            request.unlink(missing_ok=True)
