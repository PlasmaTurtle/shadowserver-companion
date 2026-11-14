"""New notification headers adopt current copy without rewriting saved pages."""

from dataclasses import asdict
from copy import deepcopy
import hashlib
import json
import subprocess
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from tools.preview_introduction import specimen
from workbench.introduction_layout import BLACK, layout_introduction
from workbench.introduction_model import PREVIOUS_REVISION, PREVIOUS_SUBJECT, REVISION, SUBJECT
from workbench.report_composition import compose
from workbench.report_layouts import adopt_current_layouts
from workbench.report_renderers import render_docx, render_pdf


def _fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def test_historical_introduction_retains_pre_review_model_and_layout():
    data = specimen(8, 3, 3)
    data["draft"].update(introduction_revision=PREVIOUS_REVISION, subject=PREVIOUS_SUBJECT)
    model = compose(data)["sections"][0]["model"]
    # Captured directly from the 0.9.96 production composition/layout code.
    assert _fingerprint(model) == "436130b8a2368fd5cc298d7745bfe5e56232ecd5986ec894be862156e306621b"
    assert _fingerprint(asdict(layout_introduction(model))) == (
        "61996e52bce8babf99948f0c51a4ab4fc0834c65f2f8fb15af56ab0c598f42a3"
    )
    assert "report_date" not in model
    adopt_current_layouts(data["draft"])
    updated = compose(data)["sections"][0]["model"]
    assert updated["revision"] == REVISION and updated["subject"] == SUBJECT
    assert updated["report_date"] == "2026-11-07"


def test_notification_date_and_corrected_subject_survive_both_exports(tmp_path):
    data = specimen(1)
    data["draft"]["report_date"] = "2025-02-03"
    data["composition"] = compose(data)
    data["composition"]["sections"] = [data["composition"]["sections"][0]]
    render_pdf(data, tmp_path / "notification.pdf", tmp_path)
    render_docx(data, tmp_path / "notification.docx", tmp_path)
    pdf_text = subprocess.check_output(
        ["pdftotext", "-layout", str(tmp_path / "notification.pdf"), "-"]
    ).decode()
    with ZipFile(tmp_path / "notification.docx") as package:
        doc = ET.fromstring(package.read("word/document.xml"))
    word_text = " ".join(node.text or "" for node in doc.iter() if node.tag.endswith("}t"))
    for output in (pdf_text, word_text):
        collapsed = " ".join(output.split())
        assert "Date:" in collapsed and "February 3, 2025" in collapsed
        assert SUBJECT in collapsed
        assert "Cyber Security" not in collapsed and "Shadow Server" not in collapsed
    assert len([page for page in pdf_text.split("\f") if page.strip()]) == 1


def test_missing_severity_has_no_red_warning_emphasis_in_current_header():
    model = specimen(1)["composition"]["sections"][0]["model"]
    model["severity"] = "Not supplied"
    severity = next(
        element
        for element in layout_introduction(model).summary.elements
        if element[0] == "text" and element[3].startswith("Reported severity:")
    )
    assert severity[-1] == BLACK


def test_cover_prioritizes_current_findings_over_older_attribution_support():
    data = specimen(2, 2)
    entries = data["qualified_lead"]["validated_leads"][0]["entries"]
    entries[0]["normalized"] = {"case_condition_scope": True, "active_conditions": []}
    entries[0]["source"]["fields"]["timestamp"] = "2025-01-01T12:00:00Z"
    entries[1]["source"]["fields"]["timestamp"] = "2026-11-12T12:00:00Z"
    original = deepcopy(data)
    content = compose(data)
    model = content["sections"][0]["model"]
    assert model["asset_line"] == "192.0.2.15 | service02.harborhealth.example"
    assert model["observed"] == "Nov 12, 2026 · 07:00 AM EST"
    assert [item["value"] for item in model["counts"]] == [1, 1, 1, 1]
    assert [group["label"] for group in model["groups"]] == ["Example Mail Server 3.2"]
    assert [finding["id"] for finding in model["findings"]] == ["CVE-2099-10002"]
    assert "Earlier observations" in model["scope_note"]
    retained = [entry for entry in content["appendix"]["entries"] if entry["kind"] == "observation"]
    assert len(retained) == 2
    assert data == original


def test_cover_with_only_support_does_not_reintroduce_assets_as_current_findings():
    data = specimen(1)
    data["qualified_lead"]["validated_leads"][0]["entries"][0]["normalized"] = {
        "case_condition_scope": True,
        "active_conditions": [],
    }
    model = compose(data)["sections"][0]["model"]
    assert model["asset_line"] == "No reported asset supplied"
    assert model["observed"] == "Not supplied"
    assert [item["value"] for item in model["counts"]] == [0, 0, 0, 0]
    assert model["groups"] == []
