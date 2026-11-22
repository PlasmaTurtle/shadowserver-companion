"""Approved copy, source lineage, export parity and section-freeze checks."""

from copy import deepcopy
import json
import socket
from zipfile import ZipFile

import pytest

from modules.investigations.tests.support.section_reviews import prepared, save, status
from tests.support.workbench import app, client, reopen_sections
from modules.investigations.tools.preview_information import specimen as current_specimen
from modules.investigations.components import approved_template as approved
from modules.investigations.components.appendix import flatten_fields
from modules.ui.components.exhibit_rendering import (
    capture_exhibit_masters,
    prepared_pages,
    svg_pages,
)
from modules.investigations.components.information_layout import (
    layout_information,
    rows_for,
    BOTTOM,
    PAGE_WIDTH,
)
from modules.investigations.components.information_model import (
    PREVIOUS_REVISION as REVISION,
    FIRST_REVIEW_REVISION,
    IC3_SOURCE,
    REVISED_IC3_SOURCE,
    reference_sources,
)
from modules.investigations.components.report_composition import compose
from modules.investigations.components.report_renderers import render_docx, render_pdf
from modules.ui.components.unicode_fonts import width as text_width


def specimen(extended=False, revision=REVISION):
    """These regressions intentionally protect the previously shipped layout."""
    return current_specimen(extended, revision)


def exhibit(data):
    return next(e for e in data["composition"]["exhibits"] if e["type"] == "information")


def test_approved_copy_is_preserved_once_with_supported_statistics():
    data = specimen(revision=FIRST_REVIEW_REVISION)
    model = exhibit(data)
    content = [b.get("body", "") for b in model["blocks"]]
    content += [text for b in model["blocks"] for text in b.get("items", [])]
    expected = [
        approved.SECURITY_INTRO,
        *approved.NEXT_STEPS.splitlines(),
        approved.FRAUD_INTRO,
        *approved.FRAUD_RISKS,
        approved.FRAUD_STATS_INTRO,
        *approved.FRAUD_STATS,
        approved.PARTNERSHIP,
    ]
    for text in expected:
        assert content.count(text) == 1
    assert data["composition"]["citation_integrity_issues"] == []
    assert len(prepared_pages(model)) == 2
    stats = next(b for b in model["blocks"] if b["kind"] == "statistics")
    source = next(
        r for r in data["composition"]["citations"] if r["number"] == stats["citations"][0]
    )
    assert source["url"] == IC3_SOURCE["public_url"]
    assert source["retrieved_at"] == IC3_SOURCE["retrieved_at"]
    record = IC3_SOURCE["record"]["business_email_compromise"]
    assert round(record["reported_losses_usd"] / record["complaints"], -3) == 123000
    entry = next(
        e
        for e in data["composition"]["appendix"]["entries"]
        if "EX-INFORMATION" in e["referenced_by"]
    )
    assert entry["fields"] == list(flatten_fields(IC3_SOURCE))
    assert entry["id"] in model["appendix_entry_ids"]


def test_revised_second_page_keeps_first_page_and_supports_each_claim():
    data = specimen()
    model = exhibit(data)
    first_review = exhibit(specimen(revision=FIRST_REVIEW_REVISION))
    assert prepared_pages(model)[0].standalone_svg == prepared_pages(first_review)[0].standalone_svg
    assert len(prepared_pages(model)) == 2
    assert model["editorial_copy_revision"] == REVISION
    assert model["approved_copy_scope"] == "Security introduction and four protective actions only."
    stats = next(b for b in model["blocks"] if b["kind"] == "statistics_table")
    assert stats["items"] == [
        ["Business email compromise", "24,768", "$3,046,598,558"],
        ["Ransomware", "3,611", "$32,320,105"],
    ]
    bodies = " ".join(b.get("body", "") for b in model["blocks"])
    assert "impersonate a trusted sender" in bodies
    assert "without encryption" in bodies
    assert "not the full cost" in bodies
    assert "average" not in bodies and "$123,000" not in bodies
    assert "average_note" not in REVISED_IC3_SOURCE["record"]["business_email_compromise"]
    assert "confirmation of compromise" in bodies
    assert data["composition"]["citation_integrity_issues"] == []
    page_citations = set(
        next(
            s["values"]
            for s in prepared_pages(model)[1].page.segments
            if s["kind"] == "page_citations"
        )
    )
    for source in reference_sources():
        citation = next(
            c for c in data["composition"]["citations"] if c["url"] == source["public_url"]
        )
        assert citation["retrieved_at"] == source["retrieved_at"]
        assert citation["number"] in page_citations
        entry = next(
            e
            for e in data["composition"]["appendix"]["entries"]
            if e["fields"] == list(flatten_fields(source))
        )
        assert entry["id"] in model["appendix_entry_ids"]


def test_layout_retains_every_body_row_and_never_overflows():
    data = specimen(True)
    model = exhibit(data)
    pages = layout_information(model)
    assert len(pages) > 2
    for block in model["blocks"]:
        segments = [s for p in pages for s in p.segments if s.get("id") == block["id"]]
        assert segments
        rows = rows_for(block)
        expected_row = 0
        for s in segments:
            assert s["first_row"] == expected_row
            expected_row += s["row_count"]
            assert s["top"] + s["height"] <= BOTTOM
        assert expected_row == len(rows)
        if block["kind"] == "explainer":
            for segment in segments[1:]:
                first = segment["first_row"]
                assert rows[first].paragraph != rows[first - 1].paragraph
    for page in pages:
        for e in page.elements:
            if e[0] == "text":
                _, x, y, text, size, bold, color = e
                assert color == "#000000"
                assert size >= 10
                assert 0 <= x and y <= page.height
                assert (
                    x + text_width(text, "ExhibitSans-Bold" if bold else "ExhibitSans", size)
                    <= PAGE_WIDTH + 0.01
                )
    all_text = " ".join(e[3] for p in pages for e in p.elements if e[0] == "text")
    assert all_text.count(approved.SECURITY_INTRO[:50]) == 1
    assert "Example Additional Advisory - continued" in all_text
    assert all(f"Example paragraph {i}." in all_text for i in range(1, 11))


def test_custom_explainers_honor_override_and_exclude_system_duplicates():
    data = specimen(True)
    data["draft"]["explainer_overrides"] = {
        "synthetic-review-guidance": {"title": "Reviewed title", "body": "Reviewed body."}
    }
    data["explainers"].append(
        {
            "id": "financial_crime",
            "title": "Duplicated system explanation",
            "body": "Do not repeat.",
            "sources": "",
        }
    )
    model = exhibit({"composition": compose(data)})
    extra = next(b for b in model["blocks"] if b["kind"] == "explainer")
    assert extra["title"] == "Reviewed title" and extra["body"] == "Reviewed body."
    assert extra["citations"]
    assert not any(b.get("body") == "Do not repeat." for b in model["blocks"])


def test_revision_is_opt_in_and_other_sections_are_unchanged():
    data = specimen()
    original = deepcopy(data)
    reviewed = compose(data)
    assert data == original
    data["draft"].pop("information_revision")
    legacy = compose(data)
    for kind in ("summary", "vulnerability", "attribution"):
        assert next(e for e in reviewed["exhibits"] if e["type"] == kind) == next(
            e for e in legacy["exhibits"] if e["type"] == kind
        )
    assert not any(e["type"] == "information" for e in legacy["exhibits"])

    def before(content):
        return content["sections"][
            : next(
                i
                for i, n in enumerate(content["sections"])
                if n.get("section_key") == "information"
            )
        ]

    assert before(reviewed) == before(legacy)
    # The closing gains the required source-register entry; its approved prose stays the same.
    for content in (reviewed, legacy):
        assert sum(n.get("text") == approved.RESPONSIBILITY for n in content["sections"]) == 1


@pytest.mark.parametrize("revision", [FIRST_REVIEW_REVISION, REVISION])
def test_frozen_master_is_shared_by_word_pdf_svg_and_detects_tampering(
    tmp_path, monkeypatch, revision
):
    data = specimen(revision=revision)
    model = exhibit(data)
    restored = json.loads(json.dumps(model))
    assert svg_pages(restored) == svg_pages(model)
    monkeypatch.setattr(
        "modules.ui.components.exhibit_rendering.layout_information",
        lambda *a: pytest.fail("Frozen Information regenerated"),
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
    pdf, docx = tmp_path / "review.pdf", tmp_path / "review.docx"
    render_pdf(data, pdf, tmp_path, draft=True)
    render_docx(data, docx, tmp_path)
    assert pdf.read_bytes().startswith(b"%PDF")
    with ZipFile(docx) as z:
        for page in prepared_pages(restored):
            from modules.ui.components.svg_resources import without_webfonts

            assert without_webfonts(page.svg) in [
                z.read(n) for n in z.namelist() if n.endswith(".svg")
            ]
    restored["blocks"][0]["body"] += " Changed."
    with pytest.raises(ValueError, match="reviewed content"):
        prepared_pages(restored)


@pytest.mark.parametrize("revision", [FIRST_REVIEW_REVISION, REVISION])
def test_information_certification_pins_revision_and_reuses_master(
    client, app, monkeypatch, revision
):
    lead = prepared(client, app, validate=False)
    response = save(client, lead, information_revision=revision)
    assert response.status_code == 200, response.text
    lead = response.json()
    response = client.post(
        f"/api/cases/{lead['case_id']}/sections/information/validate",
        json={"expected_revision": lead["draft_revision"]},
    )
    assert response.status_code == 200, response.text
    lead = response.json()
    review = status(lead, "information")
    assert review["validated_by"] == "Test Analyst"
    assert review["fingerprint_version"] == 2
    assert review["snapshot"]["exhibits"]
    assert all("rendered_masters" not in model for model in review["snapshot"]["exhibits"])
    monkeypatch.setattr(
        "modules.ui.components.exhibit_rendering.layout_information",
        lambda *a: pytest.fail("Certified Information regenerated"),
    )
    current = client.get("/api/cases/" + lead["case_id"]).json()
    assert status(current, "information")["snapshot"] == review["snapshot"]
    denied = save(client, current, information_revision="legacy")
    assert denied.status_code == 422 and "Information" in denied.text
    monkeypatch.undo()
    reopened = reopen_sections(client, current, "Review Information formatting", ["information"])
    assert any(e["reason"] == "Review Information formatting" for e in reopened["section_history"])
