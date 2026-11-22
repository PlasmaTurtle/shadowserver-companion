"""Native Chromium navigation, reported-host fallback and viewport readiness."""

from ipaddress import ip_address
import time
from urllib.parse import urlsplit, urlunsplit

from modules.tools.components.network_identity import root_domain
from .rendering import render_page
from .transport import web_url

NAVIGATION_SECONDS = 30
SCREENSHOT_RESERVE = 5


class WebsiteLoadError(ValueError):
    """The browser ran, but no acceptable target page loaded."""

    def __init__(self, message, metadata):
        super().__init__(message)
        self.metadata = metadata
        self.attempted_urls = tuple(metadata.get("attempted_urls", ()))


def extract_root_domain(value):
    host = urlsplit(value if "://" in value else "https://" + value).hostname or ""
    return root_domain(host)


def navigation_candidates(requested_url):
    """Try the reported address before changing scheme or using its main site."""
    requested = web_url(requested_url)
    parsed = urlsplit(requested)
    host = parsed.hostname or ""
    values = [
        (requested, False),
        (
            urlunsplit(parsed._replace(scheme="http" if parsed.scheme == "https" else "https")),
            False,
        ),
    ]
    try:
        ip_address(host)
        local = True
    except ValueError:
        local = "." not in host or host.endswith(".localhost")
    if not local:
        root = extract_root_domain(requested)
        values.extend(
            (f"{scheme}://{prefix}{root}/", True)
            for scheme in ("https", "http")
            for prefix in ("", "www.")
        )
    seen = set()
    for url, fallback in values:
        if url not in seen:
            seen.add(url)
            yield url, fallback


async def load_page(
    requested_url,
    *,
    open_page,
    deadline,
    cancel_event,
    metadata,
    classify,
    skip_urls=(),
    require_usable=False,
    page_check=None,
):
    skipped = set(skip_urls)
    for url, fallback in navigation_candidates(requested_url):
        if url in skipped:
            continue
        if cancel_event.is_set():
            raise ValueError("Website capture cancelled")
        if time.monotonic() >= deadline - SCREENSHOT_RESERVE:
            break
        attempt = {"url": url, "outcome": "load_failed", "final_url": "", "http_status": None}
        metadata["attempted_urls"].append(url)
        metadata["attempts"].append(attempt)
        metadata["redirects"] = [url]
        page = await open_page()
        try:
            attempt.update(
                await render_page(
                    page,
                    url,
                    deadline=min(
                        deadline - SCREENSHOT_RESERVE, time.monotonic() + NAVIGATION_SECONDS
                    ),
                    metadata=metadata,
                    classify=classify,
                )
            )
        except TimeoutError:
            if cancel_event.is_set():
                raise ValueError("Website capture cancelled")
            attempt["reason"] = "Website navigation timed out"
        page_text = attempt.pop("page_text", "")
        if len(metadata["redirects"]) > 1:
            attempt["redirects"] = list(metadata["redirects"])
        if page_check and attempt["outcome"] in {"captured", "login_required"}:
            reason = page_check(
                {**attempt, "capture_status": attempt["outcome"], "page_text": page_text}
            )
            if reason:
                attempt["reason"] = reason
                attempt["outcome"] = "rejected"
                continue
        if attempt["outcome"] in {"captured", "login_required"} or (
            not require_usable and attempt["outcome"] != "load_failed"
        ):
            metadata.update(
                final_url=attempt["final_url"],
                title=attempt.pop("title", ""),
                site_name=attempt.get("site_name", ""),
                heading=attempt.get("heading", ""),
                http_status=attempt["http_status"],
                capture_status=attempt["outcome"],
                fallback_used=fallback,
            )
            return page
    detail = (
        metadata["attempts"][-1].get("reason") if metadata["attempts"] else "Navigation timed out"
    )
    raise WebsiteLoadError(
        "Website could not be loaded: " + (detail or "No acceptable rendered page was available"),
        metadata,
    )
