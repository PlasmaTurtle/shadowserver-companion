"""Justification preserves source text, paragraph ends and historical policies."""

from copy import deepcopy
import json

import pytest

from tests.support.workbench import app, client, import_rows, reopen_sections
from modules.investigations.tools.preview_appendix import specimen
from modules.ui.components.exhibit_rendering import layout, is_page_exhibit
from modules.investigations.components.introduction_layout import layout_introduction
from modules.investigations.components.report_composition import compose
from modules.investigations.components.report_layouts import adopt_current_layouts
from modules.ui.components.text_justification import wrapped_paragraphs, word_space
from modules.ui.components.unicode_fonts import width
from modules.ui.components.vector_layout import _wrap
from modules.investigations.components.appendix_layout import AppendixLayout


@pytest.mark.parametrize(
    "value",
    [
        "A paragraph with enough words to wrap more than once. " * 4,
        "First paragraph with enough words to wrap onto two lines.\nA second paragraph.\n",
        "Multiple  internal   spaces remain in the recorded text.",
        "参考資料 日本語 example and retained source text. " * 5,
        "https://example.invalid/" + "x" * 500,
    ],
)
def test_paragraph_wrapping_preserves_exact_existing_lines_and_final_width(value):
    lines, endings = wrapped_paragraphs(value, 160, 10.5)
    assert lines == _wrap(value, 160, 10.5)
    assert len(endings) == len(lines) and endings[-1]
    for line, final in zip(lines, endings, strict=True):
        extra = word_space(line, 160, 10.5, final=final)
        if final or " " not in line.strip():
            assert extra == 0
        elif extra:
            assert width(line, "ExhibitSans", 10.5) + line.count(" ") * extra == pytest.approx(160)
    assert word_space("A heading that can wrap", 160, 10.5, bold=True) == 0


def test_all_prose_sections_justify_without_changing_text_or_pagination():
    data = specimen(capture=False)
    adopt_current_layouts(data["draft"])
    # Preserve the original reviewed copy while isolating the alignment policy.
    # The new report-family pages have their own production-layout checks.
    from modules.investigations.components.information_model import PREVIOUS_REVISION
    from modules.investigations.components.notification_narrative import (
        REVISION as PREVIOUS_NARRATIVE,
    )
    from modules.investigations.components.appendix_view import REVISION as PREVIOUS_APPENDIX

    data["draft"]["information_revision"] = PREVIOUS_REVISION
    data["draft"]["narrative_revision"] = PREVIOUS_NARRATIVE
    # This fixture verifies historical prose, including the old appendix guide.
    # Compact appendices intentionally omit that instructional page.
    data["draft"]["appendix_revision"] = PREVIOUS_APPENDIX
    data["document_policy"] = deepcopy(data["document_policy"])
    data["document_policy"].pop("paragraph_alignment", None)
    data["draft"]["document_policy"] = deepcopy(data["document_policy"])
    old = compose(data)
    data["document_policy"]["paragraph_alignment"] = "justify"
    data["draft"]["document_policy"] = deepcopy(data["document_policy"])
    current = compose(data)
    seen = set()
    for model in current["exhibits"]:
        if not is_page_exhibit(model):
            continue
        before = next(item for item in old["exhibits"] if item["id"] == model["id"])
        previous, pages = layout(before), layout(model)
        assert len(previous) == len(pages)
        for old_page, page in zip(previous, pages, strict=True):
            assert page.elements == old_page.elements
            assert page.alt_text == old_page.alt_text
            assert not any(s["kind"] == "justified_line" for s in old_page.segments)
            for line in (s for s in page.segments if s["kind"] == "justified_line"):
                seen.add(model["type"])
                matching = [
                    e
                    for e in page.elements
                    if e[0] == "text" and e[1] == line["left"] and e[2] == line["baseline"]
                ]
                assert len(matching) == 1
                _, _, _, value, size, bold, _ = matching[0]
                assert not bold
                rendered_width = (
                    width(value, "ExhibitSans", size) + value.count(" ") * line["word_space"]
                )
                assert rendered_width == pytest.approx(line["width"])
            if model["type"] in {"vulnerability", "attribution"}:
                footer = [e for e in page.elements if e[0] == "text" and e[2] >= 605]
                justified_y = {
                    s["baseline"] for s in page.segments if s["kind"] == "justified_line"
                }
                assert footer[-1][2] not in justified_y
                assert all(e[2] not in justified_y for e in footer if e[3].startswith("Sources:"))
                if model["type"] == "vulnerability":
                    first_caveat = next(
                        e for e in footer if e[3].startswith("Scores and exploitation")
                    )
                    assert first_caveat[2] in justified_y
    assert {"vulnerability", "attribution", "information", "closing", "appendix"} <= seen
    intro = next(n["model"] for n in current["sections"] if n["kind"] == "introduction")
    plan = layout_introduction(intro)
    body = [b for b in plan.blocks if b.justified]
    assert len(body) == 1 and body[0].word_spaces[-1] == 0
    assert any(extra > 0 for extra in body[0].word_spaces[:-1])
    assert all(not b.justified for b in plan.blocks if b.label or b.centered)


def test_existing_policy_requires_explicit_adoption_and_preserves_frozen_review(client, app):
    import_rows(client, app)
    lead_id = client.get("/api/leads").json()[0]["id"]
    lead = client.get("/api/leads/" + lead_id).json()
    assert lead["draft"]["document_policy"]["paragraph_alignment"] == "justify"
    old = deepcopy(lead["draft"])
    old["document_policy"].pop("paragraph_alignment")
    with app.state.store.transaction() as db:
        db.execute("UPDATE cases SET draft=? WHERE id=?", (json.dumps(old), lead["case_id"]))
    lead = client.get("/api/cases/" + lead["case_id"]).json()
    assert lead["presentation_update_available"]
    assert "paragraph_alignment" not in lead["draft"]["document_policy"]
    response = client.post(
        f"/api/cases/{lead['case_id']}/sections/closing/validate",
        json={"expected_revision": lead["draft_revision"]},
    )
    assert response.status_code == 200, response.text
    lead = response.json()
    frozen = app.state.store.all(
        "SELECT * FROM section_validations WHERE case_id=?", (lead["case_id"],)
    )
    path = f"/api/cases/{lead['case_id']}/presentation/adopt"
    response = client.post(
        path,
        json={"expected_revision": lead["draft_revision"], "reason": "Adopt justified paragraphs"},
    )
    assert response.status_code == 422 and "Closing" in response.text
    reopened = reopen_sections(client, lead, "Review justified paragraphs", ["closing"])
    response = client.post(
        path,
        json={
            "expected_revision": reopened["draft_revision"],
            "reason": "Adopt justified paragraphs",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["draft"]["document_policy"]["paragraph_alignment"] == "justify"
    saved = app.state.store.all(
        "SELECT * FROM section_validations WHERE case_id=?", (lead["case_id"],)
    )
    assert saved == frozen


@pytest.mark.parametrize(
    "prefix", ["{", "[{", '["', "<html>", "-----BEGIN", "HTTP/1.1", "GET /", "POST /"]
)
def test_appendix_literal_captures_keep_natural_spacing(prefix):
    plan = AppendixLayout({"id": "EX-LITERAL", "paragraph_alignment": "justify"})
    plan.current_record = {"id": "source-record"}
    value = prefix + " captured raw response text " * 20
    field = {
        "label": "Captured response",
        "path": "/response",
        "text": value,
        "value_type": "string",
    }
    plan.fields({"fields": [field]})
    assert not any(segment["kind"] == "justified_line" for segment in plan.segments)
    assert field["text"] == value


def test_compact_appendix_descriptions_justify_without_changing_records():
    value = "The retained description explains the source finding and its applicability. " * 4
    prose_paths = [
        "description",
        "application",
        "capture_method",
        "summary",
        "review/note",
        "explanation",
        "access_note",
        "record/scope",
        "hash_scope",
    ]
    fields = [
        {"label": "Description", "path": "/" + key, "value_type": "string", "text": value}
        for key in prose_paths
    ] + [
        {
            "label": "Public URL",
            "path": "/url",
            "value_type": "string",
            "text": "https://example.com/report",
        },
        {
            "label": "Captured JSON",
            "path": "/response",
            "value_type": "string",
            "text": '{"raw": "' + value * 2 + '"}',
        },
    ]
    old, current = (
        AppendixLayout({"id": "EX-COMPACT"}),
        AppendixLayout({"id": "EX-COMPACT", "paragraph_alignment": "justify"}),
    )
    for plan in (old, current):
        plan.current_record = {
            "id": "source-record",
            "title": "Source record",
            "label": "D-01",
            "kind_label": "Supporting record",
            "citations": [],
        }
        plan.compact_fields({"fields": fields})
    assert old.elements == current.elements
    assert [page.elements for page in old.pages] == [page.elements for page in current.pages]
    paragraphs = [s for s in current.segments if s["kind"] == "appendix_text"]
    # The test record can cross a page; inspect fragments from every page.
    paragraphs = [
        s for page in current.pages for s in page.segments if s["kind"] == "appendix_text"
    ] + paragraphs
    for path in prose_paths:
        fragments = [block for block in paragraphs if block.get("field_path") == "/" + path]
        assert fragments and all(block["justified"] for block in fragments)
        gaps = [gap for block in fragments for gap in block["word_spaces"]]
        assert all(gap > 0 for gap in gaps[:-1])
        assert gaps[-1] == 0
        assert (
            " ".join(line for block in fragments for line in block["lines"])
            == "Description: " + value
        )
    assert all(
        "justified" not in block
        for block in paragraphs
        if block.get("field_path") in {"/url", "/response"}
    )


def test_current_compact_record_prose_justifies_and_preserves_source_and_geometry():
    from modules.investigations.components.appendix import Appendix
    from modules.investigations.components.appendix_view import (
        COMPACT_REVISION,
        build_appendix_views,
    )
    from modules.investigations.components.appendix_layout import layout_appendix

    description = (
        "The captured supporting material identifies the reported asset and explains "
        "the relationship to this notification using the recorded source information. "
    ) * 4
    appendix = Appendix()
    appendix.add(
        "D",
        "supporting_material",
        "Recorded supporting material",
        {
            "description": description,
            "source_url": "https://example.com/source",
            "captured_at": "2026-11-10T12:00:00Z",
        },
    )
    source = appendix.model()
    original = deepcopy(source)
    models, _, _ = build_appendix_views(source, COMPACT_REVISION)
    assert len(models) == 1
    plain = models[0]
    justified = {**deepcopy(plain), "paragraph_alignment": "justify"}
    before, after = layout_appendix(plain), layout_appendix(justified)
    assert len(before) == len(after)
    assert [page.elements for page in before] == [page.elements for page in after]
    blocks = [
        block
        for page in after
        for block in page.segments
        if block.get("field_path") == "/description"
    ]
    assert blocks and all(block.get("justified") for block in blocks)
    spacing = [gap for block in blocks for gap in block["word_spaces"]]
    assert any(gap > 0 for gap in spacing[:-1]) and spacing[-1] == 0
    assert (
        " ".join(line for block in blocks for line in block["lines"])
        == "Description: " + description
    )
    assert source == original == appendix.model()
