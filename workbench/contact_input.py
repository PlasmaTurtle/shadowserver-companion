"""Allowlisted contact-result boundary; untrusted response bodies never enter records."""

from copy import deepcopy
import re
import unicodedata

from .contact_discovery.extract import EMAIL, candidate_key, review_url
from .contact_discovery.policy import MAX_CANDIDATES, MAX_REQUESTS, approved_url

CANDIDATE_FIELDS = {
    "key",
    "kind",
    "value",
    "name",
    "role",
    "purpose",
    "sources",
    "route_type",
    "routing_label",
    "routing_options",
    "original_url",
    "external_destination",
    "requires_review",
    "review_reason",
    "partial_source",
    "review_required",
    "published_purposes",
    "recommended_for_outreach",
    "purpose_conflict",
}
SOURCE_FIELDS = {
    "snapshot_id",
    "url",
    "excerpt",
    "purpose",
    "truncated",
    "route_type",
    "routing_label",
    "routing_options",
    "original_url",
    "external_destination",
    "requires_review",
    "review_reason",
    "partial_source",
}
RESULT_FIELDS = {
    "schema",
    "discovery_revision",
    "root_hostname",
    "aliases",
    "source_url",
    "resolved_hostname",
    "status",
    "outcome",
    "started_at",
    "finished_at",
    "request_count",
    "page_request_count",
    "redirect_request_count",
    "bytes_received",
    "candidates",
    "snapshots",
    "issues",
    "coverage",
    "stop_reason",
    "next_step",
}
ISSUE_FIELDS = {"code", "message", "url"}
COVERAGE_FIELDS = {
    "url",
    "checked_at",
    "status_code",
    "snapshot_id",
    "candidate_count",
    "referrer_url",
    "state",
    "message",
    "next_step",
    "truncated",
}
PURPOSES = {
    "security",
    "it",
    "product_support",
    "management",
    "general",
    "other",
    "privacy",
    "compliance",
    "hr",
    "media",
    "investor",
    "physical_emergency",
}
BOOL_FIELDS = {
    "truncated",
    "external_destination",
    "requires_review",
    "partial_source",
    "review_required",
    "recommended_for_outreach",
    "purpose_conflict",
}


def plain_text(value, limit=4000):
    """A plain-text field contract, not an HTML sanitizer or malware verdict."""
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError("Contact text exceeds its supported field format")
    if any(
        c in "<>" or (unicodedata.category(c).startswith("C") and c not in "\t\n\r") for c in value
    ):
        raise ValueError("Contact text must be plain text without markup or control characters")
    return value


def _fields(value, allowed):
    if not isinstance(value, dict):
        raise ValueError("Contact result requires structured fields")
    return {key: deepcopy(item) for key, item in value.items() if key in allowed}


def _text_fields(value):
    for key, item in value.items():
        if key in BOOL_FIELDS:
            if type(item) is not bool:
                raise ValueError("Contact flags must be boolean")
        elif isinstance(item, str):
            plain_text(item)
        elif key == "routing_options":
            if not isinstance(item, list) or len(item) > 50:
                raise ValueError("Contact route options are invalid")
            for option in item:
                if not isinstance(option, dict) or set(option) != {"label", "purpose"}:
                    raise ValueError("Contact route option fields are invalid")
                plain_text(option["label"], 300)
                if option["purpose"] not in PURPOSES:
                    raise ValueError("Contact route option purpose is unsupported")
        elif isinstance(item, list):
            if len(item) > 50 or any(not isinstance(x, str) for x in item):
                raise ValueError("Contact text list is invalid")
            for text in item:
                plain_text(text, 300)
        else:
            raise ValueError("Contact field has an unsupported type")


def validate_candidate_input(candidate, snapshots):
    candidate = _fields(candidate, CANDIDATE_FIELDS)
    sources = candidate.pop("sources", None)
    _text_fields(candidate)
    kind, value = candidate.get("kind"), candidate.get("value", "")
    if kind not in {"email", "phone", "form", "person"} or not value:
        raise ValueError("Contact candidate has no supported type or source")
    plain_text(value, {"email": 500, "phone": 100, "form": 2048, "person": 300}[kind])
    if kind == "email" and not EMAIL.fullmatch(value):
        raise ValueError("Contact email format is invalid")
    if kind == "phone" and (
        not re.fullmatch(r"[+\d(). /-]+(?:(?:;ext=|\s*(?:ext\.?|extension|x)\s*)\d+)?", value, re.I)
        or not 7 <= len(re.sub(r"\D", "", value)) <= 23
    ):
        raise ValueError("Contact phone format is invalid")
    if kind == "form" and review_url(value) != value:
        raise ValueError("Contact link is not canonical")
    if candidate_key(kind, value) != candidate.get("key"):
        raise ValueError("Contact candidate key does not identify its published value")
    for key in ("name", "role"):
        plain_text(candidate.get(key, ""), 300)
    if candidate.get("purpose") not in PURPOSES:
        raise ValueError("Contact purpose is unsupported")
    if any(x not in PURPOSES for x in candidate.get("published_purposes", [])):
        raise ValueError("Contact purpose is unsupported")
    if not isinstance(sources, list) or not 1 <= len(sources) <= MAX_REQUESTS * 50:
        raise ValueError("Contact candidate has no supported type or source")
    clean_sources = []
    for source in sources:
        source = _fields(source, SOURCE_FIELDS)
        _text_fields(source)
        saved = snapshots.get(source.get("snapshot_id"))
        if not saved or source.get("url") != saved.get("url"):
            raise ValueError("Contact candidate does not identify its saved source")
        if not 200 <= saved.get("status_code", 0) < 300:
            raise ValueError("Contact candidate came from an unsuccessful response")
        from .contact_discovery.validation import decode_response_text

        media = saved.get("content_type", "").split(";", 1)[0].strip().lower()
        decode_response_text(
            b"", saved.get("content_type", ""), security_source=media == "text/plain"
        )
        plain_text(source.get("excerpt", ""), 4000)
        clean_sources.append(source)
    candidate["sources"] = clean_sources
    return candidate


def clean_result(result, allowed):
    """Validate every persisted projection before opening files or transactions."""
    result = _fields(result, RESULT_FIELDS)
    snapshots = result.get("snapshots")
    candidates = result.get("candidates")
    if not isinstance(snapshots, list) or len(snapshots) > MAX_REQUESTS:
        raise ValueError("Contact result exceeded its capture budget")
    if not isinstance(candidates, list) or len(candidates) > MAX_CANDIDATES:
        raise ValueError("Contact result exceeded its capture budget")
    by_id = {}
    for snapshot in snapshots:
        if (
            not isinstance(snapshot, dict)
            or not isinstance(snapshot.get("id"), str)
            or snapshot["id"] in by_id
        ):
            raise ValueError("Contact response identity is invalid or duplicated")
        if approved_url(snapshot.get("url"), allowed) != snapshot["url"]:
            raise ValueError("Contact evidence URL is not canonical")
        if (
            type(snapshot.get("status_code")) is not int
            or not 100 <= snapshot["status_code"] <= 599
        ):
            raise ValueError("Contact HTTP status is invalid")
        by_id[snapshot["id"]] = snapshot
    result["candidates"] = [validate_candidate_input(c, by_id) for c in candidates]
    for key in ("issues", "coverage"):
        items = result.get(key, [])
        if not isinstance(items, list) or len(items) > 128:
            raise ValueError("Contact diagnostic list exceeds its limit")
        allowed_fields = ISSUE_FIELDS if key == "issues" else COVERAGE_FIELDS
        clean = []
        for item in items:
            item = _fields(item, allowed_fields)
            for name, value in item.items():
                if value is None or type(value) in (int, bool):
                    continue
                plain_text(value, 4000)
            clean.append(item)
        result[key] = clean
    for key, value in result.items():
        if key in {"snapshots", "candidates", "issues", "coverage"}:
            continue
        if key == "aliases":
            if not isinstance(value, list) or len(value) > 1:
                raise ValueError("Contact aliases are invalid")
            for item in value:
                plain_text(item, 253)
        elif value is None or type(value) is int:
            continue
        else:
            plain_text(value, 4000)
    return result
