"""Fake native-provider decisions only: no malware test strings or live input."""

import ctypes
import hashlib
import json

import pytest

from workbench.aegis import antimalware as content_scan
from workbench import aegis
from workbench.contact_discovery import ContactDiscovery, FetchResponse
from test_contact_discovery_090 import FixtureFetcher, ROOT, SECURITY, html


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


def test_system_directory_loader_exact_abi_unicode_bytes_and_context_lifecycle(monkeypatch):
    provider, loads = install(monkeypatch)
    text = "Zoë — 🌘 contact fixture"
    result = content_scan.scan_contact_text(text)
    assert result == {
        "status": "allowed",
        "provider": "windows_amsi",
        "representation": "utf-16-le",
        "verdict": "clean",
    }
    assert loads == [("amsi.dll", {"winmode": 0x800, "use_last_error": True})]
    assert provider.AmsiInitialize.argtypes == [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p)]
    assert provider.AmsiInitialize.restype is ctypes.c_int32
    assert provider.AmsiScanBuffer.argtypes == [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_wchar_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint32),
    ]
    assert provider.AmsiScanBuffer.restype is ctypes.c_int32
    assert provider.AmsiUninitialize.argtypes == [ctypes.c_void_p]
    assert provider.AmsiUninitialize.restype is None
    scan = provider.events[1]
    assert scan[1] == text.encode("utf-16-le")
    assert scan[2] == len(text.encode("utf-16-le"))
    assert text not in scan[3]
    assert [e[0] for e in provider.events] == ["initialize", "scan", "close"]
    content_scan.scan_buffer(b"another inert resource")
    assert len(loads) == 1
    assert [e[0] for e in provider.events] == ["initialize", "scan", "close"] * 2


@pytest.mark.parametrize("result", [0, 1, 2, 16383, 20480, 32767])
def test_results_below_block_threshold_preserve_provider_distinction(monkeypatch, result):
    provider, _ = install(monkeypatch, result=result)
    receipt = content_scan.scan_buffer(b"inert fixture")
    assert receipt["status"] == "allowed"
    assert receipt["verdict"] == {0: "clean", 1: "not_detected"}.get(
        result, "below_block_threshold"
    )
    assert provider.events[-1] == ("close",)


@pytest.mark.parametrize(
    "result,verdict",
    [
        (16384, "administrator_policy"),
        (20479, "administrator_policy"),
        (32768, "detected"),
        (65535, "detected"),
    ],
)
def test_detected_and_administrator_blocked_content_never_proceeds(monkeypatch, result, verdict):
    provider, _ = install(monkeypatch, result=result)
    with pytest.raises(content_scan.ContentScanError) as caught:
        content_scan.scan_contact_text("inert fixture")
    assert caught.value.code == "content_scan_blocked"
    assert caught.value.receipt["status"] == "blocked"
    assert caught.value.receipt["verdict"] == verdict
    assert provider.events[-1] == ("close",)


@pytest.mark.parametrize(
    "kwargs,closed",
    [
        ({"initialize_status": 0x80004005}, False),
        ({"initialize_status": -2147467259}, False),
        ({"null_handle": True}, False),
        ({"scan_status": 0x80004005}, True),
        ({"error_stage": "initialize"}, False),
        ({"error_stage": "scan"}, True),
        ({"error_stage": "close"}, True),
    ],
)
def test_native_failures_fail_closed_and_valid_context_is_always_released(
    monkeypatch, kwargs, closed
):
    provider, _ = install(monkeypatch, **kwargs)
    with pytest.raises(content_scan.ContentScanError) as caught:
        content_scan.scan_contact_text("inert fixture")
    assert caught.value.code == "content_scan_unavailable"
    assert caught.value.receipt["status"] == "unavailable"
    assert "INERT_PRIVATE_TEXT" not in str(caught.value)
    assert (("close",) in provider.events) is closed
    if not closed:
        assert not any(e[0] == "scan" for e in provider.events)


def test_missing_system_provider_never_falls_back(monkeypatch):
    install(monkeypatch)

    def unavailable(*args, **kwargs):
        raise OSError("INERT_PRIVATE_TEXT")

    monkeypatch.setattr(ctypes, "WinDLL", unavailable)
    with pytest.raises(content_scan.ContentScanError) as caught:
        content_scan.scan_buffer(b"inert fixture")
    assert caught.value.code == "content_scan_unavailable"
    assert "INERT_PRIVATE_TEXT" not in str(caught.value)


def test_non_windows_and_empty_buffers_truthfully_report_no_scan(monkeypatch):
    monkeypatch.setattr(content_scan, "_is_windows", lambda: False)
    monkeypatch.setattr(content_scan, "_api", lambda: pytest.fail("No native API on this platform"))
    receipt = content_scan.scan_contact_text("inert fixture")
    assert receipt["status"] == "not_supported" and receipt["provider"] == "none"
    receipt = content_scan.scan_buffer(b"")
    assert receipt["status"] == "empty" and receipt["verdict"] == "empty_not_scanned"


def test_raw_buffer_scan_does_not_decode_or_stop_at_embedded_null(monkeypatch):
    provider, _ = install(monkeypatch)
    body = b"\x89PNG\x00inert binary fixture"
    assert content_scan.scan_buffer(body)["status"] == "allowed"
    assert provider.events[1][1] == body
    assert provider.events[1][2] == len(body)


@pytest.mark.parametrize(
    "result,status,code",
    [
        (32768, "blocked", "content_scan_blocked"),
        (16384, "blocked", "content_scan_blocked"),
        (0, "unavailable", "content_scan_unavailable"),
    ],
)
def test_engine_preserves_only_rejection_receipt_and_digest_before_parsing(
    monkeypatch, result, status, code
):
    install(monkeypatch, result=result, scan_status=0x80004005 if status == "unavailable" else 0)
    from workbench.contact_discovery import engine

    monkeypatch.setattr(
        engine, "parse_html", lambda *a, **k: pytest.fail("Blocked text must not reach parser")
    )
    page = "<p>Security team: security@example.org</p>"
    fetcher = FixtureFetcher({ROOT: html(page)})
    found = ContactDiscovery(fetcher=fetcher).discover("example.org")
    snapshot = found["snapshots"][0]
    assert snapshot["content_scan"]["status"] == status
    assert snapshot["sha256"] == hashlib.sha256(page.encode()).hexdigest()
    assert snapshot["derived_evidence"] is None and "body" not in snapshot
    assert not found["candidates"]
    assert any(issue["code"] == code for issue in found["issues"])
    assert fetcher.calls == [ROOT, SECURITY]
    assert "<p>" not in json.dumps(found)


def test_engine_does_not_scan_error_or_unsupported_bodies(monkeypatch):
    monkeypatch.setattr(
        aegis,
        "scan_text",
        lambda *_: pytest.fail("No parse or scan for rejected body"),
    )
    fetcher = FixtureFetcher(
        {
            ROOT: FetchResponse(200, {"content-type": "application/pdf"}, b"inert"),
            SECURITY: FetchResponse(500, {"content-type": "text/html"}, b"inert"),
        }
    )
    result = ContactDiscovery(fetcher=fetcher).discover("example.org")
    assert not result["candidates"]
    assert all("content_scan" not in s and "body" not in s for s in result["snapshots"])


def test_engine_scan_capacity_or_timeout_never_falls_back_to_parser(monkeypatch):
    from workbench.contact_discovery import engine
    from workbench.aegis.errors import SecurityExecutionError

    def bounded(*args, **kwargs):
        raise SecurityExecutionError("security_timeout", "Synthetic scan timeout")

    monkeypatch.setattr(content_scan, "bounded_security_call", bounded)
    monkeypatch.setattr(engine, "parse_html", lambda *a, **k: pytest.fail("No scan fallback"))
    result = ContactDiscovery(
        fetcher=FixtureFetcher({ROOT: html("<p>security@example.org</p>")})
    ).discover("example.org")
    assert not result["candidates"]
    assert result["snapshots"][0]["content_scan"] == {
        "status": "unavailable",
        "provider": "windows_amsi",
        "representation": "utf-16-le",
        "verdict": "scan_unavailable",
    }
    assert result["snapshots"][0]["retention_reason"] == "content_scan_unavailable"
    assert any(i["code"] == "content_scan_unavailable" for i in result["issues"])


def test_scan_helpers_never_write_files_or_start_external_processes(monkeypatch):
    import builtins
    import subprocess
    import tempfile
    from pathlib import Path

    install(monkeypatch)

    def forbidden(*args, **kwargs):
        pytest.fail("In-memory scanning must not write content or launch a process")

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", forbidden)
        patch.setattr(Path, "write_bytes", forbidden)
        patch.setattr(Path, "write_text", forbidden)
        patch.setattr(tempfile, "mkstemp", forbidden)
        patch.setattr(subprocess, "Popen", forbidden)
        assert content_scan.scan_contact_text("inert fixture")["status"] == "allowed"
