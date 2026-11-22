"""Cancellable HTTP capture with one deadline covering DNS, headers and body.

Each call owns and closes its event loop and client. Native OS resolution is
preserved through two process-wide daemon workers, with at most two outstanding
resolutions. A blocked OS resolver cannot be cancelled, but it cannot delay an
HTTP caller past its deadline or create additional resolver threads. URL/provider
policy belongs to the caller.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from math import isfinite
import queue
import threading
import socket
from time import monotonic
import zlib
from dataclasses import dataclass

import httpx


class CaptureCancelled(ValueError):
    pass


@dataclass(frozen=True)
class CapturedResponse:
    url: str
    status_code: int
    headers: httpx.Headers
    body: bytes

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def iter_content(self, chunk_size=65536):
        for offset in range(0, len(self.body), chunk_size):
            yield self.body[offset : offset + chunk_size]


class _NativeResolver:
    """Bound native getaddrinfo work without changing hosts/NRPT/proxy policy."""

    def __init__(self):
        self.slots = threading.BoundedSemaphore(2)
        self.jobs = queue.Queue(maxsize=2)
        for index in range(2):
            threading.Thread(target=self._run, name=f"source-resolver-{index}", daemon=True).start()

    def _run(self):
        while True:
            future, args, kwargs = self.jobs.get()
            try:
                if future.set_running_or_notify_cancel():
                    try:
                        future.set_result(socket.getaddrinfo(*args, **kwargs))
                    except Exception as error:
                        future.set_exception(error)
            finally:
                self.slots.release()
                self.jobs.task_done()

    def submit(self, args, kwargs):
        if not self.slots.acquire(blocking=False):
            raise socket.gaierror(socket.EAI_AGAIN, "Native resolver capacity is occupied")
        future = concurrent.futures.Future()
        self.jobs.put_nowait((future, args, kwargs))
        return future


_resolver = None
_resolver_lock = threading.Lock()


async def _getaddrinfo(*args, **kwargs):
    # Keep the native call alive after caller cancellation, holding its slot
    # until the OS returns. Never queue an unbounded series of abandoned jobs.
    global _resolver
    with _resolver_lock:
        if _resolver is None:
            _resolver = _NativeResolver()
    return await asyncio.shield(asyncio.wrap_future(_resolver.submit(args, kwargs)))


def _loop_factory():
    loop = asyncio.new_event_loop()
    loop.getaddrinfo = _getaddrinfo
    return loop


async def _capture(url, *, headers, timeout, limit, decode, transport=None):
    async with httpx.AsyncClient(
        transport=transport,
        timeout=timeout,
        follow_redirects=False,
        trust_env=transport is None,
        headers=headers,
        limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
    ) as client:
        async with client.stream("GET", url) as response:
            encoding = response.headers.get("content-encoding", "identity").lower()
            decoder = None
            if decode and encoding not in ("identity", ""):
                if encoding not in ("gzip", "deflate"):
                    raise ValueError("Unsupported source response compression")
                decoder = zlib.decompressobj(31 if encoding == "gzip" else 15)
            raw_size = 0
            body = bytearray()
            async for chunk in response.aiter_raw():
                raw_size += len(chunk)
                if raw_size > limit:
                    raise ValueError("Source response exceeds size limit")
                if decoder:
                    try:
                        chunk = decoder.decompress(chunk, limit - len(body) + 1)
                    except zlib.error as error:
                        raise ValueError("Invalid source response compression") from error
                    if decoder.unconsumed_tail:
                        raise ValueError("Expanded source response exceeds size limit")
                body.extend(chunk)
                if len(body) > limit:
                    raise ValueError("Expanded source response exceeds size limit")
            if decoder and (not decoder.eof or decoder.unused_data):
                raise ValueError("Incomplete or trailing compressed source response")
            return CapturedResponse(
                str(response.url), response.status_code, response.headers, bytes(body)
            )


async def _bounded(url, *, budget, cancel_event, **kwargs):
    async def cancelled():
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise CaptureCancelled("Source retrieval cancelled")
            await asyncio.sleep(0.05)

    if cancel_event is not None and cancel_event.is_set():
        raise CaptureCancelled("Source retrieval cancelled")
    request = asyncio.create_task(_capture(url, **kwargs))
    monitor = asyncio.create_task(cancelled())
    try:
        async with asyncio.timeout(budget):
            completed, _ = await asyncio.wait(
                (request, monitor), return_when=asyncio.FIRST_COMPLETED
            )
            if monitor in completed:
                await monitor
            return await request
    except TimeoutError as error:
        raise ValueError("Source response exceeded its time budget") from error
    finally:
        request.cancel()
        monitor.cancel()
        await asyncio.gather(request, monitor, return_exceptions=True)


def capture_response(
    url,
    *,
    budget=20.0,
    cancel_event=None,
    limit=2 * 1024 * 1024,
    headers=None,
    timeout=10.0,
    decode=True,
    transport=None,
):
    """Sync entrypoint for existing worker threads; never creates more threads."""
    if budget <= 0 or limit < 1:
        raise ValueError("Source capture budget exhausted")
    with asyncio.Runner(loop_factory=_loop_factory) as runner:
        return runner.run(
            _bounded(
                url,
                budget=budget,
                cancel_event=cancel_event,
                headers=headers or {},
                timeout=timeout,
                limit=limit,
                decode=decode,
                transport=transport,
            )
        )


class CaptureTimedOut(ValueError):
    """The total streaming deadline expired, rather than a single idle read."""


class _StreamingResponse:
    """Synchronous, explicitly closed view of one cancellable async response."""

    def __init__(self, url, *, budget, cancel_event, limit, decode, **options):
        if not isfinite(budget) or budget <= 0:
            raise CaptureTimedOut("Source streaming budget exhausted")
        if limit < 1:
            raise ValueError("Source streaming size limit must be positive")
        self._deadline = monotonic() + budget
        self._cancel_event = cancel_event
        self._limit = limit
        self._decode = decode
        self._runner = asyncio.Runner(loop_factory=_loop_factory)
        self._client = None
        self._response = None
        self._closed = False
        self._consumed = False

        async def open_response():
            self._client = httpx.AsyncClient(
                follow_redirects=False,
                limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
                **options,
            )
            request = self._client.build_request("GET", url)
            self._response = await self._client.send(request, stream=True)

        try:
            self._runner.run(self._wait(open_response))
            self.url = str(self._response.url)
            self.status_code = self._response.status_code
            self.headers = self._response.headers
        except BaseException:
            self.close()
            raise

    def _remaining(self):
        if self._cancel_event is not None and self._cancel_event.is_set():
            raise CaptureCancelled("Source retrieval cancelled")
        remaining = self._deadline - monotonic()
        if remaining <= 0:
            raise CaptureTimedOut("Source response exceeded its time budget")
        return remaining

    async def _wait(self, action):
        remaining = self._remaining()

        async def monitor_cancel():
            while True:
                if self._cancel_event is not None and self._cancel_event.is_set():
                    raise CaptureCancelled("Source retrieval cancelled")
                await asyncio.sleep(0.05)

        task = asyncio.create_task(action())
        monitor = asyncio.create_task(monitor_cancel())
        try:
            async with asyncio.timeout(remaining):
                completed, _ = await asyncio.wait(
                    (task, monitor), return_when=asyncio.FIRST_COMPLETED
                )
                if monitor in completed:
                    await monitor
                return await task
        except TimeoutError as error:
            raise CaptureTimedOut("Source response exceeded its time budget") from error
        finally:
            task.cancel()
            monitor.cancel()
            await asyncio.gather(task, monitor, return_exceptions=True)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
        return False

    def iter_content(self, chunk_size=65536):
        """Stream bounded output without collecting the complete response body."""
        if self._closed or self._consumed:
            raise ValueError("Source stream is closed or already consumed")
        if chunk_size < 1:
            raise ValueError("Source stream chunk size must be positive")
        self._consumed = True
        encoding = self.headers.get("content-encoding", "identity").strip().lower()
        if not self._decode:
            encoding = "identity"
        if encoding not in ("", "identity", "gzip", "x-gzip", "deflate"):
            raise httpx.DecodingError("Unsupported source response compression")
        compressed = encoding in ("gzip", "x-gzip", "deflate")
        gzip_encoded = encoding in ("gzip", "x-gzip")
        decoder = zlib.decompressobj(31 if gzip_encoded else 15) if compressed else None
        raw_fallback = encoding == "deflate"
        fallback_prefix = bytearray()
        # Bound wire reads as well as expansion. HTTPX's decoded iterator inflates
        # a raw chunk before applying its output chunk size, so cannot enforce
        # the expansion limit here.
        iterator = self._response.aiter_raw(min(chunk_size, 65536, self._limit + 1))

        async def next_chunk():
            return await iterator.__anext__()

        raw_count = count = 0
        while True:
            try:
                chunk = self._runner.run(self._wait(next_chunk))
            except StopAsyncIteration:
                if compressed and (decoder is None or not decoder.eof):
                    raise httpx.DecodingError("Incomplete source response compression")
                return
            raw_count += len(chunk)
            if raw_count > self._limit:
                raise ValueError("Source response exceeds size limit")
            if not compressed:
                yield chunk
                continue
            if raw_fallback:
                # Raw DEFLATE can have a valid-looking zlib header. Retain only
                # a bounded initial prefix for retrying that interpretation,
                # and stop retaining input as soon as wrapped output is proven.
                if len(fallback_prefix) + len(chunk) <= 65536:
                    fallback_prefix.extend(chunk)
                else:
                    raw_fallback = False
                    fallback_prefix.clear()
            while True:
                self._remaining()
                if decoder.eof:
                    if not gzip_encoded:
                        raise httpx.DecodingError("Trailing source response compression")
                    # Concatenated complete gzip members are valid. Garbage or
                    # an incomplete following member still fails validation.
                    decoder = zlib.decompressobj(31)
                maximum = min(chunk_size, self._limit - count + 1)
                try:
                    output = decoder.decompress(chunk, maximum)
                except zlib.error as error:
                    if raw_fallback:
                        decoder = zlib.decompressobj(-15)
                        chunk = bytes(fallback_prefix)
                        raw_fallback = False
                        fallback_prefix.clear()
                        continue
                    raise httpx.DecodingError("Invalid source response compression") from error
                count += len(output)
                if count > self._limit:
                    raise ValueError("Expanded source response exceeds size limit")
                if output:
                    raw_fallback = False
                    fallback_prefix.clear()
                    yield output
                chunk = decoder.unconsumed_tail or decoder.unused_data
                if chunk or len(output) == maximum and not decoder.eof:
                    continue
                break

    async def _close(self):
        try:
            if self._response is not None:
                await self._response.aclose()
        finally:
            if self._client is not None:
                await self._client.aclose()

    def close(self):
        if not self._closed:
            self._closed = True
            try:
                self._runner.run(self._close())
            finally:
                self._runner.close()


def stream_response(
    url,
    *,
    budget=20.0,
    cancel_event=None,
    limit=2 * 1024 * 1024,
    headers=None,
    timeout=10.0,
    decode=True,
    transport=None,
    verify=True,
    proxy=None,
    trust_env=True,
):
    """Open headers, then stream bytes under one cancellation/time/size budget.

    Use as a context manager or explicitly close it, including when rejecting
    status/headers without reading the body. The caller owns destination and
    response policy. Identity, gzip and deflate have bounded wire and expanded
    byte counts; unsupported or incomplete HTTP encodings are rejected. Set
    ``decode=False`` to preserve raw HTTP content. No transfer threads or full-body
    buffer are created.
    Like ``capture_response``, this synchronous API runs in a worker without an
    already-running asyncio loop and shares the bounded native resolver. An
    explicitly supplied transport owns all I/O, overriding proxy/environment
    routing so fixture transports cannot escape through a proxy mount.
    """
    return _StreamingResponse(
        url,
        budget=budget,
        cancel_event=cancel_event,
        limit=limit,
        decode=decode,
        headers=headers or {},
        timeout=timeout,
        transport=transport,
        verify=verify,
        proxy=proxy if transport is None else None,
        trust_env=trust_env if transport is None else False,
    )
