"""Paginated appendix records with repeated section, record and field context."""

import re

from .closing_page_model import safe_resource_url
from .appendix_compact import REVISION as REVIEWED_COMPACT_REVISION
from .appendix_compact import PREVIOUS_REVISION as PREVIOUS_COMPACT_REVISION
from modules.ui.components.vector_layout import ExhibitPage, WIDTH, _wrap
from modules.ui.components.unicode_fonts import width as text_width
from modules.ui.components.text_justification import (
    enabled,
    mark_line,
    wrapped_paragraphs,
    prose_value,
)

PAGE_WIDTH, PAGE_HEIGHT = WIDTH - 12, 650
TOP, BOTTOM = 68, 608
LABEL_WIDTH = 176
BODY_SIZE, LEADING, PAD = 10.5, 14, 3
BLACK, RULE, SHADE = "#000000", "#D4DCE3", "#E8EDF2"


def _field_url(value, model):
    """Link one URL, preserving historical rendering of saved source fields."""
    if not safe_resource_url(value):
        return None
    if enabled(model) and (
        any(character.isspace() for character in value)
        or len(re.findall(r"https?://", value, flags=re.IGNORECASE)) != 1
    ):
        return None
    return value


class AppendixLayout:
    def __init__(self, model):
        self.model, self.pages = model, []
        self.current_record = self.current_group = None
        self.elements, self.segments, self.y = [], [], TOP

    def text(
        self,
        text,
        *,
        size=BODY_SIZE,
        bold=False,
        after=5,
        target=None,
        anchor=None,
        role=None,
        prose=False,
    ):
        lines, endings = wrapped_paragraphs(text, PAGE_WIDTH, size, bold)
        justified = enabled(self.model) and prose and not bold
        spacing = []
        top = self.y
        for line, final in zip(lines, endings, strict=True):
            spacing.append(
                mark_line(
                    self.segments,
                    0,
                    self.y + size,
                    line,
                    size,
                    PAGE_WIDTH,
                    final=final,
                    justify=justified,
                )
            )
            self.elements.append(("text", 0, self.y + size, line, size, bold, BLACK))
            self.y += LEADING if size <= 11 else 19
        self.segments.append(
            {
                "kind": "appendix_text",
                "lines": lines,
                "top": top,
                "height": self.y - top,
                "size": size,
                "bold": bold,
                "leading": LEADING if size <= 11 else 19,
                "role": role,
                "target": target,
                "anchor": anchor,
                **({"justified": True, "word_spaces": spacing} if justified else {}),
            }
        )
        if anchor:
            self.segments.append({"kind": "anchor", "name": anchor, "top": top})
        if target:
            self.segments.append(
                {
                    "kind": "link",
                    "target": target,
                    "left": 0,
                    "top": top,
                    "width": PAGE_WIDTH,
                    "height": self.y - top,
                }
            )
        self.y += after

    def finish(self):
        if not self.segments:
            return
        self.pages.append(
            ExhibitPage(
                self.model["id"],
                len(self.pages) + 1,
                PAGE_WIDTH,
                PAGE_HEIGHT,
                self.elements,
                "",
                self.segments,
            )
        )

    def new_page(self, repeat=True):
        self.finish()
        self.elements, self.segments, self.y = [], [], TOP
        if repeat and self.current_record:
            self.record_heading(self.current_record, continued=True)
            if self.current_group:
                self.group_heading(self.current_group, continued=True)

    def ensure(self, height, repeat=True):
        if self.y + height > BOTTOM:
            self.new_page(repeat)

    def compact_reference(self, record):
        return self.model.get("layout_revision") == REVIEWED_COMPACT_REVISION and record[
            "kind"
        ] in {"reference", "closing_resource"}

    def heading_after(self, record):
        # Bibliographic entries need a small title-to-metadata gap, not the
        # larger separation used by source observations. Keep the approved
        # font size and line spacing while avoiding a lone final resource.
        return 2 if self.compact_reference(record) else 5

    def record_heading(self, record, continued=False):
        title = record["title"]
        display = title if len(title) <= 145 else title[:142] + "..."
        label = record["label"] + "  " + record["kind_label"] + (" continued" if continued else "")
        compact = self.model.get("compact", False)
        if compact:
            heading = ("" if record["kind"] == "reference" else record["label"] + " · ") + title
            self.text(
                heading + (" continued" if continued else ""),
                bold=True,
                size=11,
                after=self.heading_after(record),
                anchor=None if continued else record["id"],
                role="record",
            )
        else:
            self.text(
                label,
                bold=True,
                size=12,
                after=2,
                anchor=None if continued else record["id"],
                role="record",
            )
            self.text(display, after=6)
        if not continued:
            for alias in record.get("entry_ids", []):
                if alias != record["id"]:
                    self.segments.append({"kind": "anchor", "name": alias, "top": self.y})
            for number in record.get("reference_numbers", [record.get("reference_number")]):
                if number is None:
                    continue
                self.segments.append(
                    {
                        "kind": "anchor",
                        "name": "ref" + str(number),
                        "top": self.y,
                    }
                )
            if record["citations"] and not (compact and record["kind"] == "reference"):
                # Each citation is its own linked text span; do not turn a list
                # into a single link to its first source.
                top = self.y
                self.text(
                    "Sources: " + " ".join(f"[{n}]" for n in record["citations"]), size=10, after=4
                )
                self.segments[-1]["citations"] = record["citations"]
                x = text_width("Sources: ", "ExhibitSans", 10)
                for number in record["citations"]:
                    label = f"[{number}]"
                    w = text_width(label, "ExhibitSans", 10)
                    if x + w > PAGE_WIDTH:
                        x, top = 0, top + LEADING
                    self.segments.append(
                        {
                            "kind": "link",
                            "target": "ref" + str(number),
                            "left": x,
                            "top": top,
                            "width": w,
                            "height": LEADING,
                        }
                    )
                    x += text_width(label + " ", "ExhibitSans", 10)

    def record_metadata(self, record):
        # Relationship lists may contain hundreds of observations. They belong
        # in the paginated body, not the repeated record heading.
        fields = []
        for key, label in (("related", "Related to"), ("source_ids", "Source record identifiers")):
            if record[key]:
                fields.append(
                    {"path": key, "label": label, "text": "; ".join(map(str, record[key]))}
                )
        self.compact_fields({"fields": fields}, metadata=True)

    def group_heading(self, group, continued=False):
        label = group["title"] + (" continued" if continued else "")
        self.text(label + " (source: " + group["path"] + ")", bold=True, after=5)

    def start_table(self):
        top = self.y
        self.elements.append(("rect", 0, top, PAGE_WIDTH, 24, SHADE))
        for x, value in ((PAD, "Field"), (LABEL_WIDTH + PAD, "Recorded value")):
            self.elements.append(("text", x, top + PAD + BODY_SIZE, value, BODY_SIZE, True, BLACK))
        self.y += 24
        table = {
            "kind": "appendix_table",
            "top": top,
            "height": 24,
            "label_width": LABEL_WIDTH,
            "width": PAGE_WIDTH,
            "size": BODY_SIZE,
            "leading": LEADING,
            "padding": PAD,
            "rows": [],
            "record_id": self.current_record["id"],
            "group_path": self.current_group["path"],
        }
        self.segments.append(table)
        return table

    def draw_row(self, table, row):
        y, height = self.y, row["height"]
        for x, w in ((0, PAGE_WIDTH),):
            self.elements.append(("rect", x, y + height - 0.4, w, 0.4, RULE))
        for x in (0, LABEL_WIDTH, PAGE_WIDTH - 0.4):
            self.elements.append(("rect", x, y, 0.4, height, RULE))
        for x, lines in ((PAD, row["labels"]), (LABEL_WIDTH + PAD, row["values"])):
            for i, line in enumerate(lines):
                self.elements.append(
                    ("text", x, y + PAD + BODY_SIZE + i * LEADING, line, BODY_SIZE, False, BLACK)
                )
        table["rows"].append(row)
        table["height"] += height
        if row["url"]:
            self.segments.append(
                {
                    "kind": "link",
                    "url": row["url"],
                    "left": LABEL_WIDTH,
                    "top": y,
                    "width": PAGE_WIDTH - LABEL_WIDTH,
                    "height": height,
                }
            )
        self.y += height

    def fields(self, group):
        table = None
        for field in group["fields"]:
            value = field["text"].replace("\t", "\\t").replace("\r", "\\r")
            prose = field["value_type"] == "string" and (
                len(value) > 350 or "description" in field["path"].lower()
            )
            if prose:
                table = None
                self.ensure(70)
                self.text(field["label"], bold=True, after=5)
                lines, endings = wrapped_paragraphs(value, PAGE_WIDTH, 11)
                justified = enabled(self.model) and prose_value(value)
                offset = 0
                while offset < len(lines):
                    count = min(len(lines) - offset, int((BOTTOM - self.y) // 15))
                    if count < min(2, len(lines) - offset):
                        self.new_page()
                        self.text(field["label"] + " continued", bold=True, after=5)
                        count = min(len(lines) - offset, int((BOTTOM - self.y) // 15))
                    if count <= 0:
                        raise ValueError(
                            "Appendix field heading leaves no room for source text on a page. "
                            "Review the source field label or nested path before exporting."
                        )
                    top = self.y
                    chunk = lines[offset : offset + count]
                    spacing = []
                    for line_index, line in enumerate(chunk, offset):
                        self.elements.append(("text", 0, self.y + 11, line, 11, False, BLACK))
                        spacing.append(
                            mark_line(
                                self.segments,
                                0,
                                self.y + 11,
                                line,
                                11,
                                PAGE_WIDTH,
                                final=endings[line_index],
                                justify=justified,
                            )
                        )
                        self.y += 15
                    self.segments.append(
                        {
                            "kind": "appendix_text",
                            "lines": chunk,
                            "size": 11,
                            "bold": False,
                            "leading": 15,
                            "top": top,
                            "height": self.y - top,
                            "field_path": field["path"],
                            "record_id": self.current_record["id"],
                            "first_line": offset,
                            "total_lines": len(lines),
                            **({"justified": True, "word_spaces": spacing} if justified else {}),
                        }
                    )
                    offset += count
                self.y += 9
                continue
            labels = _wrap(field["label"], LABEL_WIDTH - 2 * PAD, BODY_SIZE)
            values = _wrap(value, PAGE_WIDTH - LABEL_WIDTH - 2 * PAD, BODY_SIZE)
            offset = 0
            while offset < len(values):
                minimum = max(len(labels), min(2, len(values) - offset)) * LEADING + 2 * PAD
                if self.y + minimum + (24 if table is None else 0) > BOTTOM:
                    self.new_page()
                    table = None

                if table is None:
                    table = self.start_table()
                available = int((BOTTOM - self.y - 2 * PAD) // LEADING)
                if available < len(labels):
                    raise ValueError("Appendix field label exceeds the available page area")
                count = min(available, len(values) - offset)
                if len(values) - offset - count == 1 and count > 2:
                    count -= 1
                row_labels = labels + (["continued"] if offset else [])
                if len(row_labels) > available or count <= 0:
                    raise ValueError(
                        "Appendix field label cannot fit with its continuation on a page. "
                        "Review the source field label or nested path before exporting."
                    )
                row = {
                    "labels": row_labels,
                    "values": values[offset : offset + count],
                    "height": max(len(row_labels), count) * LEADING + 2 * PAD,
                    "field_path": field["path"],
                    "first_line": offset,
                    "total_lines": len(values),
                    "url": _field_url(value, self.model),
                }
                self.draw_row(table, row)
                offset += count
                if offset < len(values):
                    self.new_page()
                    table = None

    def compact_fields(self, group, *, metadata=False):
        """Short citations and resource metadata read as entries, not tiny tables."""
        for field in group["fields"]:
            value = field["text"].replace("\t", "\\t").replace("\r", "\\r")
            label = field["label"] + ": " if field["label"] else ""
            lines, endings = wrapped_paragraphs(label + value, PAGE_WIDTH, BODY_SIZE)
            path_parts = field["path"].lower().split("/")
            prose_field = any(
                part
                in {
                    "capture_method",
                    "application",
                    "summary",
                    "note",
                    "notes",
                    "explanation",
                    "scope",
                }
                or part.endswith(("_note", "_notes", "_scope"))
                for part in path_parts
            )
            justified = (
                enabled(self.model)
                and not metadata
                and field.get("value_type") == "string"
                and (prose_field or len(value) > 350 or "description" in field["path"].lower())
                and prose_value(value)
            )
            offset = 0
            while offset < len(lines):
                count = min(len(lines) - offset, int((BOTTOM - self.y) // LEADING))
                if count < min(2, len(lines) - offset):
                    self.new_page()
                    count = min(len(lines) - offset, int((BOTTOM - self.y) // LEADING))
                if count <= 0:
                    raise ValueError(
                        "Appendix source heading leaves no room for record text on a page. "
                        "Review the source field label or nested path before exporting."
                    )
                top = self.y
                spacing = []
                for line_index, line in enumerate(lines[offset : offset + count], offset):
                    self.elements.append(
                        ("text", 0, self.y + BODY_SIZE, line, BODY_SIZE, False, BLACK)
                    )
                    spacing.append(
                        mark_line(
                            self.segments,
                            0,
                            self.y + BODY_SIZE,
                            line,
                            BODY_SIZE,
                            PAGE_WIDTH,
                            final=endings[line_index],
                            justify=justified,
                        )
                    )
                    self.y += LEADING
                self.segments.append(
                    {
                        "kind": "appendix_text",
                        "lines": lines[offset : offset + count],
                        "size": BODY_SIZE,
                        "bold": False,
                        "leading": LEADING,
                        "top": top,
                        "height": self.y - top,
                        "record_id": self.current_record["id"],
                        "metadata_key" if metadata else "field_path": field["path"],
                        "first_line": offset,
                        "total_lines": len(lines),
                        "url": _field_url(value, self.model),
                        **({"justified": True, "word_spaces": spacing} if justified else {}),
                    }
                )
                if _field_url(value, self.model):
                    self.segments.append(
                        {
                            "kind": "link",
                            "url": value,
                            "left": 0,
                            "top": top,
                            "width": PAGE_WIDTH,
                            "height": self.y - top,
                        }
                    )
                offset += count
            self.y += 3

    def compact_record_height(self, record):
        """Reserve short entries as a unit; long records still paginate normally."""
        height = 3 if self.compact_reference(record) else 5
        if heading := record.get("section_heading"):
            height += len(wrapped_paragraphs(heading["title"], PAGE_WIDTH, 12, True)[0]) * 19 + 10
        title = ("" if record["kind"] == "reference" else record["label"] + " · ") + record["title"]
        height += len(
            wrapped_paragraphs(title, PAGE_WIDTH, 11, True)[0]
        ) * LEADING + self.heading_after(record)
        if record["citations"] and record["kind"] != "reference":
            text = "Sources: " + " ".join(f"[{n}]" for n in record["citations"])
            height += len(wrapped_paragraphs(text, PAGE_WIDTH, 10)[0]) * LEADING + 4
        for group in record["groups"]:
            for field in group["fields"]:
                value = field["text"].replace("\t", "\\t").replace("\r", "\\r")
                label = field["label"] + ": " if field["label"] else ""
                height += (
                    len(wrapped_paragraphs(label + value, PAGE_WIDTH, BODY_SIZE)[0]) * LEADING + 3
                )
                if height > BOTTOM - TOP:
                    return height
            height += 0 if self.compact_reference(record) else 3
        return height

    def build(self):
        if "directory" in self.model:
            self.text(self.model["description"], size=11, after=20, prose=True)
            self.text("Contents", size=12, bold=True, after=8)
            for item in self.model["directory"]:
                self.ensure(62, repeat=False)
                count = str(item["count"]) + (" record" if item["count"] == 1 else " records")
                self.text(
                    "Appendix " + item["section"] + "  " + item["title"] + " (" + count + ")",
                    bold=True,
                    target=item["target"],
                    after=12,
                )
            self.ensure(150, repeat=False)
            self.text("Reading the records", size=12, bold=True, after=8)
            for note in self.model["reading_notes"]:
                self.ensure(len(_wrap(note, PAGE_WIDTH, BODY_SIZE)) * LEADING + 8, repeat=False)
                self.text(note, after=8, prose=True)
        else:
            if not self.model["records"]:
                self.text("No records of this type are included in this notification.", prose=True)
            for record in self.model["records"]:
                self.current_record = self.current_group = None
                compact = self.model.get("compact", False)
                title_lines = len(
                    _wrap(
                        record["title"] if compact else record["title"][:145], PAGE_WIDTH, BODY_SIZE
                    )
                )
                heading = record.get("section_heading")
                reserved = (48 if compact else 70) + title_lines * LEADING + (30 if heading else 0)
                if compact and self.model.get("layout_revision") in {
                    PREVIOUS_COMPACT_REVISION,
                    REVIEWED_COMPACT_REVISION,
                }:
                    complete_height = self.compact_record_height(record)
                    if complete_height <= BOTTOM - TOP:
                        # Reserve the actual complete entry in the new layout.
                        # A fixed minimum stranded short links on another page.
                        reserved = (
                            complete_height
                            if self.model.get("layout_revision") == REVIEWED_COMPACT_REVISION
                            else max(reserved, complete_height)
                        )
                self.ensure(reserved, repeat=False)
                if heading:
                    self.text(
                        heading["title"],
                        bold=True,
                        size=12,
                        after=10,
                        anchor=heading["anchor"],
                        role="section",
                    )
                self.current_record = record
                self.record_heading(record)
                if not compact:
                    self.record_metadata(record)
                for group in record["groups"]:
                    self.current_group = None
                    if compact or record["kind"] in {"reference", "closing_resource"}:
                        self.compact_fields(group)
                    else:
                        self.ensure(70)
                        self.current_group = group
                        self.group_heading(group)
                        if group["path"] == "/" or len(group["fields"]) < 5:
                            self.compact_fields(group)
                        else:
                            self.fields(group)
                    self.y += (0 if self.compact_reference(record) else 3) if compact else 10
                self.y += (3 if self.compact_reference(record) else 5) if compact else 10
        self.finish()
        for page in self.pages:
            tag = (
                "Appendix " + self.model.get("display_section", self.model["section"])
                if self.model["section"]
                else "Appendix"
                if self.model.get("compact")
                else "Supporting information"
            )
            title = self.model["title"]
            headers = [
                {
                    "kind": "appendix_text",
                    "lines": [tag],
                    "size": 10,
                    "leading": 14,
                    "bold": True,
                    "top": 1,
                    "height": 14,
                },
                {
                    "kind": "appendix_text",
                    "lines": _wrap(title, PAGE_WIDTH, 16, True),
                    "size": 16,
                    "leading": 20,
                    "bold": True,
                    "top": 20,
                    "role": "section",
                },
            ]
            headers[1]["height"] = len(headers[1]["lines"]) * 20
            if page.page == 1:
                for anchor in self.model["anchors"]:
                    page.segments.append({"kind": "anchor", "name": anchor, "top": 1})
            footer = (
                "Appendix " + self.model.get("display_section", self.model["section"]) + " | "
                if self.model["section"]
                else "Appendices | "
            ) + f"Page {page.page} of {len(self.pages)}"
            foot = {
                "kind": "appendix_text",
                "lines": [footer],
                "size": 10,
                "leading": 14,
                "bold": False,
                "top": 633,
                "height": 14,
                "target": "companion-appendix",
            }
            for block in headers + [foot]:
                page.segments.append(block)
                for i, line in enumerate(block["lines"]):
                    page.elements.append(
                        (
                            "text",
                            0,
                            block["top"] + block["size"] + i * block["leading"],
                            line,
                            block["size"],
                            block["bold"],
                            BLACK,
                        )
                    )
            page.segments.append(
                {
                    "kind": "link",
                    "target": "companion-appendix",
                    "left": 0,
                    "top": 630,
                    "width": PAGE_WIDTH,
                    "height": 18,
                }
            )
            page.alt_text = "\n".join(
                e[3]
                for e in sorted(
                    [e for e in page.elements if e[0] == "text"], key=lambda e: (e[2], e[1])
                )
            )
        return self.pages


def layout_appendix(model):
    return AppendixLayout(model).build()
