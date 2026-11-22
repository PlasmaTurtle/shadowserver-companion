"""Offline recovery checks for interrupted NVD requests and truthful backoff."""

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import threading

import pytest
import requests
from urllib3.exceptions import ReadTimeoutError

from modules.library.components.cve_catalog import transport


URL = transport.API_URL + "?startIndex=2000"
KEY = "inert-test-key-not-a-real-credential"


class Response:
    def __init__(self, status=200, *, headers=None, chunks=(b"complete",)):
        self.status_code = status
        self.headers = headers if headers is not None else {"Content-Type": "application/json"}
        self.parts = chunks
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self.closed = True

    def iter_content(self, size):
        for item in self.parts:
            if isinstance(item, BaseException):
                raise item
            yield item


@pytest.fixture
def network(monkeypatch):
    pending, calls, sleeps, paced = [], [], [], []

    def get(url, **kwargs):
        calls.append((url, kwargs))
        item = pending.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    monkeypatch.setattr(transport, "_response_get", get)
    monkeypatch.setattr(transport.time, "sleep", sleeps.append)
    monkeypatch.setattr(
        transport, "pace_nvd", lambda cancel_event=None, **kwargs: paced.append(kwargs)
    )
    return transport.NVDTransport(lambda: KEY), pending, calls, sleeps, paced


def test_timeout_retries_same_page_through_authenticated_rate_gate(network):
    client, pending, calls, sleeps, paced = network
    response = Response()
    pending.extend([requests.ReadTimeout("private transport details"), response])
    assert client.bytes(URL, limit=100, api=True) == b"complete"
    assert [url for url, _ in calls] == [URL, URL]
    assert sleeps == [6]
    assert len(paced) == 2 and all(item["authenticated"] for item in paced)
    assert paced[0]["deadline"] == paced[1]["deadline"]
    assert response.closed
    for url, options in calls:
        assert KEY not in url
        assert options["headers"]["apiKey"] == KEY
        assert options["allow_redirects"] is False
        assert options["timeout"] == (10, 30)


@pytest.mark.parametrize(
    "failure",
    [
        requests.ConnectionError("connection lost"),
        requests.exceptions.ChunkedEncodingError("truncated response"),
        requests.ConnectionError(ReadTimeoutError(None, URL, "read timed out")),
    ],
)
def test_stream_retry_discards_partial_bytes_and_restarts_size_accounting(network, failure):
    client, pending, calls, sleeps, _ = network
    interrupted = Response(chunks=(b"bad", failure))
    complete = Response(chunks=(b"good",))
    pending.extend([interrupted, complete])
    assert client.bytes(URL, limit=4, api=True) == b"good"
    assert len(calls) == 2
    assert sleeps == [6]
    assert interrupted.closed and complete.closed


@pytest.mark.parametrize("status", [502, 503, 504])
@pytest.mark.parametrize("header", [None, "invalid", "NaN", "-1", "1.5"])
def test_busy_response_without_valid_deadline_uses_bounded_local_recovery(network, status, header):
    client, pending, calls, sleeps, _ = network
    headers = {} if header is None else {"Retry-After": header}
    responses = [Response(status, headers=headers) for _ in range(3)]
    pending.extend(responses)
    with pytest.raises(transport.CatalogTransient) as error:
        client.bytes(URL, limit=100, api=True)
    assert len(calls) == 3
    assert sleeps == [6, 12]
    assert error.value.retry_after == 60
    assert error.value.server_requested is False
    assert f"HTTP {status}" in str(error.value)
    assert all(response.closed for response in responses)


@pytest.mark.parametrize("status", [429, 502, 503, 504])
def test_explicit_server_deadline_is_not_retried_inline(network, status):
    client, pending, calls, sleeps, _ = network
    response = Response(status, headers={"retry-after": "7200"})
    pending.append(response)
    with pytest.raises(transport.CatalogDeferred) as error:
        client.bytes(URL, limit=100, api=True)
    assert not isinstance(error.value, transport.CatalogTransient)
    assert error.value.server_requested is True
    assert error.value.rate_limited is (status == 429)
    assert error.value.retry_after == 7200
    assert len(calls) == 1 and sleeps == []
    assert response.closed


def test_retry_after_http_date_is_supported():
    deadline = datetime.now(timezone.utc) + timedelta(minutes=10)
    delay = transport.explicit_retry_seconds(format_datetime(deadline, usegmt=True))
    assert 598 <= delay <= 600


def test_retry_after_obsolete_asctime_date_means_utc():
    deadline = datetime.now(timezone.utc) + timedelta(minutes=10)
    value = f"{deadline:%a %b} {deadline.day:2d} {deadline:%H:%M:%S %Y}"
    delay = transport.explicit_retry_seconds(value)
    assert 598 <= delay <= 600


@pytest.mark.parametrize("value", [None, "", "NaN", "inf", "-1", "1.5", "bad date", "9" * 129])
def test_invalid_retry_after_is_not_treated_as_a_server_deadline(value):
    assert transport.explicit_retry_seconds(value) is None


@pytest.mark.parametrize("header", [None, "invalid"])
def test_rate_limit_without_deadline_is_reported_as_local_one_minute_pause(network, header):
    client, pending, calls, sleeps, _ = network
    response = Response(429, headers={} if header is None else {"Retry-After": header})
    pending.append(response)
    with pytest.raises(transport.CatalogDeferred) as error:
        client.bytes(URL, limit=100, api=True)
    assert "HTTP 429" in str(error.value)
    assert error.value.server_requested is False
    assert error.value.retry_after == 60
    assert error.value.rate_limited is True
    assert len(calls) == 1 and sleeps == []
    assert response.closed


@pytest.mark.parametrize(
    "failure,reason",
    [
        (requests.exceptions.SSLError("private TLS details"), "secure connection to NVD failed"),
        (requests.exceptions.InvalidURL("private URL"), "request failed"),
        (requests.exceptions.ContentDecodingError("invalid content encoding"), "request failed"),
    ],
)
def test_nontransient_transport_errors_do_not_retry_or_expose_details(network, failure, reason):
    client, pending, calls, sleeps, _ = network
    pending.append(failure)
    with pytest.raises(transport.CatalogDeferred) as error:
        client.bytes(URL, limit=100, api=True)
    assert not isinstance(error.value, transport.CatalogTransient)
    assert reason in str(error.value)
    assert "private" not in str(error.value)
    assert len(calls) == 1 and sleeps == []


@pytest.mark.parametrize("status", [302, 400, 401, 403, 404])
def test_authentication_redirect_and_permanent_http_errors_do_not_retry(network, status):
    client, pending, calls, sleeps, _ = network
    response = Response(status)
    pending.append(response)
    with pytest.raises(transport.CatalogDeferred) as error:
        client.bytes(URL, limit=100, api=True)
    assert not isinstance(error.value, transport.CatalogTransient)
    assert len(calls) == 1 and sleeps == []
    assert response.closed


@pytest.mark.parametrize(
    "headers,chunks,limit",
    [
        ({"Content-Type": "text/html"}, (b"not-json",), 100),
        ({"Content-Type": "application/json"}, (b"too large",), 3),
    ],
)
def test_content_boundaries_do_not_trigger_network_retries(network, headers, chunks, limit):
    client, pending, calls, sleeps, _ = network
    response = Response(headers=headers, chunks=chunks)
    pending.append(response)
    with pytest.raises(ValueError) as error:
        client.bytes(URL, limit=limit, api=True)
    assert not isinstance(error.value, transport.CatalogDeferred)
    assert len(calls) == 1 and sleeps == []
    assert response.closed


def test_exhausted_timeout_has_bounded_attempts_and_explicit_error(network):
    client, pending, calls, sleeps, _ = network
    pending.extend(requests.Timeout("private") for _ in range(3))
    with pytest.raises(transport.CatalogTransient, match="timed out") as error:
        client.bytes(URL, limit=100, api=True)
    assert len(calls) == 3 and sleeps == [6, 12]
    assert error.value.retry_after == 60
    assert error.value.server_requested is False
    assert "private" not in str(error.value)


def test_cancelled_operation_never_starts(network):
    client, _, calls, sleeps, _ = network
    event = threading.Event()
    event.set()
    with pytest.raises(transport.CatalogCancelled):
        client.bytes(URL, limit=100, api=True, cancel_event=event)
    assert calls == sleeps == []


def test_cancellation_during_backoff_prevents_next_attempt(network):
    client, pending, calls, sleeps, _ = network
    pending.append(requests.Timeout())

    class CancelOnWait:
        cancelled = False
        delays = []

        def is_set(self):
            return self.cancelled

        def wait(self, seconds):
            self.delays.append(seconds)
            self.cancelled = True
            return True

    event = CancelOnWait()
    with pytest.raises(transport.CatalogCancelled):
        client.bytes(URL, limit=100, api=True, cancel_event=event)
    assert len(calls) == 1
    assert event.delays == [6]
    assert sleeps == []


def test_feed_requests_still_never_send_api_key(network):
    client, pending, calls, _, _ = network
    pending.extend([requests.Timeout(), Response(headers={"Content-Type": "text/plain"})])
    assert client.bytes(transport.FEED_BASE + "nvdcve-2.0-2026.meta", limit=100) == b"complete"
    assert len(calls) == 2
    assert all("apiKey" not in options["headers"] for _, options in calls)
