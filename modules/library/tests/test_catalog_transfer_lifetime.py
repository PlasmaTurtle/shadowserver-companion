"""Bulk transfers stop during network waits without publishing partial feeds."""

import asyncio
import base64
from datetime import datetime, timezone
import gzip
import hashlib
import ssl
from threading import Event, Thread
import time
from types import SimpleNamespace

import httpx
import pytest
import requests
from attribution.bounded_http import stream_response

from modules.library.components.cve_catalog import control, feed_http, risk, transport


EPSs = b"#model_version:v2026,score_date:2026-11-21\ncve,epss,percentile\nCVE-2026-0001,0.1,0.2\n"


class FeedBody(httpx.AsyncByteStream):
    def __init__(self, parts):
        self.parts = parts
        self.reads = 0
        self.closed = False

    async def __aiter__(self):
        for part in self.parts:
            self.reads += 1
            yield part

    async def aclose(self):
        self.closed = True


def install_http(monkeypatch, handler):
    def open_stream(url, **options):
        return stream_response(url, transport=httpx.MockTransport(handler), **options)

    monkeypatch.setattr(feed_http, "_stream_response", open_stream)


@pytest.mark.parametrize("provider", ["nvd", "epss"])
@pytest.mark.parametrize("phase", ["headers", "body"])
@pytest.mark.parametrize("stop", ["cancel", "deadline"])
def test_bulk_stop_interrupts_headers_and_body_and_removes_partial_files(
    monkeypatch, tmp_path, provider, phase, stop
):
    entered, cancellation = Event(), Event()
    header_closed = []
    # A valid gzip prefix large enough to reach Risk's staging file before the
    # stalled second read; cancellation must remove that partial file as well.
    compressed = gzip.compress(EPSs + b"CVE-2026-0001,0.1,0.2\n" * 10_000, compresslevel=0)

    class StalledBody(FeedBody):
        async def __aiter__(self):
            yield compressed[: 128 * 1024] if provider == "epss" else b"x" * (128 * 1024)
            entered.set()
            while True:
                await asyncio.sleep(0.02)
                yield b"x"

    body = StalledBody(())

    async def handle(request):
        if phase == "headers":
            entered.set()
            try:
                await asyncio.sleep(10)
            finally:
                header_closed.append(True)
        media = "application/gzip" if provider == "epss" else "text/plain"
        return httpx.Response(200, headers={"Content-Type": media}, stream=body)

    install_http(monkeypatch, handle)
    monkeypatch.setattr(
        transport if provider == "nvd" else risk, "TRANSFER_BUDGET", 1 if stop == "cancel" else 0.2
    )
    target = tmp_path / "feed"
    target.write_bytes(b"previous complete feed")

    def cancel_pending():
        if entered.wait(2):
            cancellation.set()

    canceller = Thread(target=cancel_pending) if stop == "cancel" else None
    if canceller:
        canceller.start()
    started = time.monotonic()
    try:
        with pytest.raises(
            control.CatalogCancelled if stop == "cancel" else control.CatalogDeadlineExceeded
        ):
            if provider == "nvd":
                transport.NVDTransport().bytes(
                    transport.FEED_BASE + "nvdcve-2.0-2026.meta",
                    limit=256 * 1024,
                    cancel_event=cancellation,
                )
            else:
                risk.RiskTransport().download("epss", target, cancel_event=cancellation)
    finally:
        if canceller:
            canceller.join(2)
    assert entered.is_set()
    assert time.monotonic() - started < 1
    assert header_closed if phase == "headers" else body.closed
    assert target.read_bytes() == b"previous complete feed"
    assert list(tmp_path.iterdir()) == [target]


def test_retry_wait_and_rate_gate_share_the_transfer_deadline(monkeypatch):
    calls = []

    def timed_out(*args, **kwargs):
        calls.append(True)
        raise requests.Timeout("inert failure")

    monkeypatch.setattr(transport, "TRANSFER_BUDGET", 0.06)
    monkeypatch.setattr(transport, "_response_get", timed_out)
    started = time.monotonic()
    with pytest.raises(control.CatalogDeadlineExceeded):
        transport.NVDTransport().bytes(transport.FEED_BASE + "nvdcve-2.0-2026.meta", limit=10)
    assert calls == [True]
    assert time.monotonic() - started < 0.5
    monkeypatch.setattr(transport, "_next_api", time.monotonic() + 10)
    with pytest.raises(control.CatalogDeadlineExceeded):
        transport.pace_nvd(deadline=control.transfer_deadline(0.04))


def test_risk_redirects_cannot_reset_total_budget(monkeypatch, tmp_path):
    calls = []
    bodies = []

    async def redirect(request):
        calls.append(str(request.url))
        await asyncio.sleep(0.04)
        body = FeedBody([])
        bodies.append(body)
        return httpx.Response(302, headers={"Location": risk.EPSS_FEED}, stream=body)

    install_http(monkeypatch, redirect)
    monkeypatch.setattr(risk, "TRANSFER_BUDGET", 0.1)
    with pytest.raises(control.CatalogDeadlineExceeded):
        risk.RiskTransport().download("epss", tmp_path / "feed")
    assert 1 <= len(calls) < 5
    assert all(body.closed for body in bodies)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "proxy_value", ["http://proxy.example.invalid:3128", "proxy.example.invalid:3128"]
)
@pytest.mark.parametrize("bypass", [False, True])
def test_existing_requests_ca_proxy_and_netrc_configuration_is_preserved(
    monkeypatch, tmp_path, bypass, proxy_value
):
    netrc = tmp_path / "netrc"
    netrc.write_text(
        "machine nvd.nist.gov login inert-user password inert-password\n", encoding="utf-8"
    )
    netrc.chmod(0o600)
    monkeypatch.setenv("NETRC", str(netrc))
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", requests.certs.where())
    monkeypatch.setenv("CURL_CA_BUNDLE", str(tmp_path / "unused-ca"))
    monkeypatch.setenv("SSL_CERT_FILE", str(tmp_path / "not-a-requests-setting"))
    monkeypatch.setenv("HTTPS_PROXY", proxy_value)
    monkeypatch.setenv("NO_PROXY", "nvd.nist.gov" if bypass else "")
    captured = {}

    def configured(url, **options):
        captured.update(options)
        return SimpleNamespace(url=url, status_code=200, headers={}, close=lambda: None)

    monkeypatch.setattr(feed_http, "_stream_response", configured)
    with feed_http.open_response(
        transport.FEED_BASE + "nvdcve-2.0-2026.meta",
        headers={"Accept-Encoding": "identity"},
        budget=1,
        limit=100,
    ):
        pass
    assert captured["trust_env"] is False
    assert captured["proxy"] == (None if bypass else "http://proxy.example.invalid:3128")
    assert captured["verify"].verify_mode == ssl.CERT_REQUIRED
    assert captured["verify"].check_hostname
    assert captured["verify"].options & ssl.OP_NO_TICKET
    assert captured["headers"]["Authorization"] == "Basic " + base64.b64encode(
        b"inert-user:inert-password"
    ).decode("ascii")
    assert captured["headers"]["Accept-Encoding"] == "identity"


@pytest.mark.parametrize("scheme", ["socks5", "socks5h"])
def test_unsupported_socks_proxy_is_rejected_without_exposing_credentials(monkeypatch, scheme):
    monkeypatch.setenv(
        "HTTPS_PROXY", scheme + "://inert-user:inert-password@proxy.example.invalid:1080"
    )
    monkeypatch.setenv("NO_PROXY", "")
    monkeypatch.setattr(
        feed_http,
        "_stream_response",
        lambda *args, **kwargs: pytest.fail("Unsupported proxy must not start network work"),
    )
    with pytest.raises(ValueError, match="SOCKS proxies are not supported") as failure:
        feed_http.open_response(
            transport.FEED_BASE + "nvdcve-2.0-2026.meta", headers={}, budget=1, limit=100
        )
    assert "inert-user" not in str(failure.value) and "inert-password" not in str(failure.value)
    assert "proxy.example.invalid" not in str(failure.value)


@pytest.mark.parametrize("verification", [True, False])
def test_tls_failure_stays_nonretryable_and_redacted(monkeypatch, verification):
    calls = []

    def fail(*args, **kwargs):
        calls.append(True)
        try:
            if verification:
                error = ssl.SSLCertVerificationError("inert private host detail")
                error.verify_code = 20
                raise error
            raise ssl.SSLError("inert private TLS detail")
        except ssl.SSLCertVerificationError as cause:
            raise httpx.ConnectError("inert private URL detail") from cause

    monkeypatch.setattr(feed_http, "_stream_response", fail)
    expected = "certificate code 20" if verification else "secure connection to NVD failed"
    with pytest.raises(transport.CatalogDeferred, match=expected) as failure:
        transport.NVDTransport().bytes(transport.FEED_BASE + "nvdcve-2.0-2026.meta", limit=100)
    assert not isinstance(failure.value, transport.CatalogTransient)
    assert calls == [True]
    assert "private" not in str(failure.value)


def test_request_configuration_cannot_renew_the_transfer_budget(monkeypatch):
    configure = feed_http.create_urllib3_context

    def slow_configuration():
        time.sleep(0.03)
        return configure()

    monkeypatch.setattr(feed_http, "create_urllib3_context", slow_configuration)
    monkeypatch.setattr(
        feed_http,
        "_stream_response",
        lambda *args, **kwargs: pytest.fail(
            "An expired transfer started network work after configuration"
        ),
    )
    with pytest.raises(control.CatalogDeadlineExceeded):
        feed_http.open_response(
            transport.FEED_BASE + "nvdcve-2.0-2026.meta", headers={}, budget=0.01, limit=100
        )


def test_retry_after_is_honored_before_error_body_is_read(monkeypatch):
    body = FeedBody([b"must not be consumed"])
    install_http(
        monkeypatch,
        lambda request: httpx.Response(503, headers={"Retry-After": "7200"}, stream=body),
    )
    with pytest.raises(transport.CatalogDeferred) as failure:
        transport.NVDTransport().bytes(transport.FEED_BASE + "nvdcve-2.0-2026.meta", limit=100)
    assert failure.value.retry_after == 7200 and failure.value.server_requested
    assert body.closed and body.reads == 0


@pytest.mark.parametrize(
    "header,expected,server_requested",
    [
        ("7200", 7200, True),
        ("0", 60, True),
        ("1.5", 3600, False),
        ("NaN", 3600, False),
        (None, 3600, False),
    ],
)
def test_risk_feed_distinguishes_server_guidance_from_local_fallback(
    monkeypatch, tmp_path, header, expected, server_requested
):
    body = FeedBody([b"must not be consumed"])
    headers = {} if header is None else {"retry-after": header}
    install_http(monkeypatch, lambda request: httpx.Response(503, headers=headers, stream=body))
    target = tmp_path / "feed"
    with pytest.raises(transport.CatalogDeferred) as failure:
        risk.RiskTransport().download("epss", target)
    assert failure.value.retry_after == expected
    assert failure.value.server_requested is server_requested
    assert body.closed and body.reads == 0
    assert not target.exists()


def test_nvd_prefix_rejection_closes_stream_even_while_exception_is_retained(monkeypatch, tmp_path):
    from modules.library.components.cve_catalog.catalog import Catalog

    wire = gzip.compress(b"<html>not an NVD feed</html>") + b"x" * 65536
    body = FeedBody([wire])
    install_http(
        monkeypatch,
        lambda request: httpx.Response(
            200, headers={"Content-Type": "application/gzip"}, stream=body
        ),
    )
    catalog = Catalog(tmp_path / "workspace", transport=transport.NVDTransport())
    stage = tmp_path / "stage"
    stage.mkdir()
    with pytest.raises(ValueError, match="JSON object") as retained:
        catalog._download(2026, {"gzSize": len(wire), "size": 100, "sha256": "0" * 64}, stage, None)
    assert retained.value.__traceback__ is not None
    assert body.closed, "Validation traceback retained an open network response"
    assert (stage / "nvdcve-2.0-2026.json.gz").read_bytes() == b""


def test_completed_feed_bytes_receipt_and_saved_catalog_survive_interrupted_update(
    monkeypatch, tmp_path
):
    raw = gzip.compress(EPSs)
    body = FeedBody(raw[index : index + 3] for index in range(0, len(raw), 3))
    install_http(
        monkeypatch,
        lambda request: httpx.Response(
            200, headers={"Content-Type": "application/gzip"}, stream=body
        ),
    )
    target = tmp_path / "feed"
    receipt = risk.RiskTransport().download("epss", target)
    assert target.read_bytes() == raw
    assert receipt["sha256"] == hashlib.sha256(raw).hexdigest()
    assert receipt["bytes"] == len(raw) and body.closed
    install_http(
        monkeypatch,
        lambda request: httpx.Response(
            200, headers={"Content-Type": "application/gzip"}, stream=FeedBody([raw])
        ),
    )
    store = risk.RiskStore(
        tmp_path / "workspace", clock=lambda: datetime(2026, 11, 21, tzinfo=timezone.utc)
    )
    store.sync("epss")
    before = store.status()["epss"], store.get("CVE-2026-0001")

    class Trickle(FeedBody):
        async def __aiter__(self):
            while True:
                await asyncio.sleep(0.02)
                yield b"x"

    unfinished = Trickle(())
    install_http(
        monkeypatch,
        lambda request: httpx.Response(
            200, headers={"Content-Type": "application/gzip"}, stream=unfinished
        ),
    )
    monkeypatch.setattr(risk, "TRANSFER_BUDGET", 0.1)
    with pytest.raises(control.CatalogDeadlineExceeded):
        store.sync("epss")
    assert (store.status()["epss"], store.get("CVE-2026-0001")) == before
    assert unfinished.closed
    assert not list(store.folder.glob("risk-download-*"))


def test_stop_finishes_risk_manager_worker_and_preserves_committed_records(monkeypatch, tmp_path):
    from modules.library.components.cve_catalog.risk_manager import RiskManager

    raw = gzip.compress(EPSs)
    install_http(
        monkeypatch,
        lambda request: httpx.Response(
            200, headers={"Content-Type": "application/gzip"}, stream=FeedBody([raw])
        ),
    )
    store = risk.RiskStore(
        tmp_path / "workspace", clock=lambda: datetime(2026, 11, 21, tzinfo=timezone.utc)
    )
    store.sync("epss")
    before = store.get("CVE-2026-0001")
    entered = Event()

    class Stalled(FeedBody):
        async def __aiter__(self):
            entered.set()
            while True:
                await asyncio.sleep(0.02)
                yield b"x"

    body = Stalled(())
    calls = []

    def handle(request):
        calls.append(str(request.url))
        return httpx.Response(200, headers={"Content-Type": "application/gzip"}, stream=body)

    install_http(monkeypatch, handle)
    monkeypatch.setattr(risk, "TRANSFER_BUDGET", 1)
    manager = RiskManager(store)
    try:
        manager.sync()
        assert entered.wait(2)
        started = time.monotonic()
        manager.cancel()
        manager.worker.join(1)
        assert not manager.busy()
        assert time.monotonic() - started < 1
        assert manager.status()["job"]["status"] == "cancelled"
        assert len(calls) == 1, "Cancellation must not start the next provider"
        assert body.closed
        assert store.get("CVE-2026-0001") == before
        assert not list(store.folder.glob("risk-download-*"))
    finally:
        manager.close()
