"""Production information one-pagers with a shared business advisory page."""

from copy import deepcopy

from .information_reference_data import RANSOMWARE_SOURCE, BEC_SOURCE, REVISED_IC3_SOURCE

from .report_explainers import NIST_SOURCE

REVISION = "information-2026-11-10-v1"


def _paragraph(text, citations=()):
    return {"kind": "prose", "body": text, "citations": list(citations)}


def _heading(text):
    return {"kind": "heading", "title": text}


def _reference(refs, source):
    return {"number": refs.add(source), **deepcopy(source)}


def build_information_pages(data, refs):
    from modules.settings.components.sender_identity import security_intro

    common_sources = [
        _reference(refs, s) for s in (RANSOMWARE_SOURCE, BEC_SOURCE, REVISED_IC3_SOURCE)
    ]
    ransomware, bec, stats = [s["number"] for s in common_sources]
    blocks = [
        _paragraph(
            security_intro(
                "As part of our mission to protect local businesses and the financial infrastructure of the United States, the Secret Service provides this voluntary advisory. We recommend prompt review with the person or company responsible for the technology identified in this notice.",
                data["draft"],
            )
        ),
        _heading("Suggested Security Practices"),
        {
            "kind": "number",
            "number": 1,
            "body": "Confirm the service and concern. Verify that the listed service relates to your business and whether the reported software version or condition is still present.",
        },
        {
            "kind": "number",
            "number": 2,
            "body": "Review protective measures. For a confirmed concern, assess applicable vendor updates, configuration changes, and whether the service needs to be reachable from the internet.",
            "citations": [ransomware],
        },
        {
            "kind": "number",
            "number": 3,
            "body": "Coordinate technical support. Share the details with whoever maintains the service, such as your website host, email provider, or IT professional.",
        },
        {
            "kind": "number",
            "number": 4,
            "body": "Check for unusual activity. If exposure is confirmed, have qualified personnel review available logs and alerts for signs of unauthorized access or changes.",
            "citations": [ransomware],
        },
        _heading("Why Prompt Review Matters"),
        _paragraph(
            "Weaknesses in internet-accessible services can provide an entry point for attackers. Ransomware and data theft can interrupt operations or support extortion. Business email compromise can redirect legitimate payments through impersonation or misuse of email; it can occur without exploiting the reported vulnerability.",
            [ransomware, bec],
        ),
        _heading("2025 Complaints Reported to the FBI"),
        {
            "kind": "statistics_table",
            "headers": ["Crime type", "Complaints", "Reported loss (USD)"],
            "items": [
                ["Business email compromise", "24,768", "$3,046,598,558"],
                ["Ransomware", "3,611", "$32,320,105"],
            ],
        },
        {
            "kind": "note",
            "body": "These are reported losses, not the full cost of these crimes. Ransomware totals generally exclude lost business, time, wages, files, equipment, and outside recovery services.",
            "citations": [stats],
        },
        _heading("About This Notification"),
        _paragraph(
            "This voluntary, non-regulatory advisory shares observations from a specific point in time. It is not a formal audit, a determination of regulatory compliance, or confirmation of compromise. The recommendations do not mandate a particular action. Decisions about review and response remain with your organization."
        ),
    ]
    if any(
        page.get("priority") == "incident"
        for page in data["draft"].get("report_explainer_snapshots", [])
    ):
        blocks[-1]["body"] = blocks[-1]["body"].replace(
            "It is not a formal audit, a determination of regulatory compliance, or confirmation of compromise.",
            "It is not a formal audit or a determination of regulatory compliance, and does not independently determine the full scope or impact of an incident.",
        )
    pages = [
        {
            "id": "business-information",
            "format": "one_pager",
            "title": "Information",
            "blocks": blocks,
            "references": common_sources,
        }
    ]
    for page in data["draft"].get("report_explainer_snapshots", []):
        sources = [_reference(refs, s) for s in page.get("sources", [])]
        audience_source = next(
            (s for s in sources if s.get("public_url") == NIST_SOURCE["public_url"]), None
        )
        citations = [s["number"] for s in sources if s is not audience_source]
        if audience_source is None:
            audience_source = _reference(refs, NIST_SOURCE)
            sources.append(audience_source)
        primary = citations[:1]
        page_blocks = [
            _paragraph(page["intro"], primary),
            {"kind": "heading", "title": page["examples_heading"], "citations": citations},
            {"kind": "examples", "items": deepcopy(page["examples"])},
            _heading(page["why_heading"]),
            _paragraph(page["why"], citations),
            {
                "kind": "heading",
                "title": page.get("roles_heading", "Where to Start in Your Business"),
                "citations": [audience_source["number"]],
            },
            {"kind": "routes", "items": deepcopy(page["routes"])},
        ]
        pages.append(
            {
                "id": page["id"],
                "format": "one_pager",
                "title": page["title"],
                "blocks": page_blocks,
                "references": sources,
                "source_report_types": deepcopy(page.get("source_report_types", [])),
                "source_revision": page["revision"],
            }
        )
    # Existing optional prose remains a snippet and flows after complete pages.
    snippets = []
    from modules.investigations.components import approved_template as approved

    for block in data.get("explainers", []):
        if block["id"] in approved.SYSTEM_BLOCKS:
            continue
        override = data["draft"].get("explainer_overrides", {}).get(block["id"], {})
        citations = []
        for url in dict.fromkeys(
            s.strip() for s in block.get("sources", "").splitlines() if s.strip()
        ):
            source = next(
                (
                    s
                    for s in block.get("source_metadata", [])
                    if url in (s.get("url"), s.get("public_url"))
                ),
                {},
            )
            citations.append(
                refs.add(source, public_url=url, title="Supporting reference for " + block["title"])
            )
        snippets.append(
            {
                "id": "explainer-" + block["id"],
                "format": "snippet",
                "kind": "explainer",
                "title": override.get("title", block["title"]),
                "body": override.get("body", block["body"]),
                "citations": citations,
                "source_revision": block.get("revision", 1),
            }
        )
    return {
        "id": "EX-INFORMATION",
        "type": "information",
        "owner": "information",
        "title": "Information",
        "layout_revision": REVISION,
        "paragraph_alignment": "justify",
        "pages": pages,
        "blocks": snippets,
        "source_citations": list(
            dict.fromkeys(
                [s["number"] for page in pages for s in page["references"]]
                + [c for b in snippets for c in b["citations"]]
            )
        ),
        "appendix_entry_ids": [],
        "alt_text": "Business information and report-specific explanations with starting points for internal and external technical support.",
    }
