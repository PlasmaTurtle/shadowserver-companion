"""Finding-first projections over saved appendix records and explicit provenance edges.

This is presentation only. It does not infer ownership, vulnerability applicability,
source freshness or new relationships, and never mutates the retained records.
"""

from collections import OrderedDict
from datetime import datetime

from .appendix_compact import selected_fields


def readable_time(value):
    """Display an offset-aware instant in UTC; never invent a missing timezone."""
    if not isinstance(value, str):
        return str(value)
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if instant.tzinfo is None:
            return value
        from datetime import timezone

        return instant.astimezone(timezone.utc).strftime("%d %b %Y · %H:%M:%S UTC")
    except ValueError:
        return value


def field_values(entry):
    values = {}
    for field in selected_fields(entry, current=True):
        label, value = field["label"], field["value"]
        if label in values and values[label] != value:
            values[label] = str(values[label]) + "; " + str(value)
        else:
            values[label] = value
    return values


def finding_groups(entries):
    """Collapse repeated observations of the same recorded asset and condition.

    Dates and source rows stay on every retained observation. Distinct service,
    product, version, report type or unknown identity are never merged accidentally.
    """
    groups = OrderedDict()
    for entry in entries:
        if entry.get("kind") not in {"observation", "legacy_asset_summary"}:
            continue
        values = field_values(entry)
        identity = tuple(
            str(values.get(key, ""))
            for key in (
                "Hostname",
                "IP address",
                "Port",
                "Protocol",
                "Finding",
                "Technology",
                "Version",
                "Reported software",
                "Report type",
            )
        )
        if (not values.get("Hostname") and not values.get("IP address")) or (
            not values.get("Finding") and not values.get("Report type")
        ):
            identity += (entry["id"],)
        group = groups.setdefault(identity, {"id": entry["id"], "values": values, "entries": []})
        group["entries"].append(entry)
    for group in groups.values():
        identifiers = {entry["id"] for entry in group["entries"]}
        related = [
            entry for entry in entries if identifiers.intersection(entry.get("referenced_by", []))
        ]
        citations = {
            number
            for entry in [*group["entries"], *related]
            for number in entry.get("citations", [])
        }
        references = [
            entry
            for entry in entries
            if entry.get("kind") == "reference"
            and citations.intersection(entry.get("citations", []))
        ]
        group["connections"] = list(
            {entry["id"]: entry for entry in [*related, *references]}.values()
        )
    return list(groups.values())
