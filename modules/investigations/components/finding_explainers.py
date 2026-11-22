"""Pinned technical snippets selected by exact source family and finding tag.

These explain a reported condition in the technical findings section. They are
separate from the plain-English report-family information pages.
"""

from copy import deepcopy
import re

from modules.library.resources.finding_explainer_data import (
    BANK,
    CURRENT_EDITION,
    LIFECYCLE_EDITION,
)
from modules.accretion.components.intake.versions import entry_fields
from .report_explainers import canonical_source_types

REVISION = CURRENT_EDITION
SUPPORTED_REVISIONS = {LIFECYCLE_EDITION, REVISION}


def tags(entry):
    return list(
        dict.fromkeys(
            token.casefold()
            for token in re.split(r"[;,\s]+", str(entry_fields(entry).get("tag") or ""))
            if token
        )
    )


def match_snippet(entry, tag, snippets):
    source_type = next(iter(canonical_source_types({"entries": [entry]})), "unclassified")
    fields = entry_fields(entry)
    lowered = tag.casefold()
    for snippet in snippets:
        for rule in snippet["match_rules"]:
            matches_tag = lowered in rule.get("tags", []) or any(
                lowered.startswith(prefix) for prefix in rule.get("tag_prefixes", [])
            )
            if (
                source_type in rule["report_types"]
                and matches_tag
                and lowered not in rule.get("exclude_tags", [])
                and all(fields.get(key) == value for key, value in rule.get("fields", {}).items())
            ):
                return snippet
    return None


def select_finding_explainers(lead, revision=REVISION):
    if revision not in SUPPORTED_REVISIONS:
        return []
    candidates = [
        item for item in BANK.values() if revision == REVISION or item["revision"] == revision
    ]
    matched = set()
    for entry in lead.get("entries", []):
        for tag in tags(entry):
            snippet = match_snippet(entry, tag, candidates)
            if snippet:
                matched.add(snippet["id"])
    return [deepcopy(value) for key, value in BANK.items() if key in matched]


def selection_is_current(lead, draft):
    expected = {
        snippet["id"]
        for snippet in select_finding_explainers(lead, draft["finding_explainer_revision"])
    }
    pinned = {snippet["id"] for snippet in draft.get("finding_explainer_snapshots", [])}
    return expected == pinned


def attach_explanation(item, snippet, refs, appendix):
    citations = []
    for source in snippet["sources"]:
        citation = refs.add(source)
        citations.append(citation)
        saved_source = appendix.add_source(
            source, partition="C", referenced_by=["EX-VULNERABILITY"], citations=[citation]
        )
        if saved_source and isinstance(saved_source, dict):
            item["appendix_entry_ids"].append(saved_source["id"])
    item["citations"] = citations
    item["technical_explanation"] = {
        key: deepcopy(snippet[key])
        for key in ("id", "revision", "format", "title", "body", "limitations", "review")
    }
    item["technical_explanation"]["source_citations"] = citations


def observation_conditions(entry, snippets):
    """Yield independently reported conditions, retaining evidence for unreviewed tags."""
    from .notification_narrative_v4 import source_context

    raw = str(entry_fields(entry).get("tag") or "")
    context = source_context(entry)
    tokens = {}
    for token in re.split(r"[;,\s]+", raw):
        if token:
            tokens.setdefault(token.casefold(), token)
    matches = [(token, match_snippet(entry, token, snippets)) for token in tokens.values()]
    if any(s and s["category"] != "lifecycle" for _, s in matches):
        # These tokens in the provider's example rows name the protocol/report.
        # Preserve any other unmatched condition independently of covered findings.
        family = context["id"].removeprefix("scan6_").removeprefix("scan_")
        context_tags = {
            "http_vulnerable": {"http", "https"},
            "smtp_vulnerable": {"smtp"},
            "isakmp": {"vulnerable-isakmp", "isakmp-vulnerable"},
            "badsecrets": {"http", "https"},
            "mongodb": {"mongodb"},
        }.get(family, set())
        for token, snippet in matches:
            if snippet and snippet["category"] != "lifecycle":
                yield token, snippet
            elif (
                not snippet
                and token.casefold() not in context_tags
                and not re.search(r"(^|[-_])eol($|[-_])|CVE-\d{4}-\d{4,}", token, re.I)
            ):
                yield token, None
        return
    if any(s for _, s in matches) or re.search(r"(^|[-_;,\s])eol($|[-_;,\s])", raw, re.I):
        return
    if re.search(r"CVE-\d{4}-\d{4,}", raw, re.I):
        # Missing authentication was an independently retained condition before
        # the reviewed configuration cards. Preserve that output in older drafts.
        if context["id"] in {"scan_mongodb", "scan6_mongodb"} and "mongodb-noauth" in tags(entry):
            yield "mongodb-noauth", None
        return
    yield raw, None


def enrich_eol_findings(data, observations, groups, refs, appendix):
    """Keep lifecycle findings distinct from CVEs, including excluded CVEs."""
    if data["draft"].get("finding_explainer_revision") not in SUPPORTED_REVISIONS:
        return list(groups.values())
    snippets = data["draft"].get("finding_explainer_snapshots", [])
    by_observation = {item["id"]: item for item in observations}
    revised = {}
    for original in groups.values():
        for observation_id in original["observation_ids"]:
            observation = by_observation[observation_id]
            snippet = match_snippet(observation["row"], original["label"], snippets)
            # A generic lifecycle paragraph must not merge different products.
            condition = (
                snippet["id"]
                if snippet and not snippet.get("keep_tags_separate")
                else original["label"].casefold()
            )
            key = (condition, bool(snippet))
            item = revised.setdefault(
                key,
                {
                    **deepcopy(original),
                    "observation_ids": [],
                    "appendix_entry_ids": [],
                    "citations": [],
                    "reported_versions": [],
                    "reported_tags": [],
                    "endpoints": [],
                    "ips": [],
                },
            )
            fields = observation["fields"]
            item["observation_ids"].append(observation_id)
            item["appendix_entry_ids"].append(observation["entry_id"])
            if fields.get("version") and str(fields["version"]) not in item["reported_versions"]:
                item["reported_versions"].append(str(fields["version"]))
            if original["label"] not in item["reported_tags"]:
                item["reported_tags"].append(original["label"])
            ip = str(observation["row"].get("ip") or fields.get("ip") or "")
            if ip and ip not in item["ips"]:
                item["ips"].append(ip)
            endpoint = " / ".join(
                str(value)
                for value in (
                    fields.get("hostname"),
                    ip,
                    fields.get("protocol"),
                    fields.get("port"),
                )
                if value not in (None, "")
            )
            if endpoint and endpoint not in item["endpoints"]:
                item["endpoints"].append(endpoint)
            if snippet and "technical_explanation" not in item:
                attach_explanation(item, snippet, refs, appendix)
    for item in revised.values():
        item["detail"] = "; ".join(item["reported_versions"]) or "Version not supplied"
        item["exposure_count"] = len(item.pop("ips"))
        item["observation_scope"] = "; ".join(item.pop("endpoints"))
        item["appendix_entry_ids"] = list(dict.fromkeys(item["appendix_entry_ids"]))
        if item.get("technical_explanation"):
            item["label"] = " / ".join(item["reported_tags"])
    return list(revised.values())
