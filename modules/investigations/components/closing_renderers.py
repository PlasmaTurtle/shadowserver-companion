"""Closing-report text and PDF/DOCX rendering from an explicit snapshot."""

from datetime import datetime, timezone
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.oxml.ns import qn
from docx.enum.text import WD_ALIGN_PARAGRAPH
from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, KeepTogether


def display_time(value):
    if not value:
        return "Not recorded"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).strftime("%b %d, %Y at %H:%M:%S UTC")
    except (ValueError, TypeError):
        pass
    return str(value)


def sections(data):
    preview = bool(data.get("preview"))
    delivery = (
        "Successful notification recorded on " + display_time(data["delivered_at"])
        if data["delivered_at"]
        else "Proposed closure without successful notification."
        if preview
        else "Closed without successful notification."
    )
    result = [
        ("Notification closing report", 0),
        (f"{data['business']}\n{data['title']}\nCase {data['case_id']}", 1),
        (f"{delivery}\nDisposition: {data['disposition'].replace('_', ' ')}", 1),
        ("Conclusion", 2),
        (data["conclusion"], 1),
        ("Report record", 2),
    ]
    if not data["reports"]:
        result.append(("No notification report was certified for this case.", 1))
    for report in data["reports"]:
        cert = (
            f"Certified by {report['certified_by']} on {display_time(report['certified_at'])}"
            if report["certification_source"] == "analyst"
            else "Imported finalized report; original certification identity was not recorded."
        )
        result.append(
            (
                f"Revision {report['revision']} - {display_time(report['created_at'])}\nReport ID {report['id']}\n{cert}",
                1,
            )
        )
    result.append(("Contact and response chronology", 2))
    if not data["attempts"]:
        result.append(("No contact attempts were recorded.", 1))
    for attempt in data["attempts"]:
        report = next((r for r in data["reports"] if r["id"] == attempt["report_id"]), None)
        details = [
            f"{display_time(attempt['occurred_at'])} - {attempt['channel'].replace('_', ' ')} - {attempt['outcome'].replace('_', ' ')}",
            f"Recipient: {attempt['recipient'] or 'Not recorded'}"
            + (f" ({attempt['destination']})" if attempt["destination"] else ""),
            f"Report revision: {report['revision']}" if report else "",
            f"Information source: {attempt['information_source'].replace('_', ' ')}",
            attempt["notes"],
            f"Recorded by: {attempt['recorded_by']}",
        ]
        result.append(("\n".join(x for x in details if x), 1))
    result += [
        (
            "Proposed administrative closure — case remains open"
            if preview
            else "Administrative closure",
            2,
        ),
        (
            f"Opened: {display_time(data['opened_at'])}\n"
            + (
                f"Preview generated: {display_time(data['created_at'])}\nPrepared by: "
                if preview
                else f"Closed: {display_time(data['created_at'])}\nClosing report finalized by: "
            )
            + data["closed_by"],
            1,
        ),
    ]
    return result


def render_closing(data, folder):
    # Closing rendering is also invoked in a fresh isolated renderer. Register
    # its exact bundled typefaces explicitly instead of depending on an earlier
    # notification-renderer import in the application process.
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from modules.ui.components.vector_layout import FONT_ROOT

    registered = set(pdfmetrics.getRegisteredFontNames())
    for name, filename in (
        ("ReportSans", "DejaVuSans.ttf"),
        ("ReportSans-Bold", "DejaVuSans-Bold.ttf"),
    ):
        if name not in registered:
            pdfmetrics.registerFont(TTFont(name, str(FONT_ROOT / filename)))

    justified = data.get("document_policy", {}).get("paragraph_alignment") == "justify"
    styles = {
        0: ParagraphStyle(
            "Title", fontName="ReportSans-Bold", fontSize=17, leading=22, spaceAfter=8
        ),
        1: ParagraphStyle(
            "Body",
            fontName="ReportSans",
            fontSize=10,
            leading=13,
            spaceAfter=4,
            alignment=TA_JUSTIFY if justified else TA_LEFT,
        ),
        2: ParagraphStyle(
            "Heading",
            fontName="ReportSans-Bold",
            fontSize=11,
            leading=15,
            spaceBefore=6,
            spaceAfter=4,
            keepWithNext=True,
        ),
    }
    from modules.ui.components.unicode_fonts import markup, prepare_docx

    flow = []
    content = iter(sections(data))
    for text, level in content:
        paragraph = Paragraph(markup(text, styles[level].fontName), styles[level])
        if level == 2:
            following, following_level = next(content)
            body = Paragraph(
                markup(following, styles[following_level].fontName), styles[following_level]
            )
            flow.append(KeepTogether([paragraph, body]))
            continue
        # Do not strand an event's attribution on the next page. Oversize
        # paragraphs still split through ReportLab's normal KeepTogether fallback.
        flow.append(KeepTogether([paragraph]) if level == 1 and "\n" in text else paragraph)

    def footer(canvas, doc):
        from modules.ui.components.print_policy import decorate_pdf

        decorate_pdf(
            canvas,
            doc,
            left_text="PREVIEW — CASE OPEN | CLOSING REPORT"
            if data.get("preview")
            else "SHADOWSERVER COMPANION | CLOSING REPORT",
            footer_text="Case " + data["case_id"][:12],
            font="ReportSans",
            priority=data.get("intake_score"),
        )

    SimpleDocTemplate(
        str(folder / "closing-report.pdf"),
        pagesize=(612, 792),
        leftMargin=54,
        rightMargin=54,
        topMargin=60,
        bottomMargin=62,
        title="Notification closing report",
        author=data["closed_by"],
    ).build(flow, onFirstPage=footer, onLaterPages=footer)
    doc = Document()
    if justified:
        from modules.ui.components.word_justification import configure_justification

        configure_justification(doc)
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(0.85)
    section.bottom_margin = Inches(0.85)
    section.left_margin = section.right_margin = Inches(0.75)
    for name in ("Normal", "Title", "Heading 1"):
        doc.styles[name].font.name = "Arial"
        doc.styles[name].font.color.rgb = RGBColor(0, 0, 0)
    doc.styles["Normal"].font.size = Pt(10)
    doc.styles["Normal"].paragraph_format.space_after = Pt(4)
    doc.styles["Normal"].paragraph_format.line_spacing = Pt(13)
    doc.styles["Title"].font.size = Pt(17)
    doc.styles["Title"].font.bold = True
    doc.styles["Title"].paragraph_format.space_after = Pt(8)
    borders = doc.styles["Title"]._element.find("./" + qn("w:pPr") + "/" + qn("w:pBdr"))
    if borders is not None:
        borders.getparent().remove(borders)
    doc.styles["Heading 1"].font.size = Pt(11)
    doc.styles["Heading 1"].paragraph_format.space_before = Pt(6)
    doc.styles["Heading 1"].paragraph_format.space_after = Pt(4)
    for text, level in sections(data):
        paragraph = doc.add_paragraph(text, style={0: "Title", 1: "Normal", 2: "Heading 1"}[level])
        if level == 1 and "\n" in text:
            paragraph.paragraph_format.keep_together = True
        if justified and level == 1:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    from modules.ui.components.print_policy import decorate_docx, set_document_properties

    set_document_properties(
        doc,
        title="Notification closing report",
        author=data["closed_by"],
        created_at=data.get("created_at"),
        revision=data.get("revision", 1),
    )

    decorate_docx(section, "Case " + data["case_id"][:12], priority=data.get("intake_score"))
    if data.get("preview"):
        marker = section.header.add_paragraph("PREVIEW — CASE OPEN")
        marker.paragraph_format.space_before = marker.paragraph_format.space_after = Pt(0)
        marker.paragraph_format.line_spacing = Pt(10)
        for run in marker.runs:
            run.font.size = Pt(8)
            run.font.color.rgb = RGBColor(0, 0, 0)
    prepare_docx(doc)
    doc.save(folder / "closing-report.docx")
