"""Shared vector-page records, bundled font metrics and lossless text wrapping."""

from dataclasses import dataclass, field
from pathlib import Path
import json
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from .unicode_fonts import width as text_width
from .report_operations import check_deadline

WIDTH = 489.6
FONT_ROOT = Path(__file__).resolve().parent.parent / "fonts"
for name, filename in [
    ("ExhibitSans", "DejaVuSans.ttf"),
    ("ExhibitSans-Bold", "DejaVuSans-Bold.ttf"),
]:
    if name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(name, str(FONT_ROOT / filename)))


def _value(value):
    if value is None:
        return "Not supplied"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _wrap(value, width, size=10, bold=False):
    check_deadline()
    if width <= 0 or size <= 0:
        raise ValueError("Report text needs a positive page width and font size")
    font = "ExhibitSans-Bold" if bold else "ExhibitSans"
    result = []
    for paragraph in _value(value).split("\n"):
        current = ""
        for word in paragraph.split(" "):
            candidate = current + (" " if current else "") + word
            if text_width(candidate, font, size) <= width:
                current = candidate
                continue
            if current:
                result.append(current)
                current = ""
            # Search a bounded prefix instead of repeatedly measuring the
            # complete remaining value. Raw scan fields can contain very long
            # unbroken tokens (certificates, URLs, encoded response content).
            # Whole-tail measurements made those inputs take quadratic time.
            offset = 0
            while offset < len(word):
                check_deadline()
                remaining = len(word) - offset
                low, high = 0, min(64, remaining)
                while text_width(word[offset : offset + high], font, size) <= width:
                    low = high
                    if high == remaining:
                        break
                    high = min(high * 2, remaining)
                if low == remaining:
                    break
                while low + 1 < high:
                    middle = (low + high) // 2
                    if text_width(word[offset : offset + middle], font, size) <= width:
                        low = middle
                    else:
                        high = middle
                cut = max(1, low)
                result.append(word[offset : offset + cut])
                offset += cut
            current = word[offset:]
        result.append(current)
    return result or [""]


@dataclass
class ExhibitPage:
    id: str
    page: int
    width: float
    height: float
    elements: list
    alt_text: str
    segments: list = field(default_factory=list)
