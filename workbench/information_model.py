"""Versioned advisory copy and pinned references for the Information page.

No network queries, date refreshes, or generated prose occur during composition.
The IC3 extract is a reviewed reference extract, not a copy of the source PDF.
"""

from copy import deepcopy

from . import approved_template as approved
from .information_reference_data import (
    IC3_SOURCE,
    BEC_SOURCE,
    RANSOMWARE_SOURCE,
    REVISED_IC3_SOURCE,
)

FIRST_REVIEW_REVISION = "information-2026-11-07-review-1"
PREVIOUS_REVISION = "information-2026-11-07-review-2"
REVISION = "information-2026-11-10-v1"
SUPPORTED_REVISIONS = frozenset((FIRST_REVIEW_REVISION, PREVIOUS_REVISION, REVISION))


def reference_sources(revision=REVISION):
    sources = (
        [IC3_SOURCE]
        if revision == FIRST_REVIEW_REVISION
        else [RANSOMWARE_SOURCE, BEC_SOURCE, REVISED_IC3_SOURCE]
    )
    return deepcopy(sources)


def revised_risk_blocks(refs):
    """Editorial candidate authorized for page two; not agency-approved policy."""
    ransomware = refs.add(RANSOMWARE_SOURCE)
    bec = refs.add(BEC_SOURCE)
    stats = refs.add(REVISED_IC3_SOURCE)
    counts = REVISED_IC3_SOURCE["record"]
    return [
        {
            "id": "fraud-intro",
            "kind": "prose",
            "new_page": True,
            "title": "Why Prompt Review Matters",
            "body": "Vulnerable internet-facing services can give attackers an entry point into an organization. Reviewing the reported exposure helps your technical team determine whether it remains present and what protective action is appropriate.",
            "citations": [ransomware],
            "citation_style": "inline",
        },
        {
            "id": "risk-1",
            "kind": "risk",
            "body": "Business email compromise (BEC): Criminals may impersonate a trusted sender or misuse an email account to redirect legitimate payments. These schemes can occur without exploiting the software vulnerability reported here.",
            "citations": [bec],
            "citation_style": "inline",
        },
        {
            "id": "risk-2",
            "kind": "risk",
            "body": "Ransomware and data extortion: Attackers may encrypt systems or steal data to demand payment, disrupting operations or threatening disclosure. Data extortion can also occur without encryption.",
            "citations": [ransomware],
            "citation_style": "inline",
        },
        {
            "id": "statistics",
            "kind": "statistics_table",
            "title": "2025 Complaints Reported to the FBI",
            "headers": ["Crime type", "Complaints", "Reported loss (USD)"],
            "items": [
                [
                    label,
                    f"{counts[key]['complaints']:,}",
                    f"${counts[key]['reported_losses_usd']:,}",
                ]
                for label, key in (
                    ("Business email compromise", "business_email_compromise"),
                    ("Ransomware", "ransomware"),
                )
            ],
            "source_label": "FBI Internet Crime Complaint Center (IC3)",
            "citations": [stats],
        },
        {
            "id": "statistics-scope",
            "kind": "prose",
            "body": "The totals reflect reports to IC3, not the full cost of these crimes. Ransomware figures generally exclude lost business, time, wages, files, equipment, and third-party remediation.",
            "citations": [stats],
            "citation_style": "inline",
        },
        {
            "id": "partnership",
            "kind": "prose",
            "title": "About This Notification",
            "body": "This voluntary, non-regulatory advisory shares observations from a specific point in time. It is not a formal audit, a determination of regulatory compliance, or confirmation of compromise. Please have your technical team or service provider validate the finding and determine an appropriate response.",
        },
    ]


def build_information_exhibit(data, refs):
    """Preserve old revisions and the approved first page; pin revised page-two copy."""
    from .sender_identity import security_intro

    revision = data["draft"].get("information_revision", REVISION)
    if revision == REVISION:
        from .information_pages import build_information_pages

        return build_information_pages(data, refs)
    statistical_ref = refs.add(IC3_SOURCE) if revision == FIRST_REVIEW_REVISION else None
    blocks = [
        {
            "id": "security-intro",
            "kind": "prose",
            "title": "Suggested Security Practices",
            "body": security_intro(approved.SECURITY_INTRO, data["draft"]),
        },
        *[
            {"id": f"action-{i}", "kind": "action", "number": i, "body": step}
            for i, step in enumerate(approved.NEXT_STEPS.splitlines(), 1)
        ],
        {
            "id": "fraud-intro",
            "kind": "prose",
            "new_page": True,
            "title": "Protecting Your Business from Cyber Fraud",
            "body": approved.FRAUD_INTRO,
        },
        *[
            {"id": f"risk-{i}", "kind": "risk", "body": item}
            for i, item in enumerate(approved.FRAUD_RISKS, 1)
        ],
        {"id": "statistics-intro", "kind": "prose", "body": approved.FRAUD_STATS_INTRO},
        {
            "id": "statistics",
            "kind": "statistics",
            "items": list(approved.FRAUD_STATS),
            "citations": [statistical_ref],
            "source_label": "FBI IC3 · 2025 reported complaints and losses",
        },
        {
            "id": "partnership",
            "kind": "prose",
            "title": "Advisory Information & Partnership",
            "body": approved.PARTNERSHIP,
        },
    ]
    if revision == PREVIOUS_REVISION:
        blocks = blocks[:5] + revised_risk_blocks(refs)
    for block in data.get("explainers", []):
        if block["id"] in approved.SYSTEM_BLOCKS:
            continue
        citations = []
        for url in dict.fromkeys(
            x.strip() for x in block.get("sources", "").splitlines() if x.strip()
        ):
            metadata = next(
                (
                    s
                    for s in block.get("source_metadata", [])
                    if url in (s.get("url"), s.get("public_url"))
                ),
                {},
            )
            number = refs.add(
                metadata, public_url=url, title="Supporting reference for " + block["title"]
            )
            if number:
                citations.append(number)
        override = data["draft"].get("explainer_overrides", {}).get(block["id"], {})
        blocks.append(
            {
                "id": "explainer-" + block["id"],
                "kind": "explainer",
                "title": override.get("title", block["title"]),
                "body": override.get("body", block["body"]),
                "citations": citations,
                "source_revision": block.get("revision", 1),
            }
        )
    model = {
        "id": "EX-INFORMATION",
        "type": "information",
        "owner": "information",
        "title": "Information Exhibit",
        "layout_revision": revision,
        "approved_copy_revision": approved.REVISION,
        "blocks": blocks,
        "source_citations": list(dict.fromkeys(c for b in blocks for c in b.get("citations", []))),
        "appendix_entry_ids": [],
        "alt_text": "Suggested security practices, cyber-fraud context and voluntary advisory limitations. Supporting references are retained in Appendix D.",
    }
    if revision == PREVIOUS_REVISION:
        model["approved_copy_scope"] = "Security introduction and four protective actions only."
        model["editorial_copy_revision"] = PREVIOUS_REVISION
    return model
