"""Measured Attribution pages from saved case evidence, with no live lookups.

Every paragraph and evidence field is laid out once. Ordinary association cards
stay together; oversized values continue at the same readable type size.
"""

from dataclasses import dataclass, field
from math import floor
import re

from .vector_layout import ExhibitPage, WIDTH, _wrap
from .text_justification import enabled, mark_line, wrapped_paragraphs

BLACK = "#000000"
BLUE = "#002D61"
RED = "#A52A2A"
PALE_BLUE = "#EEF3F8"
PALE_RED = "#FAF0EE"
LINE = "#D4DCE3"
PAGE_WIDTH = WIDTH - 12
PAGE_HEIGHT = 650
TOP = 50
BOTTOM = 578


def markers(values):
    return " ".join(f"[{n}]" for n in dict.fromkeys(n for n in values if n))


@dataclass
class Row:
    height: float
    elements: list = field(default_factory=list)
    keep_next: bool = False
    spacing: list = field(default_factory=list)


def _text(x, top, value, size=10, bold=False):
    return ("text", x, top + size, str(value), size, bold, BLACK)


def card_rows(
    item, width=PAGE_WIDTH, *, justify=False, include_appendix=True, compact_appendix=False
):
    """Return small independent rows, including breakable evidence columns."""
    rows = []
    inner = width - 24
    pale = PALE_BLUE if item.get("supported") and not item.get("review_required") else PALE_RED

    def paragraph(value, *, bold=False, size=10, after=0, label=None, prose=False):
        if value in (None, ""):
            return
        if label:
            for line in _wrap(label, inner, 10, True):
                rows.append(Row(13, [_text(12, 0, line, bold=True)], True))
        lines, endings = wrapped_paragraphs(value, inner, size, bold)
        for index, line in enumerate(lines):
            rows.append(
                Row(
                    size + 3 + (after if index == len(lines) - 1 else 0),
                    [_text(12, 0, line, size, bold)],
                )
            )
            mark_line(
                rows[-1].spacing,
                12,
                size,
                line,
                size,
                inner,
                final=endings[index],
                justify=justify and prose,
                bold=bold,
            )

    paragraph(item.get("label") or "Domain not recorded", bold=True, size=12, after=4)
    paragraph(item.get("method_label") or "Attribution method not recorded", bold=True, after=8)

    # All text remains black. The rail and pale evidence panels carry status
    # color, accompanied by an explicit text label on every card segment.
    column_width = (inner - 28) / 2
    positions = (12, 12 + column_width + 28)
    labels = [
        _wrap("Reported IP", column_width - 12, 10, True),
        _wrap(
            item.get("corroborated_label") or "Corroborating evidence", column_width - 12, 10, True
        ),
    ]
    for index in range(max(map(len, labels))):
        elements = []
        for x, lines in zip(positions, labels):
            elements.append(("rect", x, 0, column_width, 15, pale))
            if index < len(lines):
                elements.append(_text(x + 6, 2, lines[index], bold=True))
        rows.append(Row(15, elements, True))
    values = [
        _wrap(item.get("reported_ip") or "Not recorded", column_width - 12, 11, True),
        _wrap(item.get("corroborated_value") or "Not recorded", column_width - 12, 11, True),
    ]
    for index in range(max(map(len, values))):
        elements = []
        for x, lines in zip(positions, values):
            elements.append(("rect", x, 0, column_width, 16, pale))
            if index < len(lines):
                elements.append(_text(x + 6, 1, lines[index], 11, True))
        if index == 0:
            elements.append(_text(12 + column_width + 7, 1, "→", 12, True))
        rows.append(Row(16, elements))
    rows.append(Row(8))
    paragraph(
        item.get("explanation") or "Supporting relationship was not recorded.", after=7, prose=True
    )
    if item.get("matched_value") not in (None, ""):
        paragraph(
            str(item["matched_value"]),
            label="Matched record value",
            after=6,
        )
    paragraph(
        str(item.get("source_name") or "Source not recorded")
        + " "
        + markers(item.get("citations", [])),
        label="Source",
    )
    paragraph(item.get("source_url") or "Source address not recorded", after=7)
    paragraph("Validated: " + str(item.get("validated_at") or "Not recorded"))
    paragraph("Validated by: " + str(item.get("validated_by") or "Not recorded"))
    paragraph("Retrieved: " + str(item.get("retrieved_at") or "Not recorded"), after=6)
    if item.get("timestamp_note"):
        paragraph(item["timestamp_note"], after=6, prose=True)
    if item.get("review_note"):
        paragraph(item["review_note"], label="Recorded analyst note", after=6, prose=True)
    supporting = item.get("supporting_attribution_count", 0)
    count = item.get("reported_asset_count", 0)
    paragraph(
        f"{supporting} supporting "
        + ("association" if supporting == 1 else "associations")
        + f" / {count} reported IP "
        + ("address" if count == 1 else "addresses"),
        bold=True,
    )
    paragraph(
        (
            "Scope: this domain group. Supporting records: Appendices A and B."
            if compact_appendix
            else "Scope: this domain group. Full observations and supporting records: Appendices A and B."
        )
        if include_appendix
        else "Scope: this domain group. Full observations and supporting records are available upon request.",
        after=4,
        prose=True,
    )
    return rows


def layout_attribution(model):
    width, height = PAGE_WIDTH, PAGE_HEIGHT
    pages = []
    elements, segments = [], []
    citations = set()
    y = TOP

    def text(x, top, value, size=10, bold=False):
        elements.append(_text(x, top, value, size, bold))

    def finish():
        if not segments:
            return
        page = ExhibitPage(
            model["id"], len(pages) + 1, width, height, list(elements), "", list(segments)
        )
        page.segments.append({"kind": "page_citations", "values": sorted(citations)})
        pages.append(page)

    def next_page():
        nonlocal elements, segments, citations, y
        finish()
        elements, segments, citations, y = [], [], set(), TOP

    def prose(value, *, kind, size=11, leading=15.5, bold=False):
        nonlocal y
        if not value:
            return
        for paragraph_index, paragraph in enumerate(re.split(r"\n\s*\n", str(value))):
            if not paragraph:
                continue
            lines = _wrap(paragraph, width, size, bold)
            if (
                len(lines) * leading <= BOTTOM - TOP
                and y + len(lines) * leading > BOTTOM
                and segments
            ):
                next_page()
            offset = 0
            while offset < len(lines):
                room = floor((BOTTOM - y) / leading)
                if room < min(3, len(lines) - offset):
                    next_page()
                    continue
                take = min(room, len(lines) - offset)
                if 0 < len(lines) - offset - take < 3 and take > 3:
                    take -= 3 - (len(lines) - offset - take)
                top = y
                for line_index, line in enumerate(lines[offset : offset + take], offset):
                    text(0, y, line, size, bold)
                    mark_line(
                        segments,
                        0,
                        y + size,
                        line,
                        size,
                        width,
                        final=line_index == len(lines) - 1,
                        bold=bold,
                        justify=enabled(model) and kind not in {"business", "address"},
                    )
                    y += leading
                segments.append(
                    {
                        "kind": kind,
                        "paragraph": paragraph_index,
                        "first_line": offset,
                        "line_count": take,
                        "top": top,
                        "height": y - top,
                    }
                )
                offset += take
                if offset < len(lines):
                    next_page()
            y += 5

    prose(model.get("narrative"), kind="narrative")
    if model.get("company"):
        prose("Business: " + str(model["company"]), kind="business", size=10, leading=13, bold=True)
    if model.get("address"):
        prose(model["address"], kind="address", size=10, leading=13)
    if model.get("business_registration_note"):
        prose(
            model["business_registration_note"], kind="business_registration", size=10, leading=13
        )

    items = model.get("items") or []
    for number, item in enumerate(items, 1):
        rows = card_rows(
            item,
            width,
            justify=enabled(model),
            include_appendix=model.get("include_appendix", True),
            compact_appendix=model.get("compact_appendix", False),
        )
        header_height = 22
        total = header_height + sum(r.height for r in rows)
        if total <= BOTTOM - TOP and y + total > BOTTOM and segments:
            next_page()
        offset = 0
        part = 1
        while offset < len(rows):
            if y + header_height + rows[offset].height + 13 > BOTTOM:
                next_page()
            top = y
            supported = item.get("supported") is True and not item.get("review_required")
            color = BLUE if supported else RED
            heading = f"Association {number}" + (" — continued" if part > 1 else "")
            status = "Association supported" if supported else "Needs review"
            text(12, y, heading, 10, True)
            text(width - 150, y, status, 10, True)
            y += header_height
            start = offset
            while offset < len(rows):
                row = rows[offset]
                needed = row.height
                if row.keep_next and offset + 1 < len(rows):
                    needed += rows[offset + 1].height
                if y + needed > BOTTOM:
                    break
                for element in row.elements:
                    if element[0] == "text":
                        _, x, baseline, value, size, bold, black = element
                        elements.append(("text", x, y + baseline, value, size, bold, black))
                    else:
                        _, x, top_offset, w, h, fill = element
                        elements.append(("rect", x, y + top_offset, w, h, fill))
                segments.extend(
                    {**spacing, "baseline": spacing["baseline"] + y} for spacing in row.spacing
                )
                y += row.height
                offset += 1
            if offset == start:
                raise ValueError(
                    "An attribution row exceeds a full page at the approved type size."
                )
            citations.update(n for n in item.get("citations", []) if n)
            elements.append(("rect", 0, top + 1, 2.5, y - top, color))
            elements.append(("rect", 12, y + 3, width - 12, 0.5, LINE))
            segments.append(
                {
                    "kind": "association",
                    "id": number,
                    "part": part,
                    "first_row": start,
                    "row_count": offset - start,
                    "top": top,
                    "height": y - top,
                    "complete": start == 0 and offset == len(rows),
                }
            )
            y += 14
            if offset < len(rows):
                part += 1
                next_page()
    if not items:
        prose(
            "No supporting association is recorded for this notification. Attribution review is required.",
            kind="empty_attribution",
            size=10,
            leading=13,
        )
    finish()
    for page in pages:
        header = [
            _text(0, 1, "Attribution" + (" — continued" if page.page > 1 else ""), 16, True),
            _text(0, 27, f"Attribution Exhibit · {page.page} of {len(pages)}"),
        ]
        refs = next(s["values"] for s in page.segments if s["kind"] == "page_citations")
        footer = (
            "Sources: " + markers(refs) + " · Full records and references: Appendix B."
            if refs
            else "Full source records and attribution history: Appendix B."
        )
        if model.get("compact_appendix"):
            footer = footer.replace(
                "Full records and references", "Supporting records and references"
            ).replace(
                "Full source records and attribution history",
                "Supporting attribution records and references",
            )
        if model.get("include_appendix", True) is False:
            footer = (
                "Sources: " + markers(refs) + " · See References."
                if refs
                else "Full source records and attribution history are available upon request."
            )
        lines = _wrap(footer, width, 10)
        if len(lines) > 2:
            lines = _wrap(
                f"{len(refs)} cited sources on this page; see References."
                if model.get("include_appendix", True) is False
                else f"{len(refs)} cited sources on this page; full references: Appendix B.",
                width,
                10,
            )
        caveat_start = len(lines)
        lines += _wrap(
            "A supporting association does not establish ownership, vulnerability, or compromise.",
            width,
            10,
        )
        decorations = [("rect", 0, 590, width, 0.5, LINE)]
        for index, line in enumerate(lines):
            caveat = index >= caveat_start
            mark_line(
                page.segments,
                0,
                605 + index * 13,
                line,
                10,
                width,
                final=index == (len(lines) - 1 if caveat else caveat_start - 1),
                justify=enabled(model)
                and (caveat or (not refs and model.get("include_appendix", True) is False)),
            )
            decorations.append(_text(0, 595 + index * 13, line))
        if 605 + (len(lines) - 1) * 13 > height - 3:
            raise ValueError("Attribution source footer exceeds its page budget.")
        page.elements = header + page.elements + decorations
        page.alt_text = "\n".join(e[3] for e in page.elements if e[0] == "text")
    return pages
