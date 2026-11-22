"""Finite first-party contact discovery with source coverage and published routes."""

from __future__ import annotations

import hashlib
import math
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit

from .extract import contact_identity, parse_html, parse_security, review_url, score_link
from .policy import (
    DiscoveryError,
    approved_scope,
    approved_url,
    MAX_PAGE_BYTES,
    MAX_TOTAL_BYTES,
    MAX_REQUESTS,
    MAX_PAGE_REQUESTS,
    MAX_REDIRECT_REQUESTS,
    MAX_CANDIDATES,
    MAX_SECONDS,
    MAX_REQUEST_SECONDS,
)
from .transport import PublicHTTPSFetcher, bounded_call, bounded_fetch
from .validation import decode_response_text

REVISION = "contact-discovery-2026-11-21-v6"
PURPOSE_PRIORITY = {
    "security": 0,
    "it": 1,
    "product_support": 2,
    "management": 3,
    "general": 4,
    "other": 5,
    "privacy": 6,
    "compliance": 7,
    "hr": 8,
    "media": 9,
    "investor": 10,
    "physical_emergency": 11,
}
REFERRAL_PURPOSES = {"it", "product_support", "management"}
EXCLUDED_PURPOSES = {"privacy", "compliance", "hr", "media", "investor", "physical_emergency"}


@dataclass(frozen=True)
class DiscoveryLimits:
    max_requests: int = MAX_REQUESTS
    max_page_requests: int = MAX_PAGE_REQUESTS
    max_redirect_requests: int = MAX_REDIRECT_REQUESTS
    timeout: float = MAX_SECONDS
    request_timeout: float = MAX_REQUEST_SECONDS
    max_page_bytes: int = MAX_PAGE_BYTES
    max_total_bytes: int = MAX_TOTAL_BYTES
    max_candidates: int = MAX_CANDIDATES

    def __post_init__(self):
        caps = {
            "max_requests": MAX_REQUESTS,
            "max_page_requests": MAX_PAGE_REQUESTS,
            "max_redirect_requests": MAX_REDIRECT_REQUESTS,
            "timeout": MAX_SECONDS,
            "request_timeout": MAX_REQUEST_SECONDS,
            "max_page_bytes": MAX_PAGE_BYTES,
            "max_total_bytes": MAX_TOTAL_BYTES,
            "max_candidates": MAX_CANDIDATES,
        }
        for name, cap in caps.items():
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0 < value <= cap
            ):
                raise ValueError(f"{name} must be positive and at most {cap}.")
            if name not in {"timeout", "request_timeout"} and not isinstance(value, int):
                raise ValueError(f"{name} must be an integer.")


def _now():
    return datetime.now(timezone.utc).isoformat()


class ContactDiscovery:
    def __init__(self, *, fetcher=None, limits=None):
        self.fetcher = fetcher if fetcher is not None else PublicHTTPSFetcher()
        self.limits = limits if limits is not None else DiscoveryLimits()

    def discover(
        self, root_hostname, *, aliases=(), source_url=None, start_url=None, cancel_event=None
    ):
        limits = self.limits
        deadline = time.monotonic() + limits.timeout
        result = {
            "schema": 1,
            "discovery_revision": REVISION,
            "root_hostname": root_hostname if isinstance(root_hostname, str) else "",
            "aliases": [],
            "source_url": source_url or "",
            "start_url": start_url or "",
            "resolved_hostname": "",
            "status": "failed",
            "outcome": "incomplete",
            "started_at": _now(),
            "finished_at": None,
            "request_count": 0,
            "page_request_count": 0,
            "redirect_request_count": 0,
            "bytes_received": 0,
            "candidates": [],
            "snapshots": [],
            "issues": [],
            "coverage": [],
            "stop_reason": "",
            "next_step": "Review the unresolved source before choosing an outreach route.",
        }
        candidates, coverage, pending = {}, {}, {}
        ambiguous_identity, visited = set(), set()
        successful, interrupted = 0, False
        active_url = ""

        def issue(code, message, url=None):
            entry = {"code": code, "message": message}
            if url:
                entry["url"] = url
            if entry not in result["issues"]:
                result["issues"].append(entry)

        def record(url, state, message, *, next_step="", referrer_url="", **details):
            if url not in coverage and len(coverage) >= 64:
                issue(
                    "coverage_limit",
                    "Additional linked pages were omitted from the bounded coverage list.",
                )
                return
            item = coverage.setdefault(
                url,
                {
                    "url": url,
                    "checked_at": None,
                    "status_code": None,
                    "snapshot_id": "",
                    "candidate_count": 0,
                    "referrer_url": referrer_url,
                },
            )
            if referrer_url and not item["referrer_url"]:
                item["referrer_url"] = referrer_url
            if state == "unvisited" and item.get("state") not in {None, "unvisited"}:
                return
            item.update(state=state, message=message, next_step="", **details)

        def failure_details(url):
            if url not in visited:
                return {}
            snapshot = next(
                (item for item in reversed(result["snapshots"]) if item["url"] == url), None
            )
            if snapshot:
                return {
                    "checked_at": snapshot["retrieved_at"],
                    "status_code": snapshot["status_code"],
                    "snapshot_id": snapshot["id"],
                }
            return {"checked_at": _now()}

        def check(redirect=False):
            if cancel_event is not None and cancel_event.is_set():
                raise DiscoveryError("cancelled", "Contact discovery was cancelled.")
            if time.monotonic() >= deadline:
                raise DiscoveryError("deadline", "Contact discovery reached its total time budget.")
            if result["request_count"] >= limits.max_requests:
                raise DiscoveryError(
                    "request_limit", "The bounded total request limit was reached."
                )
            counter = "redirect_request_count" if redirect else "page_request_count"
            cap = limits.max_redirect_requests if redirect else limits.max_page_requests
            if result[counter] >= cap:
                raise DiscoveryError(
                    "redirect_limit" if redirect else "request_limit",
                    "The bounded redirect allowance was reached."
                    if redirect
                    else "The bounded page request limit was reached.",
                )
            if result["bytes_received"] >= limits.max_total_bytes:
                raise DiscoveryError(
                    "byte_limit", "The total source evidence byte limit was reached."
                )

        def add_target(url, priority, depth, referrer="", is_home=False):
            canonical = approved_url(url, hosts)
            if canonical in visited:
                return
            old = pending.get(canonical)
            if old is None or priority > old["priority"]:
                if old is None and len(pending) >= 32:
                    return
                pending[canonical] = {
                    "url": canonical,
                    "priority": priority,
                    "depth": depth,
                    "referrer": referrer,
                    "home": is_home,
                }
            record(
                canonical,
                "unvisited",
                "Published or planned source; not yet checked.",
                referrer_url=referrer,
                next_step="Open this page if a suitable route is still needed.",
            )

        def fallback_home(entry):
            if not entry["home"] or source_url or result["resolved_hostname"]:
                return
            for host in sorted(hosts - {urlsplit(entry["url"]).hostname}):
                add_target("https://" + host + "/", 1000, 0, is_home=True)

        def merge_candidate(item, snapshot, security_source):
            nonlocal interrupted
            source = {
                "snapshot_id": snapshot["id"],
                "url": snapshot["url"],
                "excerpt": item["excerpt"],
                "purpose": item["purpose"],
                "truncated": bool(snapshot["truncated"]),
            }
            metadata = (
                "route_type",
                "routing_label",
                "routing_options",
                "original_url",
                "external_destination",
                "requires_review",
                "review_reason",
                "partial_source",
            )
            for field in metadata:
                if field in item:
                    source[field] = item[field]
            identity = contact_identity(item["kind"], item["value"])
            if identity in candidates:
                existing = candidates[identity]
                if source not in existing["sources"]:
                    existing["sources"].append(source)
                purposes = set(existing.get("published_purposes", [existing["purpose"]])) | {
                    item["purpose"]
                }
                existing["published_purposes"] = sorted(purposes)
                specific = purposes - {"general", "other"}
                if len(specific) == 1:
                    existing["purpose"] = next(iter(specific))
                elif len(specific) > 1:
                    existing["purpose"] = (
                        "physical_emergency" if "physical_emergency" in specific else "other"
                    )
                    existing["purpose_conflict"] = True
                    existing["recommended_for_outreach"] = False
                    issue(
                        "contact_purpose_conflict",
                        "The same contact has different published purposes.",
                        snapshot["url"],
                    )
                if (
                    existing["name"]
                    and item["name"]
                    and existing["name"].casefold() != item["name"].casefold()
                ):
                    ambiguous_identity.add(identity)
                    existing["name"], existing["role"] = "", ""
                    issue(
                        "contact_identity_conflict",
                        "The same contact value appears with different published names.",
                        snapshot["url"],
                    )
                if identity not in ambiguous_identity:
                    for field in ("name", "role"):
                        if not existing[field] and item[field]:
                            existing[field] = item[field]
                for field in metadata:
                    if field in item and field not in existing:
                        existing[field] = item[field]
                if (
                    security_source
                    and item["purpose"] == "security"
                    and not existing.get("purpose_conflict")
                ):
                    existing["purpose"] = "security"
                existing["recommended_for_outreach"] = existing[
                    "purpose"
                ] not in EXCLUDED_PURPOSES and not existing.get("purpose_conflict")
                return
            if len(candidates) >= limits.max_candidates:
                interrupted = True
                issue(
                    "candidate_limit",
                    "Additional published contacts were omitted at the candidate limit; source evidence remains available.",
                    snapshot["url"],
                )
                return
            candidates[identity] = {
                k: item[k] for k in ("key", "kind", "value", "name", "role", "purpose")
            }
            candidates[identity].update({k: item[k] for k in metadata if k in item})
            candidates[identity].update(
                sources=[source],
                review_required=False,
                published_purposes=[item["purpose"]],
                recommended_for_outreach=item.get(
                    "recommended_for_outreach", item["purpose"] not in EXCLUDED_PURPOSES
                ),
            )
            if item.get("route_type") == "published_link" and item.get("external_destination"):
                record(
                    item["value"],
                    "unvisited",
                    "Company-published destination retained as a link; it was not fetched.",
                    referrer_url=snapshot["url"],
                    next_step="Open the published destination and check its reporting purpose and eligibility before using it.",
                )

        def retrieve(url):
            nonlocal successful, interrupted, active_url
            chain = set()
            security_source = urlsplit(url).path == "/.well-known/security.txt"
            redirect = False
            while True:
                url = approved_url(url, hosts)
                if url in chain:
                    raise DiscoveryError(
                        "redirect_loop", "The source has a redirect loop; retrieval stopped."
                    )
                # A duplicate must not consume a page slot or trigger a false budget stop.
                if url in visited:
                    return None, url
                active_url = url
                check(redirect)
                chain.add(url)
                visited.add(url)
                result["request_count"] += 1
                result["redirect_request_count" if redirect else "page_request_count"] += 1
                response = bounded_fetch(
                    self.fetcher,
                    url,
                    timeout=min(limits.request_timeout, deadline - time.monotonic()),
                    max_bytes=min(
                        limits.max_page_bytes, limits.max_total_bytes - result["bytes_received"]
                    ),
                    cancel_event=cancel_event,
                )
                headers = {str(k).lower(): str(v) for k, v in response.headers.items()}
                content_type = headers.get("content-type", "").lower()
                snapshot = {
                    "id": uuid.uuid4().hex,
                    "url": url,
                    "retrieved_at": _now(),
                    "status_code": response.status_code,
                    "content_type": content_type,
                    "title": "",
                    "sha256": hashlib.sha256(response.body).hexdigest(),
                    "truncated": response.truncated,
                    "hash_scope": "captured_prefix" if response.truncated else "captured_body",
                    "captured_bytes": len(response.body),
                    "derived_evidence": None,
                    "retention_reason": "not_parsed",
                }
                result["bytes_received"] += len(response.body)
                result["snapshots"].append(snapshot)
                details = {
                    "checked_at": snapshot["retrieved_at"],
                    "status_code": response.status_code,
                    "snapshot_id": snapshot["id"],
                }
                if response.status_code in {301, 302, 303, 307, 308}:
                    snapshot["retention_reason"] = "redirect_metadata_only"
                    location = headers.get("location", "")
                    if not location:
                        raise DiscoveryError(
                            "redirect_invalid", "The source redirect has no destination."
                        )
                    target = urljoin(url, location)
                    try:
                        snapshot["redirect_url"] = review_url(target)
                        details["redirect_url"] = snapshot["redirect_url"]
                    except DiscoveryError, ValueError:
                        pass
                    try:
                        target = approved_url(target, hosts)
                    except DiscoveryError as error:
                        record(
                            url,
                            "blocked",
                            "The redirect left the permitted company scope or used an unsupported URL.",
                            next_step="Review the published redirect destination manually; it was not followed.",
                            **details,
                        )
                        raise DiscoveryError("redirect_" + error.code, error.args[0]) from None
                    record(
                        url, "redirected", "Redirected within the company apex/www pair.", **details
                    )
                    record(
                        target,
                        "unvisited",
                        "Redirect destination not yet checked.",
                        referrer_url=url,
                    )
                    url, redirect = target, True
                    continue
                if response.status_code in {404, 410}:
                    snapshot["retention_reason"] = "http_error_metadata_only"
                    record(
                        url,
                        "not_found",
                        f"The exact URL returned HTTP {response.status_code}; other pages were not ruled out.",
                        **details,
                    )
                    return None, url
                if not 200 <= response.status_code < 300:
                    snapshot["retention_reason"] = "http_error_metadata_only"
                    record(
                        url,
                        "blocked" if response.status_code in {401, 403, 429} else "unreadable",
                        f"The page returned HTTP {response.status_code} and could not be checked.",
                        next_step="Open this source in your browser if needed. No alternate identity or block bypass was attempted.",
                        **details,
                    )
                    raise DiscoveryError(
                        "http_status",
                        f"The source returned HTTP {response.status_code}; no authentication or bypass was attempted.",
                    )
                successful += 1
                if security_source and response.truncated:
                    interrupted = True
                    code = "page_truncated"
                    message = "An incomplete security.txt cannot establish a contact's validity."
                    snapshot["retention_reason"] = "incomplete_security_metadata_only"
                    issue(code, message, url)
                    record(
                        url,
                        "incomplete" if response.truncated else "unreadable",
                        message,
                        next_step="Review the exact source in a browser; no contact absence was established.",
                        **details,
                    )
                    return None, url
                try:
                    text = decode_response_text(
                        response.body,
                        content_type,
                        security_source=security_source,
                        partial=response.truncated,
                    )
                except DiscoveryError as error:
                    snapshot["retention_reason"] = error.code
                    raise
                # The shared security module owns bounded native execution.
                from modules.workspace.components.aegis import ContentScanError, scan_text

                try:
                    snapshot["content_scan"] = scan_text(
                        text,
                        context="contact-response",
                        timeout=max(0.001, deadline - time.monotonic()),
                        cancel_event=cancel_event,
                    )
                except ContentScanError as error:
                    snapshot["content_scan"] = error.receipt
                    snapshot["retention_reason"] = error.code
                    if cancel_event is not None and cancel_event.is_set():
                        raise DiscoveryError(
                            "cancelled", "Contact discovery was cancelled."
                        ) from None
                    raise DiscoveryError(error.code, str(error)) from None
                parser = parse_security if security_source else parse_html
                parsed = bounded_call(
                    lambda _: (
                        parser(text, url, hosts, partial=True)
                        if response.truncated
                        else parser(text, url, hosts)
                    ),
                    timeout=max(0.001, deadline - time.monotonic()),
                    cancel_event=cancel_event,
                )
                snapshot["title"] = parsed["title"]
                # A response hash proves which transient bytes were inspected;
                # it is not the hash of the separately stored derived evidence.
                # Never return raw website markup to persistence or the UI.
                if parsed["candidates"]:
                    fields = {
                        "kind",
                        "value",
                        "name",
                        "role",
                        "purpose",
                        "excerpt",
                        "route_type",
                        "routing_label",
                        "routing_options",
                    }
                    snapshot["derived_evidence"] = {
                        "schema": 1,
                        "title": parsed["title"],
                        "contacts": [
                            {key: value for key, value in item.items() if key in fields}
                            for item in parsed["candidates"]
                        ],
                    }
                    snapshot["retention_reason"] = "derived_contacts"
                else:
                    snapshot["retention_reason"] = "no_contacts_metadata_only"
                incomplete = bool(
                    response.truncated or parsed.get("limited") or parsed.get("render_required")
                )
                if response.truncated:
                    issue(
                        "page_truncated",
                        "Page size limit reached. Complete contact elements were retained from the captured prefix.",
                        url,
                    )
                if parsed.get("limited"):
                    issue(
                        "extraction_limit",
                        "The document reached a parsing limit; omitted contacts must not be treated as absent.",
                        url,
                    )
                if parsed.get("render_required"):
                    issue(
                        "render_required",
                        "The page appears to require browser rendering; static discovery could not check its reporting choices.",
                        url,
                    )
                for entry in parsed.get("issues", []):
                    if entry["code"] in {
                        "security_expiry",
                        "security_canonical",
                        "security_contact_limit",
                    }:
                        incomplete = True
                    issue(entry["code"], entry["message"], entry.get("url"))
                interrupted = interrupted or incomplete
                for item in parsed["candidates"]:
                    merge_candidate(item, snapshot, security_source)
                if any(
                    item["code"] == "candidate_limit" and item.get("url") == url
                    for item in result["issues"]
                ):
                    incomplete = True
                state = (
                    "incomplete"
                    if incomplete
                    else ("checked" if parsed["candidates"] else "checked_empty")
                )
                record(
                    url,
                    state,
                    "Only part of this page could be checked."
                    if incomplete
                    else (
                        "Published contact information was captured."
                        if parsed["candidates"]
                        else "Checked this page; no supported contact was found in its captured content."
                    ),
                    next_step="Open this page in a browser to inspect the remaining content or reporting choices."
                    if incomplete
                    else "",
                    candidate_count=len(parsed["candidates"]),
                    **details,
                )
                return parsed, url

        try:
            root, aliases = approved_scope(root_hostname, aliases)
            hosts = {root, *aliases}
            result["root_hostname"], result["aliases"] = root, list(aliases)
            if source_url and start_url:
                raise DiscoveryError(
                    "invalid_scope", "Choose a focused source or a crawl starting URL."
                )
            if source_url:
                target = approved_url(source_url, hosts)
                result["source_url"] = target
                add_target(target, 1000, 1, is_home=True)
            else:
                target = approved_url(start_url, hosts) if start_url else "https://" + root + "/"
                result["start_url"] = target if start_url else ""
                add_target(target, 1000, 0, is_home=True)
                add_target(
                    "https://" + urlsplit(target).hostname + "/.well-known/security.txt", 900, 0
                )
            while pending:
                entry = min(pending.values(), key=lambda row: (-row["priority"], row["url"]))
                pending.pop(entry["url"])
                if entry["url"] in visited:
                    continue
                active_url = entry["url"]
                try:
                    parsed, final_url = retrieve(entry["url"])
                    if parsed is None:
                        fallback_home(entry)
                    if entry["home"] and parsed:
                        result["resolved_hostname"] = urlsplit(final_url).hostname
                        if not source_url:
                            # A homepage redirect does not establish equivalence of
                            # security.txt files. Check the actual host separately.
                            add_target(
                                "https://"
                                + result["resolved_hostname"]
                                + "/.well-known/security.txt",
                                900,
                                0,
                            )
                    # A focused page lookup means exactly that page (plus safe
                    # redirects), not another crawl starting from its links.
                    if parsed and not source_url and entry["depth"] < 2:
                        ranked = sorted(
                            (
                                (score_link(link, label), link)
                                for link, label in parsed["links"]
                                if score_link(link, label) > 0
                            ),
                            key=lambda row: (-row[0], row[1]),
                        )
                        for score, link in ranked[:32]:
                            add_target(link, score, entry["depth"] + 1, final_url)
                except DiscoveryError as error:
                    interrupted = True
                    issue(error.code, error.args[0], active_url)
                    previous = coverage.get(active_url, {})
                    if previous.get("state") not in {"blocked", "unreadable", "incomplete"}:
                        record(
                            active_url,
                            "unvisited" if active_url not in visited else "unreadable",
                            error.args[0],
                            next_step="Review this unresolved source manually if a suitable contact is still needed.",
                            **failure_details(active_url),
                        )
                    if error.code in {
                        "cancelled",
                        "deadline",
                        "request_limit",
                        "byte_limit",
                        "transport_busy",
                    }:
                        result["stop_reason"] = error.code
                        if error.code == "cancelled":
                            result["status"] = "cancelled"
                        break
                    if error.code != "redirect_limit":
                        fallback_home(entry)
                except Exception:
                    interrupted = True
                    issue(
                        "retrieval_failed", "The source could not be processed safely.", active_url
                    )
                    record(
                        active_url,
                        "unreadable",
                        "The source could not be processed safely.",
                        next_step="Review this source manually; contact absence was not established.",
                        **failure_details(active_url),
                    )
            result["candidates"] = sorted(
                candidates.values(),
                key=lambda c: (
                    not c.get("recommended_for_outreach", True),
                    PURPOSE_PRIORITY.get(c["purpose"], 99),
                ),
            )
            if result["status"] != "cancelled":
                if interrupted:
                    result["status"] = "partial" if successful or candidates else "failed"
                elif any(
                    c["purpose"] in {"security", *REFERRAL_PURPOSES} for c in candidates.values()
                ):
                    result["status"] = "relevant_found"
                elif candidates:
                    result["status"] = "general_only"
                else:
                    result["status"] = "not_found"
            eligible = [c for c in result["candidates"] if c.get("recommended_for_outreach", True)]
            if result["status"] == "cancelled":
                result["outcome"], result["next_step"] = (
                    "cancelled",
                    "Discovery was cancelled; unchecked pages remain unresolved.",
                )
            elif any(c["purpose"] == "security" for c in eligible):
                result["outcome"], result["next_step"] = (
                    "reporting_route_found",
                    "Review the published security route and its eligibility before using it for this notification.",
                )
            elif any(c["purpose"] in REFERRAL_PURPOSES for c in eligible):
                result["outcome"], result["next_step"] = (
                    "referral_found",
                    "Review the technical referral's scope; it is not automatically a vulnerability-reporting channel.",
                )
            elif not successful and any(c["state"] == "blocked" for c in coverage.values()):
                result["outcome"], result["next_step"] = (
                    "blocked",
                    "The site could not be checked. Open the blocked source in your browser; no contact absence was established.",
                )
            elif interrupted:
                result["outcome"], result["next_step"] = (
                    "incomplete",
                    "Review the unresolved pages below. Checked pages need not be repeated unless their content has changed.",
                )
            elif candidates:
                result["outcome"], result["next_step"] = (
                    "general_only",
                    "Only general or unrelated departmental contacts were found; review their purpose before requesting a technical referral.",
                )
            else:
                result["outcome"], result["next_step"] = (
                    "checked_no_suitable_contact",
                    "The listed pages were checked without finding a suitable contact. Consider another published company source; this is not proof that no route exists.",
                )
        except DiscoveryError as error:
            issue(error.code, error.args[0])
            result["stop_reason"] = error.code
        finally:
            # Retain the legacy field for evidence readers without generating
            # workflow instructions for a lightweight contact finder.
            result["next_step"] = ""
            result["coverage"] = list(coverage.values())
            result["finished_at"] = _now()
        return result
