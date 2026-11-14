"""Draft labeling and Word border-space regression for frozen report pages."""

from copy import deepcopy
from pathlib import Path
import shutil
import subprocess
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from docx import Document
from docx.shared import Inches, Pt
import pytest

from tools.preview_appendix import specimen
from workbench.appendix_renderers import _table
from workbench.document_fonts import embed_report_fonts
from workbench.report_renderers import render_pdf, render_docx


def test_draft_header_covers_reviewed_pages_without_mutating_frozen_content(tmp_path):
    data = specimen()
    data["demo"] = False
    frozen = deepcopy(data["composition"])
    render_pdf(data, tmp_path / "draft.pdf", tmp_path, draft=True)
    text = subprocess.check_output(["pdftotext", str(tmp_path / "draft.pdf"), "-"]).decode()
    pages = [page for page in text.split("\f") if page.strip()]
    assert len(pages) > 6
    assert all("DRAFT FOR REVIEW" in page and page.count("TLP:AMBER") == 2 for page in pages)
    render_docx(data, tmp_path / "draft.docx", tmp_path, draft=True)
    with ZipFile(tmp_path / "draft.docx") as archive:
        header = archive.read("word/header1.xml").decode()
        assert "DRAFT FOR REVIEW" in header and "TLP:AMBER" in header
        # Header's built-in centered tab must not precede our right-aligned TLP.
        assert 'w:pStyle w:val="Header"' not in header
        assert 'w:pos="9792" w:val="right"' in header
    render_docx(data, tmp_path / "final.docx", tmp_path)
    with ZipFile(tmp_path / "final.docx") as archive:
        assert b"DRAFT FOR REVIEW" not in archive.read("word/header1.xml")
    render_pdf(data, tmp_path / "final.pdf", tmp_path)
    text = subprocess.check_output(["pdftotext", str(tmp_path / "final.pdf"), "-"]).decode()
    assert "DRAFT FOR REVIEW" not in text
    assert data["composition"] == frozen


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice round-trip is optional")
def test_word_keeps_measured_table_lines_inside_exact_height(tmp_path):
    """A line just below the native 170pt limit must not wrap to a fifth line."""
    document = Document()
    section = document.sections[0]
    section.page_width, section.page_height = Inches(8.5), Inches(11)
    section.left_margin = section.right_margin = Inches(0.85)
    document.styles["Normal"].paragraph_format.space_after = Pt(0)
    lines = [
        "Cna / Metrics / item 1 / Cvss V3",
        "1 / Integrity Impact",
        "(cna/metrics/0/cvssV3_1/integrit",
        "yImpact)",
    ]
    block = {
        "label_width": 176,
        "width": 477.6,
        "padding": 3,
        "leading": 14,
        "size": 10.5,
        "rows": [{"labels": lines, "values": ["HIGH"], "height": 62, "url": None}],
    }
    _table(document, block)
    embed_report_fonts(document)
    source = tmp_path / "border.docx"
    document.save(source)
    result = subprocess.run(
        [
            shutil.which("soffice"),
            "--headless",
            "-env:UserInstallation=" + (tmp_path / "office-profile").as_uri(),
            "--convert-to",
            "pdf",
            "--outdir",
            str(tmp_path),
            str(source),
        ],
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    body = subprocess.check_output(["pdftotext", "-bbox-layout", str(tmp_path / "border.pdf"), "-"])
    tree = ET.fromstring(body)
    ns = "{http://www.w3.org/1999/xhtml}"
    rendered = [
        " ".join(w.text or "" for w in line.findall(ns + "word")) for line in tree.iter(ns + "line")
    ]
    for line in lines:
        assert line in rendered
    assert "t" not in rendered
