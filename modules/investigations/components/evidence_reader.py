"""Portable human-readable evidence, generated only from package-owned records."""

from __future__ import annotations

import hashlib
from base64 import b64encode
from html import escape
from itertools import islice
import json
from pathlib import Path
from urllib.parse import quote, urlsplit

from .appendix import display_value, flatten_fields
from .appendix_compact import meaningful, selected_fields
from .appendix_view import KINDS, decoded_parts, humanize, record_title
from .evidence_reader_assets import CSS, SCRIPT
from .evidence_dossier import field_values, finding_groups, readable_time
from modules.ui.components.print_policy import priority_mark


def _text(value):
    return escape(str(value), quote=True)


def _link(path, label):
    target = "#" + quote(path[1:], safe="") if path.startswith("#") else quote(path, safe="/")
    return '<a href="' + target + '">' + _text(label) + "</a>"


def _safe_file(root, value):
    if not isinstance(value, str) or not value or "\\" in value:
        return None
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        return None
    candidate = root / path
    if (
        candidate.is_file()
        and not candidate.is_symlink()
        and candidate.resolve().is_relative_to(root.resolve())
    ):
        return path.as_posix()
    return None


def _value(value, *, preview=False):
    text = display_value(value)
    if preview and len(text) > 1600:
        return (
            _text(text[:1600])
            + '<span class="muted"> … Full value is retained in the original record.</span>'
        )
    try:
        parsed = urlsplit(text)
        link = (
            parsed.scheme in {"https", "http"}
            and bool(parsed.hostname)
            and not any(c.isspace() for c in text)
        )
    except ValueError:
        link = False
    if link:
        return '<a href="' + _text(text) + '" rel="noreferrer">' + _text(text) + "</a>"
    return _text(text)


def _fields(fields, *, details=False):
    if not fields:
        return '<p class="muted">No additional values recorded.</p>'
    rows = []
    for field in fields:
        path = field["path"]
        label = (
            field.get("label") or " / ".join(humanize(p) for p in decoded_parts(path)) or "Value"
        )
        key = '<small class="path">' + _text(path) + "</small>" if details else ""
        value = field.get("value")
        if isinstance(value, bool) and not details:
            value = "Yes" if value else "No"
        elif not details and any(
            word in label.casefold()
            for word in (
                "observed",
                "captured",
                "retrieved",
                "validated",
                "published",
                "updated",
                "seen",
            )
        ):
            value = readable_time(value)
        rows.append(
            "<tr><th>"
            + _text(label)
            + key
            + "</th><td>"
            + _value(value, preview=True)
            + "</td></tr>"
        )
    return '<div class="table-wrap"><table><tbody>' + "".join(rows) + "</tbody></table></div>"


def _technical(fields, raw, title="Technical fields"):
    shown = fields[:80]
    note = (
        '<p class="muted">Showing the first 80 source fields. '
        + "The complete record is retained in the linked original.</p>"
        if len(fields) > len(shown)
        else ""
    )
    return (
        '<details class="technical"><summary>'
        + _text(title)
        + "</summary>"
        + ("<p>" + raw + "</p>" if raw else "")
        + note
        + _fields(shown, details=True)
        + "</details>"
    )


def _card(identifier, title, kind, overview, fields, raw, *, status=None, extra="", label=None):
    return (
        '<article class="record" id="'
        + _text(identifier)
        + '"><div class="record-heading"><span class="record-kind">'
        + _text(kind)
        + '</span><a class="record-id" aria-label="Link to record '
        + _text(label or identifier)
        + '" href="#'
        + quote(identifier, safe="")
        + '">'
        + _text(label or identifier)
        + "</a></div>"
        + "<h3>"
        + _value(title, preview=True)
        + "</h3>"
        + (
            '<p class="outcome">Recorded outcome: <strong>' + _text(status) + "</strong></p>"
            if status
            else ""
        )
        + (_fields(overview) if overview else "")
        + extra
        + ('<p class="source-links">' + raw + "</p>" if raw else "")
        + (_technical(fields, "") if fields else "")
        + "</article>"
    )


def _finding(group, labels):
    values = group["values"]
    observations = group["entries"]
    finding = values.get("Finding") or values.get("Report type") or "Reported service observation"
    identity = " · ".join(str(values[key]) for key in ("Hostname", "IP address") if key in values)
    service = " · ".join(
        str(values[key]) for key in ("Protocol", "Port", "Technology", "Version") if key in values
    )
    software = values.get("Reported software")
    if software:
        service = " · ".join(value for value in (service, str(software)) if value)
    times = list(
        dict.fromkeys(str(field_values(entry).get("Observed", "")) for entry in observations)
    )
    times = [time for time in times if time]
    sources = list(
        dict.fromkeys(str(field_values(entry).get("Source file", "")) for entry in observations)
    )
    sources = [source for source in sources if source]
    metadata = [f"{len(observations)} source observation" + ("s" if len(observations) != 1 else "")]
    if times:
        metadata.append(
            readable_time(times[0]) if len(times) == 1 else f"{len(times)} recorded timestamps"
        )
    if sources:
        metadata.append(sources[0] if len(sources) == 1 else f"{len(sources)} source files")

    def connection_title(entry):
        title = record_title(entry)
        if entry.get("kind") == "reference":
            return title
        if entry.get("partition") == "B":
            identity = field_values(entry)
            title = (
                " · ".join(
                    str(identity[key]) for key in ("Hostname", "Reported IP") if key in identity
                )
                or entry["title"]
            )
        return labels.get(entry["id"], entry["id"]) + " · " + title

    connections = "".join(
        "<li><span>"
        + _text(KINDS.get(entry["kind"], humanize(entry["kind"])))
        + "</span>"
        + _link("#" + entry["id"], connection_title(entry))
        + "</li>"
        for entry in group["connections"]
    )
    originals = []
    for entry in observations:
        anchor = (
            '<span class="record-anchor" id="' + _text(entry["id"]) + '"></span>'
            if entry["id"] != group["id"]
            else ""
        )
        originals.append(
            anchor
            + _technical(
                entry.get("fields", []),
                "",
                "Original observation · " + labels.get(entry["id"], entry["id"]),
            )
        )
    original_details = "".join(originals)
    if len(observations) > 1:
        original_details = (
            '<details class="technical observation-batch"><summary>Original observations ('
            + str(len(observations))
            + ")</summary>"
            + original_details
            + "</details>"
        )
    return (
        '<article class="record finding" id="' + _text(group["id"]) + '">'
        '<div class="record-heading"><span class="record-kind">Reported finding</span>'
        + _link("#" + group["id"], labels.get(group["id"], group["id"]))
        + "</div>"
        "<h3>"
        + _text(finding)
        + '</h3><p class="finding-asset">'
        + _text(identity or "Asset identity not supplied")
        + "</p>"
        + ('<p class="finding-service">' + _text(service) + "</p>" if service else "")
        + '<p class="provenance">'
        + ' <span aria-hidden="true">/</span> '.join(_text(item) for item in metadata)
        + "</p>"
        + (
            '<div class="evidence-chain"><h4>Linked evidence</h4><ul>' + connections + "</ul></div>"
            if connections
            else ""
        )
        + '<div class="original-records">'
        + original_details
        + "</div>"
        + '<p class="source-links">'
        + _link("evidence/appendix-records.json", "Original structured records")
        + "</p></article>"
    )


def _bibliography(entry, label, raw):
    values = field_values(entry)
    context = [str(values[key]) for key in ("Publisher",) if key in values]
    for key in ("Published", "Updated", "Captured"):
        if key in values:
            context.append(key + " " + readable_time(values[key]))
    return (
        '<article class="record bibliography-item" id="' + _text(entry["id"]) + '">'
        '<div class="bibliography-label">'
        + _link("#" + entry["id"], label)
        + '</div><div class="bibliography-body">'
        "<h3>"
        + _text(record_title(entry))
        + "</h3>"
        + ('<p class="provenance">' + _text(" · ".join(context)) + "</p>" if context else "")
        + (
            '<p class="reference-url">' + _value(values["Source URL"]) + "</p>"
            if values.get("Source URL")
            else ""
        )
        + _technical(entry.get("fields", []), raw, "Source details")
        + "</div></article>"
    )


def _generic_overview(value):
    # Bound hidden previews even for very large captured feeds. The original
    # saved file remains complete and byte-identical.
    fields = list(islice(flatten_fields(value), 81))
    if isinstance(value, dict):
        # NVD API/catalog captures and CVE Program records use different JSON
        # envelopes. Give both the same readable summary without changing the
        # full record or inventing a description when none was published.
        nvd = value.get("cve", value)
        if (
            isinstance(nvd, dict)
            and isinstance(nvd.get("id"), str)
            and nvd["id"].startswith("CVE-")
        ):
            descriptions = nvd.get("descriptions", [])
            description = (
                next(
                    (
                        item.get("value")
                        for item in descriptions
                        if isinstance(item, dict) and str(item.get("lang", "")).startswith("en")
                    ),
                    None,
                )
                if isinstance(descriptions, list)
                else None
            )
            summary = {
                "Identifier": nvd["id"],
                "Status": nvd.get("vulnStatus"),
                "Published": nvd.get("published"),
                "Updated": nvd.get("lastModified"),
                "Description": description,
            }
            return [
                {"path": "/summary/" + key, "label": key, "value": item}
                for key, item in summary.items()
                if meaningful(item)
            ], fields
        metadata = value.get("cveMetadata", {})
        containers = value.get("containers", {})
        cna = containers.get("cna", {}) if isinstance(containers, dict) else {}
        if isinstance(metadata, dict) and isinstance(cna, dict) and metadata.get("cveId"):
            descriptions = cna.get("descriptions", [])
            if not isinstance(descriptions, list):
                descriptions = []
            description = next(
                (
                    item.get("value")
                    for item in descriptions
                    if isinstance(item, dict) and str(item.get("lang", "en")).startswith("en")
                ),
                None,
            )
            summary = {
                "Identifier": metadata.get("cveId"),
                "Status": metadata.get("state"),
                "Published": metadata.get("datePublished"),
                "Updated": metadata.get("dateUpdated"),
                "Description": description,
            }
            return [
                {"path": "/summary/" + key, "label": key, "value": item}
                for key, item in summary.items()
                if meaningful(item)
            ], fields
    names = {
        "id",
        "title",
        "name",
        "description",
        "summary",
        "status",
        "outcome",
        "url",
        "source_url",
        "provider",
        "publisher",
        "retrieved_at",
        "captured_at",
        "created_at",
        "hostname",
        "ip",
        "reason",
        "value",
        "purpose",
        "actor",
        "detail",
        "label",
        "timestamp_utc",
        "section_key",
        "revision",
        "handle",
        "objectClassName",
        "startAddress",
        "endAddress",
        "country",
    }
    selected = [
        f
        for f in fields
        if len(f["path"].split("/")) <= 3
        and f["path"].rsplit("/", 1)[-1] in names
        and meaningful(f["value"])
    ]
    if not selected:
        selected = [f for f in fields if meaningful(f["value"])][:8]
    overview = selected[:12]
    collections = (
        [(key, item) for key, item in value.items() if isinstance(item, list)]
        if isinstance(value, dict)
        else [("Records", value)]
        if isinstance(value, list)
        else []
    )
    for key, items in collections[:4]:
        overview.append(
            {
                "path": "/summary/count/" + key,
                "label": humanize(key) + " count",
                "value": len(items),
            }
        )
    return overview, fields


def _priority_summary(score):
    """Readable internal assessment; source findings remain separate records."""
    mark = priority_mark(score)
    if not mark:
        return ""
    values = {
        "Quality": score.get("quality"),
        "Urgency": score.get("urgency"),
        "Aggregate": score.get("aggregate"),
        "Scored at": readable_time(score["scored_at"]) if score.get("scored_at") else None,
        "Policy version": score.get("policy_version"),
    }
    factors = score.get("factors") if isinstance(score.get("factors"), dict) else {}
    rows = []
    for phase in ("quality", "urgency"):
        for factor in factors.get(phase, []):
            if not isinstance(factor, dict):
                continue
            rows.append(
                "<tr><td>"
                + _text(phase.title())
                + "</td><td>"
                + _text(factor.get("label") or factor.get("id") or "Factor")
                + "</td><td>"
                + _value(factor.get("points"))
                + " / "
                + _value(factor.get("weight"))
                + "</td><td>"
                + _text(factor.get("reason") or "")
                + "</td></tr>"
            )
    return (
        '<div class="outreach-priority"><p style="color:#'
        + mark["color"]
        + ';font-weight:700">'
        + mark["label"]
        + "</p>"
        '<details class="package-details"><summary>Priority assessment</summary>'
        "<p>Internal outreach ranking, separate from CVSS severity and information handling. "
        "This saved assessment is retained with the report; catalog updates do not change it.</p>"
        '<dl class="summary-grid">'
        + "".join(
            "<div><dt>" + _text(key) + "</dt><dd>" + _value(value) + "</dd></div>"
            for key, value in values.items()
            if meaningful(value)
        )
        + '</dl><div class="table-wrap"><table><thead><tr><th>Phase</th><th>Factor</th>'
        "<th>Points / weight</th><th>Basis</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div><p>"
        + _link("outreach-priority.json", "Complete saved priority assessment")
        + "</p></details></div>"
    )


def _scope_ledger(scope):
    """Display the saved recipient decision separately from retained evidence."""
    rows = [row for row in scope.get("rows", []) if row.get("decision")]
    cards = []
    for number, row in enumerate(rows, 1):
        source = row.get("source", {})
        overview = [
            {"path": key, "label": label, "value": value}
            for key, label, value in (
                (
                    "decision",
                    "Recipient report",
                    "Excluded" if row["decision"] == "exclude" else "Included",
                ),
                ("finding", "Reported finding", row.get("finding")),
                (
                    "source",
                    "Original source",
                    " · ".join(
                        str(value)
                        for value in (
                            source.get("workbook"),
                            source.get("sheet"),
                            "row " + str(source["row"]) if source.get("row") is not None else None,
                        )
                        if value
                    ),
                ),
                ("reason", "Decision reason", row.get("reason")),
                ("actor", "Analyst", row.get("actor")),
                ("decided_at", "Decision time", readable_time(row.get("decided_at"))),
            )
            if value
        ]
        cards.append(
            _card(
                "scope-decision-" + str(number),
                " · ".join(str(value) for value in (row.get("hostname"), row.get("ip")) if value)
                or row["entry_id"],
                "Scope decision",
                overview,
                [],
                "",
            )
        )
    return (
        '<section id="observation-scope"><h2>Recipient scope and retained observations</h2>'
        + "<p><strong>"
        + _text(scope.get("included", 0))
        + "</strong> included in this report · <strong>"
        + _text(scope.get("excluded", 0))
        + "</strong> excluded · <strong>"
        + _text(scope.get("total", 0))
        + "</strong> original observations retained.</p>"
        + "<p>Exclusions affect this recipient notification only. They do not establish remediation or remove original evidence. A retained attribution observation may support identity without being a notified finding.</p>"
        + ("<p>No explicit scope changes were recorded.</p>" if not rows else "".join(cards))
        + "<p>"
        + _link("snapshot.json", "Complete original observations and saved decisions")
        + "</p></section>"
    ), len(rows)


def write_evidence_reader(data, root):
    """Create one offline index, without fetching or changing any source bytes."""
    root = Path(root)
    priority = _priority_summary(data.get("intake_score"))
    if priority:
        (root / "outreach-priority.json").write_text(
            json.dumps(
                {
                    "purpose": "Internal outreach priority, separate from vulnerability severity and information handling.",
                    "assessment": data["intake_score"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    appendix = data.get("composition", {}).get("appendix", {})
    entries = appendix.get("entries", [])
    labels = dict(data.get("composition", {}).get("appendix_navigation", {}).get("labels", {}))
    for code in "ABCD":
        for number, entry in enumerate(
            (entry for entry in entries if entry.get("partition") == code), 1
        ):
            labels.setdefault(entry["id"], f"{code}-{number:02d}")
    findings = finding_groups(entries)
    finding_ids = {entry["id"] for group in findings for entry in group["entries"]}
    relocated = {}
    for record in [
        *data.get("draft", {}).get("cve_records", []),
        *data.get("source_snapshots", []),
    ]:
        for source in [record, *record.get("sources", [])]:
            if source.get("original_record_path") and source.get("record_path"):
                relocated[source["original_record_path"]] = source["record_path"]
    projection = root / "evidence" / "appendix-records.json"
    projection.parent.mkdir(exist_ok=True)
    projection.write_text(json.dumps(appendix, ensure_ascii=False, indent=2), encoding="utf-8")
    sections = []
    index = []
    if data.get("observation_scope"):
        ledger, count = _scope_ledger(data["observation_scope"])
        sections.append(ledger)
        index.append(("observation-scope", "Recipient scope", count))
    codes = (
        ("A", "Findings"),
        ("B", "Attribution"),
        ("C", "Vulnerability records"),
        ("D", "References"),
    )
    for code, label in codes:
        selected = [e for e in entries if e.get("partition") == code]
        if not selected:
            continue
        display_labels = {
            entry["id"]: labels.get(entry["id"], f"{code}-{i:02d}")
            for i, entry in enumerate(selected, 1)
        }
        # Qualifying/current evidence first, while preserving lookup history.
        selected.sort(key=lambda e: e.get("kind") == "attribution_history")
        if code == "D":
            selected.sort(
                key=lambda entry: 0
                if entry.get("kind") == "reference"
                else 2
                if entry.get("kind") == "closing_resource"
                else 1
            )
        anchor = "records-" + code.lower()
        count = (
            len(findings) + sum(entry["id"] not in finding_ids for entry in selected)
            if code == "A"
            else len(selected)
        )
        index.append((anchor, label, count))
        body = [_finding(group, labels) for group in findings] if code == "A" else []
        for entry in selected:
            if entry["id"] in finding_ids:
                continue
            sources = []
            for field in entry.get("fields", []):
                if field["path"].endswith(("/record_path", "/path", "/preview_path")):
                    original = field["value"]
                    relative = _safe_file(
                        root,
                        relocated.get(original, original)
                        if isinstance(original, str)
                        else original,
                    )
                    if relative:
                        sources.append(_link(relative, "Saved source file"))
            raw = _link("evidence/appendix-records.json", "Complete structured record")
            if sources:
                raw += " · " + " · ".join(dict.fromkeys(sources))
            if code == "D":
                body.append(_bibliography(entry, display_labels[entry["id"]], raw))
                continue
            overview = selected_fields(entry, current=True)
            if not overview:
                overview = [f for f in entry.get("fields", []) if meaningful(f["value"])][:8]
            heading = record_title(entry)
            if entry.get("kind") in {"observation", "legacy_asset_summary"}:
                identity = [
                    field for field in overview if field.get("label") in {"Hostname", "IP address"}
                ]
                if identity:
                    heading = " | ".join(display_value(field["value"]) for field in identity)
                    overview = [field for field in overview if field not in identity]
            elif entry.get("kind") in {
                "attribution_evidence",
                "accepted_attribution",
                "attribution_history",
            }:
                identity = [
                    field for field in overview if field.get("label") in {"Hostname", "Reported IP"}
                ]
                if identity:
                    heading = " | ".join(display_value(field["value"]) for field in identity)
                    overview = [field for field in overview if field not in identity]
            overview = [
                field
                for field in overview
                if not (
                    field.get("label") == "Identifier" and display_value(field["value"]) == heading
                )
            ]
            related = [
                identifier
                for identifier in dict.fromkeys(entry.get("referenced_by", []))
                if identifier in labels
            ]
            extra = (
                "<details><summary>Related records ("
                + str(len(related))
                + ")</summary><p>"
                + ", ".join(_link("#" + identifier, labels[identifier]) for identifier in related)
                + "</p></details>"
                if related
                else ""
            )
            body.append(
                _card(
                    entry["id"],
                    heading,
                    KINDS.get(entry["kind"], humanize(entry["kind"])),
                    overview,
                    entry.get("fields", []),
                    raw,
                    status=entry.get("status") if entry.get("status") != "recorded" else None,
                    label=display_labels[entry["id"]],
                    extra=extra,
                )
            )
        sections.append(
            '<section id="'
            + anchor
            + '"><h2>'
            + _text(label)
            + "</h2>"
            + "".join(body)
            + "</section>"
        )

    contacts = data.get("contact_research")
    legacy_contact_paths = set()
    if contacts:
        selected = contacts.get("contacts", contacts.get("candidates", []))
        cards = []
        for i, contact in enumerate(selected, 1):
            fields = list(flatten_fields(contact))
            overview = [
                f
                for f in fields
                if meaningful(f.get("value"))
                and f["path"]
                in {
                    "/purpose",
                    "/name",
                    "/role",
                    "/source",
                    "/first_seen",
                    "/last_seen",
                }
            ]
            cards.append(
                _card(
                    "contact-" + str(i),
                    contact.get("value", "Saved contact"),
                    "Contact",
                    overview,
                    fields,
                    _link("evidence/contact-research.json", "Contact research snapshot"),
                )
            )
        for run in contacts.get("runs", []):
            for captured in run.get("snapshots", []):
                # New readers never expose a legacy raw webpage as an openable
                # resource, even if an older package still contains that file.
                from modules.entities.components.contact_evidence import is_derived_snapshot

                derived = is_derived_snapshot(captured)
                if not derived and isinstance(captured.get("path"), str):
                    legacy_contact_paths.add(captured["path"])
                path = (
                    _safe_file(root, captured.get("path"))
                    if derived and captured.get("package_availability") == "available"
                    else None
                )
                overview, fields = _generic_overview(captured)
                overview = [
                    field for field in overview if field["path"] not in {"/url", "/source_url"}
                ]
                for key, label in (
                    ("status_code", "HTTP status"),
                    ("truncated", "Partial capture"),
                    ("package_issue", "Saved file issue"),
                ):
                    if meaningful(captured.get(key)):
                        overview.append({"path": "/" + key, "label": label, "value": captured[key]})
                cards.append(
                    _card(
                        "contact-source-" + str(len(cards) + 1),
                        captured.get("url")
                        or captured.get("source_url")
                        or "Contact source capture",
                        "Contact source",
                        overview,
                        fields,
                        _link(path, "Extracted contact evidence")
                        if path
                        else _link("evidence/contact-research.json", "Contact research snapshot"),
                        status=(
                            "Source metadata only"
                            if not path
                            else "Partial capture"
                            if captured.get("truncated")
                            else "Contact extract"
                        ),
                    )
                )
        index.append(("contacts", "Contact research", len(cards)))
        sections.append(
            '<section id="contacts"><h2>Contacts</h2><p class="section-note">Saved with this package · '
            + _text(
                readable_time(
                    contacts.get("packaged_at", data.get("created_at", "Time not recorded"))
                )
            )
            + "</p>"
            + "".join(cards)
            + "</section>"
        )

    if data.get("evidence"):
        index.append(("images", "Captured images", len(data["evidence"])))
        cards = []
        for i, item in enumerate(data["evidence"], 1):
            fields = list(flatten_fields(item))
            overview = [
                f
                for f in fields
                if f["path"]
                in {
                    "/caption",
                    "/filename",
                    "/source_url",
                    "/captured_at",
                    "/kind",
                    "/source_metadata/website_capture/final_url",
                    "/source_metadata/website_capture/title",
                    "/source_metadata/website_capture/capture_status",
                }
            ]
            path = _safe_file(root, item.get("path"))
            preview = _safe_file(root, item.get("preview_path"))
            image = (
                '<img loading="lazy" alt="'
                + _text(item.get("caption") or "Captured evidence")
                + '" src="'
                + quote(preview, safe="/")
                + '">'
                if preview
                else ""
            )
            cards.append(
                _card(
                    "image-" + str(i),
                    item.get("caption") or item.get("filename") or "Captured image",
                    "Image",
                    overview,
                    fields,
                    _link(path, "Original captured file") if path else "",
                    extra=image,
                )
            )
        sections.append(
            '<section id="images"><h2>Captured images</h2>' + "".join(cards) + "</section>"
        )

    chronology = data.get("chronology", [])
    if chronology:
        index.append(("chronology", "Work and certification chronology", len(chronology)))
        rows = []
        for i, event in enumerate(chronology, 1):
            overview, fields = _generic_overview(event)
            rows.append(
                _card(
                    "event-" + str(i),
                    event.get("action") or event.get("type") or "Recorded event",
                    "Chronology",
                    overview,
                    fields,
                    _link("chronology.json", "Original chronology"),
                )
            )
        sections.append(
            '<section id="chronology"><h2>Work and certification chronology</h2>'
            + "".join(rows)
            + "</section>"
        )

    # A readable fallback covers every saved JSON type, including future source
    # schemas. Keep the full report snapshot as a linked artifact: its evidence
    # is already presented above and embedded artwork is not a useful table.
    files = []
    raw_cards = []
    specialized = {
        "snapshot.json",
        "appendix-index.json",
        "chronology.json",
        "evidence/appendix-records.json",
        "evidence/contact-research.json",
    }
    for file in sorted(root.rglob("*")):
        if not file.is_file() or file.is_symlink():
            continue
        relative = file.relative_to(root).as_posix()
        if relative == "Evidence_Record.html":
            continue
        if relative in legacy_contact_paths or (
            relative.startswith("evidence/contact-") and relative.endswith(".body.txt")
        ):
            # The contact cards retain source provenance. A general file index
            # must not reintroduce links to raw website content excluded there.
            continue
        with file.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        files.append((relative, file.stat().st_size, digest))
        if file.suffix.lower() != ".json" or relative in specialized:
            continue
        try:
            value = json.loads(file.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raw_cards.append(
                _card(
                    "source-" + str(len(raw_cards) + 1),
                    file.name,
                    "Saved source",
                    [],
                    [],
                    _link(relative, "Original bytes"),
                    status="Saved bytes could not be decoded as JSON",
                )
            )
            continue
        overview, fields = _generic_overview(value)
        source_title = next(
            (
                display_value(field["value"])
                for field in overview
                if field.get("label") == "Identifier" or field.get("path") in {"/title", "/name"}
            ),
            file.name,
        )
        overview = [
            field
            for field in overview
            if not (
                field.get("label") == "Identifier" and display_value(field["value"]) == source_title
            )
        ]
        raw_cards.append(
            _card(
                "source-" + str(len(raw_cards) + 1),
                source_title,
                "Saved source record",
                overview,
                fields,
                _link(relative, "Original JSON · " + file.name),
            )
        )
    if raw_cards:
        index.append(("sources", "Saved source records", len(raw_cards)))
        sections.append(
            '<section id="sources"><h2>Saved source records</h2>'
            + "".join(raw_cards)
            + "</section>"
        )
    index.append(("files", "Package file index", len(files)))
    rows = [
        '<tr data-path="'
        + _text(path)
        + '" data-size="'
        + str(size)
        + '" data-sha256="'
        + digest
        + '"><td>'
        + _link(path, path)
        + "</td><td>"
        + f"{size:,}"
        + "</td><td><code>"
        + digest
        + '</code></td><td class="verification">Not checked</td></tr>'
        for path, size, digest in files
    ]
    sections.append(
        '<section id="files"><h2>Package file index</h2><p>Original records retain their recorded bytes. Hashes compare file contents with this saved index; they do not establish who created a record. The reader itself is covered by the final package manifest.</p>'
        + '<div class="verify-tools" hidden><p>Select the extracted package folder or individual files to compare SHA-256 hashes. Files are read locally and are never uploaded.</p><button id="choose-folder" type="button">Choose package folder</button> <button id="choose-files" type="button">Choose files</button><input id="verify-folder" type="file" webkitdirectory multiple hidden><input id="verify-files" type="file" multiple hidden><p id="verify-result" class="verify-result" role="status" aria-live="polite"></p></div>'
        + "<details><summary>Files and SHA-256 hashes ("
        + str(len(files))
        + ')</summary><div class="table-wrap"><table class="hash-table"><thead><tr><th>File</th><th>Bytes</th><th>SHA-256</th><th>Verification</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table></div></details></section>"
    )
    order = {
        key: number
        for number, key in enumerate(
            (
                "records-a",
                "observation-scope",
                "contacts",
                "records-c",
                "records-b",
                "images",
                "records-d",
                "sources",
                "chronology",
                "files",
            )
        )
    }
    sections.sort(key=lambda html: order.get(html.split('id="', 1)[1].split('"', 1)[0], 99))
    index.sort(key=lambda row: order.get(row[0], 99))
    certification = data.get("certification", {})
    overview = {
        "Notification": data.get("notification_id") or data.get("case_id"),
        "Report revision": data.get("report_revision"),
        "Certified by": certification.get("certified_by"),
        "Certified at": readable_time(certification["certified_at"])
        if certification.get("certified_at")
        else None,
    }
    summary = (
        '<dl class="summary-grid">'
        + "".join(
            "<div><dt>" + _text(key) + "</dt><dd>" + _value(value) + "</dd></div>"
            for key, value in overview.items()
            if meaningful(value)
        )
        + "</dl>"
    )
    options = '<option value="all">All records</option>' + "".join(
        '<option value="' + _text(anchor) + '">' + _text(label) + "</option>"
        for anchor, label, count in index
        if anchor != "files"
    )
    controls = (
        '<section class="reader-controls" aria-label="Find evidence" hidden>'
        '<div class="control-row"><div class="search-control"><label class="visually-hidden" for="evidence-search">Search records</label>'
        '<input id="evidence-search" type="search" autocomplete="off" placeholder="Search findings, assets, sources…  /" aria-describedby="result-count"></div>'
        '<div class="filter-control"><label class="visually-hidden" for="evidence-filter">Record group</label><select id="evidence-filter">'
        + options
        + '</select></div><button type="button" id="print-evidence">Print view</button></div>'
        '<div class="control-actions"><span id="result-count" class="result-count" role="status" aria-live="polite"></span>'
        '<button type="button" id="reset-filters">Clear filters</button><button type="button" id="collapse-records">Collapse details</button></div></section>'
        '<p id="empty-result" class="empty-result" hidden>No records match these filters.</p>'
    )
    observation_count = sum(len(group["entries"]) for group in findings)
    assets = {
        str(group["values"].get("IP address") or group["values"].get("Hostname"))
        for group in findings
        if group["values"].get("IP address") or group["values"].get("Hostname")
    }
    counts = []
    for count, singular in (
        (len(findings), "finding"),
        (len(assets), "asset"),
        (observation_count, "source observation"),
    ):
        if count:
            counts.append(
                "<strong>" + str(count) + "</strong> " + singular + ("s" if count != 1 else "")
            )
    selected_contacts = (contacts or {}).get("contacts", (contacts or {}).get("candidates", []))
    contact_brief = ""
    if selected_contacts:
        contact_brief = '<div class="brief-contact"><span>Saved contact</span>' + _link(
            "#contact-1", selected_contacts[0].get("value") or "View contacts"
        )
        if len(selected_contacts) > 1:
            contact_brief += " <small>+" + str(len(selected_contacts) - 1) + "</small>"
        contact_brief += "</div>"
    brief = (
        '<div class="dossier-brief"><p>'
        + ' <span aria-hidden="true">/</span> '.join(counts)
        + "</p>"
        + contact_brief
        + "</div>"
        if counts or contact_brief
        else ""
    )
    script_hash = b64encode(hashlib.sha256(SCRIPT.encode()).digest()).decode()
    policy = (
        "default-src 'none'; script-src 'sha256-"
        + script_hash
        + "'; style-src 'unsafe-inline'; img-src 'self' data:; connect-src 'none'; base-uri 'none'; form-action 'none'"
    )
    navigation = (
        '<li><a href="#dossier-records" data-group="all" aria-current="true">All records</a></li>'
        + "".join(
            '<li><a href="#'
            + _text(anchor)
            + '"'
            + (' data-group="' + _text(anchor) + '"' if anchor != "files" else "")
            + ">"
            + _text(label)
            + "</a><span>"
            + str(count)
            + "</span></li>"
            for anchor, label, count in index
        )
    )
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Evidence Record — '
        + _text(data.get("entity_name") or data.get("domain") or "Notification")
        + '</title><meta http-equiv="Content-Security-Policy" content="'
        + _text(policy)
        + '"><style>'
        + CSS
        + '</style></head><body><a class="skip-link" href="#dossier-records">Skip to findings</a><main id="evidence-main">'
        '<header class="masthead"><div class="masthead-line"><span class="eyebrow">Shadowserver Eclipse / Internal evidence record</span><span class="handling">TLP:AMBER</span></div><h1>'
        + _text(data.get("entity_name") or data.get("domain") or "Evidence dossier")
        + '</h1><div class="masthead-meta"><span>'
        + _text(data.get("domain") or "")
        + "</span>"
        + _link("notification.pdf", "Recipient report")
        + (
            _link("complete-report.pdf", "Complete report")
            if _safe_file(root, "complete-report.pdf")
            else ""
        )
        + (
            _link("exhibits/exhibit-gallery.html", "Exhibit gallery")
            if _safe_file(root, "exhibits/exhibit-gallery.html")
            else ""
        )
        + "</div>"
        + brief
        + priority
        + '<details class="package-details"><summary>Package details</summary>'
        + summary
        + "<p>"
        + _link("snapshot.json", "Complete report snapshot")
        + "</p></details></header>"
        '<div class="dossier-layout"><nav class="category-rail" aria-label="Evidence index"><span class="eyebrow">In this record</span><ul>'
        + navigation
        + '</ul></nav><div class="dossier-content" id="dossier-records">'
        + controls
        + "".join(sections)
        + "</div></div><footer>Internal evidence · Saved source times remain authoritative. Displayed UTC times preserve their original instant; exact values remain in the source details.</footer></main><script>"
        + SCRIPT
        + "</script></body></html>"
    )
    (root / "Evidence_Record.html").write_text(html, encoding="utf-8")
