"""Priority follows frozen report products without rewriting source evidence."""

from copy import deepcopy
import json
import subprocess
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

from test_report_pipeline_071 import SourceWorkspace, captured_snapshot
from test_reports_040 import specimen
from workbench import compact_json, reporting
from workbench.closing_renderers import render_closing
from workbench.evidence_reader import write_evidence_reader
from workbench.print_policy import PRIORITY_MARKS, priority_mark
from workbench.report_package import PackageRenderers, assemble_package
from workbench.reviews.policy import fingerprints


def assessment(temperature="hot"):
    return {
        "schema_version": 1,
        "policy_version": 1,
        "policy_hash": "a" * 64,
        "scored_at": "2026-11-12T00:00:00Z",
        "quality": 80,
        "urgency": 70,
        "aggregate": 75,
        "temperature": temperature,
        "factors": {
            "quality": [
                {
                    "id": "finding",
                    "label": "Finding specificity",
                    "points": 30,
                    "weight": 40,
                    "reason": "Version is present; <script>sample()</script> stays text.",
                }
            ],
            "urgency": [],
        },
        "cves": [],
    }


def pdf_text(path):
    return subprocess.check_output(["pdftotext", str(path), "-"]).decode()


def footer_text(path):
    with ZipFile(path) as archive:
        return "".join(ET.fromstring(archive.read("word/footer1.xml")).itertext())


@pytest.mark.parametrize(
    "score", [None, {}, [], "hot", {"temperature": []}, {"temperature": "<hot>"}]
)
def test_absent_or_unrecognized_priority_has_no_marker(score):
    assert priority_mark(score) is None


def test_priority_labels_and_colors_are_fixed():
    for key, (label, color) in PRIORITY_MARKS.items():
        assert priority_mark({"temperature": key, "color": "url(evil)", "label": "unsafe"}) == {
            "temperature": key,
            "label": "Outreach priority: " + label,
            "color": color,
        }


@pytest.mark.parametrize("version", [1, 2])
def test_footer_temperature_is_a_frozen_dependency_only_when_scored(version):
    data = specimen()
    old = fingerprints(data, {}, sections=("closing",), version=version)["closing"]
    assert "outreach_temperature" not in old["snapshot"]
    data["intake_score"] = assessment()
    scored = fingerprints(data, {}, sections=("closing",), version=version)["closing"]
    assert scored["content_hash"] != old["content_hash"]
    assert scored["snapshot"]["outreach_temperature"] == "hot"
    data["intake_score"]["temperature"] = "blazing"
    changed = fingerprints(data, {}, sections=("closing",), version=version)["closing"]
    assert changed["content_hash"] != scored["content_hash"]
    data.pop("intake_score")
    assert fingerprints(data, {}, sections=("closing",), version=version)["closing"] == old


def test_packaged_priority_is_preserved_readable_and_separate_from_severity(tmp_path):
    data, _ = captured_snapshot(tmp_path / "sources")
    data["intake_score"] = assessment()
    before = deepcopy(data)
    destination = tmp_path / "package"
    destination.mkdir()
    built = assemble_package(
        SourceWorkspace(tmp_path / "sources"),
        data,
        destination,
        PackageRenderers(reporting.render_pdf, reporting.render_docx),
    )
    assert data == before
    assert built.snapshot["intake_score"] == before["intake_score"]
    assert (
        compact_json.loads((destination / "snapshot.json").read_text())["intake_score"]
        == before["intake_score"]
    )
    assert (
        json.loads((destination / "outreach-priority.json").read_text())["assessment"]
        == before["intake_score"]
    )
    assert "outreach-priority.json" in built.files
    for filename in ("notification.pdf", "work-log.pdf"):
        text = pdf_text(destination / filename)
        assert "Outreach priority:" not in text and "Blazing" not in text
        assert "Hot" not in text
        assert "Internal evidence record" not in text
        assert all(page.count("TLP:AMBER") == 2 for page in text.split("\f") if page.strip())
    assert "Outreach priority:" not in footer_text(destination / "notification.docx")
    assert "●" in footer_text(destination / "notification.docx")
    with ZipFile(destination / "notification.docx") as archive:
        assert b"9C461A" in archive.read("word/footer1.xml")
        recipient_text = " ".join(
            " ".join(ET.fromstring(archive.read(name)).itertext())
            for name in archive.namelist()
            if name.startswith("word/") and name.endswith(".xml")
        )
        assert "Internal evidence record" not in recipient_text
        assert "Outreach priority:" not in recipient_text
    reader = (destination / "Evidence_Record.html").read_text()
    assert "Shadowserver Eclipse / Internal evidence record</span>" in reader
    assert "Outreach priority: Hot" in reader
    assert "Priority assessment" in reader
    assert "Finding specificity" in reader
    assert "separate from CVSS severity" in reader
    assert "<script>sample()</script>" not in reader
    assert "&lt;script&gt;sample()&lt;/script&gt;" in reader
    data["intake_score"]["temperature"] = "cool"
    assert (
        json.loads((destination / "outreach-priority.json").read_text())["assessment"][
            "temperature"
        ]
        == "hot"
    )


def test_legacy_evidence_reader_stays_unscored(tmp_path):
    write_evidence_reader({"domain": "example.com"}, tmp_path)
    assert not (tmp_path / "outreach-priority.json").exists()
    reader = (tmp_path / "Evidence_Record.html").read_text()
    assert "Outreach priority:" not in reader
    assert "Shadowserver Eclipse / Internal evidence record</span>" in reader


def test_closing_report_retains_priority_marker(tmp_path):
    closing = {
        "case_id": "test-case",
        "business": "Synthetic Company",
        "title": "Synthetic closing",
        "delivered_at": None,
        "disposition": "unable_to_contact",
        "conclusion": "Synthetic test only.",
        "reports": [],
        "attempts": [],
        "opened_at": "2026-11-01T12:00:00Z",
        "created_at": "2026-11-12T12:00:00Z",
        "closed_by": "Synthetic Analyst",
        "intake_score": assessment("blazing"),
    }
    render_closing(closing, tmp_path)
    assert "Outreach priority:" not in pdf_text(tmp_path / "closing-report.pdf")
    assert "Blazing" not in pdf_text(tmp_path / "closing-report.pdf")
    assert "●" in footer_text(tmp_path / "closing-report.docx")
    assert "Blazing" not in footer_text(tmp_path / "closing-report.docx")
