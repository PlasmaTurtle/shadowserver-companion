"""Approved draft defaults, hydration, and pre-certification readiness rules."""

from __future__ import annotations

from modules.accretion.components.intake.versions import entry_fields
from .notification_narrative_v5 import report_started_date

import re
from datetime import date
from modules.investigations.components import approved_template as approved
from .report_composition import resolved_record, attribution_url
from .report_layouts import adopt_current_layouts, apply_layout_copy, layout_defaults
from .notification_narrative import PRESENTATION_REVISIONS, presentation_groups
from modules.settings.components.sender_identity import (
    capture_profile,
    effective_settings,
    profile_issue,
)

CVE = re.compile(r"CVE-\d{4}-\d{4,}", re.I)
INTRO = approved.INTRO
NEXT_STEPS = approved.NEXT_STEPS
LIMITATION = approved.PARTNERSHIP
RESOURCES = approved.RESOURCES


def narrative_groups(lead, draft):
    """Use the same scoped findings for editor values, preview and save guards."""
    if draft.get("narrative_revision") in PRESENTATION_REVISIONS:
        return presentation_groups(lead, draft)
    return approved.narrative_groups(lead, draft)


def attribution_summary(evidence):
    lines = [
        f"Queried IP: {evidence['ip']}",
        f"Source: {evidence['registry']}",
        f"Retrieved: {evidence['retrieved_at']}",
    ]
    review = evidence.get("review")
    details = evidence.get("evidence", {}).get("details", {})
    if "approval_reuse" in evidence:
        from modules.attribution.components.attribution_approval_evidence import (
            snapshot_approval_matches,
        )

        root = (evidence.get("attribution") or {}).get("root_domain")
        if snapshot_approval_matches(evidence, root):
            lines += [
                "Basis: prior domain-to-registrant approval reused with separately obtained IP evidence",
                f"Original approval: {review['reviewer']} on {review['reviewed_at']}",
                f"Current evidence evaluated: {evidence.get('evaluated_at') or 'Not recorded'}",
                "No new analyst decision was made for this IP.",
            ]
        else:
            lines.append("Basis: prior approval could not be verified against the saved evidence")
    elif review:
        lines += [
            "Basis: analyst-reviewed registration-name match",
            "Matching words: " + ", ".join(details.get("matched_words", [])),
            f"Reviewed by: {review['reviewer']} on {review['reviewed_at']}",
        ]
    elif evidence.get("protocol") == "DNS":
        lines += [
            "Basis: current DNS association",
            f"Resolved hostname: {details.get('resolved_hostname', '')}",
        ]
    else:
        lines.append("Basis: exact domain in registration record")
    lines += [
        f"Source field: {evidence['attribution']['value']}",
        f"Record: {evidence['source_url']}",
    ]
    return "\n".join(lines)


def default_draft(lead, settings):
    versions = sorted(
        {str(entry_fields(e)["version"]) for e in lead["entries"] if entry_fields(e).get("version")}
    )
    selected = []
    draft = {
        "company": lead["company"] or "",
        "contact_name": "",
        "contact_title": "",
        "contact_email": "",
        "address": "",
        "sender_name": settings["analyst_name"],
        "sender_title": settings["analyst_title"],
        "sender_profile": capture_profile(settings),
        "report_date": report_started_date(
            lead, {"report_date": date.today().isoformat()}
        ).isoformat(),
        "subject": "Cybersecurity Vulnerability Notification",
        "intro": INTRO,
        "narrative": f"Shadowserver reported observations associated with {', '.join(g['root_domain'] for g in lead.get('domain_groups', [])) or lead['domain']}. "
        + (f"The reported software versions include {', '.join(versions)}. " if versions else "")
        + "The affected assets and observations are listed below. Please confirm the findings and determine the appropriate remediation with the responsible personnel.",
        "template_revision": approved.REVISION,
        "addressee_revision": approved.ADDRESSEE_REVISION,
        "narrative_values": {},
        "outreach_template": "critical",
        "selected_ssvc_assessments": {},
        "source_restrictions": [],
        "severity": "Critical",
        "selected_explainers": selected,
        "cve_records": [],
        "cve_dispositions": {},
        "explainer_snapshots": [],
        "explainer_overrides": {},
        "report_template": {
            "id": "standard",
            "version": 2,
            "marking": "For Informational Purposes Only",
            "font_size": 9.5,
        },
        "recommendations": NEXT_STEPS,
        "limitations": LIMITATION,
        "resources": RESOURCES,
        "closing": "Thank you for your attention to this matter and for your continued partnership.",
        "include_appendix": True,
        "website_verified": False,
        "sos_verified": False,
        "reviewed": False,
        "cve_reviewed": False,
        "notes": "",
    }

    from .outreach_template import apply_outreach_template

    approved.apply_template(lead, draft, settings)
    adopt_current_layouts(draft)
    from .report_explainers import select_report_explainers

    draft["report_explainer_snapshots"] = select_report_explainers(lead)
    from .finding_explainers import select_finding_explainers

    draft["finding_explainer_snapshots"] = select_finding_explainers(lead)
    return apply_outreach_template(lead, draft)


def hydrated_draft(lead, settings):
    draft = {**default_draft(lead, settings), **layout_defaults(lead), **lead["draft"]}
    # Existing drafts must explicitly adopt identity-aware wording. New cases
    # capture their sender at creation, even before the first editor save.
    if not lead["draft"].get("sender_profile"):
        draft.pop("sender_profile", None)
    settings = effective_settings(settings, draft)
    if not draft.get("narrative_revision"):
        draft["narrative_revision"] = layout_defaults(lead)["narrative_revision"]
    if lead.get("case", {}).get("stage", "in_progress") == "in_progress":
        previous = lead["draft"]
        if previous.get("template_revision") != approved.REVISION or (
            previous.get("sender_name") != settings["analyst_name"]
            or previous.get("sender_title") != settings["analyst_title"]
        ):
            draft["reviewed"] = False
        approved.apply_template(lead, draft, settings)
        apply_layout_copy(draft)
    from .outreach_template import apply_outreach_template

    if lead.get("case", {}).get("stage", "in_progress") == "in_progress":
        apply_outreach_template(lead, draft)
    else:
        draft["narrative_revision"] = lead["draft"].get("narrative_revision") or "legacy"
    from modules.ui.components.presentation import document_policy

    draft.setdefault("document_policy", document_policy(settings))
    return draft


def readiness(lead, draft, settings=None):
    cves = {
        c.upper() for e in lead["entries"] for c in CVE.findall(str(entry_fields(e).get("tag", "")))
    }
    unresolved = sorted(c for c in cves if resolved_record(c, draft)[1] == "unresolved")
    groups = lead.get("domain_groups", [])
    attributed = bool(groups) and all(
        g.get("attribution")
        and g["attribution"].get("ip")
        and g["attribution"].get("retrieved_at")
        and attribution_url(g["attribution"].get("source_url"))
        for g in groups
    )
    from .outreach_template import narrative_scope_issue

    scope_issue = narrative_scope_issue(lead, draft)
    sender_issue = profile_issue(draft, settings)
    checks = [
        {
            "key": "sender_profile",
            "label": sender_issue or "Sender organization and identity are complete",
            "ok": not sender_issue,
        },
        {
            "key": "narrative_scope",
            "label": scope_issue or "Narrative matches the outreach scope",
            "ok": not scope_issue,
        },
        {"key": "company", "label": "Business identified", "ok": bool(draft["company"].strip())},
        {"key": "sender", "label": "Sender recorded", "ok": bool(draft["sender_name"].strip())},
        {
            "key": "attribution",
            "label": "Qualified attribution retained for every case domain group",
            "ok": attributed,
        },
        {
            "key": "cve_reference",
            "label": ("Resolve source or record a disposition: " + ", ".join(unresolved))
            if unresolved
            else "CVE sources and dispositions complete",
            "ok": not unresolved,
        },
        {
            "key": "narrative",
            "label": "Narrative written",
            "ok": bool(draft["narrative"].strip())
            or bool(cves)
            and all(resolved_record(c, draft)[1] == "excluded" for c in cves),
        },
    ]
    if draft.get("information_revision") == "information-2026-11-10-v1":
        from .report_explainers import selection_is_current

        checks.append(
            {
                "key": "report_explainers",
                "label": "Report explanations match the retained source types; adopt the current report format if the case sources changed",
                "ok": selection_is_current(lead, draft),
            }
        )
    from .finding_explainers import SUPPORTED_REVISIONS, selection_is_current as findings_current

    if draft.get("finding_explainer_revision") in SUPPORTED_REVISIONS:
        checks.append(
            {
                "key": "finding_explainers",
                "label": "Technical explanations match the retained findings; adopt the current report format if the case findings changed",
                "ok": findings_current(lead, draft),
            }
        )
    from .observation_scope import scope_checks
    from .report_screenshots import screenshot_readiness

    checks.append(screenshot_readiness(lead))
    checks.extend(scope_checks(lead))
    return checks
