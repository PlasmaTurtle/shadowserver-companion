"""Closing copy, citation continuity, clickable exports and certification."""

from copy import deepcopy
import json
import socket
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

from modules.investigations.tests.support.section_reviews import prepared, save, status
from tests.support.workbench import app, client, reopen_sections
from modules.investigations.tools.preview_closing import specimen
from modules.investigations.components import approved_template as approved
from modules.investigations.components.closing_page_layout import layout_closing, BOTTOM, PAGE_WIDTH
from modules.investigations.components.closing_page_model import (
    ADDITIONAL_URLS,
    REVISION,
    SECOND_REVIEW_REVISION,
    resource_groups,
    safe_resource_url,
)
from modules.ui.components.exhibit_rendering import (
    capture_exhibit_masters,
    prepared_pages,
    svg_pages,
)
from modules.investigations.components.report_composition import compose
from modules.investigations.components.report_renderers import render_docx, render_pdf
from modules.ui.components.unicode_fonts import width as text_width


def exhibit(data):
    return next(e for e in data["composition"]["exhibits"] if e["type"] == "closing")


def urls(model):
    return [item["url"] for group in model["resource_groups"] for item in group["items"]]


def test_existing_resources_and_approved_signoff_remain_with_three_additions():
    data = specimen()
    model = exhibit(data)
    expected = set(filter(None, approved.RESOURCES.splitlines())) | set(ADDITIONAL_URLS)
    assert set(urls(model)) == expected and len(urls(model)) == 11
    assert model["responsibility"] == approved.RESPONSIBILITY
    assert model["closing"] == data["draft"]["closing"]
    assert model["sender_lines"][:2] == [
        data["draft"]["sender_name"],
        data["draft"]["sender_title"],
    ]
    assert len(prepared_pages(model)) == 1
    resources = [
        e for e in data["composition"]["appendix"]["entries"] if e["kind"] == "closing_resource"
    ]
    assert len(resources) == 11
    assert all(e["owner"] == "closing" for e in resources)
    assert set(model["appendix_entry_ids"]) == {e["id"] for e in resources}


def test_final_closing_removes_only_redundant_heading_and_preserves_prior_layout():
    model = exhibit(specimen())
    final = layout_closing(model)
    assert not any(s.get("id") == "responsibility-heading" for p in final for s in p.segments)
    text = " ".join(e[3] for p in final for e in p.elements if e[0] == "text")
    assert approved.RESPONSIBILITY in text
    assert model["closing"] in text
    previous = deepcopy(model)
    previous["layout_revision"] = SECOND_REVIEW_REVISION
    assert any(
        s.get("id") == "responsibility-heading"
        for p in layout_closing(previous)
        for s in p.segments
    )


def test_references_move_after_signoff_without_changing_numbers_or_upstream_pages():
    data = specimen()
    reviewed = compose(data)
    data["draft"].pop("closing_revision")
    legacy = compose(data)
    assert reviewed["citations"] == legacy["citations"]
    assert reviewed["citation_integrity_issues"] == []
    for kind in ("summary", "vulnerability", "attribution", "information"):
        assert next(e for e in reviewed["exhibits"] if e["type"] == kind) == next(
            e for e in legacy["exhibits"] if e["type"] == kind
        )

    def before_closing(content):
        return content["sections"][
            : next(
                i for i, n in enumerate(content["sections"]) if n.get("section_key") == "closing"
            )
        ]

    assert before_closing(reviewed) == before_closing(legacy)
    nodes = reviewed["sections"]
    appendix_d = next(i for i, n in enumerate(nodes) if n.get("anchor") == "appendix-D")
    references = [(i, n) for i, n in enumerate(nodes) if n["kind"] == "reference"]
    assert all(i > appendix_d for i, n in references)
    assert [n["number"] for i, n in references] == [c["number"] for c in reviewed["citations"]]
    assert not any(e["type"] == "closing" for e in legacy["exhibits"])
    assert sum(n.get("text") == approved.RESPONSIBILITY for n in legacy["sections"]) == 1


def test_extended_links_are_lossless_and_pages_do_not_overflow():
    model = exhibit(specimen(True))
    pages = layout_closing(model)
    assert len(pages) > 1
    linked = [s["url"] for p in pages for s in p.segments if s["kind"] == "link"]
    assert set(linked) == set(urls(model))
    for page in pages:
        for s in page.segments:
            if s["kind"] == "closing_block" and s["id"] not in {
                "page-title",
                "page-subtitle",
                "appendix-note",
            }:
                assert s["top"] + s["height"] <= BOTTOM
        for e in page.elements:
            if e[0] == "text":
                _, x, y, value, size, bold, color = e
                assert color == "#000000" and size >= 10
                assert 0 <= y <= page.height
                assert (
                    x + text_width(value, "ExhibitSans-Bold" if bold else "ExhibitSans", size)
                    <= PAGE_WIDTH + 0.01
                )
    all_text = " ".join(e[3] for p in pages for e in p.elements if e[0] == "text")
    assert all_text.count(model["closing"]) == 1


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "file:///C:/secret",
        "https://name:pass@example.com/",
        "https://[broken",
        "https:\\example.com",
    ],
)
def test_unsafe_resources_never_become_active_links(url):
    assert not safe_resource_url(url)
    group = next(
        g for g in resource_groups({"resources": url}) if g["title"] == "Additional resources"
    )
    assert not group["items"][0]["active"]


def test_control_characters_are_rejected_in_a_link_target():
    assert not safe_resource_url("https://example.com/\nscript")
    assert not safe_resource_url("https://example.com/\x00script")


def test_native_word_pdf_and_svg_links_survive_frozen_export(tmp_path, monkeypatch):
    data = specimen()
    model = exhibit(data)
    restored = json.loads(json.dumps(model))
    monkeypatch.setattr(
        "modules.ui.components.exhibit_rendering.layout_closing",
        lambda *a: pytest.fail("Frozen Closing regenerated"),
    )
    monkeypatch.setattr(
        socket, "create_connection", lambda *a, **k: pytest.fail("Export performed a lookup")
    )
    uncaptured = deepcopy(restored)
    uncaptured.pop("rendered_masters")
    capture_exhibit_masters({"exhibits": [uncaptured]}, [restored])
    assert uncaptured == restored
    data["composition"]["sections"] = [
        n for n in data["composition"]["sections"] if n.get("exhibit_id") == model["id"]
    ]
    pdf, docx = tmp_path / "closing.pdf", tmp_path / "closing.docx"
    render_pdf(data, pdf, tmp_path, draft=True)
    render_docx(data, docx, tmp_path)
    pdf_bytes = pdf.read_bytes()
    assert pdf_bytes.startswith(b"%PDF")
    for url in urls(model):
        assert url.encode() in pdf_bytes
    with ZipFile(docx) as z:
        relationships = ET.fromstring(z.read("word/_rels/document.xml.rels"))
        targets = {
            r.attrib["Target"] for r in relationships if r.attrib["Type"].endswith("/hyperlink")
        }
        assert set(urls(model)) <= targets
        xml = z.read("word/document.xml").decode()
        assert approved.CLOSING in xml and "w:hyperlink" in xml
    svg = ET.fromstring(svg_pages(model)[0])
    assert {a.attrib["href"] for a in svg.findall("{http://www.w3.org/2000/svg}a")} == set(
        urls(model)
    )
    restored["closing"] += " Changed."
    with pytest.raises(ValueError, match="reviewed content"):
        prepared_pages(restored)


def test_full_report_resolves_relocated_reference_bookmarks(tmp_path):
    data = specimen()
    render_pdf(data, tmp_path / "full.pdf", tmp_path, draft=True)
    render_docx(data, tmp_path / "full.docx", tmp_path)
    with ZipFile(tmp_path / "full.docx") as z:
        root = ET.fromstring(z.read("word/document.xml"))
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    names = [n.attrib[ns + "name"] for n in root.iter(ns + "bookmarkStart")]
    for citation in data["composition"]["citations"]:
        assert names.count("ref" + str(citation["number"])) == 1


def test_closing_certification_pins_revision_and_requires_logged_reopening(
    client, app, monkeypatch
):
    lead = prepared(client, app, validate=False)
    response = save(client, lead, closing_revision=REVISION)
    assert response.status_code == 200, response.text
    lead = response.json()
    response = client.post(
        f"/api/cases/{lead['case_id']}/sections/closing/validate",
        json={"expected_revision": lead["draft_revision"]},
    )
    assert response.status_code == 200, response.text
    lead = response.json()
    review = status(lead, "closing")
    assert review["validated_by"] == "Test Analyst"
    assert review["fingerprint_version"] == 2
    assert review["snapshot"]["exhibits"]
    assert all("rendered_masters" not in model for model in review["snapshot"]["exhibits"])
    monkeypatch.setattr(
        "modules.ui.components.exhibit_rendering.layout_closing",
        lambda *a: pytest.fail("Certified Closing regenerated"),
    )
    current = client.get("/api/cases/" + lead["case_id"]).json()
    assert status(current, "closing")["snapshot"] == review["snapshot"]
    denied = save(client, current, closing_revision="legacy")
    assert denied.status_code == 422 and "Closing" in denied.text
    monkeypatch.undo()
    reopened = reopen_sections(client, current, "Review Closing resources", ["closing"])
    assert any(e["reason"] == "Review Closing resources" for e in reopened["section_history"])
