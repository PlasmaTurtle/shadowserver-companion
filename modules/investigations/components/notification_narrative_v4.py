"""Deterministic, source-aware narratives without upgrading evidence claims.

The established HTTP wording and emailed row-date-plus-one rule remain pinned.
Exposure reports describe reachability; incident reports describe reported
indicators. Report names, protocol versions and default severities never become
proof of a software vulnerability or successful compromise.
"""

from modules.accretion.components.intake.versions import entry_fields
from collections import OrderedDict
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import re

from modules.investigations.components import approved_template as approved
from .notification_narrative import (
    GROUP_FIELDS,
    MONTHS,
    generate_narrative as generate_v3,
    presentation_groups,
    scan_date,
)
from .notification_narrative_v2 import findings, joined, scopes

REVISION = "source-aware-2026-11-10-v4"
REPORT_STARTED_REVISION = "report-start-2026-11-12-v5"
SOURCE_AWARE_REVISIONS = frozenset((REVISION, REPORT_STARTED_REVISION))
HTTP_TYPES = frozenset(("scan_http_vulnerable", "scan6_http_vulnerable"))
FAMILIES = {
    "http_vulnerable": ("Vulnerable HTTP", "vulnerability", "software"),
    "smtp_vulnerable": ("Vulnerable SMTP", "vulnerability", "software"),
    "exchange": ("Vulnerable Exchange Server", "vulnerability", "software"),
    "isakmp": ("Vulnerable ISAKMP", "vulnerability", "protocol"),
    "badsecrets": ("Badsecrets", "weak_secret", "unspecified"),
    "rdp": ("Accessible RDP", "exposure", "protocol"),
    "mongodb": ("Open MongoDB Service", "exposure", "software"),
    "msrpc": ("Accessible MS-RPC Service", "exposure", "protocol"),
}


def source_context(entry):
    from .report_explainers import canonical_source_types

    source_id = next(iter(canonical_source_types({"entries": [entry]})), "unclassified")
    ipv6 = source_id.startswith("scan6_") or source_id.endswith("6")
    base = source_id.removeprefix("scan6_").removeprefix("scan_")
    if source_id in {"compromised_website", "compromised_website6"}:
        title, kind, semantics = "Compromised Website", "compromise_indicator", "unspecified"
    elif source_id in {"compromised_iot", "compromised_iot6"}:
        title, kind, semantics = "Compromised IoT Device", "compromise_indicator", "unspecified"
    else:
        title, kind, semantics = FAMILIES.get(
            base, ("Reported observations", "observation", "unspecified")
        )
    if ipv6 and kind != "observation":
        title = "IPv6 " + title
    return {"id": source_id, "title": title, "kind": kind, "version_semantics": semantics}


def entries_from(data):
    return data.get("entries") or [
        entry
        for group in data.get("qualified_lead", {}).get("validated_leads", [])
        for entry in group.get("entries", [])
    ]


def has_non_http(data):
    entries = entries_from(data)
    return bool(entries) and any(source_context(entry)["id"] not in HTTP_TYPES for entry in entries)


def date_basis_issue(lead):
    return any(
        entry.get("normalized", {}).get("acquisition", {}).get("kind") == "shadowserver_api_receipt"
        and entry["normalized"]["acquisition"].get("narrative_date_basis") != "emailed_row_plus_one"
        for entry in lead.get("entries", [])
    )


def _included(lead, draft):
    groups = {group["key"]: group for group in presentation_groups(lead, draft)}
    selected, members = [], OrderedDict()
    for entry in lead.get("entries", []):
        fields = entry_fields(entry)
        values = [str(fields.get(key, "") or "") for key in GROUP_FIELDS]
        key = hashlib.sha256("\0".join(values).encode()).hexdigest()[:16]
        if key not in groups:
            continue
        context = source_context(entry)
        original = groups[key]
        if original.get("excluded"):
            if context["kind"] not in {"exposure", "weak_secret", "compromise_indicator"}:
                continue
            # Excluding a CVE does not erase independently reported exposure or
            # incident indicators from the same source observation.
            original = {
                **original,
                "excluded": False,
                "tag": approved.CVE.sub("", original["tag"]).strip(" ;,"),
            }
        selected.append(entry)
        member = members.setdefault(
            (key, context["id"]), {**deepcopy(original), "ips": [], "context": context}
        )
        ip = str(entry.get("ip") or fields.get("ip") or "")
        if ip and ip not in member["ips"]:
            member["ips"].append(ip)
    return {**lead, "entries": selected}, list(members.values())


def reported_severity(lead, draft):
    selected, _ = _included(lead, draft)
    names = {
        "critical": "Critical",
        "high": "High",
        "medium": "Medium",
        "low": "Low",
        "info": "Informational",
        "informational": "Informational",
    }
    seen = set()
    for entry in selected["entries"]:
        raw = (
            str(entry.get("source", {}).get("fields", {}).get("severity") or "").strip().casefold()
        )
        seen.add(names.get(raw, "Not supplied"))
    ordered = [
        name
        for name in ("Critical", "High", "Medium", "Low", "Informational", "Not supplied")
        if name in seen
    ]
    return "; ".join(ordered) or "Not supplied"


def apply_copy(lead, draft):
    """Only this revision changes subject/intro and source-derived severity."""
    summary = reported_severity(lead, draft)
    # The saved editor field is a single-value API enum. Mixed/unknown source
    # severities remain a derived display summary, never an invented aggregate.
    draft["severity"] = (
        summary
        if summary in {"Informational", "Low", "Medium", "High", "Critical"}
        else "Not specified"
    )
    if has_non_http(lead):
        draft["subject"] = "Shadowserver - Cybersecurity Notification"
        draft["intro"] = (
            "The United States Secret Service Charlotte Cyber Fraud Task Force (CFTF) is reaching out "
            "to share cybersecurity observations associated with the system listed below. This notification "
            "is part of our ongoing effort to help organizations safeguard their infrastructure and prevent "
            "cyber-enabled financial crime. The underlying data was provided by the Shadowserver Foundation, "
            "a nonprofit security organization that monitors the global internet for security exposures and "
            "malicious activity. Please let us know if you have any questions."
        )
    return draft


def severity_summary(data):
    """Display all retained source severities without widening the draft API."""
    draft = data["draft"]
    if draft.get("narrative_revision") not in SOURCE_AWARE_REVISIONS:
        return draft.get("severity") or "Not specified"
    return reported_severity({**data, "entries": entries_from(data)}, draft)


def _opening(lead):
    dated, undated = OrderedDict(), []
    for entry in lead["entries"]:
        fields = entry_fields(entry)
        observed = scan_date(fields.get("timestamp"))
        ip = str(entry.get("ip") or fields.get("ip") or "")
        if observed is not None and observed != date.max:
            dated.setdefault(observed + timedelta(days=1), []).append(ip)
        else:
            undated.append(ip)
    prefix = ""
    if dated:
        prefix = (
            "On "
            + joined(f"{MONTHS[day.month - 1]} {day.day}, {day.year}" for day in sorted(dated))
            + ", "
        )
    ips = joined(ip for values in dated.values() for ip in values) if dated else joined(undated)
    text = (
        prefix
        + ("the" if prefix else "The")
        + " United States Secret Service, Charlotte Cyber Fraud Task Force, received a Shadowserver Notification related to reported security observations detected on "
        + ips
        + "."
    )
    if undated:
        text += (
            (" A valid scan date was not supplied for " + joined(undated) + ".")
            if dated
            else " The supplied observations do not include a valid scan date."
        )
    return text


def generate_narrative(lead, draft, *, opening_text=None):
    selected, groups = _included(lead, draft)
    if not groups:
        return ""
    if not has_non_http(selected) and (opening_text is not None or not date_basis_issue(selected)):
        text = generate_v3(lead, draft, opening_text=opening_text)
        if reported_severity(lead, draft) != "Critical":
            text = (
                text.replace("a critical security finding", "a reported security finding")
                .replace("critical security findings", "reported security findings")
                .replace(
                    "critical vulnerability handling procedures",
                    "your organization's vulnerability handling procedures",
                )
            )
        return text
    if opening_text is not None:
        first = opening_text
    elif date_basis_issue(selected):
        first = (
            "The United States Secret Service, Charlotte Cyber Fraud Task Force, is reviewing "
            "Shadowserver observations associated with "
            + joined(ip for group in groups for ip in group["ips"])
            + "."
        )
    else:
        first = _opening(selected)
    statements = [first]
    for group in groups:
        context = group["context"]
        kind = context["kind"]
        labels = joined(findings(group)) or "no tag supplied"
        if (
            kind == "exposure"
            and "mongodb-noauth" in re.split(r"[;,\s]+", group["tag"].casefold())
            and "mongodb-noauth" not in labels.casefold()
        ):
            labels += " and mongodb-noauth"
        scope = scopes([group], detailed=True)
        if kind == "compromise_indicator":
            claim = "records indicators of possible compromise"
        elif kind == "exposure":
            claim = "records an internet-reachable service"
        elif kind == "weak_secret":
            claim = "flags a potentially weak application secret"
        elif kind == "vulnerability":
            claim = "flags a potential security weakness"
        else:
            claim = "records a security observation"
        statements.append(
            f"The {context['title']} report {claim} on {scope}; the reported finding is {labels}."
        )
        if group["version"] and context["version_semantics"] == "software":
            statements.append(
                "The reported software version for " + scope + " is " + group["version"] + "."
            )
        elif group["version"] and context["version_semantics"] == "protocol":
            statements.append(
                "The reported protocol version for " + scope + " is " + group["version"] + "."
            )
        if group.get("affected_versions") and group.get("cves"):
            statements.append(
                "The selected published affected-version information is "
                + group["affected_versions"]
                + ". Applicability requires confirmation against the installed product and build."
            )
    kinds = {group["context"]["kind"] for group in groups}
    if "exposure" in kinds:
        statements.append(
            "Service reachability alone does not establish unauthorized access or a software vulnerability."
        )
    if "compromise_indicator" in kinds:
        statements.append(
            "These reported indicators warrant prompt technical review to determine their cause, current status and scope."
        )
    profile = approved.entity_profile(lead)
    location = ", ".join(str(profile[key]).strip() for key in ("city", "state") if profile.get(key))
    organization = (
        draft.get("company")
        or lead.get("company")
        or lead.get("domain")
        or "the recipient organization"
    )
    statements.append(
        "Publicly available information reviewed for this notification associates the reported assets with "
        + organization
        + (" in " + location if location else "")
        + "."
    )
    statements.append(
        "We recommend review with the responsible technical personnel to confirm the reported conditions and determine an appropriate response."
    )
    return " ".join(" ".join(statements).split())
