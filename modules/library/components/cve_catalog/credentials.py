"""NVD access held in memory or the current user's Windows Credential Manager."""

import hashlib
import os
from pathlib import Path
import re
import threading

_lock = threading.RLock()
_sessions = {}


def _identity(root):
    return hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest()[:24]


def _checked(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9A-Fa-f]{8}-(?:[0-9A-Fa-f]{4}-){3}[0-9A-Fa-f]{12}", value.strip()
    ):
        raise ValueError("Enter a valid NVD API key.")
    return value.strip()


class NVDKeys:
    def __init__(self, root, *, backend=None):
        self.identity = _identity(root)
        self.target = "ShadowserverCompanion/NVD/" + self.identity
        self.backend = backend

    def _store(self):
        if self.backend is None:
            from modules.accretion.components.shadowserver_reports.credentials import (
                WindowsCredentialStore,
            )

            self.backend = WindowsCredentialStore()
        return self.backend

    def get(self):
        with _lock:
            if self.identity in _sessions:
                return _sessions[self.identity][0]
            value = os.environ.get("NVD_API_KEY", "")
            if value:
                try:
                    return _checked(value)
                except ValueError:
                    return ""
            if os.name != "nt" and self.backend is None:
                return ""
            try:
                value = _checked(self._store().read(self.target).decode("ascii"))
            except Exception:
                return ""
            _sessions[self.identity] = (value, "windows")
            return value

    def status(self):
        with _lock:
            configured = bool(self.get())
            source = _sessions.get(self.identity, ("", "environment" if configured else "none"))[1]
            return {
                "configured": configured,
                "source": source,
                "remember_supported": os.name == "nt" or self.backend is not None,
            }

    def configure(self, key, *, remember=False):
        value = _checked(key)
        with _lock:
            if remember:
                try:
                    self._store().write(self.target, value.encode("ascii"))
                except Exception:
                    raise ValueError(
                        "NVD key could not be saved in Windows Credential Manager."
                    ) from None
            elif os.name == "nt" or self.backend is not None:
                # Session-only replaces the saved account too: it must not
                # silently return after restart. A missing vault entry is fine.
                self._delete_saved()
            _sessions[self.identity] = (value, "windows" if remember else "session")
            return self.status()

    def _delete_saved(self):
        try:
            self._store().delete(self.target)
        except Exception:
            raise ValueError(
                "NVD key could not be removed from Windows Credential Manager."
            ) from None

    def forget(self):
        with _lock:
            if os.name == "nt" or self.backend is not None:
                self._delete_saved()
            _sessions.pop(self.identity, None)
            return self.status()
