"""Synthetic Windows content-scan provider; never loads the host antimalware service.

The real scan buffer, encoding, deadline and fail-closed code still runs. Tests
can select blocked/unavailable outcomes through install() instead of depending
on the CI host's antimalware product or configuration.
"""

import ctypes

from workbench.aegis import antimalware as content_scan


class NativeFunction:
    def __init__(self, callback):
        self.callback = callback
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self.callback(*args)


class NativeProvider:
    def __init__(
        self, *, result=0, initialize_status=0, scan_status=0, null_handle=False, error_stage=None
    ):
        self.result = result
        self.initialize_status = initialize_status
        self.scan_status = scan_status
        self.null_handle = null_handle
        self.error_stage = error_stage
        self.events = []
        self.handle = 0x123456789 if ctypes.sizeof(ctypes.c_void_p) == 8 else 0x1234567
        self.AmsiInitialize = NativeFunction(self.initialize)
        self.AmsiScanBuffer = NativeFunction(self.scan)
        self.AmsiUninitialize = NativeFunction(self.close)

    def initialize(self, name, pointer):
        self.events.append(("initialize", name))
        if self.error_stage == "initialize":
            raise OSError("INERT_PRIVATE_TEXT")
        ctypes.cast(pointer, ctypes.POINTER(ctypes.c_void_p))[0] = (
            None if self.null_handle else self.handle
        )
        return self.initialize_status

    def scan(self, handle, pointer, length, name, session, result):
        assert handle.value == self.handle
        assert session is None
        self.events.append(("scan", ctypes.string_at(pointer, length), length, name))
        if self.error_stage == "scan":
            raise OSError("INERT_PRIVATE_TEXT")
        ctypes.cast(result, ctypes.POINTER(ctypes.c_uint32))[0] = self.result
        return self.scan_status

    def close(self, handle):
        assert handle.value == self.handle
        self.events.append(("close",))
        if self.error_stage == "close":
            raise OSError("INERT_PRIVATE_TEXT")


def install(monkeypatch, **kwargs):
    provider = NativeProvider(**kwargs)
    loads = []

    def load(name, **options):
        loads.append((name, options))
        return provider

    monkeypatch.setattr(content_scan, "_is_windows", lambda: True)
    monkeypatch.setattr(content_scan, "_dll", None)
    monkeypatch.setattr(ctypes, "WinDLL", load, raising=False)
    return provider, loads
