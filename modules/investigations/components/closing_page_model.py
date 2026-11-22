"""Notification sign-off and resource catalogue, distinct from the internal closing report."""

from urllib.parse import urlsplit

from modules.investigations.components import approved_template as approved

FIRST_REVIEW_REVISION = "closing-2026-11-07-review-1"
SECOND_REVIEW_REVISION = "closing-2026-11-07-review-2"
REVISION = "closing-2026-11-08-final-1"
RECIPIENT_REVISIONS = {SECOND_REVIEW_REVISION, REVISION}
SUPPORTED_REVISIONS = {FIRST_REVIEW_REVISION, *RECIPIENT_REVISIONS}
CATALOGUE_REVIEWED_AT = "2026-11-08T00:37:27Z"
GROUPS = (
    "Reporting and assistance",
    "Prevention and remediation",
    "Reference and information sharing",
    "Additional resources",
)
# Existing configured resources remain selected. The three additions fill the
# reporting and prevention gaps identified during the page review.
CATALOGUE = (
    (
        GROUPS[0],
        "U.S. Secret Service | Cyber incident assistance",
        "https://www.secretservice.gov/investigations/cyberincident",
    ),
    (GROUPS[0], "FBI IC3 | Submit an internet crime complaint", "https://complaint.ic3.gov/"),
    (
        GROUPS[1],
        "CISA | Free cybersecurity services and tools",
        "https://www.cisa.gov/resources-tools/resources/free-cybersecurity-services-and-tools",
    ),
    (
        GROUPS[1],
        "CISA | Known Exploited Vulnerabilities Catalog",
        "https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
    ),
    (
        GROUPS[1],
        "Joint agency guide | Ransomware prevention and response",
        "https://www.cisa.gov/stopransomware/ransomware-guide",
    ),
    (
        GROUPS[1],
        "FBI | Business email compromise guidance",
        "https://www.fbi.gov/how-we-can-help-you/common-frauds-and-scams/business-email-compromise",
    ),
    (
        GROUPS[2],
        "CISA | Traffic Light Protocol",
        "https://www.cisa.gov/news-events/news/traffic-light-protocol-tlp-definitions-and-usage",
    ),
    (
        GROUPS[2],
        "Shadowserver | Report information",
        "https://www.shadowserver.org/what-we-do/network-reporting/get-reports/",
    ),
    (GROUPS[2], "NIST NVD | Vulnerability reference", "https://nvd.nist.gov/"),
    (GROUPS[2], "CVE Program | Published CVE records", "https://cve.org/"),
    (
        GROUPS[2],
        "CVE Details | Supplementary vulnerability reference",
        "https://www.cvedetails.com/",
    ),
)
ADDITIONAL_URLS = (CATALOGUE[1][2], CATALOGUE[4][2], CATALOGUE[5][2])


def safe_resource_url(value):
    """Only passive HTTP(S) hyperlinks; never fetch or follow a resource here."""
    if not isinstance(value, str) or any(ord(c) < 32 for c in value) or "\\" in value:
        return False
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme in {"https", "http"}
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
        )
    except ValueError:
        return False


def resource_groups(draft):
    supplied = list(
        dict.fromkeys(x.strip() for x in draft.get("resources", "").splitlines() if x.strip())
    )
    urls = list(supplied)
    for url in ADDITIONAL_URLS:
        if url.rstrip("/") not in {s.rstrip("/") for s in urls}:
            urls.append(url)
    groups = {name: [] for name in GROUPS}
    for url in urls:
        known = next((r for r in CATALOGUE if r[2].rstrip("/") == url.rstrip("/")), None)
        group, label = known[:2] if known else (GROUPS[3], url)
        groups[group].append(
            {
                "label": label,
                "url": url,
                "active": safe_resource_url(url),
                "origin": "configured" if url in supplied else "companion-added",
                "catalogue_revision": FIRST_REVIEW_REVISION,
                "catalogue_reviewed_at": CATALOGUE_REVIEWED_AT if known else None,
            }
        )
    return [{"title": name, "items": rows} for name, rows in groups.items() if rows]


def build_closing_exhibit(data, appendix):
    draft, profile = data["draft"], data["profile"]
    from modules.settings.components.sender_identity import responsibility
    from .introduction_model import REVISION as INTRODUCTION_REVISION

    route = str(
        (draft.get("sender_profile") or {}).get("outreach_verification_route") or ""
    ).strip()
    contact = (
        {"recipient_verification": route}
        if draft.get("introduction_revision") == INTRODUCTION_REVISION and len(route) > 180
        else {}
    )

    return {
        **contact,
        "id": "EX-CLOSING",
        "type": "closing",
        "owner": "closing",
        "title": "Recommended Resources"
        if draft.get("closing_revision") in RECIPIENT_REVISIONS
        else "Closing",
        "layout_revision": draft.get("closing_revision", REVISION),
        "approved_copy_revision": approved.REVISION,
        "resource_groups": resource_groups(draft),
        "responsibility": responsibility(approved.RESPONSIBILITY, draft),
        "closing": draft["closing"],
        "sender_lines": list(
            filter(
                None,
                (
                    draft.get("sender_name"),
                    draft.get("sender_title"),
                    profile.get("agency"),
                    profile.get("office"),
                ),
            )
        ),
        "appendix_note": (
            "The full supporting appendix is available upon request."
            if draft.get("include_appendix", True) is False
            else "Supporting records follow in the appendices. Complete resource URLs and source references appear in Appendix D."
            if draft.get("closing_revision") in RECIPIENT_REVISIONS
            else "Companion Appendix follows: reported observations, attribution and vulnerability records, and complete source references. Resource URLs are listed in Appendix D."
        ),
        "appendix_entry_ids": [
            e["id"] for e in appendix["entries"] if e["kind"] == "closing_resource"
        ],
        "alt_text": "Recommended reporting, prevention and reference resources, responsibility statement and configured sender sign-off. Full source references follow in the Companion Appendix.",
    }
