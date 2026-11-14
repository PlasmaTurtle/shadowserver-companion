"""Recipient-facing appendix organization over the unchanged source-record model.

No lookups, inferred ownership or source-value edits occur here. Display labels
are separate from the original JSON Pointer paths, values and stable anchors.
"""

from collections import OrderedDict
from copy import deepcopy
import re

from . import appendix_compact

COMPACT_REVISION = appendix_compact.REVISION
LEGACY_COMPACT_REVISION = appendix_compact.LEGACY_REVISION
COMPACT_REVISIONS = appendix_compact.SUPPORTED_REVISIONS

FIRST_REVIEW_REVISION = "appendix-2026-11-07-review-1"
REVISION = "appendix-2026-11-08-final-1"
SUPPORTED_REVISIONS = {FIRST_REVIEW_REVISION, REVISION, *COMPACT_REVISIONS}
INTERNAL_METADATA = {
    "observation": (
        "/normalized/profile",
        "/normalized/schema_version",
        "/normalized/observation_ref",
    ),
    "import_provenance": (
        "/parsing_policy/report_profiles",
        "/parsing_policy/profile_inventory",
    ),
}
SECTIONS = (
    (
        "A",
        "Reported observations",
        "Original scan observations and import details.",
        "introduction",
    ),
    (
        "B",
        "Attribution records",
        "Evidence used to associate the reported systems with the recipient, followed by retained lookup history.",
        "attribution",
    ),
    (
        "C",
        "Vulnerability records",
        "Published vulnerability information, source assessments and related findings.",
        "vulnerabilities",
    ),
    (
        "D",
        "References and resources",
        "Cited publications, supporting source records and recommended resources.",
        "information",
    ),
)
KINDS = {
    "observation": "Reported observation",
    "legacy_asset_summary": "Saved asset summary",
    "import_provenance": "Original scan file",
    "attribution_evidence": "Attribution evidence",
    "attribution_history": "Lookup history",
    "vulnerability_record": "Vulnerability record",
    "source_snapshot": "Supporting source record",
    "advisory": "Selected guidance",
    "supporting_material": "Supporting material",
    "reference": "Cited source",
    "closing_resource": "Recommended resource",
}
NAMES = {
    "ip": "IP address",
    "id": "Record identifier",
    "asn": "ASN",
    "geo": "Country code",
    "hostname": "Hostname",
    "root_domain": "Root domain",
    "source_url": "Source URL",
    "public_url": "Public URL",
    "url": "URL",
    "timestamp": "Observation time",
    "retrieved_at": "Retrieved at",
    "evaluated_at": "Evaluated at",
    "validated_at": "Validated at",
    "validated_by": "Validated by",
    "private_ip": "Private IP flag",
    "body_sha256": "Response SHA-256",
    "sha256": "SHA-256",
    "record_path": "Saved record path",
    "revision_id": "Source revision",
    "from_cache": "Retrieved from cache",
    "kev": "CISA KEV listed",
    "cvss": "CVSS",
    "epss": "EPSS score",
    "epss_percentile": "EPSS percentile",
    "epss_date": "EPSS date",
    "report_type": "Report type",
    "lessThan": "Less than",
    "lessThanOrEqual": "Less than or equal to",
    "published_at": "Published at",
    "updated_at": "Updated at",
    "number": "Citation number",
}
GROUP_NAMES = {
    "/": "Record details",
    "/source": "Source file details",
    "/source/fields": "Reported scan fields",
    "/record": "Recorded source information",
    "/attribution": "Attribution result",
    "/evidence": "Supporting evidence",
    "/evidence/match": "Matched evidence",
    "/evidence/details": "Evidence details",
    "/policy": "Evaluation policy",
    "/ransomware": "Ransomware assessment",
    "/report_claim_citations": "References supporting individual assessments",
    "/normalized": "Parsed product information",
}
REPORT_LABELS = {
    "EX-SUMMARY": "Notification summary",
    "EX-ATTRIBUTION": "Attribution",
    "EX-VULNERABILITY": "Vulnerabilities",
    "EX-INFORMATION": "Information",
    "EX-CLOSING": "Recommended resources",
    "Information": "Information",
    "Attribution": "Attribution",
    "Source register": "References",
}


def humanize(key):
    if key in NAMES:
        return NAMES[key]
    value = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", key).replace("_", " ").replace("-", " ")
    return value[:1].upper() + value[1:]


def decoded_parts(path):
    return [part.replace("~1", "/").replace("~0", "~") for part in path.split("/")[1:]]


def field_group(path):
    """Keep related nested fields together without treating array indices as keys."""
    parts = path.split("/")[1:]
    if len(parts) < 2:
        return "/", parts[0] if parts else ""
    if parts[:2] == ["source", "fields"]:
        cut = 2
    elif parts[0] == "report_claim_citations":
        cut = 1
    elif len(parts) >= 3 and parts[1].isdigit():
        cut = 2
    elif parts[0] in {"record", "evidence"} and len(parts) >= 3 and not parts[2].isdigit():
        cut = 2
    else:
        cut = 1
    return "/" + "/".join(parts[:cut]), "/".join(parts[cut:])


def group_title(path):
    if path in GROUP_NAMES:
        return GROUP_NAMES[path]
    return " / ".join(
        "item " + str(int(p) + 1) if p.isdigit() else humanize(p) for p in decoded_parts(path)
    )


def display_field(relative):
    # Retain the exact escaped relative key beside its readable label. Together
    # with the group's source path it identifies every original source field.
    words = [
        "item " + str(int(p) + 1) if p.isdigit() else humanize(p)
        for p in decoded_parts("/" + relative)
    ]
    label = " / ".join(words) or "Value"
    return label if label.casefold() == relative.casefold() else label + " (" + relative + ")"


def field_map(entry):
    return {f["path"]: f["value"] for f in entry["fields"]}


def record_title(entry):
    values = field_map(entry)
    kind = entry["kind"]
    if kind == "observation":
        return (
            " | ".join(
                str(v)
                for v in (values.get("/source/fields/hostname"), values.get("/ip"))
                if v not in (None, "")
            )
            or KINDS[kind]
        )
    if kind in {"attribution_evidence", "attribution_history"}:
        return (
            " | ".join(
                str(v)
                for v in (
                    values.get("/attribution/root_domain"),
                    values.get("/ip"),
                    entry.get("status"),
                )
                if v not in (None, "")
            )
            or KINDS[kind]
        )
    return entry["title"]


def view_record(entry, label, labels, revision):
    groups = OrderedDict()
    for field in entry["fields"]:
        # These are application-generated parser descriptors, not scan cells.
        # Keep the lossless appendix model intact; only the current recipient
        # view omits their repeated presentation. Unknown fields stay visible.
        if revision == REVISION and any(
            field["path"] == prefix or field["path"].startswith(prefix + "/")
            for prefix in INTERNAL_METADATA.get(entry["kind"], ())
        ):
            continue
        path, relative = field_group(field["path"])
        group = groups.setdefault(path, {"title": group_title(path), "path": path, "fields": []})
        group["fields"].append({**deepcopy(field), "label": display_field(relative)})
    related = [
        labels.get(value, REPORT_LABELS.get(value, value)) for value in entry["referenced_by"]
    ]
    return {
        "id": entry["id"],
        "label": label,
        "title": record_title(entry),
        "kind_label": KINDS.get(entry["kind"], humanize(entry["kind"])),
        "kind": entry["kind"],
        "owner": entry["owner"],
        "groups": list(groups.values()),
        "citations": deepcopy(entry["citations"]),
        "related": list(dict.fromkeys(related)),
        "source_ids": deepcopy(entry["source_ids"]),
        "status": entry.get("status"),
        "reference_number": field_map(entry).get("/number")
        if entry["kind"] == "reference"
        else None,
    }


def build_appendix_views(appendix, revision=REVISION):
    """Return page models, document nodes and navigation, preserving every record."""
    if revision not in SUPPORTED_REVISIONS:
        raise ValueError("Unsupported appendix presentation revision")
    if revision in COMPACT_REVISIONS:
        from .appendix_compact import build_compact_views

        return build_compact_views(
            appendix,
            sections=SECTIONS,
            kinds=KINDS,
            humanize=humanize,
            record_title=record_title,
            revision=revision,
        )
    labels, ordered = {}, []
    for code, title, description, owner in SECTIONS:
        entries = [e for e in appendix["entries"] if e["partition"] == code]
        if code == "D":
            rank = {
                "reference": 0,
                "source_snapshot": 1,
                "advisory": 1,
                "supporting_material": 1,
                "closing_resource": 2,
            }
            entries.sort(key=lambda e: rank.get(e["kind"], 1))
        for number, entry in enumerate(entries, 1):
            labels[entry["id"]] = f"{code}-{number:02d}"
        ordered.append((code, title, description, owner, entries))
    views, nodes, directory, anchors = [], [], [], ["companion-appendix"]
    for code, title, description, owner, entries in ordered:
        buckets = [("", title, owner, entries)]
        if code == "D":
            buckets = [
                (
                    "-REFERENCES",
                    "Cited sources",
                    "information",
                    [e for e in entries if e["kind"] == "reference"],
                ),
                (
                    "-SUPPORT",
                    "Supporting publications and material",
                    "information",
                    [e for e in entries if e["kind"] not in {"reference", "closing_resource"}],
                ),
                (
                    "-RESOURCES",
                    "Recommended resources",
                    "closing",
                    [e for e in entries if e["kind"] == "closing_resource"],
                ),
            ]
        for bucket_index, (suffix, heading, bucket_owner, selected) in enumerate(buckets):
            if code == "D" and not selected and bucket_index:
                continue
            anchor = "appendix-" + code + suffix.lower()
            page_anchors = [anchor]
            if bucket_index == 0 and suffix:
                page_anchors.append("appendix-" + code)
            anchors.extend(page_anchors)
            records = [view_record(e, labels[e["id"]], labels, revision) for e in selected]
            for record in records:
                anchors.append(record["id"])
                if record["reference_number"] is not None:
                    anchors.append("ref" + str(record["reference_number"]))
            view = {
                "id": "EX-APPENDIX-" + code + suffix,
                "type": "appendix",
                "owner": bucket_owner,
                "layout_revision": revision,
                "title": heading,
                "section": code,
                "display_section": code + str(bucket_index + 1) if code == "D" else code,
                "section_title": title,
                "description": description,
                "anchors": page_anchors,
                "records": records,
                "appendix_entry_ids": [e["id"] for e in selected],
                "alt_text": "Appendix " + code + ": " + heading,
            }
            views.append(view)
            nodes += [
                {"kind": "page_break", "section_owner": bucket_owner},
                {"kind": "exhibit", "exhibit_id": view["id"], "section_owner": bucket_owner},
            ]
            directory.append(
                {
                    "section": view["display_section"],
                    "title": heading,
                    "description": description,
                    "count": len(records),
                    "target": anchor,
                }
            )
    guide = {
        "id": "EX-APPENDIX-INDEX",
        "type": "appendix",
        "owner": "information",
        "layout_revision": revision,
        "title": "Appendices",
        "section": "",
        "section_title": "Appendices",
        "anchors": ["companion-appendix"],
        "directory": directory,
        "description": "The following records support this notification. Each appendix identifies the source information used for the reported observations, attribution or vulnerability discussion.",
        "reading_notes": [
            "Records are numbered within each appendix. The section and current record are repeated when details continue onto another page.",
            "Source paths identify groups of original fields. Field labels are expanded for readability; the original key appears in parentheses when it differs.",
            "Times and values remain as recorded. A time ending in Z is in UTC. Empty strings, empty lists, empty objects and null values are identified explicitly.",
            "A source's published assessment or lookup result does not, by itself, establish that a reported system was compromised.",
        ],
        "appendix_entry_ids": [],
        "alt_text": "Appendix contents and guidance for reading the supporting records.",
    }
    if revision == REVISION:
        guide["reading_notes"].append(
            "The accompanying source data retains the complete import record."
        )
    nodes = [
        {"kind": "page_break", "section_owner": "closing"},
        {"kind": "exhibit", "exhibit_id": guide["id"], "section_owner": "information"},
    ] + nodes
    return [guide] + views, nodes, {"anchors": list(dict.fromkeys(anchors)), "labels": labels}
