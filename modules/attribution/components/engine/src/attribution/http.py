"""Bounded, cached HTTPS retrieval with per-authority scheduling."""

from __future__ import annotations

import math
import re
import threading
import time
import zlib
from dataclasses import dataclass, field
from datetime import timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit

import httpx

from .models import LookupFailure, ResponseSnapshot, Settings, VERSION
from .store import EvidenceStore
from .bounded_http import CaptureCancelled, capture_response

REGISTRIES = {
    "rdap.arin.net": "ARIN",
    "rdap.db.ripe.net": "RIPE NCC",
    "rdap.apnic.net": "APNIC",
    "rdap.lacnic.net": "LACNIC",
    "rdap.afrinic.net": "AFRINIC",
}
SAVED_HEADERS = {
    "content-type",
    "content-encoding",
    "cache-control",
    "etag",
    "last-modified",
    "date",
    "expires",
    "age",
    "retry-after",
    "location",
}


def validate_url(url: str, allowed_hosts: set[str]):
    try:
        parts = urlsplit(url)
        if (
            parts.scheme != "https"
            or parts.hostname not in allowed_hosts
            or parts.port not in (None, 443)
            or parts.username is not None
            or parts.password is not None
            or parts.fragment
            or "\\" in url
            or any(ord(c) < 33 for c in url)
        ):
            raise ValueError("Untrusted destination")
    except ValueError as error:
        raise LookupFailure(
            "untrusted_destination",
            "RDAP destination is outside the trusted HTTPS services",
            status="incomplete",
        ) from error
    return parts


MAX_RETRY_AFTER = 86400.0


def retry_delay(value: str | None, default=30.0) -> float:
    if value:
        try:
            delay = float(value)
        except ValueError:
            try:
                date = parsedate_to_datetime(value)
                if date.tzinfo is None:
                    date = date.replace(tzinfo=timezone.utc)
                delay = date.timestamp() - time.time()
            except (ValueError, TypeError, OverflowError):
                return min(MAX_RETRY_AFTER, max(0.0, default))
        if math.isfinite(delay):
            return min(MAX_RETRY_AFTER, max(0.0, delay))
    return min(MAX_RETRY_AFTER, max(0.0, default))


def response_ttl(headers, fallback):
    control = headers.get("cache-control", "").lower()
    if any(k in control for k in ("no-store", "no-cache")):
        return 0.0
    match = re.search(r"(?:^|,)\s*max-age\s*=\s*\"?(\d+)", control)
    try:
        age = max(0.0, float(headers.get("age", "0")))
        if not math.isfinite(age):
            age = 0.0
        if match:
            return max(0.0, min(fallback, float(match.group(1)) - age))
        if headers.get("expires"):
            expiry = parsedate_to_datetime(headers["expires"]).timestamp()
            return max(0.0, min(fallback, expiry - time.time()))
    except (ValueError, TypeError, OverflowError):
        pass
    return fallback


@dataclass
class RequestContext:
    deadline: float
    network_requests: int = 0
    cache_hits: int = 0
    snapshot_ids: list[str] = field(default_factory=list)
    cancel_event: object = None

    def remember(self, snapshots):
        for snapshot in snapshots:
            if snapshot.snapshot_id not in self.snapshot_ids:
                self.snapshot_ids.append(snapshot.snapshot_id)

    def remaining(self):
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise LookupFailure("cancelled", "Attribution cancelled")
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise LookupFailure("operation_budget", "Lookup time budget exhausted")
        return remaining

    def wait(self, delay):
        """Use the caller's event for pacing/backoff without delaying shutdown."""
        self.remaining()
        if self.cancel_event is None:
            time.sleep(delay)
        else:
            self.cancel_event.wait(delay)
        self.remaining()

    def acquire(self, lock):
        """Keep ordinary locks and observe cancellation while another lookup runs."""
        while not lock.acquire(timeout=min(0.1, self.remaining())):
            pass


@dataclass(frozen=True)
class FetchResult:
    snapshots: tuple[ResponseSnapshot, ...]
    from_cache: bool

    @property
    def response(self):
        return self.snapshots[-1]


class RegistryHttpClient:
    def __init__(self, store: EvidenceStore, settings: Settings, *, transport=None):
        self.store, self.settings = store, settings
        self._transport = transport
        self.client = (
            httpx.Client(
                transport=transport,
                follow_redirects=False,
                trust_env=transport is None,
                timeout=settings.timeout,
                headers={
                    "Accept": "application/rdap+json, application/json",
                    "Accept-Encoding": "identity",
                    "User-Agent": f"AttributionModule/{VERSION}",
                },
                limits=httpx.Limits(max_connections=8, max_keepalive_connections=8),
            )
            if transport is not None
            else None
        )
        self._guard = threading.Lock()
        self._host_locks = {}
        self._next_request = {}
        # Fixed stripes bound memory while coalescing identical URL requests.
        self._url_locks = [threading.Lock() for _ in range(64)]

    def close(self):
        if self.client is not None:
            self.client.close()

    def _host_lock(self, host):
        with self._guard:
            return self._host_locks.setdefault(host, threading.Lock())

    def _request(self, url, context, allowed_hosts):
        host = validate_url(url, allowed_hosts).hostname
        lock = self._host_lock(host)
        context.acquire(lock)
        try:
            context.remaining()
            cooldown = self.store.cooldown(host)
            if cooldown > time.time():
                raise LookupFailure(
                    "rate_limited", "Registry cooldown is active", retry_at=cooldown
                )
            pause = max(0.0, self._next_request.get(host, 0) - time.monotonic())
            if pause >= context.remaining():
                raise LookupFailure("operation_budget", "Request interval exceeds lookup budget")
            if pause:
                context.wait(pause)
            context.network_requests += 1
            timeout = min(self.settings.timeout, context.remaining())
            if self._transport is None:
                try:
                    response_context = capture_response(
                        url,
                        timeout=timeout,
                        budget=context.remaining(),
                        cancel_event=context.cancel_event,
                        decode=False,
                        limit=self.settings.max_response_bytes,
                        headers={
                            "Accept": "application/rdap+json, application/json",
                            "Accept-Encoding": "identity",
                            "User-Agent": f"AttributionModule/{VERSION}",
                        },
                    )
                except CaptureCancelled as error:
                    raise LookupFailure("cancelled", "Attribution cancelled") from error
                except ValueError as error:
                    reason = (
                        "response_too_large" if "size limit" in str(error) else "operation_budget"
                    )
                    raise LookupFailure(reason, str(error), status="incomplete") from error
            else:
                # Explicit in-process fixture transport; production always uses
                # cancellable capture above, including headers and connect time.
                response_context = self.client.stream("GET", url, timeout=timeout)
            with response_context as response:
                raw = bytearray()
                chunks = response.iter_content() if self._transport is None else response.iter_raw()
                for chunk in chunks:
                    context.remaining()
                    raw.extend(chunk)
                    if len(raw) > self.settings.max_response_bytes:
                        raise LookupFailure(
                            "response_too_large",
                            "Registry response exceeds size limit",
                            status="incomplete",
                        )
                body = bytes(raw)
                encoding = response.headers.get("content-encoding", "identity").lower()
                if encoding != "identity":
                    if encoding not in ("gzip", "deflate"):
                        raise LookupFailure(
                            "content_encoding",
                            "Unsupported response compression",
                            status="incomplete",
                        )
                    try:
                        decoder = zlib.decompressobj(31 if encoding == "gzip" else 15)
                        body = decoder.decompress(body, self.settings.max_response_bytes + 1)
                        if len(body) > self.settings.max_response_bytes or decoder.unconsumed_tail:
                            raise LookupFailure(
                                "response_too_large",
                                "Expanded response exceeds size limit",
                                status="incomplete",
                            )
                        if not decoder.eof:
                            raise ValueError("Incomplete compressed response")
                    except (zlib.error, ValueError) as error:
                        raise LookupFailure(
                            "content_encoding", "Invalid compressed response", status="incomplete"
                        ) from error
                snapshot = ResponseSnapshot.create(
                    url,
                    str(response.url),
                    response.status_code,
                    {k: v for k, v in response.headers.items() if k in SAVED_HEADERS},
                    body,
                )
                if response.status_code in (429, 503) and (
                    response.status_code == 429 or "retry-after" in response.headers
                ):
                    until = time.time() + max(
                        self.settings.interval, retry_delay(response.headers.get("retry-after"))
                    )
                    self.store.set_cooldown(host, until)
                return snapshot
        except httpx.HTTPError as error:
            # Exception messages can contain proxy credentials; keep only the class.
            raise LookupFailure(
                "network_error", f"Registry request failed: {type(error).__name__}"
            ) from error
        finally:
            self._next_request[host] = time.monotonic() + self.settings.interval
            lock.release()

    def _retain(self, snapshot, validator, context):
        """Keep source bytes only after the expected JSON record passes validation.

        Redirects, gateway errors and rejected records retain a receipt and the
        received hash, never their untrusted response bodies. The stored-body
        checksum continues to describe exactly the bytes in the evidence store.
        """
        failure = None
        try:
            if snapshot.status_code == 200:
                self._validate(snapshot, validator)
            elif snapshot.status_code == 404 and snapshot.body:
                self._validate(snapshot, self._validate_not_found)
        except LookupFailure as error:
            failure = error
        if failure or snapshot.status_code not in (200, 404):
            snapshot = snapshot.without_body("rejected_response" if failure else "http_metadata_only")
        self.store.save_snapshot(snapshot)
        context.remember([snapshot])
        if failure:
            raise failure
        return snapshot

    def fetch(
        self, url, allowed_hosts, validator, context, *, ttl=None, refresh=False, offline=False
    ):
        validate_url(url, allowed_hosts)
        key = url
        lock = self._url_locks[hash(key) % len(self._url_locks)]
        context.acquire(lock)
        try:
            context.remaining()
            cached = None if refresh else self.store.cached(key)
            if cached:
                final = cached[-1]
                validate_url(final.source_url, allowed_hosts)
                if final.status_code == 200:
                    self._validate(final, validator)
                context.cache_hits += 1
                context.remember(cached)
                return FetchResult(tuple(cached), True)
            if offline:
                raise LookupFailure(
                    "cache_miss", "No fresh cached response is available in offline mode"
                )
            chain, seen, current = [], set(), url
            for redirect in range(self.settings.max_redirects + 1):
                if current in seen:
                    raise LookupFailure(
                        "redirect_loop", "Registry redirect loop", status="incomplete"
                    )
                seen.add(current)
                snapshot = None
                for attempt in range(self.settings.retries + 1):
                    try:
                        snapshot = self._request(current, context, allowed_hosts)
                        snapshot = self._retain(snapshot, validator, context)
                    except LookupFailure as error:
                        if error.reason != "network_error" or attempt == self.settings.retries:
                            raise
                    else:
                        chain.append(snapshot)
                        if snapshot.status_code == 429 or (
                            snapshot.status_code == 503 and "retry-after" in snapshot.headers
                        ):
                            raise LookupFailure(
                                "rate_limited",
                                "Registry asked the client to retry later",
                                retry_at=self.store.cooldown(urlsplit(current).hostname),
                            )
                        if snapshot.status_code not in (500, 502, 503, 504):
                            break
                        if attempt == self.settings.retries:
                            raise LookupFailure(
                                "service_unavailable",
                                f"Registry returned HTTP {snapshot.status_code}",
                            )
                    delay = min(2**attempt, 4)
                    if delay >= context.remaining():
                        raise LookupFailure("operation_budget", "Retry exceeds lookup budget")
                    context.wait(delay)
                if snapshot.status_code in (301, 302, 303, 307, 308):
                    location = snapshot.headers.get("location")
                    if not location:
                        raise LookupFailure(
                            "invalid_redirect", "Redirect has no Location", status="incomplete"
                        )
                    current = urljoin(current, location)
                    validate_url(current, allowed_hosts)
                    continue
                if snapshot.status_code not in (200, 404):
                    raise LookupFailure(
                        "http_error",
                        f"Registry returned HTTP {snapshot.status_code}",
                        status="incomplete",
                    )
                life = ttl if ttl is not None else self.settings.cache_ttl
                if snapshot.status_code == 404:
                    life = min(life, self.settings.negative_ttl)
                self.store.cache(key, chain, response_ttl(snapshot.headers, life))
                return FetchResult(tuple(chain), False)
            raise LookupFailure(
                "redirect_limit", "Registry redirect limit reached", status="incomplete"
            )
        finally:
            lock.release()

    @staticmethod
    def _validate_not_found(data):
        if data.get("errorCode") not in (None, 404):
            raise ValueError("404 response has a conflicting RDAP error code")

    @staticmethod
    def _validate(snapshot, validator):
        media_type = snapshot.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if media_type not in ("application/rdap+json", "application/json"):
            raise LookupFailure(
                "invalid_response", "Registry did not return JSON content", status="incomplete"
            )
        try:
            validator(snapshot.record())
        except (ValueError, KeyError, TypeError, RecursionError) as error:
            raise LookupFailure(
                "invalid_response", f"Invalid registration response: {error}", status="incomplete"
            ) from error
