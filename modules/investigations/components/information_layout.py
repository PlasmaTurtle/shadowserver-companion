"""Paginate approved advisory content without rewriting or shrinking body text."""

from dataclasses import dataclass, field

from modules.ui.components.vector_layout import ExhibitPage, WIDTH, _wrap
from modules.ui.components.unicode_fonts import width as text_width
from modules.ui.components.text_justification import enabled, mark_line, wrapped_paragraphs

BLACK = "#000000"
RED = "#A52A2A"
LINE = "#D4DCE3"
PALE = "#F1F4F7"
PAGE_WIDTH, PAGE_HEIGHT = WIDTH - 12, 650
TOP, BOTTOM = 50, 578
BODY_SIZE, LEADING = 11, 15


def markers(values):
    return " ".join(f"[{n}]" for n in dict.fromkeys(values) if n)


@dataclass
class Row:
    height: float
    elements: list
    paragraph: int | None = None
    spacing: list = field(default_factory=list)


def _text(x, top, text, size=BODY_SIZE, bold=False):
    return ("text", x, top + size, str(text), size, bold, BLACK)


def rows_for(block, *, justify=False):
    """Body rows are small enough to flow; headings are kept by the paginator."""
    kind = block["kind"]
    inset = 28 if kind == "action" else 12 if kind == "risk" else 0
    rows = []
    if kind == "statistics_table":
        widths = (228, 83, PAGE_WIDTH - 311)
        for index, values in enumerate([block["headers"], *block["items"]]):
            header = index == 0
            height, size = (24, 10) if header else (26, 11)
            elements, x = [], 0
            for col, (value, width) in enumerate(zip(values, widths, strict=True)):
                elements.append(("rect", x, 0, width, height, PALE if header else "#FFFFFF"))
                elements.append(("rect", x, 0, 0.5, height, LINE))
                elements.append(("rect", x, 0, width, 0.5, LINE))
                measured = text_width(value, "ExhibitSans-Bold" if header else "ExhibitSans", size)
                tx = x + 8 if col == 0 else x + width - 8 - measured
                elements.append(_text(tx, (height - size) / 2 - 1, value, size, header))
                x += width
            elements.append(("rect", PAGE_WIDTH - 0.5, 0, 0.5, height, LINE))
            elements.append(("rect", 0, height - 0.5, PAGE_WIDTH, 0.5, LINE))
            rows.append(Row(height, elements))
        rows.append(
            Row(
                22,
                [
                    _text(
                        0,
                        6,
                        "Source: " + block["source_label"] + " " + markers(block["citations"]),
                        10,
                    )
                ],
            )
        )
        return rows
    if kind == "statistics":
        # Equal-width columns compare the two crime categories. Exact approved
        # wording, including the ransomware-loss limitation, remains intact.
        gap = 18
        width = (PAGE_WIDTH - gap) / 2
        columns = [_wrap(value, width - 16, 10) for value in block["items"]]
        for index in range(max(map(len, columns))):
            elements = []
            for col, lines in enumerate(columns):
                if index < len(lines):
                    elements.append(_text(col * (width + gap) + 8, 0, lines[index], 10))
            rows.append(Row(13, elements))
        rows.append(
            Row(
                19,
                [
                    _text(
                        0,
                        5,
                        "Source: " + block["source_label"] + " " + markers(block["citations"]),
                        10,
                    )
                ],
            )
        )
        return rows
    body = block.get("body", "")
    inline = block.get("citation_style") == "inline"
    if inline and block.get("citations"):
        body += " " + markers(block["citations"])
    for index, paragraph in enumerate(body.splitlines()):
        if not paragraph.strip():
            if rows:
                rows[-1].height += 6
            continue
        lines, endings = wrapped_paragraphs(paragraph, PAGE_WIDTH - inset, BODY_SIZE)
        for line, final in zip(lines, endings, strict=True):
            rows.append(Row(LEADING, [_text(inset, 0, line)], paragraph=index))
            mark_line(
                rows[-1].spacing,
                inset,
                BODY_SIZE,
                line,
                BODY_SIZE,
                PAGE_WIDTH - inset,
                final=final,
                justify=justify,
            )
    if block.get("citations") and not inline:
        rows.append(Row(16, [_text(inset, 3, "Sources: " + markers(block["citations"]), 10)]))
    return rows


def layout_information(model):
    if model.get("layout_revision") == "information-2026-11-10-v1":
        from .information_pages_layout import layout_information_pages

        pages = layout_information_pages(model)
        if model.get("blocks"):
            extra = {**model, "layout_revision": "information-2026-11-07-review-2"}
            for page in layout_information(extra):
                page.page = len(pages) + 1
                pages.append(page)
        return pages
    pages, elements, segments = [], [], []
    citations = set()
    y = TOP

    def finish():
        if segments:
            pages.append(
                ExhibitPage(
                    model["id"],
                    len(pages) + 1,
                    PAGE_WIDTH,
                    PAGE_HEIGHT,
                    list(elements),
                    "",
                    list(segments),
                )
            )
            pages[-1].segments.append({"kind": "page_citations", "values": sorted(citations)})

    def next_page():
        nonlocal elements, segments, citations, y
        finish()
        elements, segments, citations, y = [], [], set(), TOP

    for block in model.get("blocks", []):
        rows = rows_for(block, justify=enabled(model))
        if not rows:
            continue
        title = str(block.get("title") or "")
        header = _wrap(title, PAGE_WIDTH, 12, True) if title else []
        header_height = len(header) * 17 + (8 if title else 0)
        total = header_height + sum(r.height for r in rows)
        if block.get("new_page") and segments:
            next_page()
        if total <= BOTTOM - TOP and y + total > BOTTOM and segments:
            next_page()
        offset, part = 0, 1
        while offset < len(rows):
            continuation = (
                _wrap(title + " - continued", PAGE_WIDTH, 12, True)
                if title and part > 1
                else header
            )
            heading_height = len(continuation) * 17 + (8 if continuation else 0)
            minimum_body = sum(r.height for r in rows[offset : offset + min(3, len(rows) - offset)])
            # Keep an ordinary paragraph together; truly oversized paragraphs
            # can continue without reducing the type size.
            paragraph_end = offset + 1
            while (
                paragraph_end < len(rows)
                and rows[offset].paragraph is not None
                and rows[paragraph_end].paragraph == rows[offset].paragraph
            ):
                paragraph_end += 1
            first_paragraph = sum(r.height for r in rows[offset:paragraph_end])
            if first_paragraph <= BOTTOM - TOP - heading_height:
                minimum_body = max(minimum_body, first_paragraph)
            if y + heading_height + minimum_body > BOTTOM and segments:
                next_page()
            top = y
            for line in continuation:
                elements.append(_text(0, y, line, 12, True))
                y += 17
            if continuation:
                y += 8
            body_top = y
            end = offset
            used = 0
            while end < len(rows) and y + used + rows[end].height <= BOTTOM:
                used += rows[end].height
                end += 1
            if end < len(rows) and rows[end].paragraph is not None:
                boundary = end
                while boundary > offset and rows[boundary - 1].paragraph == rows[end].paragraph:
                    boundary -= 1
                if boundary > offset:
                    end = boundary
            # Avoid carrying a single trailing body line onto a new page.
            if len(rows) - end == 1 and end - offset > 3:
                end -= 1
            if end == offset:
                raise ValueError("Information content cannot fit at its approved type size.")
            body_height = sum(r.height for r in rows[offset:end])
            if block["kind"] == "statistics":
                col_width = (PAGE_WIDTH - 18) / 2
                for x in (0, col_width + 18):
                    elements.append(
                        ("rect", x, body_top - 3, col_width, max(0, body_height - 16), PALE)
                    )
                    elements.append(("rect", x, body_top - 3, col_width, 2, RED))
            if block["kind"] == "action":
                elements.append(("rect", 0, body_top, 20, 20, "#EAF0F7"))
                elements.append(_text(6, body_top + 3, block["number"], 11, True))
            if block["kind"] == "risk":
                elements.append(("rect", 0, body_top, 2, body_height, RED))
            for row in rows[offset:end]:
                for element in row.elements:
                    if element[0] == "text":
                        _, x, baseline, value, size, bold, color = element
                        elements.append(("text", x, y + baseline, value, size, bold, color))
                    else:
                        _, x, top, width, height, color = element
                        elements.append(("rect", x, y + top, width, height, color))
                segments.extend(
                    {**spacing, "baseline": spacing["baseline"] + y} for spacing in row.spacing
                )
                y += row.height
            citations.update(block.get("citations", []))
            segments.append(
                {
                    "kind": block["kind"],
                    "id": block["id"],
                    "part": part,
                    "first_row": offset,
                    "row_count": end - offset,
                    "top": top,
                    "height": y - top,
                }
            )
            offset = end
            y += 12 if block["kind"] == "action" else 10
            if offset < len(rows):
                part += 1
                next_page()
    finish()
    for page in pages:
        header = [
            _text(0, 1, "Information" + (" - continued" if page.page > 1 else ""), 16, True),
            _text(0, 27, f"Information Exhibit · {page.page} of {len(pages)}", 10),
        ]
        refs = next(s["values"] for s in page.segments if s["kind"] == "page_citations")
        footer = (
            "Sources: " + markers(refs) + " · Full references: Appendix D."
            if refs
            else "Advisory guidance · Supporting references: Appendix D."
        )
        if model.get("include_appendix", True) is False:
            footer = (
                "Sources: " + markers(refs) + " · See References."
                if refs
                else "Advisory guidance · See References."
            )
        lines = _wrap(footer, PAGE_WIDTH, 10)
        if len(lines) > 2:
            lines = _wrap(
                f"{len(refs)} cited sources on this page; see References."
                if model.get("include_appendix", True) is False
                else f"{len(refs)} cited sources on this page; full references: Appendix D.",
                PAGE_WIDTH,
                10,
            )
        decorations = [("rect", 0, 598, PAGE_WIDTH, 0.5, LINE)]
        decorations.extend(_text(0, 605 + i * 13, line, 10) for i, line in enumerate(lines))
        page.elements = header + page.elements + decorations
        page.alt_text = "\n".join(e[3] for e in page.elements if e[0] == "text")
    return pages
