"""Local credential providers. Secrets are never accepted as CLI arguments."""
from __future__ import annotations

import ctypes
import json
import os
import re
from ctypes import wintypes
from typing import Mapping

from .errors import ConfigurationError
from .models import Credentials


def validate_profile(profile: str) -> str:
    if not isinstance(profile, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", profile):
        raise ConfigurationError("Profile must contain 1–64 letters, numbers, dots, underscores or hyphens.")
    return profile


def _credentials(api_key: object, secret: object) -> Credentials:
    if not isinstance(api_key, str) or not isinstance(secret, str) or not api_key.strip() or not secret.strip():
        raise ConfigurationError("Both an API key and an API secret are required.")
    if len(api_key) > 1024 or len(secret) > 1024 or "\x00" in api_key or "\x00" in secret:
        raise ConfigurationError("The credential format is invalid.")
    return Credentials(api_key=api_key, secret=secret)


class EnvCredentialProvider:
    """Read SHADOWSERVER_API_KEY and SHADOWSERVER_API_SECRET when called.

    Environment variables are an opt-in alternative for controlled automation.
    They are not persisted by this module.
    """

    def __init__(self, prefix: str = "SHADOWSERVER_", *, environ: Mapping[str, str] | None = None):
        self.prefix = prefix
        self._environ = environ

    def __call__(self) -> Credentials:
        env = os.environ if self._environ is None else self._environ
        return _credentials(env.get(self.prefix + "API_KEY"), env.get(self.prefix + "API_SECRET"))


class _FILETIME(ctypes.Structure):
    # Fixed-width DWORDs are necessary even when this declaration is imported
    # on non-Windows systems for offline testing.
    _fields_ = [("dwLowDateTime", ctypes.c_uint32), ("dwHighDateTime", ctypes.c_uint32)]


class _CREDENTIAL_ATTRIBUTEW(ctypes.Structure):
    _fields_ = [
        ("Keyword", ctypes.c_wchar_p),
        ("Flags", ctypes.c_uint32),
        ("ValueSize", ctypes.c_uint32),
        ("Value", ctypes.POINTER(ctypes.c_ubyte)),
    ]


class _CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", ctypes.c_uint32),
        ("Type", ctypes.c_uint32),
        ("TargetName", ctypes.c_wchar_p),
        ("Comment", ctypes.c_wchar_p),
        ("LastWritten", _FILETIME),
        ("CredentialBlobSize", ctypes.c_uint32),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", ctypes.c_uint32),
        ("AttributeCount", ctypes.c_uint32),
        ("Attributes", ctypes.POINTER(_CREDENTIAL_ATTRIBUTEW)),
        ("TargetAlias", ctypes.c_wchar_p),
        ("UserName", ctypes.c_wchar_p),
    ]


class WindowsCredentialStore:
    """Current-user native credential bytes shared by provider adapters.

    Callers own target names and payload validation. This small public interface
    also supports Library's NVD key without coupling this standalone SDK to the
    application or duplicating Win32 credential handling.
    """
    GENERIC = 1
    LOCAL_MACHINE = 2  # Persist for the current user's subsequent logon sessions.
    NOT_FOUND = 1168
    MAX_BLOB = 2560  # Windows CRED_MAX_CREDENTIAL_BLOB_SIZE.

    def __init__(self):
        if os.name != "nt":
            raise ConfigurationError("Windows Credential Manager is available only on Windows; use the environment provider here.")
        self._api = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
        self._api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(_CREDENTIALW))]
        self._api.CredReadW.restype = wintypes.BOOL
        self._api.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIALW), wintypes.DWORD]
        self._api.CredWriteW.restype = wintypes.BOOL
        self._api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        self._api.CredDeleteW.restype = wintypes.BOOL
        self._api.CredFree.argtypes = [ctypes.c_void_p]
        self._api.CredFree.restype = None

    def read(self, target: str) -> bytes:
        pointer = ctypes.POINTER(_CREDENTIALW)()
        if not self._api.CredReadW(target, self.GENERIC, 0, ctypes.byref(pointer)):
            if ctypes.get_last_error() == self.NOT_FOUND:
                raise ConfigurationError("No credentials were found for this profile. Run configure first.")
            raise ConfigurationError("Windows Credential Manager could not read this profile.")
        try:
            record = pointer.contents
            if not record.CredentialBlob or not 0 < record.CredentialBlobSize <= self.MAX_BLOB:
                raise ConfigurationError("The stored credential record is invalid.")
            return ctypes.string_at(record.CredentialBlob, record.CredentialBlobSize)
        finally:
            self._api.CredFree(pointer)

    def write(self, target: str, payload: bytes) -> None:
        if len(payload) > self.MAX_BLOB:
            raise ConfigurationError("Credentials exceed the Windows credential-store size limit.")
        buffer = (ctypes.c_ubyte * len(payload)).from_buffer_copy(payload)
        credential = _CREDENTIALW()
        credential.Type = self.GENERIC
        credential.TargetName = target
        credential.Comment = "Shadowserver Reports API credentials"
        credential.CredentialBlobSize = len(payload)
        credential.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
        credential.Persist = self.LOCAL_MACHINE
        credential.UserName = "Shadowserver Reports API"
        try:
            if not self._api.CredWriteW(ctypes.byref(credential), 0):
                raise ConfigurationError("Windows Credential Manager could not save this profile.")
        finally:
            ctypes.memset(buffer, 0, len(buffer))

    def delete(self, target: str) -> bool:
        if self._api.CredDeleteW(target, self.GENERIC, 0):
            return True
        if ctypes.get_last_error() == self.NOT_FOUND:
            return False
        raise ConfigurationError("Windows Credential Manager could not delete this profile.")


class WindowsCredentialProvider:
    """Current-user Windows Generic Credential Manager adapter.

    The OS store is opened lazily. `_store` is an injectable offline-test adapter
    with read/write/delete methods; it is not a production storage choice.
    """

    def __init__(self, profile: str = "default", *, _store=None):
        self.profile = validate_profile(profile)
        self.target = "ShadowserverReports/" + self.profile
        self._store = _store

    def _backend(self):
        if self._store is None:
            self._store = WindowsCredentialStore()
        return self._store

    def __call__(self) -> Credentials:
        payload = self._backend().read(self.target)
        try:
            record = json.loads(payload.decode("utf-8"))
            if not isinstance(record, dict) or record.get("version") != 1:
                raise ValueError
            return _credentials(record.get("api_key"), record.get("secret"))
        except (ValueError, TypeError, UnicodeError):
            raise ConfigurationError("The stored credential record is invalid.") from None

    def store(self, credentials: Credentials) -> None:
        checked = _credentials(credentials.api_key, credentials.secret)
        payload = json.dumps({"version": 1, "api_key": checked.api_key, "secret": checked.secret}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._backend().write(self.target, payload)

    def delete(self) -> bool:
        return self._backend().delete(self.target)
