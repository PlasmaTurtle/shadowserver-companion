"""Measured one-page business/report explanations, shared by all exporters."""

from .vector_layout import ExhibitPage, WIDTH, _wrap
from .text_justification import mark_line, wrapped_paragraphs
from .unicode_fonts import width as text_width

PAGE_WIDTH, PAGE_HEIGHT = WIDTH - 12, 650
BLACK = "#000000"
GRAY = "#D3D3D3"
PALE = "#F2F2F2"
SIZE, LEADING = 10.25, 13.7


def markers(values):
    return " ".join(f"[{v}]" for v in dict.fromkeys(values) if v)


def layout_information_pages(model):
    result = []
    for definition in model["pages"]:
        elements, segments = [], []

        def text(x, y, value, size=SIZE, bold=False):
            elements.append(("text", x, y + size, str(value), size, bold, BLACK))

        def prose(value, y, *, x=0, width=PAGE_WIDTH, size=SIZE, leading=LEADING, justify=True):
            lines, ends = wrapped_paragraphs(value, width, size)
            for line, end in zip(lines, ends, strict=True):
                text(x, y, line, size)
                mark_line(segments, x, y + size, line, size, width, final=end, justify=justify)
                y += leading
            return y

        references = []
        for source in definition["references"]:
            publisher = source["publisher"]
            publisher = {
                "The Shadowserver Foundation": "Shadowserver",
                "National Institute of Standards and Technology": "NIST",
                "Federal Bureau of Investigation": "FBI",
                "Federal Bureau of Investigation, Internet Crime Complaint Center": "FBI IC3",
            }.get(publisher, publisher)
            reference = f"[{source['number']}] {publisher}. {source['title']}."
            references.extend(
                (line, source["public_url"]) for line in _wrap(reference, PAGE_WIDTH, 7.5)
            )
        references.append(
            (
                "Sources reviewed November 10, 2026. Underlined references link to the publications.",
                None,
            )
        )
        ref_top = PAGE_HEIGHT - 10 - 10 * len(references)
        elements.append(("rect", 0, ref_top - 8, PAGE_WIDTH, 0.5, GRAY))
        for index, (line, url) in enumerate(references):
            top = ref_top + index * 10
            text(0, top, line, 7.5)
            if url:
                width = text_width(line, "ExhibitSans", 7.5)
                elements.append(("rect", 0, top + 8.8, width, 0.3, BLACK))
                segments.append(
                    {
                        "kind": "link",
                        "left": 0,
                        "top": top,
                        "width": width,
                        "height": 10,
                        "url": url,
                    }
                )
        reference_elements, elements = elements, []
        title = _wrap(definition["title"], PAGE_WIDTH, 15, True)
        y = 0
        for line in title:
            text(0, y, line, 15, True)
            y += 20
        y += 12
        for block in definition["blocks"]:
            top = y
            kind = block["kind"]
            suffix = " " + markers(block.get("citations", [])) if block.get("citations") else ""
            if kind == "heading":
                y += 3
                for line in _wrap(block["title"] + suffix, PAGE_WIDTH, 11.2, True):
                    text(0, y, line, 11.2, True)
                    y += 15
                y += 5
            elif kind in ("prose", "note", "number"):
                x = 25 if kind == "number" else 0
                if kind == "number":
                    text(5, y, block["number"], 10.4, True)
                size, leading = (9.4, 12.5) if kind == "note" else (SIZE, LEADING)
                y = prose(
                    block["body"] + suffix, y, x=x, width=PAGE_WIDTH - x, size=size, leading=leading
                )
                y += 5 if kind == "number" else 7
            elif kind == "statistics_table":
                widths = (PAGE_WIDTH - 247, 92, 155)
                for index, values in enumerate([block["headers"], *block["items"]]):
                    height, size = (21, 9) if index == 0 else (22, 10)
                    elements.append(
                        ("rect", 0, y, PAGE_WIDTH, height, PALE if index == 0 else "#FFFFFF")
                    )
                    x = 0
                    for col, (value, width) in enumerate(zip(values, widths, strict=True)):
                        tx = (
                            x + 7
                            if col == 0
                            else x
                            + width
                            - 7
                            - text_width(
                                value, "ExhibitSans-Bold" if index == 0 else "ExhibitSans", size
                            )
                        )
                        text(tx, y + 4, value, size, index == 0)
                        x += width
                    y += height
                    elements.append(("rect", 0, y, PAGE_WIDTH, 0.4, GRAY))
                y += 5
            elif kind in ("examples", "routes"):
                label_width, gap = 123, 12
                detail_x = label_width + gap
                detail_width = PAGE_WIDTH - detail_x - 9
                for label, body in block["items"]:
                    labels = _wrap(label, label_width - 15, 10.1, True)
                    lines = _wrap(body, detail_width, SIZE)
                    height = max(len(labels) * 13.7, len(lines) * LEADING) + 13
                    if kind == "routes":
                        elements.extend(
                            [
                                ("rect", 0, y, PAGE_WIDTH, height, PALE),
                                ("rect", 0, y, 2, height, BLACK),
                            ]
                        )
                    for index, line in enumerate(labels):
                        text(9, y + 6 + index * 13.7, line, 10.1, True)
                    prose(body, y + 6, x=detail_x, width=detail_width)
                    y += height
                    if kind == "examples":
                        elements.append(("rect", 0, y, PAGE_WIDTH, 0.4, GRAY))
                    y += 5 if kind == "routes" else 2
                y += 5
            else:
                raise ValueError("Unsupported information page block: " + kind)
            segments.append({"kind": kind, "id": definition["id"], "top": top, "height": y - top})
        if y > ref_top - 12:
            raise ValueError(
                f"Information one-pager {definition['id']} exceeds its page: {y:.1f} > {ref_top - 12:.1f}"
            )
        elements.extend(reference_elements)
        segments.append(
            {"kind": "page_citations", "values": [s["number"] for s in definition["references"]]}
        )
        result.append(
            ExhibitPage(
                model["id"],
                len(result) + 1,
                PAGE_WIDTH,
                PAGE_HEIGHT,
                elements,
                "\n".join(e[3] for e in elements if e[0] == "text"),
                segments,
            )
        )
    return result
