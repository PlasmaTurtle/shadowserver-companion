"""Launcher-issued local browser sessions; no credentials are public HTTP data."""

from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import urlsplit

LAUNCH_SECONDS = 120
SESSION_SECONDS = 12 * 60 * 60
MAX_SESSIONS = 8
INSTANCE_FILE = "launcher-session.json"


def origin_tuple(value):
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            return None
        return (
            parsed.scheme,
            parsed.hostname.lower(),
            parsed.port or (443 if parsed.scheme == "https" else 80),
        )
    except ValueError, TypeError:
        return None


def same_origin(request):
    supplied = request.headers.get("origin")
    if supplied is None:
        return True  # Native clients still require an unguessable credential.
    expected = origin_tuple(str(request.base_url))
    return expected is not None and origin_tuple(supplied) == expected


class LocalSessions:
    def __init__(self):
        self.launcher_key = secrets.token_urlsafe(32)
        self.cookie_name = "companion_session_" + secrets.token_hex(8)
        self._launches = {}
        self._sessions = {}
        self._lock = threading.Lock()

    def launcher_authorized(self, value):
        return isinstance(value, str) and secrets.compare_digest(value, self.launcher_key)

    def issue_launch(self):
        with self._lock:
            self._prune()
            if len(self._launches) >= MAX_SESSIONS:
                self._launches.pop(next(iter(self._launches)))
            token = secrets.token_urlsafe(32)
            self._launches[self._digest(token)] = time.monotonic() + LAUNCH_SECONDS
            return token

    @staticmethod
    def _digest(value):
        return hashlib.sha256(value.encode()).hexdigest()

    def _prune(self):
        now = time.monotonic()
        for values in (self._launches, self._sessions):
            for key, deadline in list(values.items()):
                if deadline <= now:
                    del values[key]

    def exchange(self, token):
        if not isinstance(token, str) or not 30 <= len(token) <= 100:
            return None
        with self._lock:
            self._prune()
            if self._launches.pop(self._digest(token), None) is None:
                return None
            if len(self._sessions) >= MAX_SESSIONS:
                self._sessions.pop(next(iter(self._sessions)))
            session = secrets.token_urlsafe(32)
            self._sessions[self._digest(session)] = time.monotonic() + SESSION_SECONDS
            return session

    def authorized(self, request):
        value = request.cookies.get(self.cookie_name, "")
        if not 30 <= len(value) <= 100:
            return False
        with self._lock:
            self._prune()
            return self._digest(value) in self._sessions


def _dpapi(data, *, decrypt=False):
    """Bind the installed launch credential to the current Windows logon user."""
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    incoming, outgoing = Blob(len(data), buffer), Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    name = "CryptUnprotectData" if decrypt else "CryptProtectData"
    function = getattr(crypt, name)
    function.argtypes = [
        ctypes.POINTER(Blob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(Blob),
    ]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        kernel.LocalFree(outgoing.data)


def write_instance(workspace: Path, port: int, demo: bool, sessions: LocalSessions):
    key = sessions.launcher_key.encode()
    data = {
        "version": 1,
        "port": port,
        "demo": demo,
        "workspace": str(workspace.resolve()),
        "protection": "windows-dpapi" if os.name == "nt" else "user-file",
        "credential": base64.b64encode(_dpapi(key) if os.name == "nt" else key).decode(),
    }
    path = workspace / INSTANCE_FILE
    temp = workspace / (INSTANCE_FILE + "." + secrets.token_hex(8))
    try:
        descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)
    return path


def read_instance(workspace: Path, port: int, demo: bool):
    path = workspace / INSTANCE_FILE
    if path.is_symlink() or path.stat().st_size > 8192:
        raise ValueError("Invalid launcher session file")
    if os.name != "nt":
        stat = path.stat()
        if stat.st_uid != os.getuid() or stat.st_mode & 0o077:
            raise ValueError("Launcher session file must be private to this user")
    data = json.loads(path.read_text(encoding="utf-8"))
    if (
        data.get("version") != 1
        or data.get("port") != port
        or data.get("demo") is not demo
        or data.get("workspace") != str(workspace.resolve())
    ):
        raise ValueError("Launcher session belongs to a different workspace")
    protected = "windows-dpapi" if os.name == "nt" else "user-file"
    if data.get("protection") != protected:
        raise ValueError("Launcher session protection does not match this system")
    key = base64.b64decode(data["credential"], validate=True)
    return (_dpapi(key, decrypt=True) if os.name == "nt" else key).decode("ascii")
