"""Recipient navigation, retained source values, continuation and freeze behavior."""

from copy import deepcopy
from collections import defaultdict
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

from test_section_validation_050 import prepared, save, status
from test_workbench import app, client, reopen_sections
from tools.preview_appendix import specimen
from workbench.appendix_layout import layout_appendix, PAGE_WIDTH, BOTTOM
from workbench.appendix_view import REVISION, build_appendix_views
from workbench.closing_page_model import FIRST_REVIEW_REVISION, REVISION as CLOSING_REVISION
from workbench.closing_page_layout import layout_closing
from workbench.exhibit_rendering import capture_exhibit_masters, prepared_pages
from workbench.report_composition import compose
from workbench.report_renderers import render_pdf, render_docx
from workbench.unicode_fonts import width as text_width


def appendix_views(data):
    return [e for e in data["composition"]["exhibits"] if e["type"] == "appendix"]


def test_source_records_remain_identical_and_every_field_has_a_readable_location():
    data = specimen(capture=False)
    content = data["composition"]
    original = deepcopy(content["appendix"])
    views, nodes, nav = build_appendix_views(original)
    assert original == content["appendix"]
    records = {r["id"]: r for v in views for r in v.get("records", [])}
    assert set(records) == {e["id"] for e in original["entries"]}
    for entry in original["entries"]:
        fields = [f for g in records[entry["id"]]["groups"] for f in g["fields"]]
        assert {f["path"]: {k: v for k, v in f.items() if k != "label"} for f in fields} == {
            f["path"]: f for f in entry["fields"]
        }
        assert entry["id"] in nav["anchors"]
        assert records[entry["id"]]["label"] == nav["labels"][entry["id"]]
    assert {d["section"] for d in views[0]["directory"]} == {"A", "B", "C", "D1", "D2", "D3"}
    assert all(n.get("section_owner") for n in nodes)
    assert all("-" in label for label in nav["labels"].values())


def test_appendix_is_opt_in_and_does_not_change_the_front_report_or_raw_data():
    data = specimen(capture=False)
    reviewed = compose(data)
    data["draft"].pop("appendix_revision")
    legacy = compose(data)
    assert reviewed["appendix"] == legacy["appendix"]
    assert reviewed["citations"] == legacy["citations"]
    assert reviewed["citation_integrity_issues"] == []
    main = [e for e in reviewed["exhibits"] if e["type"] != "appendix"]
    assert main == legacy["exhibits"]

    def front(c):
        i = next(i for i, n in enumerate(c["sections"]) if n.get("exhibit_id") == "EX-CLOSING")
        return c["sections"][: i + 1]

    assert front(reviewed) == front(legacy)
    assert not any(e["type"] == "appendix" for e in legacy["exhibits"])
    assert not any(n["kind"] == "reference" for n in reviewed["sections"])


def test_recipient_resource_page_has_no_internal_heading_and_r1_still_exists():
    data = specimen(capture=False)
    model = next(e for e in data["composition"]["exhibits"] if e["type"] == "closing")
    text = "\n".join(p.alt_text for p in layout_closing(model))
    assert text.startswith("Recommended Resources")
    assert "Resources and sign-off" not in text and "Closing" not in text
    assert "Supporting records follow" in text
    data["draft"]["closing_revision"] = FIRST_REVIEW_REVISION
    legacy = next(e for e in compose(data)["exhibits"] if e["type"] == "closing")
    assert "Resources and sign-off" in "\n".join(p.alt_text for p in layout_closing(legacy))


@pytest.mark.parametrize("extended", [False, True])
def test_every_field_continues_losslessly_with_repeated_context(extended):
    data = specimen(extended, capture=False)
    for model in appendix_views(data):
        pages = layout_appendix(model)
        ranges = defaultdict(list)
        for page in pages:
            assert (
                "Appendix " + model.get("display_section", model["section"]) in page.alt_text
                if model["section"]
                else "Appendices" in page.alt_text
            )
            assert f"Page {page.page} of {len(pages)}" in page.alt_text
            for element in page.elements:
                if element[0] == "text":
                    _, x, y, value, size, bold, color = element
                    assert color == "#000000" and size >= 10
                    assert 0 <= y <= page.height
                    assert (
                        x + text_width(value, "ExhibitSans-Bold" if bold else "ExhibitSans", size)
                        <= PAGE_WIDTH + 0.02
                    )
            for segment in page.segments:
                if segment["kind"] == "appendix_table":
                    assert segment["top"] + segment["height"] <= BOTTOM
                    for row in segment["rows"]:
                        ranges[(segment["record_id"], row["field_path"])].append(
                            (row["first_line"], len(row["values"]), row["total_lines"])
                        )
                if segment.get("field_path"):
                    assert segment["top"] + segment["height"] <= BOTTOM
                    ranges[(segment["record_id"], segment["field_path"])].append(
                        (segment["first_line"], len(segment["lines"]), segment["total_lines"])
                    )
            if page.page > 1 and model.get("records"):
                assert any(s.get("role") == "record" for s in page.segments)
        expected = {
            (r["id"], f["path"])
            for r in model.get("records", [])
            for g in r["groups"]
            for f in g["fields"]
        }
        assert set(ranges) == expected
        for spans in ranges.values():
            offset = 0
            for first, count, total in spans:
                assert first == offset
                offset += count
            assert offset == total


def test_navigation_and_freeze_are_shared_by_full_pdf_and_native_word(tmp_path, monkeypatch):
    data = specimen()
    models = appendix_views(data)
    frozen = deepcopy(models)
    monkeypatch.setattr(
        "workbench.exhibit_rendering.layout_appendix",
        lambda *a: pytest.fail("Saved appendix repaginated"),
    )
    restored = deepcopy(models)
    for model in restored:
        model.pop("rendered_masters")
    capture_exhibit_masters({"exhibits": restored}, frozen)
    assert restored == frozen
    render_pdf(data, tmp_path / "full.pdf", tmp_path, draft=True)
    render_docx(data, tmp_path / "full.docx", tmp_path)
    with ZipFile(tmp_path / "full.docx") as z:
        root = ET.fromstring(z.read("word/document.xml"))
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    names = [n.attrib[ns + "name"] for n in root.iter(ns + "bookmarkStart")]
    targets = [
        n.attrib[ns + "anchor"] for n in root.iter(ns + "hyperlink") if ns + "anchor" in n.attrib
    ]
    expected = data["composition"]["appendix_navigation"]["anchors"]
    assert all(names.count(anchor) == 1 for anchor in expected)
    assert set(targets) <= set(names)
    for citation in data["composition"]["citations"]:
        assert "ref" + str(citation["number"]) in names
    frozen[1]["records"][0]["groups"][0]["fields"][0]["value"] = "altered"
    with pytest.raises(ValueError, match="reviewed content"):
        prepared_pages(frozen[1])


def test_appendix_uses_existing_section_certification_and_logged_reopen(client, app, monkeypatch):
    lead = prepared(client, app, validate=False)
    response = save(client, lead, appendix_revision=REVISION, closing_revision=CLOSING_REVISION)
    assert response.status_code == 200, response.text
    lead = response.json()
    response = client.post(
        f"/api/cases/{lead['case_id']}/sections/closing/validate",
        json={"expected_revision": lead["draft_revision"]},
    )
    assert response.status_code == 200, response.text
    lead = response.json()
    review = status(lead, "closing")
    assert review["validated_by"] == "Test Analyst" and review["validated_at"].endswith("Z")
    assert review["fingerprint_version"] == 2
    assert not any(e["type"] == "appendix" for e in review["snapshot"]["exhibits"])
    assert any(e["kind"] == "closing_resource" for e in review["snapshot"]["appendix"])
    original = __import__(
        "workbench.exhibit_rendering", fromlist=["layout_appendix"]
    ).layout_appendix

    def guarded(model):
        assert model["owner"] != "closing", "Certified resource appendix regenerated"
        return original(model)

    monkeypatch.setattr("workbench.exhibit_rendering.layout_appendix", guarded)
    current = client.get("/api/cases/" + lead["case_id"]).json()
    assert status(current, "closing")["snapshot"] == review["snapshot"]
    changed = save(client, current, appendix_revision="legacy")
    assert changed.status_code == 200, changed.text
    current = changed.json()
    assert status(current, "closing")["validation_id"] == review["validation_id"]
    monkeypatch.undo()
    reopened = reopen_sections(client, current, "Review appendix organization", ["closing"])
    assert any(e["reason"] == "Review appendix organization" for e in reopened["section_history"])


def test_large_relationship_lists_paginate_instead_of_overflowing_the_record_heading():
    model = appendix_views(specimen(capture=False))[1]
    record = model["records"][0]
    record["related"] = [f"Reported observation A-{i:03d}" for i in range(1, 337)]
    record["source_ids"] = [f"retained-source-{i:03d}" for i in range(1, 41)]
    pages = layout_appendix(model)
    metadata = defaultdict(list)
    for page in pages:
        for block in page.segments:
            if block.get("metadata_key"):
                assert block["top"] + block["height"] <= BOTTOM
                metadata[block["metadata_key"]].extend(block["lines"])
    assert "Reported observation A-336" in " ".join(metadata["related"])
    assert "retained-source-040" in " ".join(metadata["source_ids"])
    assert len(pages) > 1
