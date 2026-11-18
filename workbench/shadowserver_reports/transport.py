"""Signed, bounded access to the read-only Shadowserver Reports API.

The injectable backend has the same ``open(Request, timeout=seconds)`` shape as
urllib's opener. Its responses are context managers with status, headers and
read/read1 methods. The production backend verifies TLS and rejects redirects.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import socket
import ssl
from http.client import HTTPException
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

from .control import Operation
from .errors import (AuthenticationError, AuthorizationError, ConfigurationError,
                     ProtocolError, ShadowserverError, TransportError)
from .models import Credentials

API_ORIGIN = "https://transform.shadowserver.org/api2/"
ALLOWED_ENDPOINTS = frozenset({"test/ping", "key/info", "reports/subscribed",
    "reports/types", "reports/schema", "reports/list", "reports/query"})
RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _retry_delay(headers: Any, attempt: int) -> float:
    """Honor valid server guidance; waiting remains inside the operation budget."""
    value = headers.get("Retry-After") if headers is not None else None
    if value:
        try:
            seconds = float(value)
            if math.isfinite(seconds) and seconds >= 0:
                return seconds
        except (TypeError, ValueError):
            try:
                when = parsedate_to_datetime(str(value))
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
            except (TypeError, ValueError, OverflowError):
                pass
    return min(0.5 * 2 ** attempt, 8.0)


def _http_failure(status: int) -> ShadowserverError:
    if status == 401:
        return AuthenticationError("API authentication failed.")
    if status in (403, 412):
        return AuthorizationError("API request is outside the allowed scope or lacks required filters.")
    if 300 <= status < 400:
        return ProtocolError("API redirect rejected; credentials were not forwarded.")
    return TransportError(f"API request failed with HTTP status {status}.")


class SignedTransport:
    def __init__(self, provider: Callable[[], Credentials], *, backend=None,
                 request_timeout: float = 20, max_attempts: int = 3,
                 proxy: str | None = None, max_response_bytes: int = 16 * 1024 * 1024):
        if not callable(provider):
            raise ConfigurationError("A credential provider is required.")
        if not math.isfinite(request_timeout) or request_timeout <= 0:
            raise ConfigurationError("Request timeout must be positive and finite.")
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or not 1 <= max_attempts <= 5:
            raise ConfigurationError("API attempts must be between one and five.")
        if isinstance(max_response_bytes, bool) or not isinstance(max_response_bytes, int) or max_response_bytes < 1:
            raise ConfigurationError("Response size limit must be positive.")
        if proxy is not None:
            parsed = urlsplit(proxy)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                raise ConfigurationError("Proxy must be an HTTP or HTTPS URL.")
        self._provider = provider
        # Explicit proxy configuration avoids unexpectedly inheriting environment
        # proxies. TLS certificates always use the normal verified trust store.
        self._backend = backend if backend is not None else build_opener(
            ProxyHandler({"https": proxy} if proxy else {}),
            HTTPSHandler(context=ssl.create_default_context()), _NoRedirect())
        self.request_timeout = request_timeout
        self.max_attempts = max_attempts
        self.max_response_bytes = max_response_bytes
        self._closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self._closed = True
        close = getattr(self._backend, "close", None)
        if callable(close):
            close()

    def call(self, endpoint: str, payload: dict, *, operation: Operation | None = None):
        operation = operation or Operation()
        operation.check()
        if self._closed:
            raise ConfigurationError("API transport is closed.")
        if endpoint not in ALLOWED_ENDPOINTS:
            raise ConfigurationError("Only supported read-only API endpoints may be called.")
        if not isinstance(payload, dict) or "apikey" in payload:
            raise ConfigurationError("API payload must be an object without credentials.")
        try:
            credentials = self._provider()
        except ShadowserverError:
            raise
        except Exception:
            raise ConfigurationError("Credentials could not be loaded.") from None
        if not isinstance(credentials, Credentials) or not credentials.api_key or not credentials.secret:
            raise ConfigurationError("Both API key and API secret are required.")
        try:
            body = json.dumps({**payload, "apikey": credentials.api_key},
                              ensure_ascii=False, allow_nan=False,
                              separators=(",", ":")).encode("utf-8")
            signature = hmac.new(credentials.secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        except (TypeError, ValueError, UnicodeError):
            raise ConfigurationError("API payload or credentials cannot be encoded.") from None
        # Exactly these bytes are signed and transmitted. No serialization occurs
        # after signing, and no credentials ever appear in the request URL.
        for attempt in range(self.max_attempts):
            operation.request()
            request = Request(API_ORIGIN + endpoint, data=body, method="POST", headers={
                "Content-Type": "application/json; charset=utf-8",
                "Accept": "application/json", "HMAC2": signature,
                "User-Agent": "shadowserver-reports/0.1.0"})
            try:
                with self._backend.open(request, timeout=min(self.request_timeout, operation.remaining())) as response:
                    status = response.status
                    if status != 200:
                        if status in RETRYABLE_STATUS and attempt + 1 < self.max_attempts:
                            delay = _retry_delay(response.headers, attempt)
                        else:
                            raise _http_failure(status)
                    else:
                        raw = self._read(response, operation)
                        return self._decode(raw, endpoint)
            except HTTPError as error:
                status = error.code
                delay = _retry_delay(error.headers, attempt)
                error.close()
                if status not in RETRYABLE_STATUS or attempt + 1 == self.max_attempts:
                    raise _http_failure(status) from None
            except (URLError, OSError, socket.timeout, HTTPException):
                # urllib errors can include the full URL or proxy credentials;
                # never forward their text or exception chains to the caller.
                operation.check()
                if attempt + 1 == self.max_attempts:
                    raise TransportError("API connection failed after bounded attempts.") from None
                delay = _retry_delay(None, attempt)
            operation.wait(delay)
        raise TransportError("API request did not complete.")

    def _read(self, response, operation: Operation) -> bytes:
        result = bytearray()
        content_length = response.headers.get("Content-Length")
        expected_length = None
        if content_length is not None:
            try:
                if not str(content_length).isascii() or not str(content_length).isdigit():
                    raise ValueError
                expected_length = int(content_length)
            except (TypeError, ValueError):
                raise ProtocolError("API returned an invalid response length.") from None
            if expected_length > self.max_response_bytes:
                raise ProtocolError("API response exceeded the configured size limit.")
        reader = getattr(response, "read1", response.read)
        while True:
            operation.check()
            # urllib exposes the connected socket here. Refresh its timeout so
            # a slow stream cannot keep renewing a full per-request allowance.
            # The timeout API does not bound the operating system's DNS lookup.
            raw = getattr(getattr(response, "fp", None), "raw", None)
            sock = getattr(raw, "_sock", None)
            if sock is not None:
                sock.settimeout(min(self.request_timeout, operation.remaining()))
            chunk = reader(min(65536, self.max_response_bytes + 1 - len(result)))
            operation.check()
            if not chunk:
                break
            operation.consume_bytes(len(chunk))
            result.extend(chunk)
            if len(result) > self.max_response_bytes:
                raise ProtocolError("API response exceeded the configured size limit.")
        if expected_length is not None and len(result) != expected_length:
            # read1() can return EOF without raising IncompleteRead; never accept
            # a syntactically valid but truncated JSON document as success.
            raise HTTPException("Incomplete API response.")
        return bytes(result)

    @staticmethod
    def _decode(raw: bytes, endpoint: str):
        try:
            result = json.loads(raw.decode("utf-8"),
                                parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except (UnicodeError, ValueError, RecursionError):
            raise ProtocolError("API returned invalid JSON.") from None
        schema_field_map = (endpoint == "reports/schema" and isinstance(result, dict)
                            and all(isinstance(value, str) and value in {
                                "string", "integer", "int", "number", "float", "boolean", "bool",
                                "array", "object", "null", "date", "datetime", "timestamp"
                            } for value in result.values()))
        if not schema_field_map and isinstance(result, dict) and (
            "error" in result or "errors" in result or result.get("success") is False
            or str(result.get("status", "")).lower() in ("error", "failed", "failure")
        ):
            raise ProtocolError("API returned an error document with a successful HTTP status.")
        return result
