"""Compact recipient pages and portable, source-preserving internal evidence."""

from copy import deepcopy
import hashlib
import json
import shutil
import subprocess
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from modules.investigations.tools.preview_appendix import specimen
from modules.investigations.components.appendix import Appendix
from modules.investigations.components.appendix_view import (
    COMPACT_REVISION,
    REVISION,
    build_appendix_views,
)
from modules.investigations.components.appendix_compact import selected_fields
from modules.investigations.components.appendix_layout import BOTTOM, PAGE_WIDTH, layout_appendix
from modules.investigations.components.evidence_reader import write_evidence_reader
from modules.investigations.components.report_composition import compose
from modules.investigations.components.report_package import PackageRenderers, assemble_package
from modules.investigations.components.report_renderers import render_docx, render_pdf
from modules.ui.components.unicode_fonts import width as text_width
from modules.investigations.tests.support.report_artifacts import SourceWorkspace, captured_snapshot

from modules.investigations.tests.support.report_artifacts import (
    ReaderLinks,
)


def compact_specimen():
    data = specimen(capture=False)
    data["draft"]["appendix_revision"] = COMPACT_REVISION
    data["composition"] = compose(data)
    return data


def appendix_models(data):
    return [e for e in data["composition"]["exhibits"] if e["type"] == "appendix"]


def test_empty_appendix_has_no_pages_and_legacy_layout_is_preserved():
    model = Appendix().model()
    before = deepcopy(model)
    old, _, _ = build_appendix_views(model, REVISION)
    assert sum(len(layout_appendix(view)) for view in old) == 5
    views, nodes, navigation = build_appendix_views(model, COMPACT_REVISION)
    assert views == nodes == []
    assert navigation == {"anchors": [], "labels": {}}
    assert model == before


def test_complete_fixture_condenses_without_losing_raw_records_or_resource_links():
    original = specimen(capture=False)
    current = compact_specimen()
    assert current["composition"]["appendix"] == original["composition"]["appendix"]
    assert current["composition"]["citations"] == original["composition"]["citations"]
    old_pages = sum(len(layout_appendix(model)) for model in appendix_models(original))
    new_pages = sum(len(layout_appendix(model)) for model in appendix_models(current))
    assert old_pages == 22
    assert new_pages <= 3
    assert len(appendix_models(current)) == 1
    displayed = {
        field["value"]
        for record in appendix_models(current)[0]["records"]
        for group in record["groups"]
        for field in group["fields"]
        if isinstance(field["value"], str)
    }
    resources = {
        field["value"]
        for entry in current["composition"]["appendix"]["entries"]
        if entry["kind"] == "closing_resource"
        for field in entry["fields"]
        if field["path"] == "/url"
    }
    assert resources <= displayed


def test_meaningful_false_and_zero_survive_but_internal_fields_do_not_print():
    source = Appendix()
    entry = source.add(
        "C",
        "vulnerability_record",
        "CVE-2099-1",
        {
            "id": "CVE-2099-1",
            "kev": False,
            "epss": 0,
            "empty": "",
            "record_path": "private/cache.json",
            "description": None,
        },
    )
    fields = selected_fields(entry)
    assert any(f["value"] is False for f in fields)
    assert any(f["value"] == 0 and not isinstance(f["value"], bool) for f in fields)
    assert not any(f["path"] in {"/empty", "/record_path", "/description"} for f in fields)
    assert any(f["path"] == "/record_path" for f in entry["fields"])


def test_repeated_observations_group_with_counts_ranges_and_all_anchors():
    source = Appendix()
    for row in range(2, 102):
        source.add(
            "A",
            "observation",
            "Repeat observation",
            {
                "ip": "192.0.2.5",
                "source": {
                    "filename": "report.csv",
                    "row": row,
                    "fields": {
                        "hostname": "mail.example.com",
                        "ip": "192.0.2.5",
                        "port": 443,
                        "protocol": "TCP",
                        "tag": "CVE-2099-1",
                        "timestamp": f"2026-11-{2 if row < 50 else 3:02d}T00:00:00Z",
                    },
                },
            },
        )
    original = source.model()
    views, _, nav = build_appendix_views(original, COMPACT_REVISION)
    records = views[0]["records"]
    assert len(records) == 1 and len(records[0]["entry_ids"]) == 100
    fields = {f["label"]: f["text"] for f in records[0]["groups"][0]["fields"]}
    assert fields["Observations"] == "100"
    assert fields["Source rows"] == "2–101"
    assert fields["Source records"] == "A-01–A-100"
    assert fields["Observation range"] == "2026-11-02T00:00:00Z – 2026-11-03T00:00:00Z"
    assert {e["id"] for e in original["entries"]} <= set(nav["anchors"])
    assert len(layout_appendix(views[0])) == 1
    assert source.model() == original


def test_compact_pdf_docx_preserve_all_destinations_and_geometry(tmp_path):
    data = compact_specimen()
    for model in appendix_models(data):
        for page in layout_appendix(model):
            for element in page.elements:
                if element[0] == "text":
                    _, x, y, value, size, bold, _ = element
                    assert size >= 10 and 0 <= y <= page.height
                    assert (
                        x + text_width(value, "ExhibitSans-Bold" if bold else "ExhibitSans", size)
                        <= PAGE_WIDTH + 0.02
                    )
            assert all(
                segment["top"] + segment["height"] <= BOTTOM
                for segment in page.segments
                if segment.get("field_path")
            )
    render_pdf(data, tmp_path / "notification.pdf", tmp_path)
    render_docx(data, tmp_path / "notification.docx", tmp_path)
    text = subprocess.check_output(["pdftotext", str(tmp_path / "notification.pdf"), "-"]).decode()
    assert "Full source records and attribution history: Appendix B" not in text
    assert "Supporting records" in text
    assert "CVE-2099-10001" in text and "192.0.2.14" in text
    with ZipFile(tmp_path / "notification.docx") as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    anchors = [node.attrib[ns + "name"] for node in document.iter(ns + "bookmarkStart")]
    targets = [
        node.attrib[ns + "anchor"]
        for node in document.iter(ns + "hyperlink")
        if ns + "anchor" in node.attrib
    ]
    assert set(targets) <= set(anchors)
    expected = data["composition"]["appendix_navigation"]["anchors"]
    assert all(anchors.count(anchor) == 1 for anchor in expected)


def test_reader_covers_unknown_json_escapes_content_and_moves_offline(tmp_path):
    data = compact_specimen()
    root = tmp_path / "package"
    root.mkdir()
    (root / "evidence").mkdir()
    (root / "notification.pdf").write_bytes(b"synthetic notification")
    (root / "snapshot.json").write_text(json.dumps(data))
    raw = b'{"future_type":{"message":"<script>alert(1)</script>","value":false,"count":0,"empty":null}}'
    (root / "evidence" / "future.json").write_bytes(raw)
    before = deepcopy(data)
    write_evidence_reader(data, root)
    html = (root / "Evidence_Record.html").read_text(encoding="utf-8")
    assert "&lt;script&gt;" in html and "future.json" in html
    assert "false" in html and "null (supplied)" in html
    assert data == before and (root / "evidence/future.json").read_bytes() == raw
    parsed = ReaderLinks()
    parsed.feed(html)
    assert parsed.scripts == 1  # One bundled, CSP-hashed offline enhancement.
    assert len(parsed.ids) == len(set(parsed.ids))
    moved = tmp_path / "moved"
    shutil.move(root, moved)
    for href in parsed.links:
        url = urlsplit(href)
        if url.scheme:
            assert url.scheme in {"https", "http"}
        elif url.path:
            assert (moved / unquote(url.path)).is_file(), href
        else:
            assert unquote(url.fragment) in parsed.ids, href


def test_package_indexes_reader_and_retains_contact_extract_and_source_digest(tmp_path):
    from modules.entities.tests.support.contacts import contact_result
    from modules.entities.components.contact_evidence import prepare_snapshot

    data, _ = captured_snapshot(tmp_path / "sources")
    body = b'<p>Security: <a href="mailto:security@example.com">security@example.com</a></p>'
    digest = hashlib.sha256(body).hexdigest()
    result = contact_result()
    result["snapshots"][0].update(body=body, sha256=digest, truncated=True)
    captured, artifact = prepare_snapshot(result["snapshots"][0], result["candidates"])
    relative = "evidence/contact-discovery/run-one/page.contact.json"
    captured["path"] = relative
    path = tmp_path / "sources" / relative
    path.parent.mkdir(parents=True)
    path.write_bytes(artifact)
    data["contact_research"] = {
        "packaged_at": "2026-11-10T22:00:00Z",
        "contacts": [{"kind": "email", "value": "security@example.com", "purpose": "security"}],
        "runs": [
            {
                "id": "run-one",
                "snapshots": [captured],
            }
        ],
    }
    before = deepcopy(data)
    destination = tmp_path / "package"
    destination.mkdir()

    def render_stub(data, path, root):
        path.write_bytes(b"synthetic rendered output")

    package = assemble_package(
        SourceWorkspace(tmp_path / "sources"),
        data,
        destination,
        PackageRenderers(render_stub, render_stub),
    )
    assert data == before
    assert "Evidence_Record.html" in package.files
    assert "evidence/appendix-records.json" in package.files
    capture = package.snapshot["contact_research"]["runs"][0]["snapshots"][0]
    assert capture["package_availability"] == "available" and capture["truncated"] is True
    assert capture["retention"] == "contact-extract-v1"
    assert capture["sha256"] == digest
    assert capture["artifact_sha256"] == hashlib.sha256(artifact).hexdigest()
    assert capture["artifact_sha256"] != capture["sha256"]
    assert (destination / capture["path"]).read_bytes() == artifact
    assert not list(destination.rglob("*.body.txt"))
    assert all(body not in file.read_bytes() for file in destination.rglob("*") if file.is_file())
    reader = (destination / "Evidence_Record.html").read_text(encoding="utf-8")
    assert "security@example.com" in reader
    assert "Extracted contact evidence" in reader
    assert all(
        hashlib.sha256((destination / name).read_bytes()).hexdigest() == digest
        for name, digest in package.files.items()
    )
