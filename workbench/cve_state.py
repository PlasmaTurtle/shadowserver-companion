"""Case-owned authoritative CVE state history and capture-order guards.

The API must authenticate candidate records against its captured source bank
before calling this function. Prior history comes from the saved case, never the
submitted browser payload. Fetching a bank update does not change a pinned case.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import re

STATES = {"published", "reserved", "rejected"}
RESTRICTED = {"reserved", "rejected"}


def cve_excluded(cve_id, draft):
    """Only an explicit, reasoned disposition removes a CVE from notification."""
    value = draft.get("cve_dispositions", {}).get(cve_id, {})
    return value.get("action") == "exclude" and bool(str(value.get("reason", "")).strip())


def excluded_cves(draft):
    return {key for key in draft.get("cve_dispositions", {}) if cve_excluded(key, draft)}


def _instant(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        # Evidence capture is an event instant. A naive date is not proof that
        # it happened after another captured record.
        return instant.astimezone(timezone.utc) if instant.tzinfo is not None else None
    except ValueError, OverflowError:
        return None


def _state(record):
    values = [
        str(record.get(key) or "").strip().lower()
        for key in ("verification_status", "state", "status")
    ]
    return next(
        (value for value in values if value in RESTRICTED),
        next((value for value in values if value in STATES), None),
    )


def _record_list(records):
    if isinstance(records, dict):
        records = [records] if "id" in records else records.values()
    return [record for record in (records or []) if isinstance(record, dict)]


def _event(identifier, state, source, fallback=None):
    fallback = fallback or {}
    return {
        "id": identifier,
        "state": state,
        "revision_id": source.get("revision_id") or fallback.get("revision_id"),
        "retrieved_at": source.get("retrieved_at")
        if "retrieved_at" in source
        else fallback.get("retrieved_at"),
        "source": source.get("publisher")
        or source.get("source")
        or fallback.get("source")
        or "Unspecified source",
    }


def state_events(record):
    """Extract status capture provenance without substituting assessment dates."""
    if not isinstance(record, dict) or record.get("manual_fallback"):
        return []
    identifier = record.get("id")
    if not isinstance(identifier, str) or not re.fullmatch(r"CVE-\d{4}-\d{4,}", identifier):
        return []
    current_state = _state(record)
    sources = _record_list(record.get("sources", []))
    supplements = _record_list(record.get("supplementary_records", []))
    events = []
    if current_state:
        conflict = record.get("state_conflict") or {}
        # A Program rejection may sit beside a still-published primary NVD
        # record. Its actual response timestamp is the rejection capture time.
        revision = (
            conflict.get("source_revision_id")
            if str(conflict.get("supplementary_state", "")).lower() == current_state
            else record.get("revision_id")
        )
        source = next(
            (item for item in sources if revision and item.get("revision_id") == revision), None
        )
        if source is None:
            source = next(
                (
                    item.get("source", {})
                    for item in supplements
                    if revision and item.get("source", {}).get("revision_id") == revision
                ),
                None,
            )
        if (
            source is None
            and conflict.get("source_revision_id")
            and conflict.get("source_revision_id") == revision
        ):
            # Never borrow the NVD timestamp when the status came from an
            # unavailable supplementary snapshot.
            source = {"revision_id": revision, "retrieved_at": None, "publisher": "CVE Program"}
        events.append(_event(identifier, current_state, source or {}, record))
    for item in supplements:
        raw = item.get("record") or {}
        metadata = raw.get("cveMetadata", {}) if isinstance(raw, dict) else {}
        if metadata.get("cveId") != identifier:
            continue
        state = str(metadata.get("state") or "").strip().lower()
        if state in STATES:
            events.append(_event(identifier, state, item.get("source") or {}))
    return events


def _append_unique(history, events):
    seen = {json.dumps(item, sort_keys=True, ensure_ascii=False, default=str) for item in history}
    for event in events:
        key = json.dumps(event, sort_keys=True, ensure_ascii=False, default=str)
        if key not in seen:
            history.append(deepcopy(event))
            seen.add(key)


def guard_cve_states(candidate_records, prior_records, prior_history, cached_records, dispositions):
    """Return persisted history or reject an unsupported state reversal.

    Parameters are complete records already checked against the immutable bank.
    `cached_records` should contain the latest primary AND intelligence records
    for this case's CVEs. `prior_history` is the server-pinned draft list. The
    caller stores this return value in `draft.cve_state_history`, even when a
    source is omitted or excluded. It is guard metadata, not report content.

    Unchanged selected records are not invalidated by a background bank update.
    An explicit new source adoption or manual fallback must prove a subsequent
    authoritative published capture after every known reserved/rejected capture.
    """
    candidates = _record_list(candidate_records)
    prior = _record_list(prior_records)
    cached = _record_list(cached_records)
    dispositions = dispositions or {}
    history = deepcopy(prior_history or [])
    if any(
        not isinstance(item, dict) or item.get("state") not in STATES or not item.get("id")
        for item in history
    ):
        raise ValueError("Saved CVE state history is invalid; restore the retained case evidence")
    relevant_ids = (
        {record.get("id") for record in candidates + prior}
        | set(dispositions)
        | {item["id"] for item in history}
    )
    for record in prior + cached:
        if record.get("id") in relevant_ids:
            _append_unique(history, state_events(record))
    prior_by_id = {record.get("id"): record for record in prior}
    candidate_by_id = {record.get("id"): record for record in candidates}
    for identifier in relevant_ids:
        candidate = candidate_by_id.get(identifier)
        action = dispositions.get(identifier, {}).get("action")
        is_fallback = action == "fallback"
        current_state = _state(candidate or {})
        if action == "exclude":
            continue
        if not is_fallback and candidate == prior_by_id.get(identifier):
            continue
        restricted = [
            item for item in history if item["id"] == identifier and item["state"] in RESTRICTED
        ]
        restricted.extend(
            item for item in state_events(candidate or {}) if item["state"] in RESTRICTED
        )
        if is_fallback and current_state in RESTRICTED:
            raise ValueError(
                "Reserved or rejected CVEs cannot be changed into published vulnerabilities by a fallback."
            )
        if not restricted or (not is_fallback and current_state != "published"):
            continue
        selected_events = state_events(candidate or {})
        # The first event describes the record's selected/normalized state.
        # A supplementary published event cannot promote a rejected selection.
        selected = (
            selected_events[0]
            if selected_events and selected_events[0]["state"] == "published"
            else None
        )
        published_at = _instant(selected.get("retrieved_at")) if selected else None
        restricted_times = [_instant(item.get("retrieved_at")) for item in restricted]
        if (
            published_at is None
            or any(stamp is None for stamp in restricted_times)
            or any(published_at <= stamp for stamp in restricted_times if stamp is not None)
        ):
            raise ValueError(
                "Reserved or rejected CVEs require a selected authoritative published record captured after the known restricted state; an older record, missing timestamp, omission, or fallback cannot replace that evidence."
            )
    for record in candidates:
        _append_unique(history, state_events(record))
    return history
