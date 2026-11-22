"""Recipient observation scope, independent of retained source evidence.

Ordinary rows stay included until an analyst records an exclusion. Public-scan
address anomalies remain visible and block certification until excluded; an
operator reason never turns a nonpublic address into evidence of public exposure.
"""

from copy import deepcopy
from datetime import datetime

from modules.accretion.components.intake.versions import entry_fields, has_active_findings
from modules.tools.components.network_identity import comparison_address

SCOPE_FIELDS = ("observation_scope", "observation_scope_archive")


def address_issue(entry):
    value = str(entry.get("ip") or entry_fields(entry).get("ip") or "").strip()
    try:
        if "%" in value:
            raise ValueError("Scoped address")
        address = comparison_address(value)
    except ValueError:
        return "Invalid or missing IP address"
    if not address.is_global or address.is_multicast or address.is_reserved:
        return "Private, reserved, or otherwise nonpublic IP address"
    return ""


def validate_saved_scope(draft, entry_ids):
    """Validate authoritative saved decisions, including imported workspaces."""
    decisions = draft.get("observation_scope", {})
    if not isinstance(decisions, dict) or len(decisions) > 10000:
        raise ValueError("Saved observation scope is invalid")
    if not set(decisions) <= set(entry_ids):
        raise ValueError("Saved observation scope refers to an observation outside this case")
    for decision in decisions.values():
        if not isinstance(decision, dict) or decision.get("decision") not in {"include", "exclude"}:
            raise ValueError("Saved observation scope decision is invalid")
        for key, limit in (("reason", 5000), ("actor", 300), ("decided_at", 100)):
            value = decision.get(key)
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                raise ValueError("Saved observation scope needs its reason, analyst and time")
        try:
            stamp = datetime.fromisoformat(decision["decided_at"].replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                raise ValueError("Missing time zone")
        except ValueError as error:
            raise ValueError("Saved observation scope time is invalid") from error
    archive = draft.get("observation_scope_archive", {})
    fields = {
        "cve_records",
        "cve_dispositions",
        "selected_ssvc_assessments",
        "report_explainer_snapshots",
        "finding_explainer_snapshots",
        "narrative_values",
    }
    if not isinstance(archive, dict) or not set(archive) <= fields:
        raise ValueError("Saved observation scope source archive is invalid")
    for key, items in archive.items():
        kind = str if key == "selected_ssvc_assessments" else dict
        if (
            not isinstance(items, dict)
            or len(items) > 10000
            or any(
                not isinstance(name, str) or not isinstance(value, kind)
                for name, value in items.items()
            )
        ):
            raise ValueError("Saved observation scope source archive is invalid")
        if key in {
            "cve_records",
            "report_explainer_snapshots",
            "finding_explainer_snapshots",
        } and any(value.get("id") != name for name, value in items.items()):
            raise ValueError("Saved observation scope source identity is invalid")
    return decisions


def report_entries(entries, draft):
    decisions = draft.get("observation_scope", {})
    return [
        entry
        for entry in entries
        if decisions.get(entry.get("id"), {}).get("decision") != "exclude"
    ]


def finding_entries(entries):
    """Supporting attribution rows alone are not findings to notify."""
    return [entry for entry in entries if has_active_findings(entry)]


def apply_scope(lead, draft=None):
    """Project included rows without deleting the case's full original scope."""
    draft = lead.get("draft", {}) if draft is None else draft
    original = lead.get("scope_source_entries", lead.get("entries", []))
    groups = lead.get("scope_source_groups", lead.get("domain_groups", []))
    decisions = validate_saved_scope(draft, [entry["id"] for entry in original])
    included = report_entries(original, draft)
    included_ids = {entry["id"] for entry in included}
    root_by_id = lead.get("scope_root_by_id", {})
    roots = {root_by_id[entry_id] for entry_id in included_ids if entry_id in root_by_id}
    active_groups = [group for group in groups if group["root_domain"] in roots]
    rows = []
    for entry in original:
        fields = entry_fields(entry)
        decision = decisions.get(entry["id"], {})
        included_row = entry["id"] in included_ids
        issue = address_issue(entry)
        rows.append(
            {
                "entry_id": entry["id"],
                "hostname": str(fields.get("hostname") or ""),
                "ip": str(entry.get("ip") or ""),
                "service": " ".join(
                    str(fields.get(key) or "") for key in ("protocol", "port")
                ).strip(),
                "finding": str(fields.get("tag") or "Supporting attribution observation"),
                "observed_at": str(fields.get("timestamp") or ""),
                "source": {
                    key: entry.get("source", {}).get(key) for key in ("workbook", "sheet", "row")
                },
                "included": included_row,
                "issue": issue,
                "requires_review": included_row and bool(issue),
                **deepcopy(decision),
            }
        )
    rows.sort(
        key=lambda row: (
            not row["requires_review"],
            not row["included"],
            row["hostname"],
            row["ip"],
            row["entry_id"],
        )
    )
    lead["scope_source_entries"] = original
    lead["scope_source_groups"] = groups
    lead["entries"] = included
    lead["domain_groups"] = active_groups
    lead["attribution_entry_id"] = (
        active_groups[0]["attribution_entry_id"] if active_groups else None
    )
    lead["attribution"] = active_groups[0]["attribution"] if active_groups else {}
    lead["hostnames"] = list(
        {
            str(entry_fields(entry).get("hostname") or ""): {
                "name": str(entry_fields(entry).get("hostname") or ""),
                "root_domain": root_by_id.get(entry["id"], ""),
            }
            for entry in included
        }.values()
    )
    lead["observation_scope"] = {
        "total": len(original),
        "included": len(included),
        "finding_observations": len(finding_entries(included)),
        "excluded": len(original) - len(included),
        "unresolved": sum(row["requires_review"] for row in rows),
        "rows": rows,
        "editable": lead.get("case", {}).get("stage") == "in_progress",
    }
    return lead


def scope_checks(lead):
    scope = lead.get("observation_scope")
    if scope is None:
        return []
    has_findings = bool(scope.get("finding_observations", scope["included"]))
    return [
        {
            "key": "observation_scope",
            "label": f"Exclude {scope['unresolved']} nonpublic or invalid source observation(s) from the recipient report; retain them internally with a reason"
            if scope["unresolved"]
            else "Recipient observation scope has no unresolved address anomalies",
            "ok": not scope["unresolved"],
        },
        {
            "key": "observation_scope_nonempty",
            "label": "At least one finding observation is included in this notification"
            if has_findings
            else "No finding observations are included; include a supported finding or close without notification",
            "ok": has_findings,
        },
    ]


def recipient_attribution_history(data):
    """Project lookup history to recipient addresses without changing its archive.

    Provider candidate and attempt lists can contain source rows that the analyst
    excluded. Keep the original result internally; only expose queries related
    to included observations or the original supporting proof in the appendix.
    """
    qualified = data.get("qualified_lead", {})
    values = [
        entry.get("ip")
        for group in qualified.get("validated_leads", [])
        for entry in group.get("entries", [])
    ] + [proof.get("ip") for proof in qualified.get("whois", [])]
    allowed = set()
    for value in values:
        try:
            allowed.add(comparison_address(value))
        except ValueError:
            pass

    def selected(item):
        if not item.get("ip"):
            return True
        try:
            return comparison_address(item["ip"]) in allowed
        except ValueError:
            return False

    result = []
    for record in data.get("attribution_history", []):
        item = deepcopy(record)
        trimmed = False
        for key in ("candidates", "attempts", "evidence", "partial_evidence"):
            if isinstance(item.get(key), list):
                original = item[key]
                item[key] = [row for row in original if selected(row)]
                trimmed |= len(item[key]) != len(original)
        if trimmed:
            item["recipient_scope"] = (
                "Only included observation and supporting proof addresses are shown; complete lookup history remains retained internally."
            )
        result.append(item)
    return result


def legacy_scope_warning(lead):
    """Warn about retained certified anomalies without revising historical truth."""
    case = lead.get("case", {})
    if not case.get("certified_report_id") or case.get("stage") == "in_progress":
        return None
    rows = [entry for entry in lead.get("entries", []) if address_issue(entry)]
    if not rows:
        return None
    addresses = sorted({str(entry.get("ip") or "Missing IP address") for entry in rows})
    examples = ", ".join(addresses[:5]) + (", …" if len(addresses) > 5 else "")
    next_action = (
        "Revise this report, review its scope, and recertify before further outreach."
        if case.get("stage") == "pending_notification"
        else "Start a new notification and review its scope before further outreach."
    )
    return {
        "count": len(rows),
        "addresses": addresses,
        "message": (
            f"This certified report retains {len(rows)} nonpublic or invalid source "
            f"observation(s): {examples}. {next_action} "
            "Its original certified files and recorded delivery history remain unchanged."
        ),
    }
