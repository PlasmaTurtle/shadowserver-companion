"""Export contracts: offline, matching artifacts, native details and handling marks."""

from copy import deepcopy
import json
from pathlib import Path
import re
import socket
import subprocess
import zipfile
from xml.etree import ElementTree as ET

from modules.investigations.tests.support.report_artifacts import specimen
from modules.investigations.components.reporting import render_pdf, render_docx
from modules.investigations.components.report_composition import compose
from modules.ui.components.exhibit_rendering import layout, svg, png, svg_pages, export_exhibits
from modules.activity.components.work_log import render_work_log
from modules.investigations.components.closing import render_closing


def sample():
    data = specimen(2)
    rows = data["qualified_lead"]["validated_leads"][0]["entries"]
    rows[0]["source"]["fields"].update(
        ip="192.0.2.1",
        protocol="tcp",
        port=443,
        version="Example 1.0",
        tag="CVE-2099-10000;CVE-2099-10001",
        timestamp="2026-11-06T10:00:00Z",
        zero=0,
        boolean=False,
        empty="",
        null=None,
        nested={"item": ["Analyst García", "<script>literal</script>"]},
    )
    rows.append(deepcopy(rows[0]))
    data["report_revision"] = 4
    data["draft_revision"] = 9
    data["document_policy"] = {"brand_profile": {"id": "usss", "version": "1"}}
    data["composition"] = compose(data)
    return data


def test_vector_and_fallback_use_one_untruncated_layout():
    model = {
        "id": "EX-LARGE",
        "title": "Large source test",
        "type": "attribution",
        "report_revision": 1,
        "counts": [{"label": "Reported IPs", "value": 70}],
        "groups": [],
        "items": [
            {
                "label": f"Item {i}",
                "detail": "<script>literal</script> & long source details " + ("word " * 90),
                "appendix_entry_ids": ["B-one"],
                "citations": [1],
            }
            for i in range(12)
        ],
        "alt_text": "Exact case scope",
    }
    pages = layout(model)
    assert len(pages) > 1
    assert all(p.height <= 612 for p in pages)
    assert all(item[4] >= 10 for p in pages for item in p.elements if item[0] == "text")
    joined = " ".join(item[3] for p in pages for item in p.elements if item[0] == "text")
    assert "<script>literal</script>" in joined
    assert all("Item " + str(i) in joined for i in range(12))
    for page in pages:
        raw = svg(page)
        root = ET.fromstring(raw)
        assert b"<script>" not in raw and b"&lt;script&gt;" in raw
        assert all(e.attrib.get("fill") == "#000000" for e in root.iter() if e.tag.endswith("text"))
        assert png(page).startswith(b"\x89PNG")
    assert svg_pages(model) == svg_pages(model)


def test_pdf_docx_contain_exhibits_complete_native_appendix_and_markings(tmp_path, monkeypatch):
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("Network request during rendering")),
    )
    data = sample()
    render_pdf(data, tmp_path / "notification.pdf", tmp_path)
    render_docx(data, tmp_path / "notification.docx", tmp_path)
    text = subprocess.check_output(
        ["pdftotext", "-layout", str(tmp_path / "notification.pdf"), "-"]
    ).decode()
    pages = [p for p in text.split("\f") if p.strip()]
    assert all(p.count("TLP:AMBER") == 2 for p in pages)
    assert text.index("Companion Appendix") > text.index("Thank you for your attention")
    assert "Analyst García" in text and "<script>literal</script>" in text
    assert "null (supplied)" in text and "false" in text
    for exhibit in data["composition"]["exhibits"]:
        assert exhibit["title"] in text
    with zipfile.ZipFile(tmp_path / "notification.docx") as archive:
        body = archive.read("word/document.xml")
        assert b"svgBlip" in body
        assert any(name.endswith(".svg") for name in archive.namelist())
        assert any(name.endswith(".png") for name in archive.namelist())
        all_text = " ".join(ET.fromstring(body).itertext())
        assert "Companion Appendix" in all_text and "null (supplied)" in all_text
        for name in ("word/header1.xml", "word/footer1.xml"):
            xml = archive.read(name)
            assert (
                b"TLP:AMBER" in xml
                and b"FFC000" in xml
                and b"000000" in xml
                and b'w:val="24"' in xml
            )
        # Generated body links and prose are black; TLP lives in page chrome.
        root = ET.fromstring(body)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        assert all(
            n.attrib.get("{" + ns["w"] + "}val") == "000000" for n in root.findall(".//w:color", ns)
        )


def test_exhibit_package_has_marked_standalone_and_plain_embedded_masters(tmp_path):
    data = sample()
    assets = export_exhibits(data["composition"], tmp_path / "exhibits", data["document_policy"])
    assert len(assets) >= 3
    for artifact in assets:
        assert b"TLP:AMBER" in (tmp_path / "exhibits" / artifact["standalone_svg"]).read_bytes()
        assert b"TLP:AMBER" not in (tmp_path / "exhibits" / artifact["svg"]).read_bytes()
        text = subprocess.check_output(
            ["pdftotext", str(tmp_path / "exhibits" / artifact["standalone_pdf"]), "-"]
        ).decode()
        assert text.count("TLP:AMBER") >= 2


def test_worklog_and_closing_are_marked_on_every_page(tmp_path):
    render_work_log(
        {"case_id": "test-case", "domain": "example.com"}, [], tmp_path / "work-log.pdf"
    )
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
        "created_at": "2026-11-07T12:00:00Z",
        "closed_by": "Synthetic Analyst",
    }
    render_closing(closing, tmp_path)
    for name in ("work-log.pdf", "closing-report.pdf"):
        text = subprocess.check_output(["pdftotext", str(tmp_path / name), "-"]).decode()
        assert all(p.count("TLP:AMBER") == 2 for p in text.split("\f") if p.strip())


def test_unicode_fallback_is_native_and_embedded(tmp_path):
    data = sample()
    data["draft"]["company"] = "Synthetic 名字 公司"
    data["qualified_lead"]["validated_leads"][0]["entries"][0]["source"]["fields"][
        "multilingual"
    ] = "名字 公司 / García / Ελληνικά / Кириллица"
    data["composition"] = compose(data)
    render_pdf(data, tmp_path / "unicode.pdf", tmp_path)
    render_docx(data, tmp_path / "unicode.docx", tmp_path)
    text = subprocess.check_output(["pdftotext", str(tmp_path / "unicode.pdf"), "-"]).decode()
    assert "名字 公司" in text and "Ελληνικά" in text and "Кириллица" in text
    with zipfile.ZipFile(tmp_path / "unicode.docx") as archive:
        assert "word/fonts/CompanionNotoSansSC.odttf" in archive.namelist()
        assert b"embedRegular" in archive.read("word/fontTable.xml")
        assert "名字".encode() in archive.read("word/document.xml")
    from modules.ui.components.unicode_fonts import font_runs, FALLBACK

    assert font_runs("名字", "ReportSans") == [(FALLBACK, "名字")]
