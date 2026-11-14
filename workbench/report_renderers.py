"""Offline PDF and DOCX rendering from an already assembled report snapshot."""

from __future__ import annotations

import re
from pathlib import Path
from xml.sax.saxutils import escape
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image as PDFImage,
    KeepTogether,
    PageBreak,
)
from .report_composition import compose, valid_url
from .print_policy import decorate_pdf, decorate_docx, set_document_properties
from .exhibit_rendering import layout as exhibit_layout, ExhibitFlowable, add_docx_exhibit
from .exhibit_rendering import is_page_exhibit, prepared_pages, add_docx_page_exhibit
from .unicode_fonts import markup as unicode_markup, prepare_docx
from .report_contracts import ReportSnapshot
from .word_justification import configure_justification

FONT_ROOT = Path(__file__).resolve().parent.parent / "fonts"
pdfmetrics.registerFont(TTFont("ReportSans", str(FONT_ROOT / "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("ReportSans-Bold", str(FONT_ROOT / "DejaVuSans-Bold.ttf")))


def review_header(data, draft):
    """Export state stays visible without changing the saved report content."""
    if data.get("demo"):
        return ("DRAFT FOR REVIEW - " if draft else "") + "SYNTHETIC LAYOUT EXAMPLE"
    return "DRAFT FOR REVIEW" if draft else "SHADOWSERVER COMPANION"


def render_pdf(data: ReportSnapshot, destination: Path, evidence_root: Path, draft=False):
    class LeadingTextTogether(KeepTogether):
        """Keep labels with the first two lines, without moving long quotations."""

        def wrap(self, width, height):
            result = super().wrap(width, height)
            if self._content and isinstance(self._content[-1], Paragraph):
                paragraph = self._content[-1]
                paragraph_height = paragraph.wrap(width, height)[1]
                self._H -= max(0, paragraph_height - 2 * paragraph.style.leading)
            return result

    content = data.get("composition") or compose(data)
    justified = (
        data.get("document_policy") or data.get("draft", {}).get("document_policy", {})
    ).get("paragraph_alignment") == "justify"
    template = content["template"]
    size = max(10.0, float(template.get("font_size", 10)))
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            "BodyReport",
            fontName="ReportSans",
            fontSize=size,
            leading=size * 1.3,
            spaceAfter=4,
            splitLongWords=True,
        )
    )
    styles.add(
        ParagraphStyle(
            "SmallReport",
            fontName="ReportSans",
            fontSize=10,
            leading=13,
            spaceAfter=4,
            splitLongWords=True,
        )
    )
    styles.add(
        ParagraphStyle(
            "AgencyReport",
            fontName="ReportSans-Bold",
            fontSize=11.5,
            leading=16,
            alignment=TA_CENTER,
            spaceAfter=3,
        )
    )
    styles.add(
        ParagraphStyle(
            "SectionReport",
            fontName="ReportSans-Bold",
            fontSize=11,
            leading=15,
            spaceBefore=10,
            spaceAfter=6,
            keepWithNext=True,
        )
    )
    styles.add(
        ParagraphStyle(
            "SubsectionReport",
            fontName="ReportSans-Bold",
            fontSize=10,
            leading=14,
            spaceBefore=9,
            spaceAfter=5,
            keepWithNext=True,
        )
    )
    styles.add(
        ParagraphStyle(
            "NoticeReport",
            fontName="ReportSans-Bold",
            fontSize=9,
            leading=14,
            alignment=TA_CENTER,
            textColor=colors.black,
            spaceBefore=6,
            spaceAfter=9,
        )
    )
    styles.add(ParagraphStyle("SourceReport", parent=styles["SmallReport"], keepWithNext=True))
    styles.add(ParagraphStyle("ClosingReport", parent=styles["BodyReport"], keepWithNext=True))
    if justified:
        for name in ("BodyReport", "SmallReport", "ClosingReport"):
            styles.add(
                ParagraphStyle(name + "Justified", parent=styles[name], alignment=TA_JUSTIFY)
            )
    citations = {str(c["number"]) for c in content["citations"]}
    anchors = {n["anchor"] for n in content["sections"] if n.get("anchor")}
    anchors.update(e["id"] for e in content.get("exhibits", []))
    anchors.update(content.get("appendix_navigation", {}).get("anchors", []))

    def para(value, style="BodyReport", url=None, anchor=None):
        text = unicode_markup(str(value), styles[style].fontName)
        if url and valid_url(url):
            text = (
                '<link href="'
                + escape(url, {'"': "&quot;"})
                + '" color="#000000">'
                + text
                + "</link>"
            )
        else:
            text = re.sub(
                r"\[(\d+)\]",
                lambda m: '<link href="#ref' + m[1] + '" color="#000000">' + m[0] + "</link>"
                if m[1] in citations
                else m[0],
                text,
            )
        text = re.sub(
            r"(?<![\w-])(?:[A-D]-[0-9a-f]{16}(?:-\d+)?|EX-(?:SUMMARY|ATTRIBUTION|VULNERABILITY))(?![\w-])",
            lambda m: '<link href="#' + m[0] + '" color="#000000">' + m[0] + "</link>"
            if m[0] in anchors
            else m[0],
            text,
        )
        if anchor:
            text = '<a name="' + anchor + '"/>' + text
        return Paragraph(text, styles[style])

    flow = []
    for node in content["sections"]:
        kind = node["kind"]
        if kind == "introduction":
            from .introduction_renderers import IntroductionFlowable

            flow.append(IntroductionFlowable(node["model"]))
        elif kind == "text":
            style = {
                "small": "SmallReport",
                "agency": "AgencyReport",
                "notice": "NoticeReport",
                "marking": "NoticeReport",
                "source_label": "SourceReport",
                "closing": "ClosingReport",
            }.get(node["style"], "BodyReport")
            if node.get("section_owner") and node["text"].startswith(
                ("Referenced by:", "Sources:")
            ):
                style = "SourceReport"
            if (
                justified
                and style in ("BodyReport", "SmallReport", "ClosingReport")
                and node["style"] != "signature"
            ):
                style += "Justified"
            value = ("DRAFT - " if draft and node["style"] == "marking" else "") + node["text"]
            paragraph = para(value, style, anchor=node.get("anchor"))
            if node.get("target") in anchors:
                paragraph = Paragraph(
                    '<link href="#'
                    + escape(node["target"])
                    + '" color="#000000">'
                    + escape(value)
                    + "</link>",
                    styles[style],
                )
            flow.append(
                KeepTogether([paragraph])
                if node["style"] in ("list_item", "signature")
                else paragraph
            )
        elif kind == "heading":
            flow.append(
                para(
                    node["text"],
                    "SectionReport" if node["level"] == 1 else "SubsectionReport",
                    anchor=node.get("anchor"),
                )
            )
        elif kind == "metadata":
            flow.append(
                Table(
                    [[para(node["label"], "SmallReport"), para(node["text"])]],
                    colWidths=[0.7 * inch, 6.1 * inch],
                    style=TableStyle(
                        [
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 0),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ]
                    ),
                )
            )
        elif kind == "table":
            rows = [[para(h, "SmallReport") for h in node["headers"]]]
            rows += [
                [para(cell["text"], "SmallReport", cell.get("url")) for cell in row]
                for row in node["rows"]
            ]
            table = Table(
                rows,
                colWidths=[w * inch for w in node["widths"]],
                repeatRows=1,
                hAlign="LEFT",
                splitByRow=1,
                splitInRow=1,
            )
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EDF2")),
                        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D4DCE3")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            flow.append(table)
        elif kind == "exhibit":
            exhibit = next(e for e in content.get("exhibits", []) if e["id"] == node["exhibit_id"])
            if is_page_exhibit(exhibit):
                for index, page in enumerate(exhibit_layout(exhibit, data.get("document_policy"))):
                    if index:
                        flow.append(PageBreak())
                    flow.append(ExhibitFlowable(page, anchors))
                continue
            for page in exhibit_layout(exhibit, data.get("document_policy")):
                flow.append(ExhibitFlowable(page))
                flow.append(Spacer(1, 8))
            for part in sorted(
                {str(ref).split("-")[0] for ref in exhibit.get("appendix_entry_ids", [])}
            ):
                if "appendix-" + part in anchors:
                    flow.append(
                        Paragraph(
                            '<link href="#appendix-'
                            + part
                            + '" color="#000000">Complete supporting detail: Appendix '
                            + part
                            + "</link>",
                            styles["SmallReport"],
                        )
                    )
        elif kind == "page_break":
            flow.append(PageBreak())
        elif kind == "image":
            item = next(e for e in data["evidence"] if e["id"] == node["id"])
            path = evidence_root / item["preview_path"]
            if not path.is_file():
                raise ValueError("Evidence file is missing: " + item["filename"])
            with Image.open(path) as image:
                w, h = image.size
            scale = min(6.8 * inch / w, 5.4 * inch / h)
            flow.append(PDFImage(str(path), width=w * scale, height=h * scale))
        elif kind == "reference":
            flow.append(para(node["text"], "SourceReport", anchor="ref" + str(node["number"])))
            flow.append(para(node["url"], "SmallReport", url=node["url"]))
        elif kind == "link":
            flow.append(
                para(
                    node["text"],
                    "SourceReport" if node.get("keep_with_next") else "SmallReport",
                    url=node["url"],
                )
            )

    def footer(canvas, doc):
        reviewed_intro = any(n["kind"] == "introduction" for n in content["sections"]) or any(
            is_page_exhibit(e) for e in content.get("exhibits", [])
        )
        decorate_pdf(
            canvas,
            doc,
            left_text=review_header(data, draft),
            footer_text=data["domain"],
            font="ReportSans",
            marking_font="ReportSans-Bold" if reviewed_intro else "Helvetica-Bold",
            priority=data.get("intake_score"),
        )

    document = SimpleDocTemplate(
        str(destination),
        pagesize=(8.5 * inch, 11 * inch),
        rightMargin=0.85 * inch,
        leftMargin=0.85 * inch,
        topMargin=0.8 * inch,
        bottomMargin=0.85 * inch,
        title=data["draft"]["subject"],
        author=data["draft"]["sender_name"],
    )
    document.keepTogetherClass = LeadingTextTogether
    document.build(flow, onFirstPage=footer, onLaterPages=footer)


def render_docx(data: ReportSnapshot, destination: Path, evidence_root: Path, draft=False):
    from docx.opc.constants import RELATIONSHIP_TYPE

    content = data.get("composition") or compose(data)
    justified = (
        data.get("document_policy") or data.get("draft", {}).get("document_policy", {})
    ).get("paragraph_alignment") == "justify"
    doc = Document()
    if justified:
        configure_justification(doc)
    section = doc.sections[0]
    section.page_width, section.page_height = Inches(8.5), Inches(11)
    section.top_margin = Inches(0.8)
    section.bottom_margin = Inches(0.85)
    section.left_margin = section.right_margin = Inches(0.85)
    for name in ("Normal", "Title", "Heading 1", "Heading 2"):
        doc.styles[name].font.name = "Arial"
        doc.styles[name].font.color.rgb = RGBColor(0, 0, 0)
    normal = doc.styles["Normal"]
    normal.font.size = Pt(max(10.0, float(content["template"]["font_size"])))
    normal.paragraph_format.space_after = Pt(5)
    normal.paragraph_format.line_spacing = 1.15
    doc.styles["Heading 1"].font.size = Pt(11)
    doc.styles["Heading 2"].font.size = Pt(10)
    doc.styles["Heading 1"].paragraph_format.keep_with_next = True
    doc.styles["Heading 2"].paragraph_format.keep_with_next = True
    citations = {str(c["number"]) for c in content["citations"]}
    anchors = {n["anchor"] for n in content["sections"] if n.get("anchor")}
    anchors.update(e["id"] for e in content.get("exhibits", []))
    anchors.update(content.get("appendix_navigation", {}).get("anchors", []))

    def hyperlink(paragraph, label, url=None, anchor=None):
        link = OxmlElement("w:hyperlink")
        if url and valid_url(url):
            link.set(
                qn("r:id"),
                paragraph.part.relate_to(url, RELATIONSHIP_TYPE.HYPERLINK, is_external=True),
            )
        elif anchor:
            link.set(qn("w:anchor"), anchor)
        run = OxmlElement("w:r")
        pr = OxmlElement("w:rPr")
        color = OxmlElement("w:color")
        color.set(qn("w:val"), "000000")
        pr.append(color)
        run.append(pr)
        t = OxmlElement("w:t")
        t.text = label
        run.append(t)
        link.append(run)
        paragraph._p.append(link)

    bookmark_count = 1000

    def bookmark(paragraph, anchor):
        nonlocal bookmark_count
        bookmark_count += 1
        start = OxmlElement("w:bookmarkStart")
        start.set(qn("w:id"), str(bookmark_count))
        start.set(qn("w:name"), anchor)
        paragraph._p.insert(0, start)
        end = OxmlElement("w:bookmarkEnd")
        end.set(qn("w:id"), str(bookmark_count))
        paragraph._p.append(end)

    def fill(paragraph, text, small=False):
        for chunk in re.split(r"(\[\d+\])", str(text)):
            if re.fullmatch(r"\[\d+\]", chunk) and chunk[1:-1] in citations:
                hyperlink(paragraph, chunk, anchor="ref" + chunk[1:-1])
            else:
                run = paragraph.add_run(chunk)
                if small:
                    run.font.size = Pt(10)
        return paragraph

    for node in content["sections"]:
        kind = node["kind"]
        if kind == "introduction":
            from .introduction_renderers import add_docx_introduction

            add_docx_introduction(doc, node["model"], bookmark=bookmark)
        elif kind == "text":
            paragraph = fill(
                doc.add_paragraph(), node["text"], node["style"] in ("small", "source_label")
            )
            if (
                justified
                and node["style"]
                not in {"signature", "agency", "notice", "marking", "source_label"}
                and not node["text"].startswith(("Referenced by:", "Sources:"))
            ):
                paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            if node.get("anchor"):
                bookmark(paragraph, node["anchor"])
            if node.get("target") in anchors:
                paragraph.clear()
                hyperlink(paragraph, node["text"], anchor=node["target"])
            if node["style"] in ("list_item", "signature"):
                paragraph.paragraph_format.keep_together = True
            if (
                node["style"] in ("source_label", "closing")
                or node.get("section_owner")
                and node["text"].startswith(("Referenced by:", "Sources:"))
            ):
                paragraph.paragraph_format.keep_with_next = True
            if node["style"] in ("agency", "notice", "marking"):
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for run in paragraph.runs:
                    run.bold = True
                    run.font.size = Pt(11.5 if node["style"] == "agency" else 9)
                    run.font.color.rgb = RGBColor(0, 0, 0)
        elif kind == "heading":
            paragraph = doc.add_heading(node["text"], node["level"])
            if node.get("anchor"):
                bookmark(paragraph, node["anchor"])
        elif kind == "metadata":
            paragraph = doc.add_paragraph()
            paragraph.add_run(node["label"] + ": ").bold = True
            fill(paragraph, node["text"])
        elif kind == "table":
            table = doc.add_table(rows=1, cols=len(node["headers"]))
            table.style = "Table Grid"
            table.autofit = False
            borders = OxmlElement("w:tblBorders")
            for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
                edge = OxmlElement("w:" + side)
                edge.set(qn("w:val"), "single")
                edge.set(qn("w:sz"), "4")
                edge.set(qn("w:color"), "D9D9D9")
                borders.append(edge)
            table._tbl.tblPr.append(borders)
            for column, width in zip(table.columns, node["widths"]):
                column.width = Inches(width)
            for cell, label, width in zip(table.rows[0].cells, node["headers"], node["widths"]):
                cell.width = Inches(width)
                fill(cell.paragraphs[0], label, True)
                cell.paragraphs[0].paragraph_format.keep_with_next = True
                for run in cell.paragraphs[0].runs:
                    run.bold = True
                shade = OxmlElement("w:shd")
                shade.set(qn("w:fill"), "E8EDF2")
                cell._tc.get_or_add_tcPr().append(shade)
            repeat = OxmlElement("w:tblHeader")
            table.rows[0]._tr.get_or_add_trPr().append(repeat)
            for values in node["rows"]:
                row = table.add_row()
                # Keep a score and its contributor on the same page.
                if node.get("section_owner") is None or node.get("keep_rows"):
                    row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
                cells = row.cells
                for cell, value, width in zip(cells, values, node["widths"]):
                    cell.width = Inches(width)
                    if value.get("url"):
                        hyperlink(cell.paragraphs[0], value["text"], url=value["url"])
                    elif value.get("target") in anchors:
                        hyperlink(cell.paragraphs[0], value["text"], anchor=value["target"])
                    else:
                        fill(cell.paragraphs[0], value["text"], True)
                    cell.paragraphs[0].paragraph_format.space_after = Pt(4)
        elif kind == "exhibit":
            exhibit = next(e for e in content.get("exhibits", []) if e["id"] == node["exhibit_id"])
            if is_page_exhibit(exhibit):
                for index, rendered in enumerate(prepared_pages(exhibit)):
                    if index:
                        doc.add_page_break()
                    add_docx_page_exhibit(doc, rendered, bookmark=bookmark)
                continue
            paragraph = doc.add_paragraph()
            paragraph.paragraph_format.space_after = Pt(0)
            bookmark(paragraph, exhibit["id"])
            for page in exhibit_layout(exhibit, data.get("document_policy")):
                add_docx_exhibit(doc, page)
            for part in sorted(
                {str(ref).split("-")[0] for ref in exhibit.get("appendix_entry_ids", [])}
            ):
                if "appendix-" + part in anchors:
                    hyperlink(
                        doc.add_paragraph(),
                        "Complete supporting detail: Appendix " + part,
                        anchor="appendix-" + part,
                    )
        elif kind == "page_break":
            doc.add_page_break()
        elif kind == "image":
            item = next(e for e in data["evidence"] if e["id"] == node["id"])
            path = evidence_root / item["preview_path"]
            with Image.open(path) as image:
                w, h = image.size
            scale = min(6.8 / w, 5.4 / h)
            doc.add_picture(str(path), width=Inches(w * scale), height=Inches(h * scale))
        elif kind == "reference":
            paragraph = doc.add_paragraph()
            paragraph.paragraph_format.keep_with_next = True
            start = OxmlElement("w:bookmarkStart")
            start.set(qn("w:id"), str(node["number"]))
            start.set(qn("w:name"), "ref" + str(node["number"]))
            paragraph._p.append(start)
            fill(paragraph, node["text"], True)
            end = OxmlElement("w:bookmarkEnd")
            end.set(qn("w:id"), str(node["number"]))
            paragraph._p.append(end)
            if valid_url(node["url"]):
                hyperlink(doc.add_paragraph(), node["url"], url=node["url"])
            else:
                fill(doc.add_paragraph(), node["url"], True)
        elif kind == "link":
            paragraph = doc.add_paragraph()
            paragraph.paragraph_format.keep_with_next = bool(node.get("keep_with_next"))
            hyperlink(paragraph, node["text"], url=node["url"])
    decorate_docx(section, data["domain"], priority=data.get("intake_score"))
    if draft or data.get("demo"):
        from docx.enum.text import WD_TAB_ALIGNMENT

        header = section.header.paragraphs[0]
        header.style = doc.styles["Normal"]
        header.alignment = WD_ALIGN_PARAGRAPH.LEFT
        header.paragraph_format.tab_stops.add_tab_stop(Inches(6.8), WD_TAB_ALIGNMENT.RIGHT)
        label = header.add_run(review_header(data, draft) + "\t")
        label.font.name = "Arial"
        label.font.size = Pt(7)
        label.font.color.rgb = RGBColor(0, 0, 0)
        header._p.insert(1, label._r)
    set_document_properties(
        doc,
        title=data["draft"]["subject"],
        author=data["draft"]["sender_name"],
        created_at=data.get("created_at"),
        revision=data.get("report_revision", 1),
    )
    prepare_docx(doc)
    doc.save(destination)
