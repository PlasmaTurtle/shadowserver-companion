"""Offline report composition, pagination and document agreement contracts."""

import re
import shutil
import subprocess
import zipfile
from xml.etree import ElementTree as ET

from modules.investigations.components.reporting import render_pdf, render_docx
from modules.investigations.components.report_composition import compose, resolved_record

from modules.investigations.tests.support.report_artifacts import (
    specimen,
)


def test_text_metrics_citations_and_order():
    data = specimen(2)
    model = data["composition"]
    nodes = model["sections"]
    summary = next(n for n in nodes if n["kind"] == "table" and n["headers"][0] == "CVE")
    assert len(summary["rows"]) == 2
    assert (
        "9.8 CRITICAL" in summary["rows"][0][2]["text"]
        and "8.1 HIGH" in summary["rows"][0][2]["text"]
    )
    assert (
        "12.34% probability" in summary["rows"][0][3]["text"]
        and "87.65" in summary["rows"][0][3]["text"]
    )
    assert "Not listed in retrieved catalog" in summary["rows"][0][4]["text"]
    for record in data["draft"]["cve_records"]:
        assert any(n.get("text", "").startswith(record["description"]) for n in nodes)
    index = next(i for i, n in enumerate(nodes) if n.get("section_key") == "attribution")
    assert nodes[index - 1]["kind"] == "page_break"
    assert [c["number"] for c in model["citations"]] == list(range(1, len(model["citations"]) + 1))
    assert not any("services.nvd.nist.gov" in c["url"] for c in model["citations"])


def test_zero_metrics_not_missing_and_dns_citation():
    data = specimen(dns=True)
    record = data["draft"]["cve_records"][0]
    record.update(epss=0, epss_percentile=0, kev=None, cvss_assessments=[])
    model = compose(data)
    table = next(n for n in model["sections"] if n["kind"] == "table" and n["headers"][0] == "CVE")
    assert table["rows"][0][2]["text"] == "Unavailable"
    assert "0.00% probability" in table["rows"][0][3]["text"]
    assert table["rows"][0][4]["text"] == "Unavailable"
    assert model["attribution_groups"][0]["citation"] is not None
    assert any(c["url"].startswith("dns://") for c in model["citations"])


def test_fallback_exclusion_and_rejected_record_rules():
    data = specimen()
    draft = data["draft"]
    ident = data["cves"][0]
    draft["cve_records"][0]["verification_status"] = "unavailable"
    assert resolved_record(ident, draft)[1] == "unresolved"
    draft["cve_dispositions"] = {
        ident: {
            "action": "fallback",
            "reason": "API unavailable",
            "description": "Official captured text",
            "publisher": "Vendor",
            "source_url": "https://example.com/advisory",
            "retrieved_at": "2026-11-06T12:00:00Z",
            "evidence_text": "Official captured text",
        }
    }
    assert resolved_record(ident, draft)[1] == "fallback"
    draft["cve_records"][0]["verification_status"] = "rejected"
    assert resolved_record(ident, draft)[1] == "unresolved"
    draft["cve_dispositions"][ident] = {"action": "exclude", "reason": "Rejected by publisher"}
    result = compose(data)
    assert result["excluded_cves"] == [{"id": ident, "reason": "Rejected by publisher"}]
    assert not any(n["kind"] == "table" and n["headers"][0] == "CVE" for n in result["sections"])


def test_failed_nvd_attempt_not_cited_for_cna_fallback():
    data = specimen()
    record = data["draft"]["cve_records"][0]
    record.update(
        source="CVE Program", public_url="https://www.cve.org/CVERecord?id=" + record["id"]
    )
    record["sources"] = [
        {
            "publisher": "NVD",
            "http_status": 429,
            "public_url": "https://nvd.nist.gov/",
            "retrieved_at": "2026-11-06",
        },
        {
            "publisher": "CVE Program",
            "http_status": 200,
            "retrieved_at": "2026-11-06",
            "url": "https://cveawg.mitre.org/api/cve/" + record["id"],
        },
    ]
    result = compose(data)
    assert result["citations"][0]["publisher"] == "CVE Program"
    assert result["citations"][0]["url"].startswith("https://www.cve.org/")


def test_advisory_source_metadata_pinned_in_citations():
    data = specimen()
    data["explainers"][0]["source_metadata"] = [
        {
            "url": "https://www.cisa.gov/",
            "publisher": "CISA",
            "title": "Captured advisory reference",
            "retrieved_at": "2026-11-01T12:00:00Z",
            "date_published": "2026-10-01",
            "date_updated": "2026-10-03",
        }
    ]
    result = compose(data)
    citation = next(c for c in result["citations"] if c["url"] == "https://www.cisa.gov/")
    assert citation["publisher"] == "CISA"
    assert citation["title"] == "Captured advisory reference"
    assert citation["retrieved_at"] == "2026-11-01T12:00:00Z"
    assert citation["published_at"] == "2026-10-01"
    assert citation["updated_at"] == "2026-10-03"


def test_both_formats_long_source_text_and_hyperlinks(tmp_path):
    data = specimen(3, long=True)
    render_pdf(data, tmp_path / "long.pdf", tmp_path)
    render_docx(data, tmp_path / "long.docx", tmp_path)
    assert (tmp_path / "long.pdf").read_bytes().startswith(b"%PDF")
    with zipfile.ZipFile(tmp_path / "long.docx") as archive:
        xml = archive.read("word/document.xml")
        assert b"w:tblHeader" in xml and b'w:type="page"' in xml
        assert b"w:bookmarkStart" in xml and b"w:hyperlink" in xml
        text = " ".join(ET.fromstring(xml).itertext())
        for r in data["draft"]["cve_records"]:
            assert " ".join(r["description"].split()) in " ".join(text.split())
        rels = archive.read("word/_rels/document.xml.rels").decode()
        assert "https://nvd.nist.gov/vuln/detail/CVE-2099-10000" in rels
    if shutil.which("pdftotext"):
        raw = subprocess.check_output(
            ["pdftotext", "-layout", str(tmp_path / "long.pdf"), "-"]
        ).decode()
        pages = raw.split("\f")
        attribution = next(
            i for i, p in enumerate(pages) if re.search(r"^\s*Attribution\s*$", p, re.M)
        )
        closing = next(i for i, p in enumerate(pages) if re.search(r"^\s*Closing\s*$", p, re.M))
        appendix = next(
            i for i, p in enumerate(pages) if re.search(r"^\s*Companion Appendix\s*$", p, re.M)
        )
        assert attribution < closing < appendix
        assert re.search(r"^\s*Attribution\s*$", pages[attribution], re.M)
        assert "TLP:AMBER" in pages[attribution]
        raw = re.sub(
            r"^.*(?:TLP:AMBER|SHADOWSERVER COMPANION|For Informational Purposes Only|Page \d+).*$",
            "",
            raw,
            flags=re.M,
        )
        for record in data["draft"]["cve_records"]:
            assert " ".join(record["description"].split()) in " ".join(raw.split())
