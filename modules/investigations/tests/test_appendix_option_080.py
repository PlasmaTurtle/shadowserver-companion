"""Recipient appendix selection retains provenance and independently deliverable detail."""

from copy import deepcopy
import hashlib
import json
from modules.workspace.components import compact_json
import re
import subprocess
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

from tests.support.workbench import app, client, import_rows, ready, validate_sections
from modules.investigations.tools.preview_closing import specimen
from modules.investigations.components.appendix_view import REVISION as APPENDIX_REVISION
from modules.investigations.components.attribution_model import REVISION as ATTRIBUTION_REVISION
from modules.investigations.components.report_composition import compose
from modules.investigations.components.report_package import supporting_appendix_snapshot
from modules.investigations.components.report_renderers import render_pdf, render_docx
from modules.investigations.components.reviews.policy import fingerprints
from modules.investigations.components.report_snapshot import snapshot

NOTE = "The full supporting appendix is available upon request."
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def pdf_text(path):
    return subprocess.check_output(["pdftotext", "-layout", str(path), "-"]).decode()


def word_text_and_links(path):
    with ZipFile(path) as package:
        root = ET.fromstring(package.read("word/document.xml"))
    text = " ".join(
        [(element.text or "") for element in root.findall(".//w:t", NS)]
        + [element.attrib["descr"] for element in root.iter() if "descr" in element.attrib]
    )
    names = {
        element.attrib["{" + NS["w"] + "}name"]
        for element in root.findall(".//w:bookmarkStart", NS)
    }
    anchors = {
        element.attrib["{" + NS["w"] + "}anchor"]
        for element in root.findall(".//w:hyperlink", NS)
        if "{" + NS["w"] + "}anchor" in element.attrib
    }
    return " ".join(text.split()), names, anchors


@pytest.mark.parametrize("reviewed_appendix", [False, True])
def test_recipient_option_keeps_sources_references_and_separate_documents(
    tmp_path, reviewed_appendix
):
    data = specimen()
    data["draft"]["attribution_revision"] = ATTRIBUTION_REVISION
    data["draft"]["appendix_revision"] = APPENDIX_REVISION if reviewed_appendix else "legacy"
    data["draft"].pop("include_appendix", None)
    full = compose(data)
    data["draft"]["include_appendix"] = True
    assert compose(data) == full  # Existing/default-true composition bytes stay stable.
    raw = deepcopy(data["qualified_lead"])
    data["draft"]["include_appendix"] = False
    data["composition"] = compose(data)
    content = data["composition"]
    assert content["appendix"] == full["appendix"]
    assert content["citations"] == full["citations"]
    assert data["qualified_lead"] == raw
    assert content["supporting_appendix_sections"]
    appendix_ids = {e["id"] for e in content["exhibits"] if e["type"] == "appendix"}
    assert not any(n.get("exhibit_id") in appendix_ids for n in content["sections"])
    assert {n["number"] for n in content["sections"] if n["kind"] == "reference"} == {
        c["number"] for c in content["citations"]
    }
    assert "appendix_navigation" not in content
    compact = tmp_path / "recipient.pdf"
    word = tmp_path / "recipient.docx"
    render_pdf(data, compact, tmp_path)
    render_docx(data, word, tmp_path)
    text = " ".join(pdf_text(compact).split())
    word_text, names, anchors = word_text_and_links(word)
    for rendered in (text, word_text):
        assert NOTE in rendered
        assert not re.search(r"Appendi(?:x|ces) [ABCD]\b|Companion Appendix", rendered)
        assert "Full observations and supporting records are available upon request." in rendered
        assert "Advisory guidance · See References." in rendered
        assert "Supporting references: References" not in rendered
        assert "full references: References" not in rendered
        assert "References" in rendered
    assert anchors <= names, anchors - names
    appendix = supporting_appendix_snapshot(data)
    render_pdf(appendix, tmp_path / "appendix.pdf", tmp_path)
    render_docx(appendix, tmp_path / "appendix.docx", tmp_path)
    appendix_text = pdf_text(tmp_path / "appendix.pdf")
    assert re.search(r"Appendix [ABCD]\b|Appendices", appendix_text)
    assert NOTE not in appendix_text
    _, appendix_names, appendix_anchors = word_text_and_links(tmp_path / "appendix.docx")
    assert appendix_anchors <= appendix_names
    # Standalone rendering must not mutate the compact report model.
    assert data["composition"] is content
    assert content["sections"] != appendix["composition"]["sections"]


def opened(client, app):
    import_rows(client, app)
    lead_id = client.get("/api/leads").json()[0]["id"]
    return client.get("/api/leads/" + lead_id).json()


def save_option(client, lead, included):
    return client.put(
        f"/api/leads/{lead['id']}/draft?case_id={lead['case_id']}",
        json={
            "expected_revision": lead["draft_revision"],
            "fields": {**lead["draft"], "include_appendix": included},
        },
    )


def test_default_option_preserves_existing_review_fingerprints(client, app):
    lead = opened(client, app)
    data = snapshot(
        app.state.store, lead["id"], lead["case_id"], capture_sections=(), include_reviews=False
    )
    data["draft"].pop("include_appendix", None)
    data["composition"] = compose(data)
    before = fingerprints(data, lead)
    data["draft"]["include_appendix"] = True
    data["composition"] = compose(data)
    assert fingerprints(data, lead) == before


@pytest.mark.parametrize("initial", [True, False])
def test_appendix_choice_preserves_frozen_content_sections(client, app, initial):
    lead = opened(client, app)
    lead = save_option(client, lead, initial).json()
    response = client.post(
        f"/api/cases/{lead['case_id']}/sections/closing/validate",
        json={"expected_revision": lead["draft_revision"]},
    )
    assert response.status_code == 200, response.text
    lead = response.json()
    changed = save_option(client, lead, not initial)
    assert changed.status_code == 200, changed.text
    assert changed.json()["draft"]["include_appendix"] is not initial
    prior = next(r for r in lead["section_reviews"] if r["key"] == "closing")
    current = next(r for r in changed.json()["section_reviews"] if r["key"] == "closing")
    assert current["status"] == "validated"
    assert current["validation_id"] == prior["validation_id"]


def test_compact_certification_publishes_manifest_guarded_appendix_downloads(client, app):
    lead = opened(client, app)
    lead = save_option(client, lead, False).json()
    ready(client, lead["id"])
    response = client.post(f"/api/leads/{lead['id']}/finalize?case_id={lead['case_id']}")
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["supporting_appendix_available"]
    folder = app.state.store.path(report["path"])
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    for extension in ("pdf", "docx"):
        name = "supporting-appendix." + extension
        assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == manifest["files"][name]
        download = client.get(f"/api/reports/{report['id']}/appendix-{extension}")
        assert download.status_code == 200
        assert download.content == (folder / name).read_bytes()
    saved = compact_json.loads((folder / "snapshot.json").read_text(encoding="utf-8"))
    assert saved["composition"]["appendix"]["entries"]
    assert saved["composition"]["supporting_appendix_sections"]
    assert client.get("/api/reports").json()[0]["supporting_appendix_available"]
    (folder / "supporting-appendix.pdf").write_bytes(b"changed")
    assert client.get(f"/api/reports/{report['id']}/appendix-pdf").status_code == 409
