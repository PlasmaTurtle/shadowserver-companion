"""Recipient clarity, evidence-preserving compaction and closure state."""

from copy import deepcopy
import subprocess

from tools.preview_introduction import specimen
from workbench.report_composition import compose
from workbench.introduction_model import REVISION as INTRODUCTION_REVISION, NOTIFICATION_REVISION
from workbench.vulnerability_model import (
    CURRENT_REVISION,
    EDITORIAL_REVISION,
    build_vulnerability_exhibit,
)
from workbench.vulnerability_layout import layout_vulnerabilities
from workbench.appendix import Appendix
from workbench.appendix_view import build_appendix_views
from workbench.appendix_compact import REVISION as APPENDIX_REVISION, PREVIOUS_REVISION
from workbench.appendix_layout import layout_appendix
from workbench.closing_renderers import render_closing, sections


def test_cover_keeps_source_product_with_bare_version_and_preserves_pinned_layout():
    data = specimen(1)
    row = data["qualified_lead"]["validated_leads"][0]["entries"][0]
    row["normalized"] = {}
    row["source"]["fields"].update(product="PHP", version="5.6.29")
    original = deepcopy(row)
    data["draft"]["introduction_revision"] = INTRODUCTION_REVISION
    model = compose(data)["sections"][0]["model"]
    assert model["groups"][0]["label"] == "PHP 5.6.29"
    data["draft"]["introduction_revision"] = NOTIFICATION_REVISION
    assert compose(data)["sections"][0]["model"]["groups"][0]["label"] == "5.6.29"
    assert row == original


def test_cover_action_and_contact_use_only_the_pinned_sender_profile():
    data = specimen(1)
    data["draft"].update(
        introduction_revision=INTRODUCTION_REVISION,
        sender_profile={
            "email": "frozen@example.test",
            "outreach_verification_route": "Call the published office number to verify this notification.",
        },
    )
    data["profile"]["email"] = "later-settings@example.test"
    model = compose(data)["sections"][0]["model"]
    assert model["recipient_reply"] == "frozen@example.test"
    from workbench.introduction_layout import layout_introduction

    text = " ".join(line for block in layout_introduction(model).blocks for line in block.lines)
    assert "First action:" in text and "Reply to: frozen@example.test" in text
    assert "later-settings" not in text
    data["draft"]["introduction_revision"] = NOTIFICATION_REVISION
    assert "recipient_action" not in compose(data)["sections"][0]["model"]


def test_long_verification_route_moves_intact_to_resources_with_cover_pointer():
    from workbench.closing_page_model import build_closing_exhibit
    from workbench.closing_page_layout import closing_blocks

    data = specimen(1)
    route = "Use the independently published office contact. " * 8
    data["draft"].update(
        introduction_revision=INTRODUCTION_REVISION,
        sender_profile={"outreach_verification_route": route},
    )
    model = compose(data)["sections"][0]["model"]
    assert "See Recommended Resources" in model["recipient_verification"]
    closing = build_closing_exhibit(data, {"entries": []})
    assert closing["recipient_verification"] == route.strip()
    assert route.strip() in " ".join(block["text"] for block in closing_blocks(closing))


def test_long_identity_keeps_cover_action_contact_and_product_without_smaller_type():
    from workbench.introduction_layout import layout_introduction

    data = specimen(2, 1, 1)
    model = data["composition"]["sections"][0]["model"]
    model["to"] = (
        "Principal Executive / IT Director\nSynthetic Coastal Manufacturing and International Logistics Research Organization\n100 Long Example Boulevard, Research and Engineering Campus\nCharlotte, North Carolina 28202"
    )
    model["sender"] = (
        "Alexandria Montgomery-Worthington — SIMULATION\nSupervisory Special Agent for Cybercrime and Technical Operations\nSynthetic Evaluation Office\nCharlotte Test Office"
    )
    model["recipient_reply"] = "analyst@example.test"
    model["recipient_verification"] = (
        "SYNTHETIC ONLY: independently confirm the office number and ask for the analyst."
    )
    plan = layout_introduction(model)
    text = (
        " ".join(line for block in plan.blocks for line in block.lines)
        + " "
        + " ".join(element[3] for element in plan.summary.elements if element[0] == "text")
    )
    assert "International Logistics Research Organization" in text
    assert "Supervisory Special Agent for Cybercrime and Technical Operations" in text
    assert model["recipient_verification"] in text and model["recipient_reply"] in text
    assert model["groups"][0]["label"] in text
    assert min(block.size for block in plan.blocks) >= 10
    assert sum(block.height for block in plan.blocks) + plan.summary.height == plan.height


def test_eol_display_and_actual_reference_destination_preserve_raw_tag():
    from test_finding_explanation_layout import item

    data = {
        "draft": {
            "vulnerability_revision": CURRENT_REVISION,
            "narrative": "Reported lifecycle condition.",
        }
    }
    source = {"id": "EX-VULNERABILITY", "items": [item()]}
    saved = deepcopy(source)
    model = build_vulnerability_exhibit(data, source, [], [])
    text = " ".join(page.alt_text for page in layout_vulnerabilities(model))
    assert "PHP outside normal support" in text
    assert "References: Appendix D." in text
    assert "Appendix C" not in text
    assert model["items"][0]["label"] == "eol-php" and source == saved
    model["include_appendix"] = False
    text = " ".join(page.alt_text for page in layout_vulnerabilities(model))
    assert "Appendix" not in text and "See References" in text
    data["draft"]["vulnerability_revision"] = EDITORIAL_REVISION
    old = build_vulnerability_exhibit(data, source, [], [])
    assert "references_appendix" not in old and "display_title" not in old["items"][0]


def test_two_eol_findings_use_space_after_narrative_and_keep_both_explanations():
    from test_finding_explanation_layout import item

    php, iis = item(), item()
    php["technical_explanation"]["body"] += " UniquePHPEvidence."
    iis.update(label="eol-iis", detail="7.5")
    iis["technical_explanation"].update(
        title="IIS and Windows support status",
        body="UniqueIISEvidence. " + iis["technical_explanation"]["body"],
    )
    draft = {
        "vulnerability_revision": CURRENT_REVISION,
        "narrative": " ".join(f"NarrativeWord{i:03}" for i in range(65)),
    }
    model = build_vulnerability_exhibit(
        {"draft": draft}, {"id": "EX-VULNERABILITY", "items": [php, iis]}, [], []
    )
    pages = layout_vulnerabilities(model)
    assert len(pages) == 2
    assert any(segment["kind"] == "finding" for segment in pages[0].segments)
    text = " ".join(page.alt_text for page in pages)
    assert text.count("UniquePHPEvidence") == 1 and text.count("UniqueIISEvidence") == 1
    assert all(text.count(f"NarrativeWord{i:03}") == 1 for i in range(65))


def test_identical_publication_prints_once_with_every_citation_anchor_and_raw_record():
    appendix = Appendix()
    for number in (1, 2, 3):
        appendix.add(
            "D",
            "reference",
            f"[{number}] Example publication",
            {
                "number": number,
                "title": "Example publication",
                "publisher": "Example",
                "url": "https://example.test/reference",
                "retrieved_at": "2026-11-13T00:00:00Z",
            },
            identity={"number": number},
        )
    source = appendix.model()
    original = deepcopy(source)
    views, _, navigation = build_appendix_views(source, APPENDIX_REVISION)
    assert len(views[0]["records"]) == 1
    assert views[0]["records"][0]["title"] == "[1] [2] [3] Example publication"
    assert (
        views[0]["records"][0]["section_heading"]["title"]
        == "Appendix D · References and resources"
    )
    assert set(views[0]["records"][0]["entry_ids"]) == {entry["id"] for entry in source["entries"]}
    pages = layout_appendix(views[0])
    anchors = {s["name"] for p in pages for s in p.segments if s["kind"] == "anchor"}
    assert {"ref1", "ref2", "ref3"} <= anchors
    assert {"ref1", "ref2", "ref3"} <= set(navigation["anchors"])
    assert source == original
    old, _, _ = build_appendix_views(source, PREVIOUS_REVISION)
    assert len(old[0]["records"]) == 3


def test_six_cve_example_has_no_lone_resource_page_and_retains_all_record_anchors():
    from tools.generate_examples import synthetic_example

    data = synthetic_example(multiple=True)
    model = next(e for e in data["composition"]["exhibits"] if e["type"] == "appendix")
    pages = layout_appendix(model)
    assert len(pages) == 5
    assert sum(s.get("role") == "record" for s in pages[-1].segments) > 1
    anchors = {s["name"] for p in pages for s in p.segments if s["kind"] == "anchor"}
    assert {record["id"] for record in model["records"]} <= anchors
    assert (
        min(
            s["size"]
            for p in pages
            for s in p.segments
            if s["kind"] == "appendix_text" and s.get("field_path")
        )
        == 10.5
    )


def closing_fixture():
    report = {
        "id": "report-1",
        "revision": 1,
        "created_at": "2026-11-13T12:00:00Z",
        "certified_at": "2026-11-13T12:00:00Z",
        "certified_by": "Example Analyst",
        "certification_source": "analyst",
    }
    return {
        "business": "Synthetic Company",
        "title": "Synthetic notification",
        "case_id": "case-1",
        "opened_at": "2026-11-13T12:00:00Z",
        "created_at": "2026-11-13T13:00:00Z",
        "delivered_at": "2026-11-13T12:30:00Z",
        "closed_by": "Example Analyst",
        "disposition": "notified",
        "conclusion": "Delivery confirmed. Remediation was not independently verified.",
        "reports": [report],
        "attempts": [
            {
                "report_id": report["id"],
                "occurred_at": "2026-11-13T12:30:00Z",
                "channel": "email",
                "outcome": "recipient_update",
                "recipient": "Example Recipient",
                "destination": "example@example.test",
                "information_source": "recipient_reported",
                "notes": "Recipient reports patching.",
                "recorded_by": "Example Analyst",
            }
        ],
    }


def test_closing_preview_never_claims_finalized_closure_and_long_notes_remain_complete(tmp_path):
    data = closing_fixture()
    data["preview"] = True
    text = "\n".join(t for t, _ in sections(data))
    assert "Proposed administrative closure" in text and "case remains open" in text
    assert "Closed:" not in text and "Closing report finalized by:" not in text
    assert "recipient reported" in text and "not independently verified" in text
    data.pop("preview")
    assert "Closed:" in "\n".join(t for t, _ in sections(data))
    data["attempts"][0]["notes"] = " ".join(f"ChronologyWord{i:04}" for i in range(700))
    render_closing(data, tmp_path)
    text = subprocess.check_output(
        ["pdftotext", str(tmp_path / "closing-report.pdf"), "-"], text=True
    )
    assert all(text.count(f"ChronologyWord{i:04}") == 1 for i in range(700))
    assert text.count("Recorded by: Example Analyst") == 1
