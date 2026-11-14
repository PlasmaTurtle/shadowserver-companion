"""Attribution exhibit from frozen observations and their saved evidence only.

This adapter explains a recorded association; it does not run a lookup, change
qualification, or extend the supporting decision to every IP in a domain group.
"""

from copy import deepcopy
from datetime import datetime
from ipaddress import ip_address, ip_network

from attribution.matching import domain_equal_or_below, normalize_domain, text_domains
from attribution.google_dns import SOURCE_NAME as GOOGLE_DNS_NAME, query_url, validated_answers
from attribution.cloudflare_dns import (
    SOURCE_NAME as CLOUDFLARE_DNS_NAME,
    query_url as cloudflare_query_url,
)
from attribution.models import LookupFailure

from . import approved_template as approved
from .attribution_approval_evidence import snapshot_approval_matches

REVISION = "attribution-2026-11-07-review-1"


def _ip(value):
    try:
        address = ip_address(str(value))
        return getattr(address, "ipv4_mapped", None) or address
    except ValueError:
        return None


def _domain(value):
    try:
        return normalize_domain(value)
    except (ValueError, TypeError):
        return ""


def _within(value, root):
    normalized = _domain(value)
    return bool(normalized and root and domain_equal_or_below(normalized, root))


def _field(record, path):
    """Resolve the saved evidence pointer without walking unrelated fields."""
    if not path or not isinstance(path, str):
        return None
    parts = (
        [part.replace("~1", "/").replace("~0", "~") for part in path[1:].split("/")]
        if path.startswith("/")
        else path.removeprefix("record.").split(".")
    )
    value = record
    try:
        for part in parts:
            value = value[int(part)] if isinstance(value, list) else value[part]
        return value
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _network(record, details):
    """Return displayed range, normalized bounds, and a consistency issue."""
    raw_start, raw_end = record.get("startAddress"), record.get("endAddress")
    start = details.get("network_start") or raw_start
    end = details.get("network_end") or raw_end
    label = ""
    bounds = None
    if start or end:
        label = f"{start or 'Start not recorded'} – {end or 'End not recorded'}"
        bounds = (_ip(start), _ip(end))
    cidr = details.get("cidr") or details.get("network_range")
    if cidr:
        try:
            if "/" in str(cidr):
                network = ip_network(str(cidr), strict=False)
                other = (_ip(network.network_address), _ip(network.broadcast_address))
            else:
                parts = str(cidr).replace("–", "-").split("-", 1)
                other = (_ip(parts[0].strip()), _ip(parts[1].strip()))
            if bounds and other != bounds:
                return label, bounds, "Saved network range fields disagree."
            label, bounds = str(cidr), other
        except (ValueError, IndexError):
            return str(cidr), bounds, "Saved network range cannot be interpreted."
    if not bounds:
        return None, None, "Covering network was not recorded."
    left, right = bounds
    if not left or not right or left.version != right.version or int(left) > int(right):
        return label, bounds, "Saved network range is invalid."
    if (raw_start and _ip(raw_start) != left) or (raw_end and _ip(raw_end) != right):
        return label, bounds, "Saved network range fields disagree."
    return label, bounds, None


def _time(value):
    if not value:
        return None, "Validation time was not recorded."
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value), "Validation time is not a recognizable timestamp."
    if stamp.tzinfo is None:
        return str(value), "The validation timestamp has no recorded time zone."
    return str(value), None


def _item(group, original, exported):
    proof = group.get("source") or {}
    evidence = proof.get("evidence") or {}
    details = evidence.get("details") or {}
    match = evidence.get("match") or proof.get("attribution") or {}
    record = proof.get("record") or {}
    review = proof.get("review") or {}
    root = _domain(group.get("hostname"))
    entries = exported.get("entries") or []
    # LeadExportService puts the actual selected observation first. Do not
    # construct a reported IP from the proof we are trying to corroborate.
    selected = exported.get("supporting_observation") or (entries[0] if entries else {})
    reported = selected.get("ip")
    reported_ip = _ip(reported)
    proof_ip = _ip(proof.get("ip"))
    evidence_ip = _ip(evidence.get("ip") or proof.get("ip"))
    hostname = selected.get("source", {}).get("fields", {}).get("hostname")
    issues = []
    if not selected or not reported_ip or not _within(hostname, root):
        issues.append(
            "The selected supporting observation is missing or outside this domain group."
        )
    if not proof_ip or reported_ip != proof_ip or reported_ip != evidence_ip:
        issues.append("The selected reported IP does not match the saved evidence IP.")
    target = match.get("target_domain") or match.get("root_domain")
    if target and _domain(target) != root:
        issues.append("The saved attribution names a different domain group.")

    field = match.get("field_path") or match.get("field")
    value = match.get("value")
    if not field or value in (None, ""):
        issues.append("The matching source field and value were not recorded.")
    method = evidence.get("method") or ("dns" if proof.get("protocol") == "DNS" else "rdap")
    if method not in {"rdap", "whois", "dns", "rdap_keyword"}:
        issues.append("The saved attribution method is not recognized by this exhibit.")
    accepted = review.get("decision") == "accept"
    reused = "approval_reuse" in proof
    if reused and not snapshot_approval_matches(proof, root):
        issues.append("The prior registrant approval does not match the saved evidence.")
        accepted = False
    elif (
        not reused
        and review.get("result_id")
        and proof.get("result_id")
        and review["result_id"] != proof["result_id"]
    ):
        issues.append("The saved analyst decision belongs to a different attribution result.")
        accepted = False
    reused = reused and accepted
    network, bounds, network_issue = _network(record, details)
    corroborated_label, corroborated = "Evidence IP", proof.get("ip")
    if method == "dns":
        label = (
            "Forward-confirmed reverse DNS"
            if details.get("basis") == "forward_confirmed_reverse"
            else "Forward DNS match"
        )
        resolved = details.get("resolved_hostname") or match.get("matched_domain")
        # Provider identity is not a schema version: earlier Google captures
        # retained the normalized query/type/answers schema and its own pointer.
        # Any raw-response marker (even in a damaged or mixed record) must stay
        # on the strict raw path rather than fall back to normalized answers.
        google = bool(
            {"Status", "TC", "RD", "RA", "AD", "CD", "Question", "Answer"} & record.keys()
        ) or (isinstance(field, str) and (field == "/Answer" or field.startswith("/Answer/")))
        if google:
            matching = []
            try:
                kind = "A" if reported_ip.version == 4 else "AAAA"
                name = normalize_domain(resolved)
                source = evidence.get("source_url") or proof.get("source_url")
                source_name = evidence.get("source_name") or proof.get("registry")
                query_builder = {
                    GOOGLE_DNS_NAME: query_url,
                    CLOUDFLARE_DNS_NAME: cloudflare_query_url,
                }.get(source_name)
                if (
                    query_builder is None
                    or source != query_builder(name + ".", kind)
                    or details.get("record_type") != kind
                ):
                    raise ValueError("DNS source query differs from saved evidence")
                answers, _, _, _ = validated_answers(record, name, kind)
                matching = [
                    answer
                    for answer, index, original in answers
                    if _ip(answer) == reported_ip
                    and field == f"/Answer/{index}/data"
                    and value == original
                    and _field(record, field) == original
                ]
            except (ValueError, TypeError, KeyError, AttributeError, LookupFailure):
                issues.append("The saved public DNS response does not match its source query.")
        else:
            # Historical observations (including named Google captures) retain
            # their normalized schema and original source identity.
            answers = record.get("answers") or []
            answers = answers if isinstance(answers, list) and _domain(record.get("query")) else []
            matching = [
                str(answer) for answer in answers if _ip(answer) and _ip(answer) == reported_ip
            ]
        corroborated_label, corroborated = (
            "DNS answer",
            ", ".join(dict.fromkeys(matching)) or "No matching saved answer",
        )
        if (
            details.get("dns_forward_match") is not True
            or not matching
            or not _within(resolved, root)
        ):
            issues.append(
                "The saved forward DNS response does not establish this domain-to-IP match."
            )
        if not google and record.get("query") and _domain(record["query"]) != _domain(resolved):
            issues.append("The saved DNS query and matched hostname disagree.")
        if not google and record.get("type") not in {"A", "AAAA"}:
            issues.append("The saved DNS record does not identify a forward address query.")
        explanation = (
            f"A saved forward lookup of {resolved or 'the hostname'} returned the reported IP."
        )
        if details.get("basis") == "forward_confirmed_reverse":
            explanation = f"Reverse DNS identified {resolved or 'the hostname'}; its saved forward response returned the reported IP."
    else:
        label = (
            "Prior registrant approval reused"
            if reused
            else "Analyst-reviewed registration-name match"
            if accepted
            else "Registration-name match pending review"
            if method == "rdap_keyword"
            else "Exact domain in registration record"
        )
        corroborated_label, corroborated = "Covering network", network or "Not recorded"
        if network_issue:
            issues.append(network_issue)
        elif (
            not reported_ip
            or reported_ip.version != bounds[0].version
            or not int(bounds[0]) <= int(reported_ip) <= int(bounds[1])
        ):
            issues.append("The reported IP is outside the saved registered network.")
        if value is not None and _field(record, field) != value:
            issues.append("The matching value is not present at its saved source field.")
        if reused:
            explanation = (
                "The saved registration for this reported IP identifies the same registrant "
                f"previously approved for this domain by {review.get('reviewer') or 'an analyst'} "
                f"on {review.get('reviewed_at') or 'an unrecorded date'}. "
                "That prior approval was reused; this IP was not separately reviewed by the analyst."
            )
        elif accepted:
            explanation = "An analyst accepted the registration-name association for this reported IP and domain group."
        elif method == "rdap_keyword":
            explanation = (
                "Matching registration words are a review lead; no analyst acceptance is recorded."
            )
            issues.append(
                "The partial registration-name match has not been accepted by an analyst."
            )
        else:
            found = match.get("matched_domain")
            value_domains = list(text_domains(str(value or "")))
            if not _within(found, root) or not any(
                _within(domain, root) for domain in value_domains
            ):
                issues.append(
                    "The source value does not establish the recorded exact-domain match."
                )
            explanation = f"The saved registration record contains {found or root or 'the domain'}; the reported IP is within its recorded network."
    if review and not accepted:
        issues.append("The saved analyst decision does not accept this association.")
    source_name = evidence.get("source_name") or proof.get("registry")
    source_url = evidence.get("source_url") or proof.get("source_url")
    if not source_name or not source_url:
        issues.append("The supporting source and its location were not fully recorded.")
    for evidence_key, proof_key in (
        ("source_name", "registry"),
        ("source_url", "source_url"),
        ("retrieved_at", "retrieved_at"),
    ):
        left, right = evidence.get(evidence_key), proof.get(proof_key)
        if left and right and left != right:
            if evidence_key == "retrieved_at":
                try:
                    if datetime.fromisoformat(
                        str(left).replace("Z", "+00:00")
                    ) == datetime.fromisoformat(str(right).replace("Z", "+00:00")):
                        continue
                except ValueError:
                    pass
            issues.append("The source citation metadata disagrees with the saved evidence.")
    if not group.get("citation"):
        issues.append("A reference for the supporting source was not recorded.")
    stamp = (
        review.get("reviewed_at")
        if accepted and not reused
        else proof.get("validated_at") or proof.get("decision_at") or proof.get("evaluated_at")
    )
    validated_at, timestamp_note = _time(stamp)
    validated_by = (
        review.get("reviewer")
        if accepted and not reused
        else proof.get("validated_by")
        or proof.get("decision_by")
        or ("Attribution Module" if proof.get("evaluated_at") else None)
    )
    review_required = bool(issues or timestamp_note or not validated_by)
    if issues:
        explanation = "Review required: " + " ".join(dict.fromkeys(issues))
    result = deepcopy(original)
    result.update(
        label=group.get("hostname") or "Domain not recorded",
        method_label=label,
        supported=not issues,
        review_required=review_required,
        reported_ip=str(reported) if reported is not None else "Not recorded",
        reported_hostname=hostname,
        corroborated_value=corroborated,
        corroborated_label=corroborated_label,
        explanation=explanation,
        matched_field=field,
        matched_value=value,
        source_name=source_name or "Source not recorded",
        source_url=source_url,
        citations=[group["citation"]] if group.get("citation") else [],
        retrieved_at=evidence.get("retrieved_at") or proof.get("retrieved_at"),
        validated_at=validated_at,
        validated_by=validated_by,
        timestamp_note=timestamp_note,
        reported_asset_count=len({_ip(e.get("ip")) for e in entries} - {None}),
        supporting_attribution_count=0 if issues else 1,
        review_note=review.get("note"),
        from_cache=evidence.get("from_cache", proof.get("from_cache", False)),
    )
    if reused:
        result.update(
            prior_approval_at=review.get("reviewed_at"),
            prior_approval_by=review.get("reviewer"),
        )
    return result


def build_attribution_exhibit(data, exhibit, attribution_groups):
    model = deepcopy(exhibit)
    exported = {
        group.get("hostname"): group
        for group in data.get("qualified_lead", {}).get("validated_leads", [])
    }
    originals = {item.get("label"): item for item in exhibit.get("items", [])}
    items = [
        _item(
            group, originals.get(group.get("hostname"), {}), exported.get(group.get("hostname"), {})
        )
        for group in attribution_groups
    ]
    reported_ips = {
        _ip(entry.get("ip")) for group in exported.values() for entry in group.get("entries", [])
    } - {None}
    model.update(
        title="Attribution",
        layout_revision=REVISION,
        narrative=approved.ATTRIBUTION,
        company=data.get("draft", {}).get("company")
        or data.get("entity_name")
        or "Organization not recorded",
        address=data.get("draft", {}).get("address") or "",
        business_registration_reviewed=bool(data.get("draft", {}).get("sos_verified")),
        business_registration_note=(
            "Business-registration information reviewed by the analyst; supporting details are recorded with the case."
            if data.get("draft", {}).get("sos_verified")
            else ""
        ),
        items=items,
        counts=[
            {"label": "Reported IPs", "value": len(reported_ips)},
            {
                "label": "Supporting associations",
                "value": sum(item["supporting_attribution_count"] for item in items),
            },
            {
                "label": "Associations needing review",
                "value": sum(item["review_required"] for item in items),
            },
        ],
        count_note="One supporting association is used for each domain group. Other reported IPs are retained for recipient review; they are not individually attributed by this exhibit.",
    )
    return model
