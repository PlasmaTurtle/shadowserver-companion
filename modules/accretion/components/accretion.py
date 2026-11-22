"""Pure, explainable ranking of qualified finding scope.

Policy belongs to scoring_matrix; local evidence capture to scoring_evidence.
The established scoring and vetting exports remain available to existing callers.
"""

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from ipaddress import ip_address

from .intake.versions import entry_fields, has_active_findings, selected_version
from .intake.domains import CVE_TAG as CVE, HOSTNAME, root_domain as registered_root
from .report_profiles import has_independent_finding
from .scoring_matrix import (
    POLICY_VERSION,
    TEMPERATURES,
    normalize_policy,
    policy_defaults as policy_defaults,
    policy_hash,
    factor as _factor,
)
from .scoring_evidence import (
    parse_date,
    score_stamp,
    validated_cve,
    snapshot_order,
    vet_cves as vet_cves,
)

from .scoring_urgency import strongest_finding

SCHEMA_VERSION = 1


def _entry(value):
    value = asdict(value) if is_dataclass(value) else value
    if not isinstance(value, Mapping):
        raise ValueError("Accretion requires observation records")
    source = value.get("source", value)
    fields = source.get("fields", source)
    normalized = value.get("normalized") or {}
    return entry_fields({"source": {"fields": fields}, "normalized": normalized}), normalized


def _ids(fields, normalized):
    if normalized.get("case_condition_scope"):
        return {
            str(value).upper()
            for value in normalized.get("active_conditions", [])
            if CVE.fullmatch(str(value).upper())
        }
    ids = {v.upper() for v in CVE.findall(str(fields.get("tag") or ""))}
    ids.update(
        str(item.get("id")).upper()
        for item in normalized.get("findings", [])
        if isinstance(item, Mapping) and CVE.fullmatch(str(item.get("id")).upper())
    )
    return ids


def _present(value):
    return value is not None and str(value).strip().casefold() not in {
        "",
        "null",
        "none",
        "n/a",
        "unknown",
        "-",
    }


def _timestamp(value):
    try:
        return isinstance(value, (datetime, date)) or bool(parse_date(str(value)))
    except (TypeError, ValueError, OverflowError):
        return False


def _data(fields, normalized):
    try:
        valid_address = bool(ip_address(str(fields.get("ip") or "")))
        valid_root = bool(HOSTNAME.fullmatch(str(fields.get("hostname") or "")))
    except ValueError:
        valid_address = valid_root = False
    complete = all(_present(fields.get(key)) for key in ("ip", "hostname", "region", "tag"))
    value = 0.625 if complete and valid_address and valid_root else 0
    timed = _timestamp(normalized.get("scan_timestamp") or fields.get("timestamp"))
    if timed:
        value += 0.25
    source_hash = normalized.get("source_sha256")
    port = fields.get("port")
    try:
        endpoint = not isinstance(port, bool) and str(port).isdigit() and 1 <= int(port) <= 65535
    except (ValueError, TypeError, OverflowError):
        endpoint = False
    provenance = (
        isinstance(source_hash, str)
        and len(source_hash) == 64
        and all(c in "0123456789abcdef" for c in source_hash)
    )
    if endpoint or provenance:
        value += 0.125
    return value, (
        "Complete source identity"
        if complete and valid_address and valid_root
        else "Incomplete source identity"
    ) + ("; dated observation" if timed else "; observation time unknown") + (
        "; source or endpoint traceable" if endpoint or provenance else ""
    )


def _finding(fields, normalized, records):
    products = normalized.get("products") or []
    if any(
        isinstance(p, Mapping) and _present(p.get("product")) and _present(p.get("version"))
        for p in products
    ):
        return (
            1.0,
            "Explicit observed product and software version; applicability still requires evidence",
        )
    profile = normalized.get("profile") or {}
    if (
        profile.get("capability") == "eligible"
        and profile.get("version_requirement") in {"none", "not_required", "eol_only"}
        and not _ids(fields, normalized)
    ):
        return 0.85, "Supported finding profile does not require a software version"
    ids = _ids(fields, normalized)
    if any(records.get(identifier, {}).get("status") == "available" for identifier in ids):
        return (
            0.75,
            "Reported CVE resolves in the local catalog; affected-version match is not established",
        )
    if _present(normalized.get("raw_version", selected_version(fields, profile)["raw_version"])):
        return 0.75, "Observed version text retained; product applicability is not established"
    if ids:
        return 0.5, "CVE identifier reported; local reference is unavailable or unresolved"
    if profile.get("capability") == "eligible":
        return 0.5, "Recognized service or incident finding"
    return 0.0, "No supported finding detail"


def _entity(association, root):
    if isinstance(association, (tuple, list)) and len(association) >= 3:
        state, basis = association[1], association[2]
    elif isinstance(association, Mapping):
        state, basis = association.get("status", association.get("state")), association.get("basis")
    else:
        state, basis = None, None
    if state == "known" and basis == "qualified":
        return 1.0, "Domain attribution passed qualification"
    if state == "known" and basis in {
        "hostname",
        "saved_ip",
        "rdap",
        "root_domain",
        "Stored hostname association",
        "Saved entity IP association",
    }:
        return 1.0, "Existing explicit entity association: " + str(basis)
    if state == "review":
        return 0.0, "Entity association is ambiguous; shared IP does not establish ownership"
    return (
        (0.5, "Registrable domain is identifiable; organization attribution is not established")
        if root and HOSTNAME.fullmatch(root)
        else (0.0, "Entity identity unavailable")
    )


def score_lead(
    entries,
    *,
    root_domain=None,
    association=None,
    cve_records=None,
    policy=None,
    as_of=None,
    priority=None,
):
    """Score retained observations without mutating inputs or performing I/O."""
    policy = normalize_policy(policy)
    parsed = [
        (fields, normalized)
        for fields, normalized in map(_entry, entries)
        if has_active_findings({"normalized": normalized})
    ]
    if root_domain is None and parsed:
        root_domain = registered_root(str(parsed[0][0].get("hostname") or ""))
    ids, embedded, captured = set(), {}, {}
    for fields, normalized in parsed:
        row_ids = _ids(fields, normalized)
        ids.update(row_ids)
        if cve_records is None:
            for identifier in row_ids:
                item = validated_cve(
                    identifier, (normalized.get("accretion_cves") or {}).get(identifier)
                )
                order = snapshot_order(item)
                if identifier not in captured or order > captured[identifier]:
                    embedded[identifier], captured[identifier] = item, order
    vetted = [
        validated_cve(identifier, cve_records.get(identifier))
        if cve_records is not None
        else embedded[identifier]
        for identifier in sorted(ids)
    ]
    records = {item["id"]: item for item in vetted}
    # Withdrawn findings remain visible in evidence; they must not lend their
    # old reported critical label to a different observation that opened a group.
    parsed = [
        (fields, normalized)
        for fields, normalized in parsed
        if (normalized.get("eligibility") or {}).get("reason") != "withdrawn_cve_only"
        and not (
            (row_ids := _ids(fields, normalized))
            and all(records[identifier]["status"] == "rejected" for identifier in row_ids)
            and not has_independent_finding(fields, normalized.get("profile") or {})
        )
    ]
    qweights = policy["quality_weights"]
    data = max((_data(f, n) for f, n in parsed), default=(0.0, "No observations"))
    finding = max((_finding(f, n, records) for f, n in parsed), default=(0.0, "No observations"))
    entity = _entity(association, root_domain) if parsed else (0.0, "No observations")
    qfactors = [
        _factor(key, label, value[0], qweights[key], value[1])
        for key, label, value in (
            ("data", "Data", data),
            ("finding", "Finding", finding),
            ("entity", "Entity", entity),
        )
    ]
    best = strongest_finding(
        [(fields, normalized, _ids(fields, normalized)) for fields, normalized in parsed],
        records,
        policy,
        priority,
    )
    ufactors = best[3]
    quality, urgency = (
        round(sum(f["points"] for f in qfactors), 1),
        round(sum(f["points"] for f in ufactors), 1),
    )
    aggregate = round(
        (
            quality * policy["aggregate_weights"]["quality"]
            + urgency * policy["aggregate_weights"]["urgency"]
        )
        / 100,
        1,
    )
    from modules.leads.components.provider_policy import is_provider

    adjustments = []
    if parsed and (
        is_provider(root_domain) or all(is_provider(fields.get("hostname")) for fields, _ in parsed)
    ):
        multiplier = policy["provider_outreach_multiplier"]
        base = aggregate
        aggregate = round(base * multiplier, 1)
        adjustments.append(
            {
                "id": "provider_outreach",
                "label": "ISP outreach priority",
                "base_aggregate": base,
                "multiplier": multiplier,
                "points": round(aggregate - base, 1),
                "reason": "Provider-owned domain; reduced agency outreach priority. Evidence quality and vulnerability metrics are unchanged.",
            }
        )
    temperature = TEMPERATURES[
        sum(aggregate >= threshold for threshold in policy["temperature_thresholds"])
    ]
    warnings = sorted({warning for item in vetted for warning in item.get("warnings", [])})
    return {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "policy_hash": policy_hash(policy),
        "policy": policy,
        "scored_at": score_stamp(as_of) if as_of is not None else None,
        "quality": quality,
        "urgency": urgency,
        "aggregate": aggregate,
        "ranking_adjustments": adjustments,
        "temperature": temperature,
        "factors": {"quality": qfactors, "urgency": ufactors},
        "strongest_finding": {"id": best[1], "basis": best[2], "score": round(best[0], 1)}
        if parsed
        else None,
        "cves": vetted,
        "warnings": warnings,
    }


def score_leads(
    groups,
    *,
    workspace_root=None,
    cve_records=None,
    associations=None,
    policy=None,
    as_of=None,
    priorities=None,
):
    """Score a batch after at most one local vetting call; never fetch remotely."""
    if isinstance(groups, Mapping):
        groups = {root: list(entries) for root, entries in groups.items()}
    else:
        groups = {group.root_domain: list(group.observations) for group in groups}
    if cve_records is None and workspace_root is not None:
        ids = set()
        for entries in groups.values():
            for entry in entries:
                ids.update(_ids(*_entry(entry)))
        cve_records = vet_cves(workspace_root, ids, as_of=as_of)
    return {
        root: score_lead(
            entries,
            root_domain=root,
            association=(associations or {}).get(root),
            cve_records=cve_records,
            policy=policy,
            as_of=as_of,
            priority=(priorities or {}).get(root),
        )
        for root, entries in groups.items()
    }
