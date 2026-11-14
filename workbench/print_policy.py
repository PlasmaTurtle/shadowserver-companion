"""Shared offline print treatment. Handling marks are independent of agency themes."""

from datetime import datetime, timezone

from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from reportlab.lib import colors

TLP_LABEL = "TLP:AMBER"
TLP_EXPLANATION = (
    "TLP:AMBER — Share on a need-to-know basis within the receiving organization and its clients. "
    "Source-specific additional restrictions remain applicable."
)
PRINT_RENDERER_VERSION = "0.9.91"

# Temperature is an internal outreach priority, independent of TLP and CVSS.
# Fixed labels and print-safe colors prevent stored input becoming styling.
PRIORITY_MARKS = {
    "cool": ("Cool", "12675F"),
    "warm": ("Warm", "805A13"),
    "hot": ("Hot", "9C461A"),
    "blazing": ("Blazing", "A72E48"),
}


def set_document_properties(doc, *, title, author, created_at=None, revision=1):
    """Replace the Word template's sample metadata with this export's facts.

    A missing or ambiguous timestamp stays absent instead of inheriting the
    library template's 2013 dates. The report date remains a separate body field.
    """
    properties = doc.core_properties
    properties.title = str(title or "")[:255]
    properties.author = str(author or "")[:255]
    properties.last_modified_by = properties.author
    properties.comments = ""
    properties.subject = ""
    properties.keywords = ""
    properties.category = ""
    try:
        properties.revision = max(1, int(revision))
    except TypeError, ValueError:
        properties.revision = 1
    try:
        instant = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        if instant.tzinfo is None:
            instant = None
        else:
            instant = instant.astimezone(timezone.utc)
    except TypeError, ValueError, OverflowError:
        instant = None
    for tag in ("dcterms:created", "dcterms:modified", "cp:lastPrinted"):
        for element in list(properties._element.findall(qn(tag))):
            properties._element.remove(element)
    if instant is not None:
        properties.created = instant
        properties.modified = instant


def priority_mark(score):
    if not isinstance(score, dict):
        return None
    temperature = score.get("temperature")
    if not isinstance(temperature, str) or temperature not in PRIORITY_MARKS:
        return None
    label, color = PRIORITY_MARKS[temperature]
    return {"temperature": temperature, "label": "Outreach priority: " + label, "color": color}


def draw_tlp(canvas, right, baseline, font="Helvetica-Bold"):
    size, padding = 12, 5
    width = canvas.stringWidth(TLP_LABEL, font, size)
    canvas.setFillColor(colors.black)
    canvas.rect(
        right - width - padding * 2, baseline - 3, width + padding * 2, 18, fill=1, stroke=0
    )
    canvas.setFillColor(colors.HexColor("#FFC000"))
    canvas.setFont(font, size)
    canvas.drawString(right - width - padding, baseline, TLP_LABEL)


def decorate_pdf(
    canvas,
    doc,
    left_text="",
    footer_text="",
    font="Helvetica",
    marking_font="Helvetica-Bold",
    priority=None,
):
    """Every page, including appendix pages, receives two unscaled 12pt markings."""
    canvas.saveState()
    width, height = doc.pagesize
    left, right = doc.leftMargin, width - doc.rightMargin
    canvas.setFillColor(colors.black)
    canvas.setFont(font, 7)
    if left_text:
        canvas.drawString(left, height - 33, left_text)
    if footer_text:
        canvas.drawString(left, 34, footer_text)
    canvas.drawCentredString(width / 2, 20, "Page " + str(doc.page))
    mark = priority_mark(priority)
    if mark:
        canvas.setFillColor(colors.HexColor("#" + mark["color"]))
        canvas.circle(left + 2, 22, 2, fill=1, stroke=0)
    draw_tlp(canvas, right, height - 34, marking_font)
    draw_tlp(canvas, right, 31, marking_font)
    canvas.restoreState()


def _mark_paragraph(paragraph):
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.line_spacing = Pt(18)
    run = paragraph.add_run(TLP_LABEL)
    run.bold = True
    run.font.name = "Arial"
    run.font.size = Pt(12)
    run.font.color.rgb = RGBColor.from_string("FFC000")
    shade = OxmlElement("w:shd")
    shade.set(qn("w:val"), "clear")
    shade.set(qn("w:color"), "auto")
    shade.set(qn("w:fill"), "000000")
    run._r.get_or_add_rPr().append(shade)


def decorate_docx(section, footer_text="", *, priority=None):
    section.different_first_page_header_footer = False
    section.header_distance = Pt(20)
    section.footer_distance = Pt(18)
    _mark_paragraph(section.header.paragraphs[0])
    _mark_paragraph(section.footer.paragraphs[0])
    paragraph = section.footer.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.line_spacing = Pt(10)
    mark = priority_mark(priority)
    if mark:
        label = paragraph.add_run("●  ")
        label.font.size = Pt(7)
        label.font.color.rgb = RGBColor.from_string(mark["color"])
    run = paragraph.add_run((footer_text + " | " if footer_text else "") + "Page ")
    run.font.size = Pt(7)
    run.font.color.rgb = RGBColor(0, 0, 0)
    page = OxmlElement("w:fldSimple")
    page.set(qn("w:instr"), "PAGE")
    run_xml = OxmlElement("w:r")
    properties = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), "000000")
    properties.append(color)
    size = OxmlElement("w:sz")
    size.set(qn("w:val"), "14")
    properties.append(size)
    run_xml.append(properties)
    value = OxmlElement("w:t")
    value.text = "1"
    run_xml.append(value)
    page.append(run_xml)
    paragraph._p.append(page)
