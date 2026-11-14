"""Fixed public NVD destinations with bounded streams and a shared API budget."""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import threading
import time
import math
import re
from urllib.parse import urlencode

import requests
from urllib3.exceptions import ReadTimeoutError

from .content_validation import validate_feed_media

FEED_BASE = "https://nvd.nist.gov/feeds/json/cve/2.0/"
API_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
_rate_lock = threading.Lock()
_next_api = 0.0


class CatalogCancelled(ValueError):
    pass


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


def cancelled(event):
    if event is not None and event.is_set():
        raise CatalogCancelled("Catalog update cancelled")


def retry_nvd(operation, *, cancel_event=None):
    """Retry one complete operation, never append a restarted response stream.

    Three attempts and 6/12-second waits are local recovery policy, not a
    server-provided retry deadline. Explicit Retry-After responses bypass this
    helper and are persisted by the catalog's existing deferral mechanism.
    """
    for attempt in range(3):
        cancelled(cancel_event)
        try:
            return operation()
        except CatalogTransient:
            if attempt == 2:
                raise
            delay = 6 * (attempt + 1)
            if cancel_event is None:
                time.sleep(delay)
            else:
                cancel_event.wait(delay)
            cancelled(cancel_event)


def pace_nvd(cancel_event=None, *, authenticated=False):
    """All in-process NVD API callers share one conservative shared API gate."""
    global _next_api
    while True:
        cancelled(cancel_event)
        with _rate_lock:
            remaining = _next_api - time.monotonic()
            if remaining <= 0:
                _next_api = time.monotonic() + (2.0 if authenticated else 6.1)
                return
        delay = min(remaining, 0.25)
        if cancel_event is None:
            time.sleep(delay)
        else:
            cancel_event.wait(delay)


def retry_seconds(value):
    try:
        return max(60, float(value))
    except ValueError, TypeError:
        try:
            return max(
                60, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
            )
        except ValueError, TypeError, OverflowError:
            return 3600


def explicit_retry_seconds(value):
    """Return a valid HTTP Retry-After delay, or None when none was supplied."""
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        return None
    value = value.strip()
    try:
        if value.isascii() and value.isdecimal():
            delay = float(value)
        else:
            deadline = parsedate_to_datetime(value)
            if deadline.tzinfo is None:
                # HTTP's obsolete asctime form has no zone marker but denotes
                # GMT. Do not reinterpret arbitrary zone-less date strings.
                if not re.fullmatch(
                    r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) "
                    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) "
                    r"[ 0-9][0-9] [0-9]{2}:[0-9]{2}:[0-9]{2} [0-9]{4}",
                    value,
                ):
                    return None
                deadline = deadline.replace(tzinfo=timezone.utc)
            delay = (deadline - datetime.now(timezone.utc)).total_seconds()
        return max(0, delay) if math.isfinite(delay) else None
    except ValueError, TypeError, OverflowError:
        return None


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

    def open(self, url, *, api=False, cancel_event=None):
        cancelled(cancel_event)
        if not (url.startswith(FEED_BASE + "nvdcve-2.0-") or url.startswith(API_URL + "?")):
            raise ValueError("Unapproved catalog destination")
        key = self.key_provider() if api and url.startswith(API_URL + "?") else ""
        if api:
            pace_nvd(cancel_event, authenticated=bool(key))
        try:
            response = requests.get(
                url,
                stream=True,
                timeout=(10, 30),
                allow_redirects=False,
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

    def chunks(self, url, *, limit, api=False, cancel_event=None):
        started = time.monotonic()
        count = 0
        with self.open(url, api=api, cancel_event=cancel_event) as response:
            validate_feed_media(
                response.headers, "json" if api else "gzip" if url.endswith(".gz") else "meta"
            )
            try:
                for chunk in response.iter_content(1024 * 128):
                    cancelled(cancel_event)
                    count += len(chunk)
                    if count > limit or time.monotonic() - started > 900:
                        raise ValueError("NVD download exceeded its size or time budget")
                    yield chunk
            except requests.RequestException as error:
                raise _network_failure(error, downloading=True) from error

    def bytes(self, url, *, limit, api=False, cancel_event=None):
        return retry_nvd(
            lambda: b"".join(self.chunks(url, limit=limit, api=api, cancel_event=cancel_event)),
            cancel_event=cancel_event,
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
