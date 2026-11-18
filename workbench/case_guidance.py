"""Batched, saved-record guidance for the daily work queue.

This is a next-step projection, not a certification decision. It never builds
a report, opens evidence files, hashes packages, fetches sources or writes
staleness events. Final review/certification performs those deeper checks.
"""

from collections import defaultdict
import json

from .case_conditions import project
from .intake.versions import entry_fields, has_active_findings
from .intelligence.identifiers import identifiers
from .intelligence_index import notification_records
from .report_composition import attribution_url, resolved_record
from .reviews.policy import SECTIONS


def saved_case_facts(db, case_ids=None):
    """Read each working case's saved scope/review facts in three bulk queries."""
    facts = defaultdict(lambda: {"entries": [], "groups": [], "sections": {}})
    if case_ids is not None and not case_ids:
        return facts
    scope = " AND c.id IN (SELECT value FROM json_each(?))" if case_ids is not None else ""
    args = (json.dumps(list(case_ids)),) if case_ids is not None else ()
    for row in db.execute(
        """SELECT ce.case_id,e.id,e.root_domain,e.payload,cc.conditions
        FROM cases c JOIN case_entries ce ON ce.case_id=c.id
        JOIN entries e ON e.id=ce.entry_id
        LEFT JOIN case_entry_conditions cc ON cc.case_id=c.id AND cc.entry_id=e.id
        WHERE c.stage='in_progress'"""
        + scope,
        args,
    ):
        entry = {
            **json.loads(row["payload"]),
            "id": row["id"],
            "_guidance_root": row["root_domain"],
        }
        if row["conditions"] is not None:
            entry = project(entry, json.loads(row["conditions"]))
        facts[row["case_id"]]["entries"].append(entry)
    for row in db.execute(
        """SELECT g.case_id,g.root_domain,g.attribution FROM case_groups g
        JOIN cases c ON c.id=g.case_id WHERE c.stage='in_progress'"""
        + scope,
        args,
    ):
        facts[row["case_id"]]["groups"].append(
            {"root_domain": row["root_domain"], "attribution": json.loads(row["attribution"])}
        )
    for row in db.execute(
        """SELECT e.case_id,e.section_key,e.action,e.validation_id,
        EXISTS(SELECT 1 FROM section_events stale
          WHERE stale.case_id=e.case_id AND stale.section_key=e.section_key
          AND stale.validation_id=e.validation_id AND stale.action='stale') AS stale
        FROM section_events e
        JOIN (SELECT se.case_id,se.section_key,MAX(se.id) id FROM section_events se
          JOIN cases c ON c.id=se.case_id
          WHERE c.stage='in_progress' AND se.action IN ('validated','reopened')"""
        + scope
        + """
          GROUP BY se.case_id,se.section_key) latest ON latest.id=e.id""",
        args,
    ):
        facts[row["case_id"]]["sections"][row["section_key"]] = (
            "stale" if row["stale"] else "validated" if row["validation_id"] else "draft"
        )
    return facts


def working_case_signals(facts, draft):
    """Current recipient scope controls working-case source signals.

    The saved intake score is historical and deliberately not recalculated.
    """
    from .observation_scope import report_entries

    entries = [
        entry for entry in report_entries(facts["entries"], draft) if has_active_findings(entry)
    ]
    cves = set(identifiers(entry_fields(entry).get("tag", "") for entry in entries))
    selected = [record for record in notification_records(draft) if record.get("id") in cves]
    critical = any(
        str(entry_fields(entry).get("severity", "")).lower() == "critical" for entry in entries
    )
    return selected, critical


def working_case_action(facts, draft, identity, settings):
    """Return the first actionable saved blocker without certifying readiness."""
    from .observation_scope import report_entries, address_issue
    from .sender_identity import effective_settings, profile_issue

    entries = report_entries(facts["entries"], draft)
    active = [entry for entry in entries if has_active_findings(entry)]
    anomalies = [entry for entry in entries if address_issue(entry)]
    if not active:
        return (
            "Include a supported observation or close without notification",
            "notification",
            "Vulnerabilities",
            "report_scope",
        )
    if anomalies:
        return (
            f"Review {len(anomalies)} non-public or invalid IP observation{'s' if len(anomalies) != 1 else ''}",
            "notification",
            "Vulnerabilities",
            "report_scope",
        )
    sender_issue = profile_issue(draft, settings)
    if sender_issue:
        return sender_issue, "notification", "Introduction", "sender"
    sender_settings = effective_settings(settings, draft)
    if not (sender_settings.get("analyst_name") or "").strip():
        return (
            "Set the analyst name before validating the report",
            "notification",
            "Introduction",
            "sender",
        )
    if not (draft.get("company") or identity.get("company") or "").strip():
        return "Identify the business for this report", "notification", "Introduction", "company"
    roots = {entry["_guidance_root"] for entry in active if entry.get("_guidance_root")}
    # Groups may have no normalized hostname in legacy imports. Retain every
    # pinned attribution group rather than omitting a possibly required root.
    groups = [g for g in facts["groups"] if not roots or g["root_domain"] in roots]
    if not groups or any(
        not (
            g["attribution"].get("ip")
            and g["attribution"].get("retrieved_at")
            and attribution_url(g["attribution"].get("source_url"))
        )
        for g in groups
    ):
        return "Review missing qualified attribution", "notification", "Attribution", "attribution"
    unresolved = [
        cve
        for cve in identifiers(entry_fields(entry).get("tag", "") for entry in active)
        if resolved_record(cve, draft)[1] == "unresolved"
    ]
    if unresolved:
        shown = ", ".join(unresolved[:3])
        remainder = f" and {len(unresolved) - 3} more" if len(unresolved) > 3 else ""
        return (
            "Resolve CVE source or disposition: " + shown + remainder,
            "notification",
            "Vulnerabilities",
            "cve_reference",
        )
    sections = facts["sections"]
    stale = [SECTIONS[key] for key in SECTIONS if sections.get(key) == "stale"]
    if stale:
        return (
            "Reopen and review changed section: " + stale[0],
            "notification",
            stale[0],
            "stale_section",
        )
    remaining = [SECTIONS[key] for key in SECTIONS if sections.get(key) != "validated"]
    if remaining:
        return "Review and freeze " + remaining[0], "notification", remaining[0], "section_review"
    return (
        "Review the final preview and certify the report",
        "notification",
        "Closing",
        "certification",
    )
