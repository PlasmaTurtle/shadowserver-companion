"""Read-only attribution cards from the observations and evidence in a case.

These cards explain a recorded decision. They do not perform a fresh lookup or
promote other observations in the same domain group to individually verified IPs.
"""

from __future__ import annotations

from contextlib import ExitStack
from ipaddress import ip_address
import sqlite3

from attribution import EvidenceStore
from attribution.matching import domain_equal_or_below, normalize_domain

from .attribution_bridge import checked_result
from .attribution_approval_evidence import snapshot_approval_matches


def _domain(value):
    try:
        return normalize_domain(value)
    except (TypeError, ValueError):
        return ""


def _ip(value):
    try:
        address = ip_address(value)
        return str(getattr(address, "ipv4_mapped", None) or address)
    except (TypeError, ValueError):
        return None


def _belongs(entry, root):
    hostname = entry.get("source", {}).get("fields", {}).get("hostname", "")
    found = _domain(hostname)
    return bool(found and root and domain_equal_or_below(found, root))


def attribution_summaries(store, lead):
    """Return one explanatory card per supplied (case-frozen) domain group.

    Callers must pass Cases.view(...) for a notification. The entity's current
    attribution is deliberately never consulted. Older records may recover their
    evaluation time only from their original immutable result, not retrieval time.
    """
    from .observation_scope import finding_entries

    entries = finding_entries(lead.get("entries", []))
    by_id = {
        entry["id"]: entry for entry in lead.get("scope_source_entries", entries) if "id" in entry
    }
    results = {}
    summaries = []
    evidence_store = None
    evidence_error = None
    with ExitStack() as stack:
        for group in lead.get("domain_groups", []):
            root = _domain(group.get("root_domain", ""))
            attribution = group.get("attribution") or {}
            evidence = attribution.get("evidence") or {}
            match = evidence.get("match") or attribution.get("attribution") or {}
            details = evidence.get("details") or {}
            record = attribution.get("record") or {}
            review = attribution.get("review") or {}
            selected = by_id.get(group.get("attribution_entry_id"))
            group_entries = [entry for entry in entries if _belongs(entry, root)]
            reported_ips = {_ip(entry.get("ip")) for entry in group_entries} - {None}
            reported_ip = selected.get("ip") if selected else None
            validated_ip = evidence.get("ip") or attribution.get("ip")
            warnings = []
            if not selected or not _belongs(selected, root):
                warnings.append("The supporting observation is not present in this domain group.")
            if not _ip(reported_ip) or _ip(reported_ip) != _ip(validated_ip):
                warnings.append("The reported IP does not match the IP in the saved attribution.")
            recorded_root = _domain(match.get("target_domain") or match.get("root_domain") or root)
            if recorded_root != root:
                warnings.append("The saved attribution belongs to a different domain group.")

            evaluated_at = attribution.get("evaluated_at")
            result_id = attribution.get("result_id")
            timestamp_note = None
            if not evaluated_at and result_id:
                # Opening a store can migrate it; never create an evidence database
                # just to display a legacy record that has no standalone history.
                if evidence_store is None and evidence_error is None:
                    path = store.root / "attribution.sqlite3"
                    if path.is_file():
                        try:
                            evidence_store = stack.enter_context(EvidenceStore(path))
                        except (OSError, sqlite3.Error, ValueError) as error:
                            evidence_error = str(error)
                    else:
                        evidence_error = "The saved attribution database is unavailable."
                if evidence_store is not None:
                    key = (result_id, root)
                    if key not in results:
                        try:
                            results[key] = checked_result(evidence_store, result_id, root)
                        except (KeyError, ValueError, sqlite3.Error) as error:
                            results[key] = error
                    result = results[key]
                    if isinstance(result, Exception):
                        timestamp_note = str(result)
                        if "does not belong" in str(result):
                            warnings.append(str(result))
                    else:
                        evaluated_at = result.get("evaluated_at")
                else:
                    timestamp_note = evidence_error

            is_review = review.get("decision") == "accept"
            reused = "approval_reuse" in attribution
            if reused and not snapshot_approval_matches(attribution, root):
                warnings.append("The prior registrant approval does not match the saved evidence.")
                is_review = False
            elif (
                not reused
                and review.get("result_id")
                and result_id
                and review["result_id"] != result_id
            ):
                warnings.append(
                    "The saved analyst decision belongs to a different attribution result."
                )
                is_review = False
            reused = reused and is_review
            raw_method = evidence.get("method") or (
                "dns" if attribution.get("protocol") == "DNS" else "rdap"
            )
            matched_field = match.get("field_path") or match.get("field")
            matched_value = match.get("value")
            matched_domain = match.get("matched_domain")
            if reused:
                method = "registrant_approval_reuse"
                validated_at = evaluated_at
                validated_by = "Attribution Module" if evaluated_at else None
                kind = "automatic" if evaluated_at else "unknown"
                summary = (
                    "The saved registration identifies the same registrant previously approved "
                    f"for this domain by {review.get('reviewer') or 'an analyst'} on "
                    f"{review.get('reviewed_at') or 'an unrecorded date'}. "
                    "The prior approval was reused with this IP's registration evidence; "
                    "no new analyst decision was made."
                )
            elif is_review:
                method = "analyst_review"
                validated_at = review.get("reviewed_at")
                validated_by = review.get("reviewer") or None
                kind = "analyst"
                words = ", ".join(str(word) for word in details.get("matched_words", []))
                summary = "An analyst accepted the registration-name association"
                summary += f" after reviewing the matching words: {words}." if words else "."
            elif raw_method == "dns":
                method = "dns"
                validated_at = evaluated_at
                validated_by = "Attribution Module" if evaluated_at else None
                kind = "automatic" if evaluated_at else "unknown"
                hostname = details.get("resolved_hostname") or matched_domain or root
                if details.get("dns_forward_match") is not True:
                    warnings.append("The saved DNS evidence does not record a forward IP match.")
                if details.get("basis") == "forward_confirmed_reverse":
                    summary = f"Reverse DNS identified {hostname}; a saved forward lookup returned the reported IP."
                else:
                    summary = f"A saved forward lookup of {hostname} returned the reported IP."
            elif raw_method == "rdap_keyword":
                method, kind = "unknown", "unknown"
                validated_at = validated_by = None
                warnings.append(
                    "A partial registration-name match has no recorded analyst acceptance."
                )
                summary = "The registration-name association still requires analyst review."
            else:
                method = "registration"
                validated_at = evaluated_at
                validated_by = "Attribution Module" if evaluated_at else None
                kind = "automatic" if evaluated_at else "unknown"
                if not matched_domain or not domain_equal_or_below(_domain(matched_domain), root):
                    warnings.append(
                        "The saved registration evidence does not identify a matching domain."
                    )
                summary = f"The saved registration record contains {matched_domain or root}"
                summary += f" in {matched_field}." if matched_field else "."

            supported = bool(attribution and not warnings)
            if warnings:
                summary = "This saved attribution needs review: " + " ".join(warnings)
            summaries.append(
                {
                    "root_domain": root or group.get("root_domain"),
                    "reported_ip": reported_ip,
                    "validated_ip": validated_ip,
                    "source_name": evidence.get("source_name")
                    or attribution.get("registry")
                    or "Source not recorded",
                    "source_url": evidence.get("source_url") or attribution.get("source_url"),
                    "method": method,
                    "match_summary": summary,
                    "supported": supported,
                    "validated_at": validated_at,
                    "validated_by": validated_by,
                    "validation_kind": kind,
                    "retrieved_at": evidence.get("retrieved_at") or attribution.get("retrieved_at"),
                    "from_cache": evidence.get("from_cache", attribution.get("from_cache", False)),
                    "reuse": attribution.get("reuse")
                    if isinstance(attribution.get("reuse"), dict)
                    else None,
                    "supporting_ip_count": 1 if supported else 0,
                    "reported_ip_count": len(reported_ips),
                    "details": {
                        "matched_field": matched_field,
                        "matched_value": matched_value,
                        "matched_domain": matched_domain,
                        "network_start": details.get("network_start") or record.get("startAddress"),
                        "network_end": details.get("network_end") or record.get("endAddress"),
                        "resolved_hostname": details.get("resolved_hostname"),
                        "dns_basis": details.get("basis"),
                        "resolver_comparison": details.get("resolver_comparison"),
                        "resolver_results": details.get("resolver_results"),
                        "raw_record": record,
                        "result_id": result_id,
                        "snapshot_id": attribution.get("snapshot_id")
                        or evidence.get("snapshot_id"),
                        "body_sha256": attribution.get("body_sha256"),
                        "review_note": review.get("note"),
                        "prior_approval_at": review.get("reviewed_at") if reused else None,
                        "prior_approval_by": review.get("reviewer") if reused else None,
                        "approval_source_result_id": (
                            attribution["approval_reuse"].get("source_result_id")
                            if reused
                            else None
                        ),
                        "evaluated_at": evaluated_at,
                        "integrity_warning": " ".join(warnings) or None,
                        "timestamp_note": timestamp_note
                        or (None if validated_at else "Validation time was not recorded."),
                    },
                }
            )
    return summaries
