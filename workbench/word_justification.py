"""Word justification from the same measured word gaps as vector report pages."""

import re
from math import floor

from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from .unicode_fonts import font_runs, FALLBACK


def configure_justification(doc):
    """Do not stretch a source paragraph's explicit final soft-return line."""
    settings = doc.settings.element
    compat = settings.find(qn("w:compat"))
    if compat is None:
        compat = OxmlElement("w:compat")
        settings.append(compat)
    option = compat.find(qn("w:doNotExpandShiftReturn"))
    if option is None:
        option = OxmlElement("w:doNotExpandShiftReturn")
        compat.append(option)
    option.set(qn("w:val"), "1")


def measured_paragraph(paragraph, lines, word_spaces):
    """Retain paragraph-final lines and page continuations without adding text.

    These layouts already use measured soft line breaks. Explicit space-run
    tracking avoids Word stretching a source paragraph's final line at a soft
    break, and keeps continued fragments justified at a physical page break.
    Tracking is distributed in twentieths of a point, to within one twip of
    the vector line's total width. The source characters remain unchanged.
    """
    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    configure_justification(paragraph.part.document)
    runs = []

    def add_text(value):
        added = []
        for face, text in font_runs(value, "ExhibitSans"):
            run = paragraph.add_run(text)
            if face == FALLBACK:
                run.font.name = "Companion Noto Sans SC"
            runs.append(run)
            added.append(run)
        return added

    for index, line in enumerate(lines):
        if index:
            add_text("\n")
        extra = word_spaces[index] if index < len(word_spaces) else 0
        spaces = str(line).count(" ")
        if extra > 0 and spaces:
            # Never exceed the measured frame through twentieth-point rounding.
            total = floor(extra * spaces * 20)
            gap, remainder = divmod(total, spaces)
            ordinal = 0
            for token in re.split(r"( )", str(line)):
                if not token:
                    continue
                added = add_text(token)
                if token == " ":
                    spacing = OxmlElement("w:spacing")
                    spacing.set(qn("w:val"), str(gap + (ordinal < remainder)))
                    added[0]._r.get_or_add_rPr().append(spacing)
                    ordinal += 1
        else:
            add_text(str(line))
    return runs
