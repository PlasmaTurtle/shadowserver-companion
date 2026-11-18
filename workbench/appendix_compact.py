"""Concise, deterministic field projections over unchanged appendix evidence.

This module only selects display fields. Original observations, values, source
paths and raw records remain in the saved snapshot and internal evidence reader.
"""

from collections import OrderedDict
from copy import deepcopy
import json

LEGACY_REVISION = "appendix-2026-11-10-compact-1"
PREVIOUS_REVISION = "appendix-2026-11-13-compact-2"
REVISION = "appendix-2026-11-13-compact-3"
SUPPORTED_REVISIONS = {LEGACY_REVISION, PREVIOUS_REVISION, REVISION}


def meaningful(value):
    """Zero and false can carry evidence; only actual empty values are omitted."""
    return value is not None and value != "" and value != [] and value != {}


def _field(entry, label, *paths):
    fields = {field["path"]: field for field in entry.get("fields", [])}
    for path in paths:
        field = fields.get(path)
        if field and meaningful(field.get("value")):
            return {**deepcopy(field), "label": label}
    return None


def _matching(entry, keys, *, prefixes=()):
    for field in entry.get("fields", []):
        path = field["path"]
        if path.rsplit("/", 1)[-1] not in keys or not meaningful(field.get("value")):
            continue
        if not prefixes or any(path.startswith(prefix) for prefix in prefixes):
            yield field


def selected_fields(entry, *, current=False):
    """Select useful values for the recipient appendix and evidence overview."""
    kind = entry.get("kind", "")
    selected = []

    def add(label, *paths):
        field = _field(entry, label, *paths)
        if field:
            selected.append(field)

    if kind in {"observation", "legacy_asset_summary"}:
        for label, key in (
            ("Hostname", "hostname"),
            ("IP address", "ip"),
            ("Port", "port"),
            ("Protocol", "protocol"),
            ("Finding", "tag"),
            ("Technology", "product"),
            ("Version", "version"),
            ("Observed", "timestamp"),
        ):
            if current and key == "version":
                # Intake pins the selected software/protocol version. Preserve
                # that choice even when a report also has a generic version
                # column (for example HTTP/1.1 beside component_version).
                paths = {field["path"] for field in entry.get("fields", [])}
                if "/normalized/raw_version" in paths:
                    add(label, "/normalized/raw_version")
                else:
                    add(
                        label,
                        "/source/fields/component_version",
                        "/source/fields/device_version",
                        "/source/fields/version",
                        "/version",
                    )
            else:
                add(label, "/source/fields/" + key, "/" + key)
        if not any(f["label"] == "Observed" for f in selected):
            add("Observed", "/observed_at")
        add(
            "Source file",
            "/source/filename",
            "/source/file_name",
            "/source/name",
            "/source/workbook",
            "/source/file",
        )
        add("Source row", "/source/row", "/source/row_number")
        add("Report type", "/source/report_type", "/normalized/report_type", "/report_type")
        products = OrderedDict()
        for field in _matching(entry, {"product", "version"}, prefixes=("/normalized/products/",)):
            if current:
                prefix, name = field["path"].rsplit("/", 1)
                products.setdefault(prefix, {})[name] = field
            else:
                label = "Reported " + field["path"].rsplit("/", 1)[-1]
                if not any(f["value"] == field["value"] for f in selected):
                    selected.append({**deepcopy(field), "label": label})
        # Keep each product paired with its own version. A dict keyed only by
        # "Reported version" used to drop all but the last product in the reader.
        for prefix, product in products.items():
            combined = _combined(
                "Reported software", [product.get("product"), product.get("version")], path=prefix
            )
            if combined:
                selected.append(combined)
    elif kind in {"attribution_evidence", "accepted_attribution", "attribution_history"}:
        for label, paths in (
            ("Hostname", ("/attribution/root_domain", "/hostname", "/root_domain")),
            ("Reported IP", ("/ip", "/reported_ip")),
            ("Source", ("/registry", "/provider", "/source")),
            ("Method", ("/protocol", "/method")),
            ("Matched field", ("/attribution/field", "/evidence/match/field")),
            ("Matched value", ("/attribution/value", "/evidence/match/value")),
            ("Network", ("/evidence/details/network_range", "/evidence/details/cidr")),
            ("Retrieved", ("/retrieved_at", "/captured_at")),
            ("Validated", ("/validated_at", "/review/reviewed_at", "/evaluated_at")),
            ("Validated by", ("/validated_by", "/review/reviewer")),
            ("Decision", ("/review/decision", "/decision", "/status")),
            ("Decision reason", ("/review/reason", "/reason")),
            ("Source URL", ("/source_url", "/url")),
        ):
            add(label, *paths)
    elif kind == "vulnerability_record":
        for label, paths in (
            ("Identifier", ("/id", "/cve_id")),
            ("Status", ("/verification_status", "/status")),
            ("Source", ("/source", "/provider")),
            ("Published", ("/published_at", "/published")),
            ("Updated", ("/updated_at", "/last_modified")),
            ("Retrieved", ("/retrieved_at",)),
            ("CISA KEV listed", ("/kev",)),
            ("EPSS score", ("/epss",)),
            ("EPSS date", ("/epss_date",)),
            ("Disposition", ("/case_disposition/action",)),
            ("Reason", ("/case_disposition/reason",)),
            ("Reference", ("/source_url", "/url", "/official_url")),
        ):
            add(label, *paths)
        for field in _matching(
            entry, {"baseScore", "baseSeverity", "vectorString"}, prefixes=("/cvss",)
        ):
            selected.append(
                {**deepcopy(field), "label": "CVSS " + field["path"].rsplit("/", 1)[-1]}
            )
    elif kind in {
        "reference",
        "closing_resource",
        "source_snapshot",
        "advisory",
        "supporting_material",
        "import_provenance",
    }:
        for label, paths in (
            ("Publisher", ("/publisher", "/provider")),
            ("Source file", ("/filename", "/original_filename")),
            ("Source URL", ("/url", "/source_url", "/public_url")),
            ("Published", ("/published_at",)),
            ("Updated", ("/updated_at",)),
            ("Captured", ("/captured_at", "/retrieved_at", "/created_at")),
            ("Report date", ("/report_date", "/acquisition/report_date")),
            ("Outcome", ("/availability", "/status", "/outcome")),
            ("Description", ("/caption", "/description", "/summary")),
        ):
            add(label, *paths)
        if kind == "closing_resource":
            selected = [field for field in selected if field["label"] == "Source URL"]
    else:
        # Unknown record types remain readable and traceable; the evidence
        # reader supplies the complete labeled source fields below this summary.
        for field in entry.get("fields", []):
            if meaningful(field.get("value")) and len(field["path"].split("/")) <= 3:
                name = field["path"].rsplit("/", 1)[-1].replace("_", " ").capitalize()
                selected.append({**deepcopy(field), "label": name or "Value"})
                if len(selected) == 8:
                    break
    unique = OrderedDict()
    for field in selected:
        unique.setdefault((field["label"], field["text"]), field)
    return list(unique.values())


def _combined(label, fields, *, path):
    values = list(dict.fromkeys(field["text"] for field in fields if field))
    if not values:
        return None
    text = " · ".join(values)
    return {"path": path, "value": text, "text": text, "value_type": "string", "label": label}


def compact_record(entry, label, labels, *, kinds, humanize, record_title, current=False):
    fields = selected_fields(entry, current=current)
    if entry["kind"] in {"observation", "legacy_asset_summary"}:
        by_label = {f["label"]: f for f in fields}
        # Hostname/IP are already in the record heading. Keep all asset values
        # in the internal readable evidence card, without printing them twice.
        title = " | ".join(by_label[k]["text"] for k in ("Hostname", "IP address") if k in by_label)
        service = _combined(
            "Service",
            [by_label.get(k) for k in ("Port", "Protocol", "Technology", "Version")],
            path="/display/service",
        )
        fields = [
            f
            for f in fields
            if f["label"]
            not in {"Hostname", "IP address", "Port", "Protocol", "Technology", "Version"}
        ]
        if service:
            fields.insert(0, service)
    else:
        title = record_title(entry)
    if entry["kind"] in {"attribution_evidence", "accepted_attribution"}:
        by_label = {f["label"]: f for f in fields}
        match = _combined(
            "Matched evidence",
            [by_label.get("Matched field"), by_label.get("Matched value")],
            path="/display/matched_evidence",
        )
        repeated = {"Hostname", "Reported IP", "Matched field", "Matched value"}
        if entry.get("citations"):
            repeated.update({"Source", "Source URL"})
        fields = [f for f in fields if f["label"] not in repeated]
        if match:
            fields.insert(0, match)
    if entry["kind"] == "vulnerability_record":
        repeated = {"Identifier"}
        if entry.get("citations"):
            repeated.update({"Source", "Retrieved", "Reference"})
        fields = [f for f in fields if f["label"] not in repeated]
    if entry["kind"] == "reference":
        source = _combined(
            "Source",
            [f for f in fields if f["label"] in {"Publisher", "Published", "Updated", "Captured"}],
            path="/display/source",
        )
        fields = [
            f for f in fields if f["label"] not in {"Publisher", "Published", "Updated", "Captured"}
        ]
        if source:
            source["text"] = "; ".join(
                f["label"] + ": " + f["text"]
                for f in selected_fields(entry)
                if f["label"] in {"Publisher", "Published", "Updated", "Captured"}
            )
            source["value"] = source["text"]
            source["label"] = ""
            fields.insert(0, source)
    return {
        "id": entry["id"],
        "label": label,
        "title": title or record_title(entry),
        "kind": entry["kind"],
        "kind_label": kinds.get(entry["kind"], humanize(entry["kind"])),
        "owner": entry["owner"],
        "groups": [{"title": "", "path": "/", "fields": fields}],
        "citations": list(entry.get("citations", [])),
        "related": [],
        "source_ids": [],
        "status": entry.get("status"),
        "entry_ids": [entry["id"]],
        "reference_number": next(
            (f["value"] for f in entry["fields"] if f["path"] == "/number"), None
        )
        if entry["kind"] == "reference"
        else None,
    }


def _integer_ranges(values, prefix="", width=0):
    ordered = sorted(set(values))
    groups = []
    for value in ordered:
        if groups and value == groups[-1][-1] + 1:
            groups[-1].append(value)
        else:
            groups.append([value])

    def label(value):
        return prefix + str(value).zfill(width)

    return ", ".join(
        label(group[0]) if len(group) == 1 else label(group[0]) + "–" + label(group[-1])
        for group in groups
    )


def build_compact_views(appendix, *, sections, kinds, humanize, record_title, revision=REVISION):
    """One flowing appendix with section/record anchors, never empty pages."""
    if not appendix.get("entries"):
        return [], [], {"anchors": [], "labels": {}}
    labels = {}
    for code, _, _, _ in sections:
        for number, entry in enumerate(
            (e for e in appendix["entries"] if e["partition"] == code), 1
        ):
            labels[entry["id"]] = f"{code}-{number:02d}"
    records, section_anchors = [], []
    # Raw source bodies, old lookup attempts, and full advisory text are internal
    # evidence. Their cited publications remain in References below.
    omitted_kinds = {"source_snapshot", "attribution_history", "advisory"}
    printed_ids = set()
    for code, title, _, _ in sections:
        selected = [
            e
            for e in appendix["entries"]
            if e["partition"] == code and e["kind"] not in omitted_kinds
        ]
        if code == "D":
            selected.sort(key=lambda e: (e["kind"] != "reference", e["kind"]))
        grouped = OrderedDict()
        reference_urls = {
            field["value"]
            for entry in selected
            if entry["kind"] == "reference"
            for field in entry["fields"]
            if field["path"] == "/url"
        }
        for entry in selected:
            if entry["kind"] == "closing_resource" and any(
                field["path"] == "/url" and field["value"] in reference_urls
                for field in entry["fields"]
            ):
                continue
            record = compact_record(
                entry,
                labels[entry["id"]],
                labels,
                kinds=kinds,
                humanize=humanize,
                record_title=record_title,
                current=revision != LEGACY_REVISION,
            )
            if revision == REVISION and record["kind"] == "reference":
                record["reference_numbers"] = [record["reference_number"]]
            if (
                not any(group["fields"] for group in record["groups"])
                and entry["kind"] != "reference"
            ):
                continue
            key = entry["id"]
            if revision == REVISION and entry["kind"] == "reference":
                # The same publication can be cited by two pinned explainers.
                # Coalesce its displayed metadata, but retain every citation,
                # entry and internal revision. Different capture dates/body
                # hashes remain separate evidence.
                key = json.dumps(
                    sorted(
                        (field["path"], field["value"])
                        for field in entry["fields"]
                        if field["path"]
                        in {
                            "/publisher",
                            "/title",
                            "/url",
                            "/published_at",
                            "/updated_at",
                            "/retrieved_at",
                            "/sha256",
                        }
                    ),
                    sort_keys=True,
                )
            if entry["kind"] == "observation":
                key = json.dumps(
                    {
                        "title": record["title"],
                        "fields": [
                            (f["label"], f["value"])
                            for f in record["groups"][0]["fields"]
                            if f["label"] not in {"Observed", "Source row", "Source file"}
                        ],
                    },
                    sort_keys=True,
                )
            if key in grouped:
                existing = grouped[key]
                existing["entry_ids"].append(entry["id"])
                if revision == REVISION and entry["kind"] == "reference":
                    existing["reference_numbers"].extend(record["reference_numbers"])
                    reference_title = record["title"].split("] ", 1)[-1]
                    existing["title"] = (
                        " ".join(f"[{number}]" for number in existing["reference_numbers"])
                        + " "
                        + reference_title
                    )
                existing["citations"] = list(
                    dict.fromkeys(existing["citations"] + record["citations"])
                )
                original_fields = existing["groups"][0]["fields"]
                for field in record["groups"][0]["fields"]:
                    if field["label"] in {"Observed", "Source file", "Source row"}:
                        prior = next(
                            (f for f in original_fields if f["label"] == field["label"]), None
                        )
                        if prior and field["text"] not in prior["text"].split("; "):
                            prior["text"] += "; " + field["text"]
                            prior["value"] = prior["text"]
                        elif not prior:
                            original_fields.append(field)
            else:
                grouped[key] = record
        if not grouped:
            continue
        section_anchors.append("appendix-" + code)
        section_records = list(grouped.values())
        section_records[0]["section_heading"] = {
            "title": "Appendix " + code + " · " + title,
            "anchor": "appendix-" + code,
        }
        for record in section_records:
            if len(record["entry_ids"]) > 1 and record["kind"] == "observation":
                ids = record["entry_ids"]
                for field in record["groups"][0]["fields"]:
                    values = field["text"].split("; ")
                    if field["label"] == "Observed" and len(values) > 1:
                        values = sorted(set(values))
                        field["label"] = "Observation range"
                        field["value"] = field["text"] = values[0] + " – " + values[-1]
                    elif field["label"] == "Source row" and all(
                        value.isdigit() for value in values
                    ):
                        field["label"] = "Source rows"
                        field["value"] = field["text"] = _integer_ranges(map(int, values))
                record["groups"][0]["fields"].append(
                    {
                        "path": "/display/observations",
                        "label": "Observations",
                        "value": len(ids),
                        "text": str(len(ids)),
                        "value_type": "number",
                    }
                )
                record["groups"][0]["fields"].append(
                    {
                        "path": "/display/source_references",
                        "label": "Source records",
                        "value": ids,
                        "text": _integer_ranges(
                            (int(labels[i].split("-")[1]) for i in ids), prefix=code + "-", width=2
                        ),
                        "value_type": "string",
                    }
                )
            printed_ids.update(record["entry_ids"])
            records.append(record)
    if not records:
        return [], [], {"anchors": [], "labels": {}}
    # Existing front-page links to retained raw source records still resolve to
    # the appendix start; the detailed records are in the internal reader.
    omitted_anchors = [e["id"] for e in appendix["entries"] if e["id"] not in printed_ids]
    missing_sections = [
        "appendix-" + code for code, *_ in sections if "appendix-" + code not in section_anchors
    ]
    start_anchors = ["companion-appendix", *omitted_anchors, *missing_sections]
    anchors = [
        *start_anchors,
        *section_anchors,
        *(identifier for record in records for identifier in record["entry_ids"]),
    ]
    anchors += [
        "ref" + str(number)
        for record in records
        for number in record.get("reference_numbers", [record["reference_number"]])
        if number is not None
    ]
    model = {
        "id": "EX-APPENDIX-COMPACT",
        "type": "appendix",
        "owner": "information",
        "layout_revision": revision,
        "compact": True,
        "title": "Supporting records",
        "section": "",
        "section_title": "Supporting records",
        "anchors": start_anchors,
        "records": records,
        "appendix_entry_ids": [e["id"] for e in appendix["entries"]],
        "alt_text": "Concise reported observations, attribution, vulnerability records and source references.",
    }
    nodes = [
        {"kind": "page_break", "section_owner": "information"},
        {"kind": "exhibit", "exhibit_id": model["id"], "section_owner": "information"},
    ]
    return [model], nodes, {"anchors": list(dict.fromkeys(anchors)), "labels": labels}
