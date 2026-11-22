"""Cross-provider claims remain tied to the selected immutable response offline."""

from copy import deepcopy
import hashlib
import json
import shutil
import socket
import subprocess
from pathlib import Path
from zipfile import ZipFile

import pytest

from modules.investigations.tests.support.report_artifacts import specimen
from tests.support.workbench import app, client, import_rows, observations, ready
from modules.investigations.components.report_composition import compose
from modules.investigations.components.report_snapshot import snapshot
from modules.investigations.components.reporting import render_pdf, render_docx
from modules.library.components.cve_intelligence import ransomware


def multiple_sources():
    data = specimen()
    record = data["draft"]["cve_records"][0]
    record["record_path"] = "captured-nvd.json"
    record["revision_id"] = "nvd-v1"
    record["sources"][0].update(revision_id="nvd-v1", record_path="captured-nvd.json")
    program = {
        "publisher": "CVE Program",
        "url": "https://cveawg.mitre.org/api/cve/" + record["id"],
        "public_url": "https://www.cve.org/CVERecord?id=" + record["id"],
        "retrieved_at": "2026-11-07T01:02:03Z",
        "revision_id": "program-v2",
        "sha256": "a" * 64,
        "record_path": "captured-program.json",
    }
    record["sources"].append(program)
    record["sources"][1].update(revision_id="epss-v3", sha256="b" * 64)
    record["sources"][2].update(revision_id="kev-v4", sha256="c" * 64)
    record["cvss_assessments"][1]["source_revision_id"] = "program-v2"
    record["ransomware"] = ransomware({"knownRansomwareCampaignUse": "Known"}, "kev-v4")
    record["ssvc_assessments"] = [
        {
            "id": "assessment-1",
            "publisher": "CISA",
            "label": "Active exploitation reported",
            "exploitation": "active",
            "assessed_at": "2026-11-05T12:00:00Z",
            "source_revision_id": "program-v2",
        }
    ]
    record["selected_ssvc_assessment_id"] = "assessment-1"
    record["impacts"] = [
        {
            "label": "Synthetic impact",
            "source_text": "SYNTHETIC consequence.",
            "basis": "structured_source",
            "source_revision_id": "program-v2",
        }
    ]
    return data


def test_every_included_claim_uses_its_captured_revision():
    data = multiple_sources()
    before = deepcopy(data)
    model = compose(data)
    assert data == before
    assert model["citation_integrity_issues"] == []
    by_number = {c["number"]: c for c in model["citations"]}
    item = next(e for e in model["exhibits"] if e["type"] == "vulnerability")["items"][0]
    mapping = item["claim_citations"]
    expected = {
        "description": ["nvd-v1"],
        "cvss": ["nvd-v1", "program-v2"],
        "epss": ["epss-v3"],
        "kev": ["kev-v4"],
        "ransomware": ["kev-v4"],
        "ssvc": ["program-v2"],
        "impacts": ["program-v2"],
    }
    assert {
        key: [by_number[n]["revision_id"] for n in numbers] for key, numbers in mapping.items()
    } == expected
    assert by_number[mapping["cvss"][1]]["retrieved_at"] == "2026-11-07T01:02:03Z"
    table = next(n for n in model["sections"] if n["kind"] == "table" and n["headers"][0] == "CVE")
    assert "Fixture CNA [" + str(mapping["cvss"][1]) + "]" in table["rows"][0][2]["text"]
    assert set(item["citations"]) >= {n for values in mapping.values() for n in values}
    record_entry = next(
        e for e in model["appendix"]["entries"] if e["kind"] == "vulnerability_record"
    )
    assert any(f["path"].startswith("/report_claim_citations/") for f in record_entry["fields"])


def test_explicit_unknown_revision_never_inherits_primary_source():
    data = multiple_sources()
    data["draft"]["cve_records"][0]["cvss_assessments"][1]["source_revision_id"] = "missing"
    model = compose(data)
    assert any(
        "CVSS" in issue and "missing" in issue for issue in model["citation_integrity_issues"]
    )
    item = next(e for e in model["exhibits"] if e["type"] == "vulnerability")["items"][0]
    assert item["claim_citations"]["cvss"][1] is None


def test_explicit_revision_cannot_borrow_primary_retrieval_time():
    data = multiple_sources()
    data["draft"]["cve_records"][0]["sources"][-1].pop("retrieved_at")
    assert any("retrieval time" in issue for issue in compose(data)["citation_integrity_issues"])


def test_absent_optional_feeds_do_not_create_citation_blockers():
    data = specimen()
    record = data["draft"]["cve_records"][0]
    record.update(epss=None, epss_percentile=None, kev=None)
    record["sources"] = record["sources"][:1]
    assert compose(data)["citation_integrity_issues"] == []


def test_used_optional_value_requires_its_own_source():
    data = specimen()
    data["draft"]["cve_records"][0]["sources"] = data["draft"]["cve_records"][0]["sources"][:1]
    issues = compose(data)["citation_integrity_issues"]
    assert any("EPSS" in issue for issue in issues)
    assert any("KEV" in issue for issue in issues)


def test_optional_feed_cannot_stand_in_for_description_source():
    data = specimen()
    record = data["draft"]["cve_records"][0]
    record["sources"] = record["sources"][1:]
    model = compose(data)
    assert any("published description" in issue for issue in model["citation_integrity_issues"])
    item = next(e for e in model["exhibits"] if e["type"] == "vulnerability")["items"][0]
    assert item["claim_citations"]["description"] == [None]


def test_missing_included_revision_blocks_section_certification(client, app):
    rows = [{**row, "tag": "CVE-2099-10000"} for row in observations()]
    import_rows(client, app, rows)
    lead_id = client.get("/api/leads").json()[0]["id"]
    lead = ready(client, lead_id, validate=False)
    draft = deepcopy(lead["draft"])
    draft["cve_records"] = specimen()["draft"]["cve_records"]
    draft["cve_records"][0]["cvss_assessments"][1]["source_revision_id"] = "unavailable-revision"
    data = snapshot(app.state.store, lead_id, draft_override=draft)
    condition = next(r for r in data["readiness"] if r["key"] == "citation_integrity")
    assert not condition["ok"] and "CVSS" in condition["label"]
    review = next(r for r in data["section_reviews"] if r["key"] == "vulnerabilities")
    assert not review["can_validate"]
    assert condition["label"] in review["issues"]


def test_offline_frozen_snapshot_roundtrip_keeps_values_and_citations(tmp_path, monkeypatch):
    data = multiple_sources()
    data["composition"] = compose(data)
    frozen = tmp_path / "snapshot.json"
    frozen.write_text(json.dumps(data), encoding="utf-8")
    before = frozen.read_bytes()

    def forbidden(*args, **kwargs):
        pytest.fail("Report generation attempted a network connection")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    restored = json.loads(before)
    assert compose(restored) == data["composition"]
    render_pdf(restored, tmp_path / "report.pdf", tmp_path)
    render_docx(restored, tmp_path / "report.docx", tmp_path)
    assert frozen.read_bytes() == before
    assert restored == json.loads(before)
    assert (tmp_path / "report.pdf").read_bytes().startswith(b"%PDF")
    if shutil.which("pdftotext"):
        text = subprocess.check_output(
            ["pdftotext", "-layout", str(tmp_path / "report.pdf"), "-"]
        ).decode()
        assert "9.8" in text and "8.1" in text and "12.34" in text
        assert "CVE Program" in text and "2026-11-07T01:02:03Z" in text
    with ZipFile(tmp_path / "report.docx") as document:
        xml = document.read("word/document.xml").decode()
        assert "Fixture CNA" in xml and "report_claim_citations" in xml


def test_approved_paragraph_bytes_are_unchanged():
    from tests.approved_copy_helpers import accepted_source_bytes

    assert (
        hashlib.sha256(accepted_source_bytes()).hexdigest()
        == "3b139d987f9e83e97f289b45b69f8b755a06bda1b495452697c59bc8d494d1d3"
    )
