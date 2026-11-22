"""Bundled Unicode fallback for native text and self-contained exhibit graphics."""

from __future__ import annotations
from pathlib import Path
import base64
from functools import lru_cache
from xml.sax.saxutils import escape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from ..helpers.fonts import embed_font

FONT_ROOT = Path(__file__).resolve().parents[3] / "modules/ui/fonts"
FALLBACK = "CompanionCJK"
if FALLBACK not in pdfmetrics.getRegisteredFontNames():
    pdfmetrics.registerFont(TTFont(FALLBACK, str(FONT_ROOT / "NotoSansSC-Regular.ttf")))


def font_runs(value, base):
    text = str(value)
    face = pdfmetrics.getFont(base).face
    fallback = pdfmetrics.getFont(FALLBACK).face
    runs = []
    selected, chunk = None, []
    for char in text:
        code = ord(char)
        name = (
            base
            if code in face.charToGlyph or char in "\n\r\t"
            else FALLBACK
            if code in fallback.charToGlyph
            else None
        )
        if name is None:
            raise ValueError(
                f"The bundled report fonts do not support U+{code:04X}; retain the source and add a suitable licensed font before export."
            )
        if selected is not None and selected != name:
            runs.append((selected, "".join(chunk)))
            chunk = []
        selected = name
        chunk.append(char)
    if selected is not None:
        runs.append((selected, "".join(chunk)))
    return runs


def width(value, base, size):
    return sum(pdfmetrics.stringWidth(text, font, size) for font, text in font_runs(value, base))


def markup(value, base):
    return "".join(
        escape(text).replace("\n", "<br/>")
        if font == base
        else '<font name="' + FALLBACK + '">' + escape(text).replace("\n", "<br/>") + "</font>"
        for font, text in font_runs(value, base)
    )


@lru_cache(maxsize=3)
def embedded_face(filename, family, weight="400"):
    content = base64.b64encode((FONT_ROOT / filename).read_bytes()).decode("ascii")
    return (
        "@font-face{font-family:'"
        + family
        + "';font-weight:"
        + weight
        + ";src:url(data:font/woff;base64,"
        + content
        + ") format('woff');}"
    )


def svg_font_style(needs_cjk=False):
    content = embedded_face("DejaVuSans.woff", "Companion Exhibit Sans") + embedded_face(
        "DejaVuSans-Bold.woff", "Companion Exhibit Sans", "700"
    )
    if needs_cjk:
        content += embedded_face("NotoSansSC-Regular.woff", "Companion CJK")
    return "<defs><style>" + content + "</style></defs>"


def prepare_docx(doc):
    """Embed the CJK font only when a document contains its characters.

    Word uses standard obfuscated OpenType embedding. Native text remains
    editable/searchable; no font install is required on the recipient's system.
    """
    from docx.oxml.ns import qn
    from lxml import etree

    if "ReportSans" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("ReportSans", str(FONT_ROOT / "DejaVuSans.ttf")))
    used = False
    for run in list(doc._element.xpath(".//w:r")):
        texts = run.xpath("./w:t")
        if not texts:
            continue
        content = "".join(t.text or "" for t in texts)
        selected = font_runs(content, "ReportSans")
        if not any(font == FALLBACK for font, text in selected):
            continue
        # Preserve each native run's formatting and replace only its text;
        # source runs are literal text (not fields/drawings).
        from copy import deepcopy

        parent = run.getparent()
        position = parent.index(run)
        for offset, (font, text) in enumerate(selected):
            item = deepcopy(run)
            for t in list(item.xpath("./w:t")):
                item.remove(t)
            t = etree.SubElement(item, qn("w:t"))
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            t.text = text
            if font == FALLBACK:
                used = True
                pr = item.find(qn("w:rPr"))
                if pr is None:
                    pr = etree.Element(qn("w:rPr"))
                    item.insert(0, pr)
                rfonts = pr.find(qn("w:rFonts"))
                if rfonts is None:
                    rfonts = etree.SubElement(pr, qn("w:rFonts"))
                for key in ("ascii", "hAnsi", "eastAsia", "cs"):
                    rfonts.set(qn("w:" + key), "Companion Noto Sans SC")
            parent.insert(position + offset, item)
        parent.remove(run)
    if not used:
        return
    package = doc.part.package
    if any(
        str(part.partname) == "/word/fonts/CompanionNotoSansSC.odttf"
        for part in package.iter_parts()
    ):
        return
    fonttable = next(
        part for part in package.iter_parts() if str(part.partname) == "/word/fontTable.xml"
    )
    root = etree.fromstring(fonttable.blob)
    font = etree.SubElement(root, qn("w:font"))
    font.set(qn("w:name"), "Companion Noto Sans SC")
    family = etree.SubElement(font, qn("w:family"))
    family.set(qn("w:val"), "swiss")
    embed_font(
        package,
        fonttable,
        font,
        FONT_ROOT / "NotoSansSC-Regular.ttf",
        "/word/fonts/CompanionNotoSansSC.odttf",
        "Regular",
        "82156389-4e28-4821-8bce-cdf0b2ed44c0",
    )
    fonttable._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    settings = doc.settings.element
    if settings.find(qn("w:embedTrueTypeFonts")) is None:
        etree.SubElement(settings, qn("w:embedTrueTypeFonts"))
