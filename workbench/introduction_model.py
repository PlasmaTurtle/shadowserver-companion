"""Versioned notification introduction composed from saved report values.

Historical drafts retain their wording and layout until explicit adoption.
No source requests or current-date substitutions occur during composition.
"""

from copy import deepcopy
from datetime import datetime
from functools import lru_cache
from pathlib import Path
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .intake.versions import entry_fields, has_active_findings

PREVIOUS_REVISION = "introduction-2026-11-07-review-1"
NOTIFICATION_REVISION = "introduction-2026-11-13-notification-1"
REVISION = "introduction-2026-11-13-notification-2"
SUPPORTED_REVISIONS = frozenset((PREVIOUS_REVISION, NOTIFICATION_REVISION, REVISION))
PREVIOUS_SUBJECT = "Shadow Server Cyber Security Vulnerabilities – Notification"
SUBJECT = "Shadowserver - Cybersecurity Vulnerability Notification"
INTRO = (
    "The United States Secret Service Charlotte Cyber Fraud Task Force (CFTF) is reaching out "
    "to notify you of a potential cybersecurity vulnerability associated with the system listed "
    "below. This notification is part of our ongoing effort to help organizations safeguard "
    "their infrastructure and prevent cyber-enabled financial crime. The underlying data was "
    "provided by the Shadowserver Foundation, a nonprofit security organization that monitors "
    "the global Internet for vulnerabilities. Please let us know if you have any questions."
)


def _unique(values):
    return list(dict.fromkeys(v for v in values if v not in (None, "")))


@lru_cache(maxsize=1)
def office_timezone():
    try:
        return ZoneInfo("America/New_York")
    except ZoneInfoNotFoundError:
        # Windows' embedded CPython has no system IANA database. The reviewed
        # TZif fallback is bundled with its license, version and content hash.
        path = Path(__file__).resolve().parents[1] / "resources/timezones/America_New_York.tzif"
        with path.open("rb") as stream:
            return ZoneInfo.from_file(stream, key="America/New_York")


def display_time(value):
    """Convert explicit instants to office time; do not guess a missing zone."""
    if not value:
        return "Not supplied"
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    if stamp.tzinfo is None:
        return str(value) + " (source time; zone not supplied)"
    local = stamp.astimezone(office_timezone())
    return local.strftime("%b ") + str(local.day) + local.strftime(", %Y · %I:%M %p %Z")


def _finding_scope(entries, summary):
    """Scope the cover to current findings; retain proof-only rows elsewhere.

    Summary appendix identifiers already align with the full observation order.
    Filtering those associations preserves product normalization and source
    identity without rebuilding the retained evidence or changing its meaning.
    """
    active = [index for index, entry in enumerate(entries) if has_active_findings(entry)]
    if len(active) == len(entries):
        return entries, summary
    selected = [entries[index] for index in active]
    summary = deepcopy(summary)
    retained_ids = summary["appendix_entry_ids"]
    ids = {retained_ids[index] for index in active}
    ip_by_id = {
        retained_ids[index]: str(
            entries[index].get("ip") or entry_fields(entries[index]).get("ip") or ""
        )
        for index in active
    }
    groups = []
    for group in summary["groups"]:
        matches = [
            (observation, appendix_id)
            for observation, appendix_id in zip(
                group["observation_ids"], group["appendix_entry_ids"], strict=True
            )
            if appendix_id in ids
        ]
        if matches:
            group.update(
                value=len(matches),
                observation_ids=[observation for observation, _ in matches],
                appendix_entry_ids=[appendix_id for _, appendix_id in matches],
                ip_addresses=_unique(ip_by_id[appendix_id] for _, appendix_id in matches),
            )
            groups.append(group)
    fields = [entry_fields(entry) for entry in selected]
    endpoints = {
        (
            str(entry.get("ip") or row.get("ip") or ""),
            str(row.get("protocol", "")),
            str(row.get("port", "")),
            str(entry.get("endpoint_role") or row.get("endpoint_role") or "reported"),
        )
        for entry, row in zip(selected, fields, strict=True)
    }
    dates = sorted(str(row["timestamp"]) for row in fields if row.get("timestamp"))
    for item, value in zip(
        summary["counts"][:3],
        (len(_unique(ip_by_id.values())), len(endpoints), len(selected)),
        strict=True,
    ):
        item["value"] = value
    summary["counts"][3]["value"] = len(
        {
            match.upper()
            for row in fields
            for match in re.findall(r"CVE-\d{4}-\d{4,}", str(row.get("tag", "")), re.I)
        }
    )
    summary.update(
        groups=groups,
        appendix_entry_ids=[value for value in retained_ids if value in ids],
        reporting_period={
            "first": dates[0] if dates else None,
            "last": dates[-1] if dates else None,
        },
    )
    return selected, summary


def build_introduction(data, exhibits):
    """One bounded presentation model; complete records remain in the appendix."""
    draft, profile = data["draft"], data["profile"]
    from .notification_narrative_v4 import (
        SOURCE_AWARE_REVISIONS,
        severity_summary,
        has_non_http,
    )

    source_aware = draft.get("narrative_revision") in SOURCE_AWARE_REVISIONS
    revision = draft.get("introduction_revision", REVISION)
    current = revision in {NOTIFICATION_REVISION, REVISION}
    subject = SUBJECT if current else PREVIOUS_SUBJECT
    summary = next(e for e in exhibits if e["type"] == "summary")
    vulnerability = next(e for e in exhibits if e["type"] == "vulnerability")
    entries = [
        entry
        for group in data.get("qualified_lead", {}).get("validated_leads", [])
        for entry in group.get("entries", [])
    ]
    supporting = 0
    if current and entries:
        selected, summary = _finding_scope(entries, summary)
        supporting = len(entries) - len(selected)
        entries = selected
    rows = [
        {
            **entry.get("source", {}).get("fields", {}),
            "ip": entry.get("ip") or entry.get("source", {}).get("fields", {}).get("ip", ""),
        }
        for entry in entries
    ]
    if not rows and not supporting:
        rows = deepcopy(data.get("assets", []))
    pairs = {}
    for row in rows:
        key = (str(row.get("ip") or "Not supplied"), str(row.get("hostname") or "Not supplied"))
        asset = pairs.setdefault(key, {"ip": key[0], "hostname": key[1], "networks": []})
        location = row.get("location") or ", ".join(
            str(row[k]) for k in ("city", "region", "geo") if row.get(k)
        )
        network = " · ".join(
            filter(None, ["AS" + str(row["asn"]) if row.get("asn") else "", location])
        )
        if network and network not in asset["networks"]:
            asset["networks"].append(network)
    assets = list(pairs.values())
    proofs = data.get("qualified_lead", {}).get("whois", [])
    primary_ip = proofs[0].get("ip") if proofs else None
    primary = next((a for a in assets if a["ip"] == primary_ip), assets[0] if assets else None)
    ips = _unique(a["ip"] for a in assets)
    hosts = _unique(a["hostname"] for a in assets)
    # Only source-backed positive KEV assertions are promoted to the first page.
    # An unavailable/absent/false value never becomes a negative assurance.
    kev = [
        i
        for i in vulnerability["items"]
        if i.get("kev") is True and any(i.get("claim_citations", {}).get("kev", []))
    ]
    findings = [i for i in vulnerability["items"] if i.get("finding_type") == "cve"]
    if supporting:
        current_cves = {
            match.upper()
            for entry in entries
            for match in re.findall(
                r"CVE-\d{4}-\d{4,}", str(entry_fields(entry).get("tag", "")), re.I
            )
        }
        findings = [item for item in findings if item["label"] in current_cves]
        kev = [item for item in kev if item["label"] in current_cves]
    kev_versions = {v for i in kev for v in i.get("reported_versions", [])}
    period = summary["reporting_period"]
    first = period.get("first") or (
        None
        if supporting
        else next(
            (a.get("first_seen") for a in data.get("assets", []) if a.get("first_seen")), None
        )
    )
    last = period.get("last") or first
    observed = display_time(first)
    if last and last != first:
        observed += " to " + display_time(last)
    recipient_guidance = {}
    if revision == REVISION:
        sender = draft.get("sender_profile") or {}
        route = str(sender.get("outreach_verification_route") or "").strip()
        recipient_guidance = {
            "recipient_action": "First action: Ask your IT contact to confirm the reported assets and review the technical findings.",
            "recipient_reply": str(sender.get("email") or "").strip(),
            "recipient_verification": route
            if len(route) <= 180
            else "See Recommended Resources for the configured independent verification route.",
        }
    return {
        **recipient_guidance,
        "revision": revision,
        "layout_revision": 2 if current else 1,
        **(
            {
                "report_date": draft.get("report_date", ""),
                "severity_from_source": source_aware,
            }
            if current
            else {}
        ),
        "agency": [profile["department"], profile["agency"].upper(), profile["office"]],
        "marking": "For Informational Purposes Only",
        "to": "\n".join(
            filter(None, [draft.get("contact_name"), draft.get("company"), draft.get("address")])
        ),
        "sender": "\n".join(
            filter(
                None,
                [
                    draft.get("sender_name"),
                    draft.get("sender_title"),
                    profile["agency"],
                    profile["office"],
                ],
            )
        ),
        "subject": draft.get("subject", subject) if source_aware else subject,
        "asset_line": primary["ip"] + " | " + primary["hostname"]
        if primary
        else "No reported asset supplied",
        "additional_assets": (
            f"{len(ips)} reported IPs · {len(hosts)} hostnames · "
            + (
                "full inventory available upon request"
                if draft.get("include_appendix", True) is False
                else "full inventory in Appendix A"
            )
            if len(assets) > 1
            else ""
        ),
        "intro": draft.get("intro", INTRO) if source_aware else INTRO,
        "severity": severity_summary(data)
        if source_aware
        else draft.get("severity") or "Not specified",
        "observed": observed,
        "assets": assets,
        "counts": deepcopy(summary["counts"]),
        "groups": sorted(
            deepcopy(summary["groups"]),
            key=lambda g: (
                g["label"] not in kev_versions,
                -len(g.get("ip_addresses", [])),
                g["label"],
                g.get("detail", ""),
            ),
        ),
        "findings": [
            {"id": i["label"], "versions": i.get("reported_versions", [])} for i in findings
        ],
        "kev": [
            {"id": i["label"], "citations": [n for n in i["claim_citations"]["kev"] if n]}
            for i in kev
        ],
        "eol_count": sum(i.get("finding_type") == "eol" for i in vulnerability["items"]),
        "summary_id": summary["id"],
        "appendix_entry_ids": deepcopy(summary["appendix_entry_ids"]),
        "demo": bool(data.get("demo")),
        **(
            {
                "scope_note": "This summary covers current findings. Earlier observations used for attribution remain in the supporting records."
            }
            if supporting
            else {}
        ),
        **(
            {
                "supporting_records_note": "Full observations and supporting records are available upon request."
            }
            if source_aware and has_non_http(data)
            else {}
        ),
    }
