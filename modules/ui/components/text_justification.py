"""Measured inter-word spacing for versioned, justified report paragraphs.

Text and line breaks remain unchanged. The last line of each source paragraph,
headings, identifiers and lines without an inter-word gap retain natural width.
"""

from .unicode_fonts import width as text_width


def enabled(model):
    return model.get("paragraph_alignment") == "justify"


def prose_value(value):
    """Keep obvious structured/code captures as literal records, not prose."""
    text = str(value).lstrip()
    return not text.startswith(("{", "[{", '["', "<", "-----BEGIN", "HTTP/", "GET /", "POST /"))


def wrapped_paragraphs(value, width, size=10, bold=False):
    """Return unchanged wrapped lines and their source-paragraph ending flags."""
    from .vector_layout import _wrap, _value

    lines, endings = [], []
    for paragraph in _value(value).split("\n"):
        rows = _wrap(paragraph, width, size, bold)
        lines.extend(rows)
        endings.extend([False] * (len(rows) - 1) + [True])
    return lines, endings


def word_space(value, width, size, *, bold=False, final=False, justify=True):
    if not justify or final or bold or not value.strip():
        return 0.0
    gaps = value.count(" ")
    if not gaps or not value.strip().count(" "):
        return 0.0
    natural = text_width(value, "ExhibitSans-Bold" if bold else "ExhibitSans", size)
    return max(0.0, (width - natural) / gaps)


def mark_line(segments, x, baseline, value, size, width, *, final=False, justify=True, bold=False):
    extra = word_space(value, width, size, bold=bold, final=final, justify=justify)
    if extra > 1e-8:
        segments.append(
            {
                "kind": "justified_line",
                "left": x,
                "baseline": baseline,
                "width": width,
                "word_space": extra,
            }
        )
    return extra
