"""Native Word tables and text from the appendix's frozen page geometry."""

from docx.shared import Pt, RGBColor
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT, WD_ROW_HEIGHT_RULE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE

from .closing_page_model import safe_resource_url
from modules.ui.components.document_fonts import embed_report_fonts
from modules.ui.components.unicode_fonts import font_runs, FALLBACK
from modules.ui.components.word_justification import measured_paragraph


def _fill(paragraph, text, size, bold=False, url=None, target=None):
    link = None
    if url and safe_resource_url(url) or target:
        link = OxmlElement("w:hyperlink")
        if target:
            link.set(qn("w:anchor"), target)
        else:
            link.set(
                qn("r:id"),
                paragraph.part.relate_to(url, RELATIONSHIP_TYPE.HYPERLINK, is_external=True),
            )
    for font, value in font_runs(text, "ExhibitSans-Bold" if bold else "ExhibitSans"):
        run = paragraph.add_run(value)
        run.font.name = "Companion Noto Sans SC" if font == FALLBACK else "DejaVu Sans"
        run.font.size, run.bold = Pt(size), bold
        run.font.color.rgb = RGBColor(0, 0, 0)
        if link is not None:
            run.underline = True
            link.append(run._r)
    if link is not None:
        paragraph._p.append(link)


def _paragraph(doc, block, before):
    paragraph = doc.add_paragraph()
    fmt = paragraph.paragraph_format
    fmt.left_indent, fmt.right_indent = Pt(6), Pt(6)
    fmt.space_before, fmt.space_after = Pt(before), Pt(0)
    fmt.line_spacing = Pt(block["leading"])
    fmt.keep_together = True
    fmt.keep_with_next = block.get("role") in {"section", "record"}
    if block.get("role") in {"section", "record"}:
        level = OxmlElement("w:outlineLvl")
        level.set(qn("w:val"), "0" if block["role"] == "section" else "1")
        paragraph._p.get_or_add_pPr().append(level)
    if block.get("citations"):
        _fill(paragraph, "Sources: ", block["size"])
        for number in block["citations"]:
            _fill(paragraph, f"[{number}]", block["size"], target="ref" + str(number))
            _fill(paragraph, " ", block["size"])
    elif block.get("justified"):
        for run in measured_paragraph(paragraph, block["lines"], block.get("word_spaces", [])):
            if run.font.name != "Companion Noto Sans SC":
                run.font.name = "DejaVu Sans"
            run.font.size, run.bold = Pt(block["size"]), block.get("bold", False)
            run.font.color.rgb = RGBColor(0, 0, 0)
    else:
        _fill(
            paragraph,
            "\n".join(block["lines"]),
            block["size"],
            block.get("bold", False),
            url=block.get("url"),
            target=block.get("target"),
        )
    return paragraph


def _table(doc, block):
    table = doc.add_table(rows=1, cols=2)
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    widths = [block["label_width"], block["width"] - block["label_width"]]
    for column, width in zip(table.columns, widths):
        column.width = Pt(width)
    properties = table._tbl.tblPr
    indent = OxmlElement("w:tblInd")
    indent.set(qn("w:w"), "120")
    indent.set(qn("w:type"), "dxa")
    properties.append(indent)
    margins = OxmlElement("w:tblCellMar")
    for side in ("top", "bottom", "left", "right"):
        margin = OxmlElement("w:" + side)
        # Row height already includes vertical breathing room; vertical center
        # alignment supplies it without adding renderer-specific cell padding.
        # Word reserves space for the cell border in addition to its margins.
        # Leave a one-point tolerance so a premeasured line at the native
        # column limit does not wrap again and get clipped by the frozen row.
        padding = 0 if side in {"top", "bottom"} else max(0, block["padding"] - 1)
        margin.set(qn("w:w"), str(int(padding * 20)))
        margin.set(qn("w:type"), "dxa")
        margins.append(margin)
    properties.append(margins)
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        border = OxmlElement("w:" + side)
        for name, value in {"val": "single", "sz": "4", "color": "D4DCE3"}.items():
            border.set(qn("w:" + name), value)
        borders.append(border)
    properties.append(borders)
    rows = [{"labels": ["Field"], "values": ["Recorded value"], "height": 24, "url": None}] + block[
        "rows"
    ]
    for index, record in enumerate(rows):
        row = table.rows[0] if index == 0 else table.add_row()
        # The saved geometry includes cell padding. An 'at least' height is
        # interpreted differently by Word/LibreOffice and grows every row.
        row.height_rule, row.height = WD_ROW_HEIGHT_RULE.EXACTLY, Pt(record["height"])
        row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
        if index == 0:
            row._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))
        for column, (cell, lines, width) in enumerate(
            zip(row.cells, [record["labels"], record["values"]], widths)
        ):
            cell.width = Pt(width)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            paragraph = cell.paragraphs[0]
            fmt = paragraph.paragraph_format
            fmt.space_before = fmt.space_after = Pt(0)
            fmt.line_spacing = Pt(block["leading"])
            if index == 0:
                shade = OxmlElement("w:shd")
                shade.set(qn("w:fill"), "E8EDF2")
                cell._tc.get_or_add_tcPr().append(shade)
            _fill(
                paragraph,
                "\n".join(lines),
                block["size"],
                index == 0,
                url=record.get("url") if column == 1 else None,
            )
    return table.rows[0].cells[0].paragraphs[0]


def add_docx_appendix_page(doc, rendered, *, bookmark=None):
    page = rendered.page
    blocks = sorted(
        (b for b in page.segments if b["kind"] in {"appendix_text", "appendix_table"}),
        key=lambda b: b["top"],
    )
    attached = {}
    for segment in page.segments:
        if segment["kind"] == "anchor":
            index = min(range(len(blocks)), key=lambda i: abs(blocks[i]["top"] - segment["top"]))
            attached.setdefault(index, []).append(segment["name"])
    bottom = 0
    for index, block in enumerate(blocks):
        before = max(0, block["top"] - bottom) + (6 if index == 0 else 0)
        if block["kind"] == "appendix_table":
            if before:
                spacer = doc.add_paragraph()
                fmt = spacer.paragraph_format
                fmt.space_before = fmt.space_after = Pt(0)
                fmt.line_spacing = Pt(before)
                spacer.add_run().font.size = Pt(1)
            paragraph = _table(doc, block)
        else:
            paragraph = _paragraph(doc, block, before)
        if bookmark:
            if index == 0 and page.page == 1:
                bookmark(paragraph, page.id)
            for anchor in attached.get(index, []):
                bookmark(paragraph, anchor)
        bottom = block["top"] + block["height"]
    embed_report_fonts(
        doc,
        include_cjk=any(
            font == FALLBACK
            for element in page.elements
            if element[0] == "text"
            for font, _ in font_runs(element[3], "ExhibitSans")
        ),
    )
