"""Read the versioned Library wording that Investigations can pin in a report."""

from copy import deepcopy
from typing import Literal, NotRequired, TypedDict

from pydantic import ConfigDict, with_config

from ..resources.finding_explainer_data import BANK as FINDINGS
from ..resources.report_explainer_data import BANK as REPORTS, DEFERRED


@with_config(ConfigDict(extra="allow"))
class ReviewedGuide(TypedDict):
    """Common fields plus the complete original report, finding or context wording."""

    id: str
    kind: Literal["report", "finding", "context"]
    title: str
    sources: list[dict]
    revision: NotRequired[str]
    report_types: NotRequired[list[str]]
    body: NotRequired[str]
    intro: NotRequired[str]
    limitations: NotRequired[str]
    review: NotRequired[str]
    match_rules: NotRequired[list[dict]]


class GuideResults(TypedDict):
    items: list[ReviewedGuide]


def guides(query=""):
    """Find a family or condition by title, source identity or finding tag."""
    term = query.casefold().strip()
    result = []
    for kind, bank in (("report", REPORTS), ("finding", FINDINGS)):
        for record in bank.values():
            keys = [record["id"], record["title"], *record.get("source_types", [])]
            keys.extend(record.get("report_types", []))
            for rule in record.get("match_rules", []):
                for field in ("report_types", "tags", "tag_prefixes"):
                    keys.extend(rule.get(field, []))
                for field, value in rule.get("fields", {}).items():
                    keys.extend((field, str(value), f"{field}={value}"))
            if not term or any(term in key.casefold() for key in keys):
                result.append({**deepcopy(record), "kind": kind})
    for key, context in DEFERRED.items():
        if not term or term in key.casefold() or term in context["name"].casefold():
            result.append(
                {
                    "id": key,
                    "kind": "context",
                    "title": context["name"],
                    "report_types": [key],
                    "body": context["reason"],
                    "sources": [
                        {
                            "publisher": "The Shadowserver Foundation",
                            "title": context["name"],
                            "public_url": context["source_url"],
                        }
                    ],
                }
            )
    return sorted(result, key=lambda row: (row["title"].casefold(), row["id"]))
