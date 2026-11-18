"""Public-only, IP-pinned HTTP(S) for the isolated capture browser.

The browser itself has no direct network path. Each intercepted GET is acquired
here without cookies, authorization, inherited proxies or automatic redirects.
"""

import asyncio
import socket
import ssl
from urllib.parse import urlsplit, urlunsplit, quote
import zlib

from ..contact_discovery.policy import DiscoveryError, hostname, public_address
from ..contact_discovery.transport import _pool, _read_body, FetchResponse, bounded_call

MAX_RESOURCE = 4 * 1024 * 1024


def web_url(value):
    if (
        not isinstance(value, str)
        or len(value) > 4096
        or any(ord(c) < 33 for c in value)
        or "\\" in value
    ):
        raise ValueError("Invalid website URL")
    try:
        p = urlsplit(value)
        if p.scheme not in ("http", "https") or p.username is not None or p.password is not None:
            raise ValueError("Only public HTTP or HTTPS websites can be captured")
        port = p.port or (443 if p.scheme == "https" else 80)
        if port != (443 if p.scheme == "https" else 80):
            raise ValueError("Website capture uses standard HTTP and HTTPS ports")
        host = hostname(p.hostname or "")
    except (ValueError, DiscoveryError) as error:
        raise ValueError(str(error)) from None
    return urlunsplit(
        (
            p.scheme,
            host,
            quote(p.path or "/", safe="/%:@!$&'()*+,;=-._~"),
            quote(p.query, safe="%/?@:!$&'()*+,;=-._~"),
            "",
        )
    )


def resolve_public(host, port):
    answers = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not answers or any(not public_address(a[4][0]) for a in answers):
        raise ValueError("Website address is not public; request blocked")
    return answers


async def connect_public(answers):
    attempted = set()
    last_error = None
    for family, kind, proto, _, address in answers:
        identity = (family, address)
        if identity in attempted:
            continue
        attempted.add(identity)
        if len(attempted) > 8:
            break
        raw = socket.socket(family, kind, proto)
        raw.setblocking(False)
        try:
            await asyncio.wait_for(asyncio.get_running_loop().sock_connect(raw, address), 1.5)
            return raw
        except (OSError, TimeoutError) as error:
            last_error = error
            raw.close()
        except BaseException:
            raw.close()
            raise
    raise last_error or OSError("No public website endpoint was reachable")


async def _get(url, limit):
    p = urlsplit(web_url(url))
    port = 443 if p.scheme == "https" else 80
    answers = await asyncio.shield(
        asyncio.wrap_future(_pool("website-dns").submit(resolve_public, p.hostname, port))
    )
    # A valid public DNS answer can be unreachable from this workstation (often
    # IPv6). Try other validated addresses within the caller's overall deadline.
    raw = await connect_public(answers)
    writer = None
    try:
        options = (
            {"ssl": ssl.create_default_context(), "server_hostname": p.hostname}
            if p.scheme == "https"
            else {}
        )
        reader, writer = await asyncio.open_connection(sock=raw, limit=65536, **options)
        target = p.path + ("?" + p.query if p.query else "")
        message = f"GET {target} HTTP/1.1\r\nHost: {p.hostname}\r\nUser-Agent: Mozilla/5.0 ShadowserverCompanion/0.9 WebsiteCapture\r\nAccept: */*\r\nAccept-Encoding: gzip, deflate\r\nConnection: close\r\n\r\n"
        writer.write(message.encode("ascii"))
        await writer.drain()
        header = await reader.readuntil(b"\r\n\r\n")
        lines = header.decode("iso-8859-1").split("\r\n")
        first = lines.pop(0).split(" ", 2)
        if len(first) < 2 or first[0] not in ("HTTP/1.0", "HTTP/1.1") or not first[1].isdigit():
            raise ValueError("Invalid website response")
        status = int(first[1])
        if not 200 <= status <= 599:
            raise ValueError("Unsupported website response")
        headers = {}
        for line in lines:
            if not line:
                continue
            if line[0].isspace() or ":" not in line:
                raise ValueError("Invalid website headers")
            name, value = line.split(":", 1)
            name, value = name.lower().strip(), value.strip()
            if not name or any(not (c.isalnum() or c in "!#$%&'*+-.^_`|~") for c in name):
                raise ValueError("Invalid website header name")
            if name in headers and name in (
                "content-length",
                "transfer-encoding",
                "content-encoding",
                "location",
            ):
                raise ValueError("Ambiguous website headers")
            headers[name] = value
        encoding = headers.get("content-encoding", "identity").lower()
        framing = dict(headers, **{"content-encoding": "identity"})
        body, truncated = await _read_body(reader, framing, limit)
        if truncated:
            raise ValueError("Website resource exceeded its size limit")
        if encoding in ("gzip", "deflate"):
            decoder = zlib.decompressobj(31 if encoding == "gzip" else 15)
            body = decoder.decompress(body, limit + 1)
            if len(body) > limit or decoder.unconsumed_tail or not decoder.eof:
                raise ValueError(
                    "Website resource exceeded its decoded size limit or was incomplete"
                )
        elif encoding not in ("identity", ""):
            raise ValueError("Unsupported website compression")
        # Fetch supplies the decoded body and its framing. Never pass cookies,
        # authentication, downloads, refresh headers, or connection directives.
        allowed = {
            "content-type",
            "location",
            "content-security-policy",
            "x-content-type-options",
            "access-control-allow-origin",
            "access-control-allow-headers",
            "access-control-allow-methods",
            "cross-origin-resource-policy",
        }
        return FetchResponse(status, {k: v for k, v in headers.items() if k in allowed}, body)
    finally:
        if writer is not None:
            writer.close()
            writer.transport.abort()
        raw.close()


async def _timed(url, limit, timeout, cancel):
    task = asyncio.create_task(_get(url, limit))
    try:
        async with asyncio.timeout(timeout):
            while not task.done():
                if cancel.is_set():
                    raise ValueError("Website capture cancelled")
                await asyncio.wait((task,), timeout=0.025)
            return await task
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def fetch(url, *, timeout, cancel_event=None, max_bytes=MAX_RESOURCE):
    url = web_url(url)
    return bounded_call(
        lambda cancel: asyncio.run(_timed(url, max_bytes, timeout, cancel)),
        timeout=timeout,
        cancel_event=cancel_event,
        pool_name="website-fetch",
    )
