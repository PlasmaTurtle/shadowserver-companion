"""Measured closing pages shared by selectable PDF, editable Word and SVG previews."""

from modules.ui.components.vector_layout import ExhibitPage, WIDTH, _wrap
from modules.ui.components.unicode_fonts import width as text_width
from modules.ui.components.text_justification import (
    enabled,
    mark_line,
    wrapped_paragraphs,
    word_space,
)
from .closing_page_model import REVISION, RECIPIENT_REVISIONS

PAGE_WIDTH, PAGE_HEIGHT = WIDTH - 12, 650
TOP, BOTTOM = 51, 578
BLACK = "#000000"


def closing_blocks(model):
    blocks = [
        {
            "id": "resources-heading",
            "text": "Recommended Resources",
            "size": 12,
            "bold": True,
            "leading": 17,
            "after": 7,
            "keep_next": True,
        }
    ]
    for i, group in enumerate(model["resource_groups"]):
        blocks.append(
            {
                "id": f"group-{i}",
                "text": group["title"],
                "bold": True,
                "size": 11,
                "leading": 15,
                "after": 3,
                "keep_next": True,
            }
        )
        for j, resource in enumerate(group["items"]):
            blocks.append(
                {
                    "id": f"resource-{i}-{j}",
                    "text": resource["label"],
                    "size": 10.5,
                    "leading": 14,
                    "after": 3 if j < len(group["items"]) - 1 else 10,
                    "indent": 10,
                    "url": resource["url"] if resource["active"] else None,
                }
            )
    if model.get("layout_revision") != REVISION:
        blocks.append(
            {
                "id": "responsibility-heading",
                "text": "Responsibility",
                "size": 12,
                "bold": True,
                "leading": 17,
                "after": 7,
                "keep_next": True,
            }
        )
    if model.get("recipient_verification"):
        blocks.append(
            {
                "id": "recipient-verification",
                "text": "Independent verification: " + model["recipient_verification"],
                "size": 10.5,
                "leading": 14,
                "after": 12,
            }
        )
    blocks.extend(
        [
            {
                "id": "responsibility",
                "text": model["responsibility"],
                "size": 11,
                "leading": 15,
                "after": 17,
            },
            {
                "id": "signoff",
                "text": model["closing"],
                "size": 11,
                "leading": 15,
                "after": 9,
                "keep_next": True,
            },
            {
                "id": "sender",
                "text": "\n".join(model["sender_lines"]),
                "size": 11,
                "leading": 15,
                "after": 0,
            },
        ]
    )
    return blocks


def layout_closing(model):
    pages, segments, elements = [], [], []
    recipient_layout = model.get("layout_revision") in RECIPIENT_REVISIONS
    start_y = 1 if recipient_layout else TOP
    y = start_y
    blocks = closing_blocks(model)
    if recipient_layout:
        blocks[0].update(size=16, leading=22, after=13)
    for block in blocks:
        available = PAGE_WIDTH - block.get("indent", 0)
        block["lines"], endings = wrapped_paragraphs(
            block["text"], available, block["size"], block.get("bold", False)
        )
        if enabled(model) and block["id"] in {"responsibility", "signoff"}:
            block["justified"] = True
            block["word_spaces"] = [
                word_space(line, available, block["size"], final=final)
                for line, final in zip(block["lines"], endings, strict=True)
            ]

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

    def next_page():
        nonlocal y, segments, elements
        finish()
        y, segments, elements = 45 if recipient_layout else TOP, [], []

    def place(block, lines, first, part):
        nonlocal y
        top, indent = y, block.get("indent", 0)
        for line_index, line in enumerate(lines, first):
            elements.append(
                (
                    "text",
                    indent,
                    y + block["size"],
                    line,
                    block["size"],
                    block.get("bold", False),
                    BLACK,
                )
            )
            if block.get("justified") and block["word_spaces"][line_index] > 0:
                segments.append(
                    {
                        "kind": "justified_line",
                        "left": indent,
                        "baseline": y + block["size"],
                        "width": PAGE_WIDTH - indent,
                        "word_space": block["word_spaces"][line_index],
                    }
                )
            if block.get("url"):
                elements.append(
                    (
                        "rect",
                        indent,
                        y + block["size"] + 1.5,
                        text_width(line, "ExhibitSans", block["size"]),
                        0.4,
                        BLACK,
                    )
                )
            y += block["leading"]
        segment = {
            **block,
            "kind": "closing_block",
            "lines": list(lines),
            "top": top,
            "height": y - top,
            "first_line": first,
            "part": part,
        }
        segment.pop("text")
        if block.get("justified"):
            segment["word_spaces"] = block["word_spaces"][first : first + len(lines)]
        segments.append(segment)
        if block.get("url"):
            segments.append(
                {
                    "kind": "link",
                    "url": block["url"],
                    "left": indent,
                    "top": top,
                    "width": PAGE_WIDTH - indent,
                    "height": y - top,
                }
            )

    for index, block in enumerate(blocks):
        total = len(block["lines"]) * block["leading"]
        needed = total
        if block.get("keep_next") and index + 1 < len(blocks):
            following = blocks[index + 1]
            needed += block["after"] + min(2, len(following["lines"])) * following["leading"]
        # Keep the entire short sign-off with its sender.
        if block["id"] == "signoff":
            needed = (
                total
                + block["after"]
                + len(blocks[index + 1]["lines"]) * blocks[index + 1]["leading"]
            )
        # Keep responsibility and signature together when the whole tail fits.
        tail_start = (
            "responsibility"
            if model.get("layout_revision") == REVISION
            else "responsibility-heading"
        )
        if block["id"] == tail_start:
            tail = sum(len(b["lines"]) * b["leading"] + b["after"] for b in blocks[index:])
            if tail <= BOTTOM - TOP:
                needed = tail
        if y + needed > BOTTOM and needed <= BOTTOM - TOP and segments:
            next_page()
        offset, part = 0, 1
        while offset < len(block["lines"]):
            available = int((BOTTOM - y) // block["leading"])
            if available < min(2, len(block["lines"]) - offset) and segments:
                next_page()
                available = int((BOTTOM - y) // block["leading"])
            count = min(available, len(block["lines"]) - offset)
            if count <= 0:
                raise ValueError("Closing content cannot fit at its approved type size.")
            if len(block["lines"]) - offset - count == 1 and count > 2:
                count -= 1
            place(block, block["lines"][offset : offset + count], offset, part)
            offset += count
            if offset < len(block["lines"]):
                part += 1
                next_page()
        y += block["after"]
    finish()
    for page in pages:
        headings = [
            {
                "id": "page-title",
                "lines": ["Closing" + (" - continued" if page.page > 1 else "")],
                "size": 16,
                "leading": 22,
                "bold": True,
                "top": 1,
            },
            {
                "id": "page-subtitle",
                "lines": [f"Resources and sign-off · {page.page} of {len(pages)}"],
                "size": 10,
                "leading": 14,
                "bold": False,
                "top": 27,
            },
        ]
        if recipient_layout:
            headings = (
                []
                if page.page == 1
                else [
                    {
                        "id": "page-title",
                        "lines": ["Recommended Resources continued"],
                        "size": 16,
                        "leading": 22,
                        "bold": True,
                        "top": 1,
                    }
                ]
            )
        note = (
            model["appendix_note"]
            if page.page == len(pages)
            else (
                "Additional resources follow on the next page. Complete resource URLs and source references appear in Appendix D."
                if recipient_layout
                else "Closing continues on the next page. Full resource URLs and source references: Appendix D."
            )
        )
        if page.page != len(pages) and model.get("include_appendix", True) is False:
            note = "Additional resources follow on the next page. Full source references appear in References."
        if page.page != len(pages) and model.get("recipient_verification"):
            note = note.replace("Additional resources follow", "This section continues")
        footer = {
            "id": "appendix-note",
            "lines": _wrap(note, PAGE_WIDTH, 10),
            "size": 10,
            "leading": 13,
            "bold": False,
            "top": 605,
        }
        if enabled(model):
            footer["justified"] = True
            footer["word_spaces"] = [
                word_space(line, PAGE_WIDTH, footer["size"], final=i == len(footer["lines"]) - 1)
                for i, line in enumerate(footer["lines"])
            ]
        for block in headings + [footer]:
            page.segments.append(
                {**block, "kind": "closing_block", "height": len(block["lines"]) * block["leading"]}
            )
            for row, line in enumerate(block["lines"]):
                mark_line(
                    page.segments,
                    0,
                    block["top"] + row * block["leading"] + block["size"],
                    line,
                    block["size"],
                    PAGE_WIDTH,
                    final=row == len(block["lines"]) - 1,
                    justify=bool(block.get("justified")),
                )
                page.elements.append(
                    (
                        "text",
                        0,
                        block["top"] + row * block["leading"] + block["size"],
                        line,
                        block["size"],
                        block["bold"],
                        BLACK,
                    )
                )
        page.elements.append(("rect", 0, 598, PAGE_WIDTH, 0.5, "#D4DCE3"))
        page.alt_text = "\n".join(
            e[3] for e in sorted([e for e in page.elements if e[0] == "text"], key=lambda e: e[2])
        )
    return pages
