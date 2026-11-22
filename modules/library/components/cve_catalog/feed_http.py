"""Requests configuration compatibility over cancellable streaming I/O.

Provider policy stays in NVDTransport/RiskTransport. Preparing a Requests session
retains existing proxy, netrc and CA-bundle behavior without sending a request.
Only the shared bounded transport owns sockets and their lifetime.
"""

from contextlib import contextmanager
from pathlib import Path
import ssl
from urllib.parse import urlsplit

import httpx
import requests
from urllib3.util import create_urllib3_context
from attribution.bounded_http import (
    CaptureCancelled,
    CaptureTimedOut,
    stream_response as _stream_response,
)

from .control import CatalogCancelled, CatalogDeadlineExceeded, remaining, transfer_deadline


def _tls_error(problem):
    seen = set()
    while problem is not None and id(problem) not in seen:
        if isinstance(problem, ssl.SSLError):
            return True
        seen.add(id(problem))
        problem = problem.__cause__ or problem.__context__
    return False


@contextmanager
def _errors():
    try:
        yield
    except CaptureCancelled as error:
        raise CatalogCancelled("Catalog update cancelled") from error
    except CaptureTimedOut as error:
        raise CatalogDeadlineExceeded(
            "Catalog download exceeded its total time budget. Completed records are retained."
        ) from error
    except (ssl.SSLError, httpx.RequestError) as error:
        if _tls_error(error):
            translated = requests.exceptions.SSLError
        elif isinstance(error, httpx.TimeoutException):
            translated = requests.Timeout
        elif isinstance(error, httpx.ProxyError):
            translated = requests.exceptions.ProxyError
        elif isinstance(error, httpx.RemoteProtocolError):
            translated = requests.exceptions.ChunkedEncodingError
        elif isinstance(error, httpx.DecodingError):
            translated = requests.exceptions.ContentDecodingError
        elif isinstance(error, (httpx.ConnectError, httpx.ReadError, httpx.WriteError)):
            translated = requests.ConnectionError
        else:
            translated = requests.RequestException
        # Provider layers deliberately expose only classified, non-secret errors.
        raise translated("Catalog HTTP transport failed") from error


class _Response:
    def __init__(self, response):
        self._response = response
        self.url = response.url
        self.status_code = response.status_code
        self.headers = response.headers

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
        return False

    def close(self):
        with _errors():
            self._response.close()

    def iter_content(self, size):
        with _errors():
            yield from self._response.iter_content(size)


def open_response(
    url,
    *,
    headers,
    budget,
    limit,
    cancel_event=None,
    timeout=(10, 30),
    stream=True,
    allow_redirects=False,
):
    if not stream or allow_redirects:
        raise ValueError("Catalog HTTP requires explicit streaming and redirect policy")
    deadline = transfer_deadline(budget)
    remaining(deadline, cancel_event)
    with requests.Session() as session:
        prepared = session.prepare_request(requests.Request("GET", url, headers=headers))
        settings = session.merge_environment_settings(prepared.url, {}, True, None, None)
    proxy = requests.utils.select_proxy(prepared.url, settings["proxies"])
    if proxy:
        try:
            proxy = requests.utils.prepend_scheme_if_needed(proxy, "http")
            scheme = urlsplit(proxy).scheme.lower()
        except (ValueError, requests.RequestException) as error:
            raise ValueError("Catalog proxy configuration is invalid") from error
        if scheme not in ("http", "https"):
            raise ValueError(
                "Catalog downloads require an HTTP or HTTPS proxy; SOCKS proxies are not supported."
            )
    verification = settings["verify"]
    if verification is True:
        verification = requests.certs.where()
    if not verification:
        raise ValueError("Catalog HTTP requires certificate verification")
    path = Path(verification)
    with _errors():
        # Keep Requests/urllib3's TLS defaults, including disabled session tickets,
        # while HTTPX owns cancellable I/O on the resulting verified context.
        context = create_urllib3_context()
        context.load_verify_locations(
            **({"capath": str(path)} if path.is_dir() else {"cafile": str(path)})
        )
        response = _stream_response(
            prepared.url,
            budget=remaining(deadline, cancel_event),
            limit=limit,
            cancel_event=cancel_event,
            headers=dict(prepared.headers),
            timeout=httpx.Timeout(timeout[1], connect=timeout[0]),
            verify=context,
            proxy=proxy,
            trust_env=False,
            decode=True,
        )
    return _Response(response)
