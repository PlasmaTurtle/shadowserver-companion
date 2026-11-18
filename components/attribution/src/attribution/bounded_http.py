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
import queue
import threading
import socket
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
