"""Fixed public NVD destinations with bounded streams and a shared API budget."""

from datetime import datetime, timezone
import threading
import time
import math
from urllib.parse import urlencode

import requests
from urllib3.exceptions import ReadTimeoutError

from modules.tools.components.http import parse_retry_after

from .content_validation import validate_feed_media
from .control import CatalogCancelled as CatalogCancelled, cancelled as cancelled
from .control import remaining, transfer_deadline, wait
from .feed_http import open_response as _response_get

FEED_BASE = "https://nvd.nist.gov/feeds/json/cve/2.0/"
API_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
_rate_lock = threading.Lock()
_next_api = 0.0
TRANSFER_BUDGET = 900.0


class CatalogDeferred(ValueError):
    def __init__(self, message, retry_after=3600, *, server_requested=False, rate_limited=False):
        super().__init__(message)
        value = float(retry_after)
        self.retry_after = max(value, 60) if math.isfinite(value) else 3600
        self.server_requested = server_requested
        self.rate_limited = rate_limited


class CatalogTransient(CatalogDeferred):
    """A failed read-only request that can safely restart from byte zero."""

    def __init__(self, message):
        super().__init__(message, 60)


def retry_nvd(operation, *, cancel_event=None, deadline=None):
    """Retry one complete operation, never append a restarted response stream.

    Three attempts and 6/12-second waits are local recovery policy, not a
    server-provided retry deadline. Explicit Retry-After responses bypass this
    helper and are persisted by the catalog's existing deferral mechanism.
    """
    for attempt in range(3):
        cancelled(cancel_event)
        if deadline is not None:
            remaining(deadline, cancel_event)
        try:
            return operation()
        except CatalogTransient:
            if attempt == 2:
                raise
            delay = 6 * (attempt + 1)
            wait(delay, cancel_event=cancel_event, deadline=deadline)


def pace_nvd(cancel_event=None, *, authenticated=False, deadline=None):
    """All in-process NVD API callers share one conservative shared API gate."""
    global _next_api
    while True:
        cancelled(cancel_event)
        if deadline is not None:
            remaining(deadline, cancel_event)
        with _rate_lock:
            delay_until_slot = _next_api - time.monotonic()
            if delay_until_slot <= 0:
                _next_api = time.monotonic() + (2.0 if authenticated else 6.1)
                return
        wait(min(delay_until_slot, 0.25), cancel_event=cancel_event, deadline=deadline)


def explicit_retry_seconds(value):
    """Supply the current instant without adding provider fallback policy."""
    return parse_retry_after(value, now=datetime.now(timezone.utc))


def _network_failure(error, *, downloading=False):
    """Translate transport errors without exposing URLs, headers or credentials."""
    if isinstance(error, requests.exceptions.SSLError):
        return CatalogDeferred("NVD TLS verification failed. Existing records are retained.")
    # Requests wraps streaming urllib3 read timeouts in ConnectionError.
    wrapped = error.args[0] if error.args else None
    if isinstance(error, requests.Timeout) or isinstance(wrapped, ReadTimeoutError):
        return CatalogTransient("NVD request timed out. Completed records are retained.")
    if isinstance(error, (requests.ConnectionError, requests.exceptions.ChunkedEncodingError)):
        message = (
            "NVD download was interrupted. Completed records are retained."
            if downloading
            else "NVD could not be reached. Completed records are retained."
        )
        return CatalogTransient(message)
    return CatalogDeferred("NVD request failed. The existing catalog is available.")


class NVDTransport:
    def __init__(self, key_provider=None):
        self.key_provider = key_provider or (lambda: "")

    def has_key(self):
        return bool(self.key_provider())

    def open(self, url, *, api=False, cancel_event=None, deadline=None, limit=256 * 1024 * 1024):
        deadline = transfer_deadline(TRANSFER_BUDGET) if deadline is None else deadline
        cancelled(cancel_event)
        if not (url.startswith(FEED_BASE + "nvdcve-2.0-") or url.startswith(API_URL + "?")):
            raise ValueError("Unapproved catalog destination")
        key = self.key_provider() if api and url.startswith(API_URL + "?") else ""
        if api:
            pace_nvd(cancel_event, authenticated=bool(key), deadline=deadline)
        try:
            response = _response_get(
                url,
                stream=True,
                timeout=(10, 30),
                allow_redirects=False,
                budget=remaining(deadline, cancel_event),
                cancel_event=cancel_event,
                limit=limit,
                headers={
                    "User-Agent": "ShadowserverCompanion/CVECatalog",
                    "Accept-Encoding": "identity",
                    **({"apiKey": key} if key else {}),
                },
            )
        except requests.RequestException as error:
            raise _network_failure(error) from error
        if response.status_code in {429, 502, 503, 504}:
            status = response.status_code
            header = next(
                (v for k, v in response.headers.items() if k.lower() == "retry-after"), None
            )
            delay = explicit_retry_seconds(header)
            response.close()
            if delay is not None:
                raise CatalogDeferred(
                    f"NVD returned HTTP {status} with a Retry-After deadline. Completed records are retained.",
                    delay,
                    server_requested=True,
                    rate_limited=status == 429,
                )
            if status == 429:
                raise CatalogDeferred(
                    "NVD rate limit reached (HTTP 429). Eclipse will retry after a one-minute pause.",
                    60,
                    rate_limited=True,
                )
            raise CatalogTransient(
                f"NVD is temporarily unavailable (HTTP {status}). Completed records are retained."
            )
        if response.status_code in {401, 403} and key:
            response.close()
            raise CatalogDeferred(
                "NVD rejected authenticated access. Check the API key in Settings or retry later.",
                3600,
            )
        if response.status_code != 200:
            status = response.status_code
            response.close()
            raise CatalogDeferred(f"NVD returned HTTP {status}. The existing catalog is available.")
        return response

    def chunks(self, url, *, limit, api=False, cancel_event=None, deadline=None):
        deadline = transfer_deadline(TRANSFER_BUDGET) if deadline is None else deadline
        count = 0
        with self.open(
            url, api=api, cancel_event=cancel_event, deadline=deadline, limit=limit
        ) as response:
            validate_feed_media(
                response.headers, "json" if api else "gzip" if url.endswith(".gz") else "meta"
            )
            try:
                for chunk in response.iter_content(1024 * 128):
                    remaining(deadline, cancel_event)
                    count += len(chunk)
                    if count > limit:
                        raise ValueError("NVD download exceeded its size or time budget")
                    yield chunk
            except requests.RequestException as error:
                raise _network_failure(error, downloading=True) from error

    def bytes(self, url, *, limit, api=False, cancel_event=None):
        deadline = transfer_deadline(TRANSFER_BUDGET)
        return retry_nvd(
            lambda: b"".join(
                self.chunks(url, limit=limit, api=api, cancel_event=cancel_event, deadline=deadline)
            ),
            cancel_event=cancel_event,
            deadline=deadline,
        )

    def api_page(self, start, end, index, *, cancel_event=None):
        params = {
            "lastModStartDate": start,
            "lastModEndDate": end,
            "resultsPerPage": 2000,
            "startIndex": index,
        }
        url = API_URL + "?" + urlencode(params)
        return self.bytes(url, limit=64 * 1024 * 1024, api=True, cancel_event=cancel_event), url

    def bulk_page(self, index, *, cancel_event=None):
        if not self.has_key():
            raise ValueError("Add your NVD API key in Settings before downloading the CVE catalog.")
        url = API_URL + "?" + urlencode({"resultsPerPage": 2000, "startIndex": index})
        return self.bytes(url, limit=64 * 1024 * 1024, api=True, cancel_event=cancel_event), url
