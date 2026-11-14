"""Bounded HTTPS GETs with public DNS validation and IP-pinned verified TLS.

No HTTP library redirect, proxy, authentication or cookie policy is inherited.
Daemon work slots are bounded: an OS resolver or injected fetcher that never
returns cannot make the calling job hang or create unbounded abandoned threads.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import queue
import re
import socket
import ssl
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from .policy import DiscoveryError, public_address

ERROR_BODY_LIMIT = 64 * 1024
_HEADER_NAME = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+")
_FRAMING_HEADERS = {"content-length", "transfer-encoding", "content-encoding"}


def _validated_headers(items):
    headers = {}
    total = 0
    for name, value in items:
        if (
            not isinstance(name, str)
            or not isinstance(value, str)
            or not _HEADER_NAME.fullmatch(name)
            or any(ord(c) < 32 and c != "\t" or ord(c) == 127 for c in value)
        ):
            raise DiscoveryError("invalid_response", "The source returned invalid HTTP headers.")
        name, value = name.lower(), value.strip()
        total += len(name) + len(value)
        if total > 65536:
            raise DiscoveryError("invalid_response", "The source returned excessive HTTP headers.")
        if name in headers and name in (_FRAMING_HEADERS | {"content-type", "location"}):
            raise DiscoveryError("invalid_response", "The source returned ambiguous HTTP headers.")
        headers[name] = value
    _framing(headers)
    return headers


def _framing(headers):
    encoding = headers.get("content-encoding", "identity").lower()
    if encoding not in ("", "identity"):
        raise DiscoveryError(
            "unsupported_encoding", "The server ignored the request for an uncompressed response."
        )
    transfer = headers.get("transfer-encoding", "").lower()
    length = headers.get("content-length")
    if transfer and (transfer != "chunked" or length is not None):
        raise DiscoveryError(
            "invalid_response", "The response has unsupported or ambiguous framing."
        )
    if length is not None and (not re.fullmatch(r"[0-9]{1,20}", length)):
        raise DiscoveryError("invalid_response", "The response has invalid content length.")
    return transfer, int(length) if length is not None else None


@dataclass(frozen=True)
class FetchResponse:
    status_code: int
    headers: dict = field(default_factory=dict)
    body: bytes = b""
    truncated: bool = False


class _DaemonPool:
    def __init__(self, name, capacity=2):
        self.slots = threading.BoundedSemaphore(capacity)
        self.jobs = queue.Queue(maxsize=capacity)
        for index in range(capacity):
            threading.Thread(target=self._work, name=f"{name}-{index}", daemon=True).start()

    def _work(self):
        while True:
            future, function, args, kwargs = self.jobs.get()
            try:
                if future.set_running_or_notify_cancel():
                    try:
                        future.set_result(function(*args, **kwargs))
                    except BaseException as error:
                        future.set_exception(error)
            finally:
                self.slots.release()
                self.jobs.task_done()

    def submit(self, function, *args, **kwargs):
        if not self.slots.acquire(blocking=False):
            raise DiscoveryError(
                "transport_busy", "Contact retrieval capacity is occupied; try again later."
            )
        future = concurrent.futures.Future()
        self.jobs.put_nowait((future, function, args, kwargs))
        return future


_pool_lock = threading.Lock()
_pools = {}


def _pool(name):
    with _pool_lock:
        if name not in _pools:
            _pools[name] = _DaemonPool(name)
        return _pools[name]


def public_addresses(host):
    """Resolve once; reject the whole answer if any address is non-public."""
    try:
        answers = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError:
        raise DiscoveryError("dns_failed", "The approved hostname could not be resolved.") from None
    if not answers:
        raise DiscoveryError("dns_failed", "The approved hostname returned no addresses.")
    if any(not public_address(answer[4][0]) for answer in answers):
        raise DiscoveryError(
            "nonpublic_address",
            "The hostname resolved to a non-public address; retrieval was blocked.",
        )
    return answers


class _CombinedCancel:
    def __init__(self, parent=None):
        self.parent = parent
        self.local = threading.Event()

    def is_set(self):
        return self.local.is_set() or (self.parent is not None and self.parent.is_set())


def bounded_call(function, *, timeout, cancel_event=None, pool_name="contact-parse"):
    if cancel_event is not None and cancel_event.is_set():
        raise DiscoveryError("cancelled", "Contact discovery was cancelled.")
    cancel = _CombinedCancel(cancel_event)
    deadline = time.monotonic() + timeout
    capacity_deadline = min(deadline, time.monotonic() + 0.1)
    while True:
        if cancel.is_set():
            raise DiscoveryError("cancelled", "Contact discovery was cancelled.")
        try:
            future = _pool(pool_name).submit(function, cancel)
            break
        except DiscoveryError:
            if time.monotonic() >= capacity_deadline:
                raise
            time.sleep(min(0.005, max(0, capacity_deadline - time.monotonic())))
    try:
        while True:
            if cancel.is_set():
                raise DiscoveryError("cancelled", "Contact discovery was cancelled.")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise DiscoveryError(
                    "request_timeout", "The source exceeded its retrieval time budget."
                )
            try:
                return future.result(timeout=min(remaining, 0.05))
            except concurrent.futures.TimeoutError:
                if future.done():
                    raise DiscoveryError(
                        "request_timeout", "The source exceeded its retrieval time budget."
                    ) from None
    finally:
        cancel.local.set()
        future.cancel()


def bounded_fetch(fetcher, url, *, timeout, max_bytes, cancel_event=None):
    function = getattr(fetcher, "fetch", fetcher)
    response = bounded_call(
        lambda cancel: function(url, timeout=timeout, max_bytes=max_bytes, cancel_event=cancel),
        timeout=timeout,
        cancel_event=cancel_event,
        pool_name="contact-fetch",
    )
    if isinstance(response, dict):
        response = FetchResponse(
            **{
                k: response[k]
                for k in ("status_code", "headers", "body", "truncated")
                if k in response
            }
        )
    if (
        not isinstance(response, FetchResponse)
        or not isinstance(response.body, bytes)
        or type(response.status_code) is not int
        or not 200 <= response.status_code <= 599
        or not isinstance(response.headers, dict)
        or not isinstance(response.truncated, bool)
    ):
        raise DiscoveryError("invalid_response", "The source returned an invalid response.")
    headers = _validated_headers(response.headers.items())
    _, declared = _framing(headers)
    if declared is not None and (
        len(response.body) > declared or not response.truncated and len(response.body) != declared
    ):
        raise DiscoveryError(
            "invalid_response", "The source returned an incomplete or ambiguous body."
        )
    if response.status_code in {204, 205, 304} and response.body:
        raise DiscoveryError("invalid_response", "A bodyless HTTP response contained data.")
    response = FetchResponse(response.status_code, headers, response.body, response.truncated)
    # Error/redirect pages are inspected only up to a small transient prefix.
    # Their raw bodies never enter retained evidence. Enforce the same cap for
    # injected transports as for the production HTTP reader.
    if not 200 <= response.status_code < 300:
        max_bytes = min(max_bytes, ERROR_BODY_LIMIT)
    if len(response.body) > max_bytes:
        response = FetchResponse(
            response.status_code, response.headers, response.body[:max_bytes], True
        )
    return response


async def _read_body(reader, headers, limit):
    transfer, length = _framing(headers)
    body = bytearray()
    if transfer == "chunked":
        while True:
            line = await reader.readline()
            if len(line) > 128 or not line.endswith(b"\r\n"):
                raise DiscoveryError("invalid_response", "The response has invalid chunk framing.")
            size_token = line[:-2].split(b";", 1)[0]
            if not re.fullmatch(rb"[0-9a-fA-F]{1,16}", size_token):
                raise DiscoveryError("invalid_response", "The response has invalid chunk framing.")
            size = int(size_token, 16)
            if not size:
                trailer_bytes = 0
                for _ in range(33):
                    trailer = await reader.readline()
                    trailer_bytes += len(trailer)
                    if trailer_bytes > 8192 or not trailer.endswith(b"\r\n"):
                        break
                    if trailer == b"\r\n":
                        return bytes(body), False
                    if trailer[:1].isspace() or b":" not in trailer:
                        break
                    key, value = trailer[:-2].decode("iso-8859-1").split(":", 1)
                    _validated_headers([(key, value)])
                    if key.lower() in (_FRAMING_HEADERS | {"content-type", "location"}):
                        break
                raise DiscoveryError("invalid_response", "The response has invalid chunk trailers.")
            count = min(size, limit - len(body))
            body.extend(await reader.readexactly(count))
            if size > count:
                return bytes(body), True
            if await reader.readexactly(2) != b"\r\n":
                raise DiscoveryError("invalid_response", "The response has invalid chunk framing.")
    if length is not None:
        size = length
        return await reader.readexactly(min(size, limit)), size > limit
    while len(body) < limit:
        chunk = await reader.read(min(65536, limit - len(body)))
        if not chunk:
            return bytes(body), False
        body.extend(chunk)
    # No declared length: exactly at the cap is conservatively incomplete.
    return bytes(body), True


async def _request(url, max_bytes):
    parsed = urlsplit(url)
    host = parsed.hostname
    answers = await asyncio.shield(
        asyncio.wrap_future(_pool("contact-dns").submit(public_addresses, host))
    )
    family, socktype, proto, _, address = answers[0]
    raw = socket.socket(family, socktype, proto)
    raw.setblocking(False)
    writer = None
    try:
        await asyncio.get_running_loop().sock_connect(raw, address)
        # The connected socket cannot trigger another DNS lookup. The original
        # approved hostname remains the SNI name and certificate-check target.
        reader, writer = await asyncio.open_connection(
            sock=raw, ssl=ssl.create_default_context(), server_hostname=host, limit=65536
        )
        request = f"GET {parsed.path or '/'} HTTP/1.1\r\nHost: {host}\r\nUser-Agent: Shadowserver-Companion-ContactDiscovery/0.9\r\nAccept: text/html, text/plain;q=0.9, application/xhtml+xml;q=0.8\r\nAccept-Encoding: identity\r\nConnection: close\r\n\r\n"
        writer.write(request.encode("ascii"))
        await writer.drain()
        raw_headers = await reader.readuntil(b"\r\n\r\n")
        lines = raw_headers.decode("iso-8859-1").split("\r\n")
        parts = lines[0].split(" ", 2)
        if len(parts) < 2 or parts[0] not in ("HTTP/1.0", "HTTP/1.1") or not parts[1].isdigit():
            raise DiscoveryError("invalid_response", "The source returned invalid HTTP headers.")
        status = int(parts[1])
        if not 200 <= status <= 599:
            raise DiscoveryError(
                "invalid_response", "The source returned an unsupported HTTP status."
            )
        header_items = []
        for line in lines[1:]:
            if not line:
                continue
            if line[0].isspace() or ":" not in line:
                raise DiscoveryError(
                    "invalid_response", "The source returned invalid HTTP headers."
                )
            name, value = line.split(":", 1)
            header_items.append((name, value))
        headers = _validated_headers(header_items)
        if status in {204, 205, 304}:
            transfer, length = _framing(headers)
            if transfer or status != 304 and length not in (None, 0):
                raise DiscoveryError(
                    "invalid_response", "A bodyless HTTP response had invalid framing."
                )
            return FetchResponse(status, headers, b"", False)
        body_limit = max_bytes if 200 <= status < 300 else min(max_bytes, ERROR_BODY_LIMIT)
        body, truncated = await _read_body(reader, headers, body_limit)
        return FetchResponse(status, headers, body, truncated)
    finally:
        if writer is not None:
            writer.close()
            writer.transport.abort()
        raw.close()


async def _capture(url, timeout, max_bytes, cancel_event):
    async def cancellation():
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise DiscoveryError("cancelled", "Contact discovery was cancelled.")
            await asyncio.sleep(0.025)

    request = asyncio.create_task(_request(url, max_bytes))
    monitor = asyncio.create_task(cancellation())
    try:
        async with asyncio.timeout(timeout):
            done, _ = await asyncio.wait((request, monitor), return_when=asyncio.FIRST_COMPLETED)
            if monitor in done:
                await monitor
            return await request
    finally:
        request.cancel()
        monitor.cancel()
        await asyncio.gather(request, monitor, return_exceptions=True)


class PublicHTTPSFetcher:
    def fetch(self, url, *, timeout, max_bytes, cancel_event=None):
        try:
            return asyncio.run(_capture(url, timeout, max_bytes, cancel_event))
        except DiscoveryError:
            raise
        except ssl.SSLError:
            raise DiscoveryError(
                "tls_failed", "The source did not pass TLS certificate verification."
            ) from None
        except TimeoutError:
            raise DiscoveryError(
                "request_timeout", "The source exceeded its retrieval time budget."
            ) from None
        except (OSError, ValueError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            raise DiscoveryError(
                "network_failed", "The source could not be retrieved safely."
            ) from None
