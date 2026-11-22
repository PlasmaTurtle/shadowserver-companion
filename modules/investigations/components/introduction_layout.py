"""Measured first-page text and a bounded, adaptive Summary Exhibit.

No text is scaled down to make a case fit. The summary selects a more compact
representation and explicitly identifies supporting detail in the appendix.
The same measured lines feed PDF, native Word paragraphs and browser preview.
"""

from dataclasses import dataclass, field
from datetime import date

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from modules.ui.components.exhibit_rendering import ExhibitPage, WIDTH, FONT_ROOT, _wrap
from modules.ui.components.unicode_fonts import width as text_width
from modules.ui.components.text_justification import (
    enabled,
    mark_line,
    wrapped_paragraphs,
    word_space,
)

RED = "#A52A2A"
BLACK = "#000000"
BLUE = "#002D61"
RULE = "#D4DCE3"
PAGE_WIDTH = WIDTH - 12  # Match the existing document frame's inner padding.
PAGE_HEIGHT = 650
pdfmetrics.registerFont(TTFont("IntroSerif", str(FONT_ROOT / "DejaVuSerif.ttf")))


@dataclass
class TextBlock:
    lines: list[str]
    size: float = 10.5
    leading: float = 14
    indent: float = 0
    after: float = 0
    bold: bool = False
    color: str = BLACK
    centered: bool = False
    serif: bool = False
    underline: bool = False
    label: str = ""
    justified: bool = False
    word_spaces: list[float] = field(default_factory=list)

    @property
    def height(self):
        return len(self.lines) * self.leading + self.after


@dataclass
class IntroductionLayout:
    blocks: list[TextBlock] = field(default_factory=list)
    summary: ExhibitPage | None = None
    width: float = PAGE_WIDTH
    height: float = PAGE_HEIGHT


def _short_list(values, limit=3, *, include_appendix=True):
    values = list(dict.fromkeys(values))
    shown = ", ".join(values[:limit])
    return shown + (
        f"; {len(values) - limit} more "
        + ("in Appendix C" if include_appendix else "available upon request")
        if len(values) > limit
        else ""
    )


def summary_layout(model, width, height):
    """Prefer detail when it fits; every omitted group is explicitly counted."""
    if height < 160:
        raise ValueError(
            "Introduction text leaves less than 160 points for its Summary Exhibit. Review the address or subject length; text has not been reduced or clipped."
        )
    elements, segments = [], []
    y = 0

    def text(x, baseline, value, size=10, bold=False, color=BLACK):
        elements.append(("text", x, baseline, str(value), size, bold, color))

    def rule(top):
        elements.append(("rect", 0, top, width, 0.5, RULE))

    def lines(value, top, *, size=10, bold=False, color=BLACK, x=0, available=None, prose=False):
        rows, endings = wrapped_paragraphs(value, available or width, size, bold)
        for index, row in enumerate(rows):
            text(x, top + size + index * 13, row, size, bold, color)
            mark_line(
                segments,
                x,
                top + size + index * 13,
                row,
                size,
                available or width,
                final=endings[index],
                bold=bold,
                justify=enabled(model) and prose,
            )
        return len(rows) * 13

    text(0, 14, "Summary Exhibit", 13, True)
    severity = "Reported severity: " + model["severity"]
    severity_color = (
        BLACK
        if model["severity"] == "Not specified"
        or (model.get("layout_revision") == 2 and model["severity"] == "Not supplied")
        else RED
    )
    w = text_width(severity, "ExhibitSans", 10)
    if w <= width - 180:
        text(width - w, 14, severity, color=severity_color)
        y = 27
    else:
        y = 22 + lines(severity, 22, color=severity_color)
    # Four distinct metrics share one line. Source rows are never called assets.
    labels = ["Reported IPs", "Endpoints", "Observations", "Reported CVEs"]
    for index, (count, label) in enumerate(zip(model["counts"], labels)):
        x = index * width / 4
        if index:
            elements.append(("rect", x - 10, y, 0.5, 37, RULE))
        text(x, y + 18, count["value"], 18, True)
        text(x, y + 35, label, 10)
    y += 46
    y += lines("Observed: " + model["observed"], y)
    y += 7
    # Reserve the source/appendix note first so it can never be pushed off page.
    note = (
        "Supporting asset and scan records: Appendix A."
        if model.get("compact_appendix")
        else "Full asset and scan details: Appendix A."
    )
    if model["findings"]:
        note += " Vulnerability sources: Appendix C."
    if model.get("include_appendix", True) is False:
        note = model.get(
            "supporting_records_note",
            "Full asset, scan and vulnerability records are available upon request.",
        )
    if model.get("scope_note"):
        note += " " + model["scope_note"]
    note_height = len(_wrap(note, width, 10)) * 13
    limit = height - note_height - 8

    if model["kev"]:
        citations = sorted({n for item in model["kev"] for n in item["citations"]})
        signal = (
            model["kev"][0]["id"] + " · Known exploited · CISA KEV"
            if len(model["kev"]) == 1
            else f"{len(model['kev'])} included CVEs listed in CISA KEV; see Appendix C"
        )
        if model.get("include_appendix", True) is False:
            signal = signal.replace("; see Appendix C", "")
        signal += " " + " ".join(f"[{n}]" for n in citations)
        signal_height = len(_wrap(signal, width, 10)) * 13
        if y + signal_height + 37 <= limit:
            y += lines(signal, y, color=RED, bold=True)
            y += 6

    groups = model["groups"]
    # A single product gets useful service/finding/network detail instead of a
    # mostly empty distribution graphic. Mixed cases use a compact comparison.
    same_product = bool(model.get("recipient_action")) and len({g["label"] for g in groups}) == 1
    compact_single = (len(groups) == 1 and len(model["assets"]) == 1) or same_product
    if compact_single:
        g = groups[0]
        service = (
            " · ".join(dict.fromkeys(g.get("detail", "") for g in groups))
            if same_product
            else g.get("detail", "")
        )
        details = [(g["label"], RED, True), (service, BLACK, False)]
        if model["findings"]:
            details.insert(
                1,
                (
                    _short_list(
                        (f["id"] for f in model["findings"]),
                        include_appendix=model.get("include_appendix", True),
                    ),
                    RED,
                    False,
                ),
            )
        elif model["eol_count"]:
            details.insert(1, ("Reported end-of-life software", RED, False))
        if len(model["assets"]) == 1:
            details += [(network, BLACK, False) for network in model["assets"][0]["networks"]]
        detail_height = sum(len(_wrap(v, width, 10, b)) * 13 for v, _, b in details if v)
        if y + detail_height <= limit:
            for value, color, bold in details:
                if value:
                    y += lines(value, y, color=color, bold=bold)
        else:
            compact_single = False

    if not compact_single:
        # Aggregate by reported product and service; rank by unique reported IPs.
        # Each row keeps its exact label and wraps rather than truncating.
        product_width, service_width = width * 0.57, width * 0.26
        header_h = 22
        rows = []
        used = y + header_h
        for group_index, g in enumerate(groups):
            product = _wrap(g["label"], product_width - 12, 10)
            service = _wrap(g.get("detail", ""), service_width - 12, 10)
            h = max(len(product), len(service), 1) * 13 + 8
            if used + h + (15 if group_index < len(groups) - 1 else 0) > limit:
                break
            rows.append((g, product, service, h))
            used += h
        if rows:
            text(0, y + 10, "Reported product / version", bold=True)
            text(product_width, y + 10, "Service", bold=True)
            text(width - 42, y + 10, "IPs", bold=True)
            rule(y + 17)
            y += header_h
            for g, product, service, h in rows:
                for index, value in enumerate(product):
                    text(0, y + 10 + index * 13, value, color=RED)
                for index, value in enumerate(service):
                    text(product_width, y + 10 + index * 13, value)
                text(width - 42, y + 10, len(g.get("ip_addresses", [])))
                rule(y + h - 3)
                y += h
        hidden = len(groups) - len(rows)
        if hidden:
            message = f"{hidden} additional product/service group{'s' if hidden != 1 else ''} in Appendix A."
            if model.get("include_appendix", True) is False:
                message = f"{hidden} additional product/service group{'s' if hidden != 1 else ''}; details on request."
            if y + len(_wrap(message, width, 10)) * 13 <= limit:
                y += lines(message, y)
            else:
                # No partial row or silent loss: show an exact scope statement.
                y += lines(
                    f"{len(groups)} product/service groups; "
                    + (
                        "details on request."
                        if model.get("include_appendix", True) is False
                        else "see Appendix A."
                    ),
                    y,
                )
        if not groups:
            y += lines(
                "Product / version not supplied; original fields available upon request."
                if model.get("include_appendix", True) is False
                else "Product / version not supplied; see supporting observations in Appendix A."
                if model.get("compact_appendix")
                else "Product / version not supplied; see original fields in Appendix A.",
                y,
            )
    if y > limit + 0.01:
        raise ValueError("The Summary Exhibit could not fit without clipping its detail.")
    rule(height - note_height - 6)
    lines(note, height - note_height, prose=True)
    alt = (
        f"{model['counts'][0]['value']} reported IPs; {model['counts'][1]['value']} endpoints; "
        f"{model['counts'][2]['value']} observations; {model['counts'][3]['value']} reported CVEs. "
        f"Reported severity: {model['severity']}. Observed: {model['observed']}. " + note
    )
    return ExhibitPage(model["summary_id"], 1, width, height, elements, alt, segments)


def layout_introduction(model, width=PAGE_WIDTH, height=PAGE_HEIGHT):
    result = IntroductionLayout(width=width, height=height)

    def add(value, **kw):
        size = kw.get("size", 10.5)
        available = width - kw.get("indent", 0)
        if kw.get("serif"):
            # Agency titles have fixed, short lines in the approved reference.
            # Reject long configuration instead of reducing the text size.
            lines = str(value).splitlines()
            if any(text_width(line, "IntroSerif", size) > available for line in lines):
                raise ValueError("Agency heading is too long for the introduction page.")
        else:
            lines = _wrap(value, available, size, kw.get("bold", False))
        block = TextBlock(lines, **kw)
        if block.justified:
            _, endings = wrapped_paragraphs(value, available, size, block.bold)
            block.word_spaces = [
                word_space(line, available, size, bold=block.bold, final=final)
                for line, final in zip(lines, endings, strict=True)
            ]
        result.blocks.append(block)

    readable = bool(model.get("recipient_action"))
    add(
        "\n".join(model["agency"]),
        size=15,
        leading=18,
        centered=True,
        serif=True,
        after=10 if readable else 15,
    )
    add(
        model["marking"],
        size=13,
        leading=17,
        centered=True,
        bold=True,
        color=RED,
        underline=True,
        after=14 if readable else 24,
    )
    add(model["to"], label="To:", indent=78, after=10 if readable else 14)
    add(model["sender"], label="From:", indent=78, after=12 if readable else 18)
    if model.get("layout_revision") == 2:
        value = model.get("report_date") or "Not supplied"
        try:
            selected = date.fromisoformat(value)
            value = selected.strftime("%B ") + str(selected.day) + selected.strftime(", %Y")
        except (TypeError, ValueError):
            pass
        add(value, label="Date:", indent=78, after=10)
    add(model["subject"], label="Subject:", indent=78, after=2)
    add(model["asset_line"], indent=78, color=RED, after=0)
    if model["additional_assets"]:
        add(model["additional_assets"], indent=78, size=10, leading=13, after=0)
    result.blocks[-1].after += 12 if readable else 19
    add(model["intro"], leading=14.2, after=10 if readable else 19, justified=enabled(model))
    if readable:
        add(model["recipient_action"], leading=14, after=4)
        if model.get("recipient_reply"):
            add("Reply to: " + model["recipient_reply"], leading=14, after=4)
        if model.get("recipient_verification"):
            add("Verification: " + model["recipient_verification"], leading=14, after=4)
        result.blocks[-1].after += 8
    available = height - sum(block.height for block in result.blocks)
    if readable and available < 160:
        # Long real names/titles get modestly tighter paragraph spacing before
        # we reject a cover. Never shrink type, truncate identity, or omit the
        # first action, reply route, or supporting-record scope.
        for block in result.blocks:
            reclaim = min(max(0, block.after - 6), 160 - available)
            block.after -= reclaim
            available += reclaim
            if available >= 160:
                break
    result.summary = summary_layout(model, width, available)
    return result
