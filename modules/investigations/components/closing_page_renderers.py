"""Editable Word closing text and real hyperlinks from frozen page geometry."""

from docx.shared import Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE

from .closing_page_model import safe_resource_url
from modules.ui.components.document_fonts import embed_report_fonts
from modules.ui.components.word_justification import measured_paragraph


def add_docx_closing_page(doc, rendered, bookmark=None):
    blocks = sorted(
        (b for b in rendered.page.segments if b["kind"] == "closing_block"), key=lambda b: b["top"]
    )
    previous_bottom = 0
    for index, block in enumerate(blocks):
        paragraph = doc.add_paragraph()
        fmt = paragraph.paragraph_format
        fmt.left_indent, fmt.right_indent = Pt(6 + block.get("indent", 0)), Pt(6)
        fmt.space_before = Pt(max(0, block["top"] - previous_bottom) + (6 if index == 0 else 0))
        fmt.space_after = Pt(0)
        fmt.line_spacing = Pt(block["leading"])
        fmt.keep_together = True
        fmt.keep_with_next = bool(block.get("keep_next"))
        if bookmark and index == 0:
            bookmark(paragraph, rendered.page.id)
        runs = (
            measured_paragraph(paragraph, block["lines"], block.get("word_spaces", []))
            if block.get("justified")
            else [paragraph.add_run("\n".join(block["lines"]))]
        )
        for run in runs:
            if run.font.name != "Companion Noto Sans SC":
                run.font.name = "DejaVu Sans"
            run.font.size = Pt(block["size"])
            run.font.color.rgb = RGBColor(0, 0, 0)
            run.bold = block.get("bold", False)
        if block.get("url") and safe_resource_url(block["url"]):
            hyperlink = OxmlElement("w:hyperlink")
            hyperlink.set(
                qn("r:id"),
                paragraph.part.relate_to(
                    block["url"], RELATIONSHIP_TYPE.HYPERLINK, is_external=True
                ),
            )
            for run in runs:
                run.underline = True
                hyperlink.append(run._r)
            paragraph._p.append(hyperlink)
        if block["id"] == "appendix-note":
            borders, top = OxmlElement("w:pBdr"), OxmlElement("w:top")
            for key, value in {"val": "single", "sz": "4", "space": "5", "color": "D4DCE3"}.items():
                top.set(qn("w:" + key), value)
            borders.append(top)
            paragraph._p.get_or_add_pPr().append(borders)
        previous_bottom = block["top"] + block["height"]
    embed_report_fonts(doc)
