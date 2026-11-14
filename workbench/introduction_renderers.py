"""PDF and editable DOCX output from the same introduction layout."""

from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import Flowable
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor
from .exhibit_rendering import ExhibitFlowable, add_docx_exhibit
from .introduction_layout import layout_introduction
from .unicode_fonts import font_runs
from .document_fonts import embed_report_fonts
from .word_justification import measured_paragraph


class IntroductionFlowable(Flowable):
    """One measured page, with selectable body text and vector exhibit text."""

    def __init__(self, model):
        super().__init__()
        self.plan = layout_introduction(model)
        self.width, self.height = self.plan.width, self.plan.height

    def draw(self):
        canvas = self.canv
        canvas.saveState()
        y = 0
        for block in self.plan.blocks:
            font = (
                "IntroSerif" if block.serif else "ExhibitSans-Bold" if block.bold else "ExhibitSans"
            )
            canvas.setFillColor(HexColor(block.color))
            if block.label:
                canvas.setFont("ExhibitSans-Bold", block.size)
                canvas.drawString(0, self.height - y - block.size, block.label)
            for index, line in enumerate(block.lines):
                extra = block.word_spaces[index] if block.justified else 0
                selected = font_runs(line, font)
                line_width = sum(
                    pdfmetrics.stringWidth(value, face, block.size) for face, value in selected
                )
                x = (self.width - line_width) / 2 if block.centered else block.indent
                baseline = self.height - y - index * block.leading - block.size
                start = x
                for face, value in selected:
                    canvas.setFont(face, block.size)
                    if extra:
                        canvas.drawString(x, baseline, value, wordSpace=extra)
                    else:
                        canvas.drawString(x, baseline, value)
                    x += pdfmetrics.stringWidth(value, face, block.size) + extra * value.count(" ")
                if block.underline:
                    canvas.setStrokeColor(HexColor(block.color))
                    canvas.setLineWidth(0.6)
                    canvas.line(start, baseline - 1.5, x, baseline - 1.5)
            y += block.height
        ExhibitFlowable(self.plan.summary).drawOn(canvas, 0, 0)
        canvas.restoreState()


def add_docx_introduction(doc, model, *, bookmark=None):
    """Keep paragraphs editable; only the Summary Exhibit uses SVG + PNG fallback."""
    plan = layout_introduction(model)
    for index, block in enumerate(plan.blocks):
        paragraph = doc.add_paragraph()
        fmt = paragraph.paragraph_format
        fmt.left_indent = Pt(6 + block.indent)
        fmt.right_indent = Pt(6)
        fmt.space_before = Pt(6 if index == 0 else 0)
        fmt.space_after = Pt(block.after)
        fmt.line_spacing = Pt(block.leading)
        fmt.keep_together = True
        fmt.keep_with_next = True
        if block.centered:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if block.label:
            fmt.first_line_indent = Pt(-block.indent)
            fmt.tab_stops.add_tab_stop(Pt(block.indent + 6))
            run = paragraph.add_run(block.label + "\t")
            run.bold = True
        if block.justified:
            content_runs = measured_paragraph(paragraph, block.lines, block.word_spaces)
        else:
            content_runs = [paragraph.add_run("\n".join(block.lines))]
        for run in content_runs:
            run.bold = block.bold
            run.underline = block.underline
        for run in paragraph.runs:
            if run.font.name != "Companion Noto Sans SC":
                run.font.name = "DejaVu Serif" if block.serif else "DejaVu Sans"
            run.font.size = Pt(block.size)
            run.font.color.rgb = RGBColor.from_string(block.color.removeprefix("#"))
    picture = add_docx_exhibit(doc, plan.summary, office_font_names=True)
    for side in ("distL", "distR", "distT", "distB"):
        picture._inline.set(side, "0")
    paragraph = doc.paragraphs[-1]
    if bookmark is not None:
        bookmark(paragraph, plan.summary.id)
    paragraph.paragraph_format.left_indent = Pt(6)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.line_spacing = 1
    paragraph.paragraph_format.keep_together = True
    for run in paragraph.runs:
        run.font.size = Pt(1)
    embed_report_fonts(doc)
    return plan
