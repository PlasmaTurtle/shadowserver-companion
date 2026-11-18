"""Shared PDF/SVG/PNG word gaps and native Word paragraph-final behavior."""

from copy import deepcopy
import base64
from io import BytesIO
from math import floor
import re
import subprocess
from types import SimpleNamespace
from xml.etree import ElementTree as ET
from zipfile import ZipFile
import zlib

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from PIL import Image, ImageChops
from reportlab.pdfgen.canvas import Canvas
from reportlab.pdfbase import pdfmetrics
import pytest

from workbench.appendix_renderers import _paragraph
from workbench.closing_page_renderers import add_docx_closing_page
from workbench.exhibit_rendering import ExhibitFlowable, png, svg
from workbench.report_renderers import render_docx, render_pdf
from workbench.vector_layout import ExhibitPage
from workbench.word_justification import measured_paragraph
from workbench.unicode_fonts import width, FALLBACK


def page(extra=None):
    return ExhibitPage(
        "EX-JUSTIFY",
        1,
        300,
        100,
        [
            ("text", 0, 20, "First source line", 11, False, "#000000"),
            ("text", 0, 40, "Final line", 11, False, "#000000"),
        ],
        "First source line\nFinal line",
        []
        if extra is None
        else [
            {"kind": "justified_line", "left": 0, "baseline": 20, "word_space": extra, "width": 300}
        ],
    )


def pdf_bytes(value):
    stream = BytesIO()
    canvas = Canvas(stream, pagesize=(300, 100), invariant=1)
    ExhibitFlowable(value).drawOn(canvas, 0, 0)
    canvas.save()
    return stream.getvalue()


def pdf_streams(blob):
    decoded = []
    for raw in re.findall(rb"stream\r?\n(.*?)endstream", blob, re.DOTALL):
        try:
            if raw.rstrip().endswith(b"~>"):
                raw = base64.a85decode(raw.rstrip(), adobe=True)
            decoded.append(zlib.decompress(raw))
        except (ValueError, zlib.error):
            decoded.append(raw)
    return b"\n".join(decoded)


def pdf_text(blob):
    return subprocess.run(
        ["pdftotext", "-", "-"], input=blob, capture_output=True, check=True
    ).stdout


def test_vector_renderers_share_word_gap_and_leave_final_line_unchanged():
    original, justified = page(), page(5.25)
    plain_pdf, justified_pdf = pdf_bytes(original), pdf_bytes(justified)
    assert pdf_text(plain_pdf) == pdf_text(justified_pdf)
    assert b"5.25 Tw" in pdf_streams(justified_pdf)
    assert b"5.25 Tw" not in pdf_streams(plain_pdf)
    root = ET.fromstring(svg(justified))
    words = root.findall("{http://www.w3.org/2000/svg}text")
    spans = list(words[0])
    assert all("x" in span.attrib for span in spans)
    assert "word-spacing" not in words[0].attrib
    assert all("x" not in span.attrib for span in words[1])
    assert float(spans[-1].attrib["x"]) + width(spans[-1].text, "ExhibitSans", 11) == pytest.approx(
        width(justified.elements[0][3], "ExhibitSans", 11) + 2 * 5.25
    )
    assert ["".join(item.itertext()) for item in words] == [e[3] for e in justified.elements]
    before, after = Image.open(BytesIO(png(original))), Image.open(BytesIO(png(justified)))
    assert ImageChops.difference(
        before.crop((0, 0, 900, 90)), after.crop((0, 0, 900, 90))
    ).getbbox()
    assert not ImageChops.difference(
        before.crop((0, 90, 900, 300)), after.crop((0, 90, 900, 300))
    ).getbbox()
    # Absolute positions also retain literal repeated spaces, citations, URLs,
    # and mixed fallback-font runs when Office ignores CSS spacing properties.
    value = "参考資料  retained source [1] https://example.com/a?b=1&c=2"
    justified.elements[0] = ("text", 0, 20, value, 11, False, "#000000")
    first = ET.fromstring(svg(justified)).find("{http://www.w3.org/2000/svg}text")
    assert "".join(first.itertext()) == value
    cursor = 0
    for span in first:
        assert float(span.attrib["x"]) == pytest.approx(cursor)
        font = FALLBACK if span.attrib["font-family"] == "Companion CJK" else "ExhibitSans"
        cursor += pdfmetrics.stringWidth(span.text, font, 11) + 5.25 * span.text.count(" ")
    assert cursor == pytest.approx(width(value, "ExhibitSans", 11) + 5.25 * value.count(" "))


def test_old_geometry_without_alignment_metadata_retains_exact_renderer_bytes():
    original = page()
    preserved = deepcopy(original)
    # Existing unrelated page metadata cannot activate the new renderer behavior.
    preserved.segments.append({"kind": "page_citations", "values": []})
    assert pdf_bytes(preserved) == pdf_bytes(original)
    assert svg(preserved) == svg(original)
    assert png(preserved) == png(original)


def test_measured_word_paragraph_retains_source_and_gap_rounding(tmp_path):
    doc = Document()
    paragraph = doc.add_paragraph()
    lines = ["First source  paragraph", "Its final line", "参考資料 retained source line"]
    measured_paragraph(paragraph, lines, [1.123, 0, 2.25])
    assert paragraph.text == "\n".join(lines)
    assert paragraph.alignment == WD_ALIGN_PARAGRAPH.JUSTIFY
    values = [int(value) for value in paragraph._p.xpath(".//w:rPr/w:spacing/@w:val")]
    assert sum(values) == floor(1.123 * 3 * 20) + floor(2.25 * 3 * 20)
    assert any(run.font.name == "Companion Noto Sans SC" for run in paragraph.runs)
    assert doc.settings.element.find(".//" + qn("w:doNotExpandShiftReturn")).get(qn("w:val")) == "1"
    destination = tmp_path / "measured.docx"
    doc.save(destination)
    with ZipFile(destination) as archive:
        xml = archive.read("word/document.xml")
        assert b'w:jc w:val="both"' in xml
        assert b"w:spacing" in xml


def test_native_closing_and_appendix_use_frozen_line_gaps():
    lines = ["Continued supporting paragraph", "Second line continues"]
    block = {
        "kind": "closing_block",
        "id": "responsibility",
        "lines": lines,
        "word_spaces": [1.25, 2.5],
        "justified": True,
        "top": 1,
        "height": 30,
        "size": 11,
        "leading": 15,
    }
    value = page()
    value.segments = [block]
    doc = Document()
    add_docx_closing_page(doc, SimpleNamespace(page=value))
    paragraph = doc.paragraphs[0]
    assert paragraph.text == "\n".join(lines)
    assert paragraph.alignment == WD_ALIGN_PARAGRAPH.JUSTIFY
    assert len(paragraph._p.xpath(".//w:rPr/w:spacing")) == 4
    appendix = _paragraph(doc, {**block, "kind": "appendix_text"}, 0)
    assert appendix.text == paragraph.text
    assert appendix.alignment == WD_ALIGN_PARAGRAPH.JUSTIFY
    assert appendix._p.xpath(".//w:rPr/w:spacing/@w:val") == paragraph._p.xpath(
        ".//w:rPr/w:spacing/@w:val"
    )


def test_generic_report_justifies_prose_but_not_metadata_tables_or_signature(tmp_path):
    body = "Retained source paragraph explains the supporting report evidence. " * 12
    data = {
        "domain": "example.com",
        "draft": {"subject": "Notification", "sender_name": "Analyst"},
        "evidence": [],
        "document_policy": {"paragraph_alignment": "justify"},
        "composition": {
            "template": {"font_size": 10},
            "citations": [],
            "exhibits": [],
            "sections": [
                {"kind": "text", "style": "body", "text": body},
                {"kind": "text", "style": "signature", "text": "Analyst, Special Agent"},
                {"kind": "metadata", "label": "To", "text": "Example recipient"},
                {
                    "kind": "table",
                    "headers": ["Label", "Value"],
                    "widths": [2, 4.8],
                    "rows": [[{"text": "Source"}, {"text": "Preserved"}]],
                },
            ],
        },
    }
    render_docx(data, tmp_path / "report.docx", tmp_path)
    doc = Document(tmp_path / "report.docx")
    assert doc.paragraphs[0].alignment == WD_ALIGN_PARAGRAPH.JUSTIFY
    assert doc.paragraphs[1].alignment is None
    assert all(
        p.alignment is None
        for table in doc.tables
        for row in table.rows
        for cell in row.cells
        for p in cell.paragraphs
    )
    render_pdf(data, tmp_path / "report.pdf", tmp_path)
    content = pdf_streams((tmp_path / "report.pdf").read_bytes())
    assert b" Tw" in content
    # A saved policy without the new marker remains left aligned.
    data["document_policy"] = {}
    render_docx(data, tmp_path / "legacy.docx", tmp_path)
    assert Document(tmp_path / "legacy.docx").paragraphs[0].alignment is None
