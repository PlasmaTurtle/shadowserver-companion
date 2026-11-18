"""Exact report identity, immutable one-pager selection, and source lineage.

Selection uses retained import identity, never a vulnerability tag, protocol,
port, or the presence of an IPv6 address. The bank is fully offline.
"""

from copy import deepcopy
import re

from .report_explainer_data import BANK, DEFERRED

REVISION = "report-explainers-2026-11-10-v1"
NIST_SOURCE = {
    "publisher": "National Institute of Standards and Technology",
    "title": "Building Your Small Business's Cybersecurity Team: From In-House to Outsourcing",
    "public_url": "https://www.nist.gov/itl/smallbusinesscyber/guidance-topic/building-your-team",
    "retrieved_at": "2026-11-10T00:00:00Z",
    "revision_id": REVISION + "-business-team",
    "partition": "D",
    "referenced_by": ["EX-INFORMATION"],
    "record": {
        "summary": "Businesses may use internal personnel, external providers, or a combination. The notification's audience starting points are tailored recommendations."
    },
}


def _identities():
    identities = {key: key for key in DEFERRED}
    for page in BANK.values():
        identities.update({key: key for key in page["report_types"]})
    identities.update(
        {
            "http_vulnerable": "scan_http_vulnerable",
            "http_vulnerable_ipv6": "scan6_http_vulnerable",
        }
    )
    return identities


def canonical_source_types(lead):
    """Prefer preserved schema identity; exact fallback supports older imports."""
    from .intake.versions import has_active_findings

    identities = _identities()
    result = []
    for entry in lead.get("entries", []):
        if not has_active_findings(entry):
            continue
        source = entry.get("source", {})
        normalized = entry.get("normalized", {})
        raw = normalized.get("profile", {}).get("id")
        if raw in (None, "", "unclassified"):
            raw = source.get("fields", {}).get("report_type")
        if not raw:
            filename = str(
                source.get("workbook") or source.get("file") or source.get("filename") or ""
            ).casefold()
            raw = next(
                (
                    key
                    for key in sorted(identities, key=len, reverse=True)
                    if re.search(
                        r"(?:^|[^a-z0-9_])"
                        + re.escape(key).replace("_", "[-_]")
                        + r"(?:[^a-z0-9_]|$)",
                        filename,
                    )
                ),
                None,
            )
        key = identities.get(str(raw).strip().casefold(), str(raw or "unclassified"))
        if key not in result:
            result.append(key)
    return result


def select_report_explainers(lead):
    """Pin complete reusable content once; IPv4/IPv6 share one family page."""
    observed = canonical_source_types(lead)
    selected = []
    for page in BANK.values():
        matched = [key for key in observed if key in page["report_types"]]
        if matched:
            item = deepcopy(page)
            item["source_report_types"] = matched
            selected.append(item)
    return selected


def selection_notices(lead):
    covered = {key for page in BANK.values() for key in page["report_types"]}
    return [
        {
            "report_type": key,
            "message": DEFERRED.get(key, {}).get("reason")
            or "No report-specific one-pager is selected for this source type. Review its original report documentation.",
        }
        for key in canonical_source_types(lead)
        if key not in covered
    ]


def selection_is_current(lead, draft):
    """Changed source families require deliberate adoption before freezing."""
    expected = {p["id"]: p["source_report_types"] for p in select_report_explainers(lead)}
    pinned = {
        p["id"]: p.get("source_report_types", [])
        for p in draft.get("report_explainer_snapshots", [])
    }
    return expected == pinned


def pinned_sources(draft):
    pages = draft.get("report_explainer_snapshots", [])
    sources = [deepcopy(source) for page in pages for source in page.get("sources", [])]
    if pages:
        sources.append(deepcopy(NIST_SOURCE))
    return sources
