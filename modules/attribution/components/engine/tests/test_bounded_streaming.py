"""Managed streaming interrupts network waits and always releases the response."""

import asyncio
import gzip
from threading import Event, Thread
from time import monotonic
import tracemalloc
import zlib

import httpx
import pytest

from attribution.bounded_http import CaptureCancelled, CaptureTimedOut, stream_response


class Body(httpx.AsyncByteStream):
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


@pytest.mark.parametrize("budget", [0, -1, float("nan"), float("inf")])
def test_streaming_requires_a_finite_total_budget_before_opening(budget):
    with pytest.raises(CaptureTimedOut):
        stream_response("https://example.invalid/feed", budget=budget)


@pytest.mark.parametrize("phase", ["headers", "body"])
@pytest.mark.parametrize("stop", ["cancel", "deadline"])
def test_stalled_headers_and_trickling_body_are_interrupted_and_closed(phase, stop):
    entered, cancellation = Event(), Event()
    header_closed = []

    class Trickle(Body):
        async def __aiter__(self):
            entered.set()
            while True:
                await asyncio.sleep(0.02)
                self.reads += 1
                yield b"x"

    body = Trickle(())

    async def handle(request):
        if phase == "headers":
            entered.set()
            try:
                await asyncio.sleep(10)
            finally:
                header_closed.append(True)
        return httpx.Response(200, stream=body)

    def cancel_when_pending():
        if entered.wait(2):
            cancellation.set()

    canceller = Thread(target=cancel_when_pending) if stop == "cancel" else None
    if canceller:
        canceller.start()
    started = monotonic()
    try:
        with pytest.raises(CaptureCancelled if stop == "cancel" else CaptureTimedOut):
            with stream_response(
                "https://example.invalid/feed",
                transport=httpx.MockTransport(handle),
                budget=1 if stop == "cancel" else 0.15,
                cancel_event=cancellation,
            ) as response:
                list(response.iter_content(128 * 1024))
    finally:
        if canceller:
            canceller.join(2)
    assert entered.is_set()
    assert monotonic() - started < 1
    assert header_closed if phase == "headers" else body.closed


def test_status_rejection_does_not_read_body_and_closes_response():
    body = Body([b"unwanted error document"])
    with stream_response(
        "https://example.invalid/feed",
        transport=httpx.MockTransport(lambda request: httpx.Response(503, stream=body)),
    ) as response:
        assert response.status_code == 503
        assert body.reads == 0
    assert body.closed and body.reads == 0


def test_explicit_transport_cannot_escape_through_proxy_routing():
    body = Body([b"offline fixture"])
    with stream_response(
        "https://example.invalid/feed",
        proxy="unsupported-proxy://must-not-be-used",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=body)),
    ) as response:
        assert b"".join(response.iter_content()) == b"offline fixture"
    assert body.closed


def test_streaming_is_lazy_and_early_consumer_exit_closes_it():
    body = Body([b"abcd"] * 1000)
    response = stream_response(
        "https://example.invalid/feed",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=body)),
    )
    with response:
        assert next(response.iter_content(2)) == b"ab"
        assert body.reads == 1
    assert body.closed and body.reads == 1
    response.close()  # Explicit closure is idempotent.


@pytest.mark.parametrize("decode", [False, True])
def test_http_encoding_is_explicit_and_does_not_change_raw_mode(decode):
    raw = b"original source records"
    wire = gzip.compress(raw)
    body = Body(wire[index : index + 2] for index in range(0, len(wire), 2))
    with stream_response(
        "https://example.invalid/feed",
        decode=decode,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, headers={"Content-Encoding": "gzip"}, stream=body)
        ),
    ) as response:
        assert b"".join(response.iter_content(3)) == (raw if decode else wire)
    assert body.closed


@pytest.mark.parametrize("encoding", ["gzip", "x-gzip", "deflate", "raw-deflate", "gzip-members"])
def test_valid_compressed_http_preserves_bytes_across_tiny_wire_chunks(encoding):
    raw = b"first retained record\nsecond retained record\n"
    if encoding in ("gzip", "x-gzip"):
        wire = gzip.compress(raw)
    elif encoding == "gzip-members":
        wire = gzip.compress(raw[:10]) + gzip.compress(raw[10:])
    elif encoding == "deflate":
        wire = zlib.compress(raw)
    else:
        compressor = zlib.compressobj(wbits=-15)
        wire = compressor.compress(raw) + compressor.flush()
    header = (
        "gzip"
        if encoding == "gzip-members"
        else "deflate"
        if encoding == "raw-deflate"
        else encoding
    )
    body = Body(wire[index : index + 1] for index in range(len(wire)))
    with stream_response(
        "https://example.invalid/feed",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, headers={"Content-Encoding": header}, stream=body)
        ),
    ) as response:
        assert b"".join(response.iter_content(3)) == raw
    assert body.closed


def test_raw_deflate_can_begin_with_a_valid_looking_zlib_header():
    raw = b"x" * 156
    wire = b"\x78\x9c\x00\x63\xff" + raw + b"\x01\x00\x00\xff\xff"
    assert zlib.decompress(wire, -15) == raw
    body = Body(wire[index : index + 1] for index in range(len(wire)))
    with stream_response(
        "https://example.invalid/feed",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, headers={"Content-Encoding": "deflate"}, stream=body
            )
        ),
    ) as response:
        assert b"".join(response.iter_content(3)) == raw
    assert body.closed


def test_http_expansion_is_rejected_without_allocating_the_expanded_body():
    wire = gzip.compress(b"x" * (4 * 1024 * 1024))
    assert len(wire) < 16 * 1024
    body = Body([wire])
    with stream_response(
        "https://example.invalid/feed",
        limit=16 * 1024,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, headers={"Content-Encoding": "gzip"}, stream=body)
        ),
    ) as response:
        tracemalloc.start()
        try:
            with pytest.raises(ValueError, match="size limit"):
                list(response.iter_content(4096))
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
    assert peak < 512 * 1024
    assert body.closed


def test_compressed_wire_bytes_have_a_limit_independent_of_expanded_size():
    body = Body([gzip.compress(b"")] * 20)
    with pytest.raises(ValueError, match="size limit"):
        with stream_response(
            "https://example.invalid/feed",
            limit=100,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, headers={"Content-Encoding": "gzip"}, stream=body
                )
            ),
        ) as response:
            list(response.iter_content(20))
    assert body.closed


@pytest.mark.parametrize(
    "encoding,wire",
    [
        ("gzip", gzip.compress(b"retained")[:-3]),
        ("gzip", gzip.compress(b"retained") + b"trailing garbage"),
        ("deflate", zlib.compress(b"retained") + b"trailing garbage"),
        ("zstd", b"unsupported"),
    ],
)
def test_unsupported_or_incomplete_http_encoding_fails_closed(encoding, wire):
    body = Body([wire])
    with pytest.raises(httpx.DecodingError):
        with stream_response(
            "https://example.invalid/feed",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, headers={"Content-Encoding": encoding}, stream=body
                )
            ),
        ) as response:
            list(response.iter_content(10))
    assert body.closed


def test_size_rejection_closes_response():
    body = Body([b"abcd", b"efgh"])
    with pytest.raises(ValueError, match="size limit"):
        with stream_response(
            "https://example.invalid/feed",
            limit=5,
            transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=body)),
        ) as response:
            chunks = response.iter_content(4)
            assert next(chunks) == b"abcd"
            next(chunks)
    assert body.closed


def test_consumer_failure_closes_response():
    body = Body([b"abcd"])
    with pytest.raises(RuntimeError, match="consumer stopped"):
        with stream_response(
            "https://example.invalid/feed",
            transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=body)),
        ):
            raise RuntimeError("consumer stopped")
    assert body.closed


def test_deadline_cannot_restart_between_stream_reads():
    body = Body([b"abcd", b"efgh"])
    with stream_response(
        "https://example.invalid/feed",
        budget=0.05,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=body)),
    ) as response:
        chunks = response.iter_content(4)
        assert next(chunks) == b"abcd"
        Event().wait(0.07)
        with pytest.raises(CaptureTimedOut):
            next(chunks)
    assert body.closed
