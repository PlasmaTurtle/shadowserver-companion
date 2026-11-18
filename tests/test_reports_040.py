"""Offline report composition, pagination and document agreement contracts."""

import copy
from pathlib import Path
import re
import shutil
import subprocess
import zipfile
from xml.etree import ElementTree as ET

from workbench.reporting import default_draft, render_pdf, render_docx
from workbench.report_composition import compose, resolved_record
from workbench.store import DEFAULT_SETTINGS
from workbench.report_layouts import CURRENT_LAYOUTS


def specimen(count=1, long=False, dns=False):
    lead = {"entries": [], "company": "Synthetic Example Company", "domain": "example.com"}
    draft = default_draft(lead, DEFAULT_SETTINGS)
    # Keep the historical export fixture on its original layout. Current-layout
    # adoption and end-to-end generation have their own integration coverage.
    draft.update({key: "legacy" for key in CURRENT_LAYOUTS})
    draft.update(
        sender_name="Test Analyst",
        company=lead["company"],
        narrative="Synthetic document test. No real business or exposure is represented.",
        website_verified=True,
        reviewed=True,
    )
    cves = [f"CVE-2099-{10000 + i}" for i in range(count)]
    records = []
    for ident in cves:
        body = "SYNTHETIC TEST DESCRIPTION. A fictional component is used solely to test document generation. The precise source wording, including qualifiers, must remain unchanged."
        if long:
            body += "\n\n" + (
                "This synthetic paragraph verifies that a long published description can flow across pages while preserving every word and qualifying condition. "
                * 40
            )
        records.append(
            {
                "id": ident,
                "source": "NVD",
                "verification_status": "published",
                "description": body,
                "description_contributor": "Fixture CNA",
                "public_url": "https://nvd.nist.gov/vuln/detail/" + ident,
                "retrieved_at": "2026-11-06T12:00:00Z",
                "revision_id": "test-" + ident,
                "cvss_assessments": [
                    {
                        "score": 9.8,
                        "severity": "CRITICAL",
                        "version": "3.1",
                        "source": "nvd@nist.gov",
                        "vector": "CVSS:3.1/test",
                    },
                    {
                        "score": 8.1,
                        "severity": "HIGH",
                        "version": "3.1",
                        "source": "Fixture CNA",
                        "vector": "CVSS:3.1/fixture",
                    },
                ],
                "epss": 0.1234,
                "epss_percentile": 0.8765,
                "epss_date": "2026-11-05",
                "epss_retrieved_at": "2026-11-06T12:00:00Z",
                "kev": False,
                "kev_date": "2026-11-06",
                "kev_retrieved_at": "2026-11-06T12:00:00Z",
                "sources": [
                    {
                        "publisher": "NVD",
                        "url": "https://services.nvd.nist.gov/rest/json/cves/2.0?cveId=" + ident,
                        "retrieved_at": "2026-11-06T12:00:00Z",
                    },
                    {
                        "publisher": "FIRST EPSS",
                        "public_url": "https://www.first.org/epss/",
                        "retrieved_at": "2026-11-06T12:00:00Z",
                    },
                    {
                        "publisher": "CISA KEV",
                        "public_url": "https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
                        "retrieved_at": "2026-11-06T12:00:00Z",
                    },
                ],
            }
        )
    draft["cve_records"] = records
    proof = {
        "ip": "192.0.2.1",
        "registry": "Fixture Registry",
        "source_url": "dns://192.0.2.53/example.com/A"
        if dns
        else "https://example.com/registration",
        "retrieved_at": "2026-11-06T12:00:00Z",
        "protocol": "DNS" if dns else "RDAP",
        "attribution": {"value": "contact@example.com"},
        "body_sha256": "f" * 64,
    }
    data = {
        "draft": draft,
        "profile": copy.deepcopy(DEFAULT_SETTINGS),
        "domain": "example.com",
        "demo": True,
        "cves": cves,
        "evidence": [],
        "explainers": [
            {
                "id": "context",
                "title": "General security context",
                "body": "Reusable advisory text for this synthetic test.",
                "sources": "https://www.cisa.gov/",
                "revision": 3,
            }
        ],
        "assets": [
            {
                "hostname": "example.com",
                "ip": "192.0.2.1",
                "asn": 64496,
                "location": "Example, NC, US",
                "private_ip": False,
                "protocol": "tcp",
                "port": 443,
                "version": "1.0",
                "tag": ";".join(cves) or "eol-example",
                "first_seen": "2026-11-05",
                "last_seen": "2026-11-05",
            }
        ],
        "qualified_lead": {
            "validated_leads": [
                {
                    "hostname": "example.com",
                    "entries": [
                        {"ip": "192.0.2.1", "source": {"fields": {"hostname": "example.com"}}}
                    ],
                }
            ],
            "whois": [proof],
        },
    }
    data["composition"] = compose(data)
    return data


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
