"""Controlled loopback checks for deadlines, cancellation, compression and backoff."""

import gzip
import json
import socket
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from attribution.bounded_http import capture_response, CaptureCancelled
from attribution import bounded_http
from attribution.http import retry_delay, MAX_RETRY_AFTER
from workbench.intelligence import service as sources
from workbench.intelligence import acquisition
from workbench.store import Store


@contextmanager
def local_source(mode):
    stop = threading.Event()
    requests_seen = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_):
            pass

        def do_GET(self):
            requests_seen.append(self.path)
            try:
                if mode == "headers":
                    self.wfile.write(b"HTTP/1.1 200 OK\r\nX-Slow: ")
                elif mode == "body":
                    self.send_response(200)
                    self.send_header("Content-Length", "65536")
                    self.end_headers()
                elif mode == "redirect":
                    self.send_response(302)
                    self.send_header("Location", "/must-not-follow")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                else:
                    content = gzip.compress(b"x" * 4096)
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(content)))
                    self.send_header("Content-Encoding", "gzip")
                    self.end_headers()
                    self.wfile.write(content)
                    return
                while not stop.wait(0.02):
                    self.wfile.write(b"x")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/source", requests_seen
    finally:
        stop.set()
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


@pytest.mark.parametrize("mode", ["headers", "body"])
def test_trickling_response_cannot_exceed_total_deadline(mode):
    with local_source(mode) as (url, seen):
        start = time.monotonic()
        with pytest.raises(ValueError, match="time budget"):
            # Include cold HTTP/TLS client initialization under a loaded full
            # suite. A 250 ms budget could expire before the server was reached,
            # exercising startup timing instead of the intended trickle path.
            capture_response(url, budget=1.0, timeout=2)
        assert time.monotonic() - start < 2.0
        assert seen == ["/source"]


def test_cancellation_interrupts_in_progress_body():
    cancel = threading.Event()
    with local_source("body") as (url, _):
        timer = threading.Timer(0.2, cancel.set)
        timer.start()
        start = time.monotonic()
        try:
            with pytest.raises(CaptureCancelled):
                capture_response(url, budget=5, timeout=2, cancel_event=cancel)
        finally:
            timer.cancel()
            timer.join()
        assert time.monotonic() - start < 1.25


def test_cancelled_request_does_not_contact_server():
    cancel = threading.Event()
    cancel.set()
    with local_source("body") as (url, seen):
        with pytest.raises(CaptureCancelled):
            capture_response(url, cancel_event=cancel)
        assert seen == []


def test_redirect_is_captured_and_never_followed():
    with local_source("redirect") as (url, seen):
        result = capture_response(url)
        assert result.status_code == 302
        assert seen == ["/source"]


def test_compressed_response_has_independent_expanded_size_cap():
    with local_source("gzip") as (url, _):
        with pytest.raises(ValueError, match="size limit"):
            capture_response(url, limit=128)


@pytest.mark.parametrize("value", ["315360000", "inf", "nan", "invalid", "-10"])
def test_retry_after_delta_is_bounded(value):
    assert 0 <= retry_delay(value) <= MAX_RETRY_AFTER


def test_retry_after_future_http_date_is_bounded():
    future = format_datetime(datetime.now(timezone.utc) + timedelta(days=3650))
    assert retry_delay(future) == MAX_RETRY_AFTER


def test_cve_backoff_clamped_but_original_header_preserved(tmp_path, monkeypatch):
    header = format_datetime(datetime.now(timezone.utc) + timedelta(days=3650))
    result = bounded_http.CapturedResponse(
        acquisition.KEV_URL, 429, httpx.Headers({"Retry-After": header}), b"{}"
    )
    monkeypatch.setattr(acquisition, "_response_get", lambda *a, **k: result)
    store = Store(tmp_path)
    _, source = acquisition._capture(
        store, acquisition.KEV_URL, "CISA KEV", "https://www.cisa.gov/"
    )
    until = json.loads(
        store.one("SELECT payload FROM cache WHERE key=?", ("source-backoff:CISA KEV",))["payload"]
    )["retry_at"]
    assert source["retry_after"] == header
    assert (
        0 <= (datetime.fromisoformat(until) - datetime.now(timezone.utc)).total_seconds() <= 86400
    )


@pytest.mark.parametrize(
    "url,publisher",
    [
        ("http://services.nvd.nist.gov/rest/json/cves/2.0?cveId=CVE-2025-12345", "NVD"),
        (acquisition.NVD_URL + "CVE-2025-12345&other=1", "NVD"),
        ("https://services.nvd.nist.gov.attacker.invalid/", "NVD"),
        ("https://127.0.0.1/", "CISA KEV"),
    ],
)
def test_provider_endpoint_policy_rejects_unexpected_destination(
    tmp_path, monkeypatch, url, publisher
):
    def forbidden(*a, **k):
        pytest.fail("Rejected provider URL reached transport")

    monkeypatch.setattr(acquisition, "_response_get", forbidden)
    with pytest.raises(ValueError, match="approved provider"):
        acquisition._capture(Store(tmp_path), url, publisher, "https://example.com")


def test_native_resolver_is_bounded_and_deadline_does_not_wait_for_it(monkeypatch):
    release = threading.Event()
    entered = threading.Event()
    real = socket.getaddrinfo

    def slow_native(host, *args, **kwargs):
        if host == b"blocked.example" or host == "blocked.example":
            entered.set()
            release.wait(3)
            raise socket.gaierror(socket.EAI_AGAIN, "Synthetic resolver stall")
        return real(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", slow_native)

    # Test the private request loop's resolver directly, avoiding proxy settings.
    async def lookup():
        import asyncio

        async with asyncio.timeout(0.1):
            return await bounded_http._getaddrinfo("blocked.example", 443)

    import asyncio

    try:
        start = time.monotonic()
        for _ in range(2):
            with asyncio.Runner(loop_factory=bounded_http._loop_factory) as runner:
                with pytest.raises(TimeoutError):
                    runner.run(lookup())
        assert entered.is_set()
        with asyncio.Runner(loop_factory=bounded_http._loop_factory) as runner:
            with pytest.raises(socket.gaierror, match="capacity"):
                runner.run(lookup())
        assert time.monotonic() - start < 1.0
        assert len([t for t in threading.enumerate() if t.name.startswith("source-resolver-")]) == 2
    finally:
        release.set()
        if bounded_http._resolver:
            bounded_http._resolver.jobs.join()


def test_proxy_error_details_do_not_reach_case_errors(tmp_path, monkeypatch):
    def fail(*a, **k):
        raise httpx.ProxyError("https://user:password@proxy.example")

    monkeypatch.setattr(acquisition, "_response_get", fail)
    with pytest.raises(ValueError) as error:
        acquisition._capture(Store(tmp_path), acquisition.KEV_URL, "CISA KEV", "")
    assert str(error.value) == "Source request failed: ProxyError"


def test_cve_capture_uses_transport_deadline_and_keeps_no_partial_record(tmp_path, monkeypatch):
    with local_source("headers") as (url, _):
        monkeypatch.setattr(acquisition, "CAPTURE_BUDGET", 0.2)
        monkeypatch.setattr(
            acquisition, "_response_get", lambda original, **kw: capture_response(url, **kw)
        )
        store = Store(tmp_path)
        start = time.monotonic()
        with pytest.raises(ValueError, match="time budget"):
            acquisition._capture(store, acquisition.KEV_URL, "CISA KEV", "https://www.cisa.gov/")
        assert time.monotonic() - start < 1.25
        assert not list((store.root / "evidence").rglob("*.json"))


def test_registry_production_transport_enforces_context_deadline(tmp_path, monkeypatch):
    from attribution import http
    from attribution.models import LookupFailure, Settings
    from attribution.store import EvidenceStore

    with local_source("body") as (url, _):
        monkeypatch.setattr(
            http, "capture_response", lambda original, **kw: capture_response(url, **kw)
        )
        store = EvidenceStore(tmp_path / "registry.sqlite3")
        client = http.RegistryHttpClient(store, Settings(interval=0, retries=0))
        start = time.monotonic()
        try:
            with pytest.raises(LookupFailure) as error:
                client._request(
                    "https://rdap.arin.net/registry/ip/8.8.8.8",
                    http.RequestContext(time.monotonic() + 0.2),
                    {"rdap.arin.net"},
                )
            assert error.value.reason == "operation_budget"
            assert time.monotonic() - start < 1.25
        finally:
            client.close()
            store.close()


def test_cve_cancellation_is_not_converted_into_failure_or_stale_success(tmp_path, monkeypatch):
    cancel = threading.Event()
    with local_source("body") as (url, _):
        monkeypatch.setattr(
            acquisition, "_response_get", lambda original, **kw: capture_response(url, **kw)
        )
        timer = threading.Timer(0.2, cancel.set)
        timer.start()
        try:
            with pytest.raises(sources.SourceCancelled):
                sources.cached_json(
                    Store(tmp_path), "kev", acquisition.KEV_URL, cancel_event=cancel
                )
        finally:
            timer.cancel()
            timer.join()
