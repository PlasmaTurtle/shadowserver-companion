"""Deterministic vector exhibits and compatible PNGs from a single layout.

No browser, external images, font downloads, or live source calls are involved.
Coordinates are points. Legacy text is black; new layouts may specify approved emphasis.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re
from xml.sax.saxutils import escape
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import Flowable
from .unicode_fonts import font_runs, svg_font_style, FALLBACK
from .report_operations import check_deadline
from .text_justification import enabled, mark_line, wrapped_paragraphs
from .vector_layout import WIDTH as WIDTH, FONT_ROOT, ExhibitPage, _value, _wrap
from .vulnerability_layout import layout_vulnerabilities
from .vulnerability_model import SUPPORTED_REVISIONS as VULNERABILITY_REVISIONS
from .attribution_layout import layout_attribution
from .attribution_model import REVISION as ATTRIBUTION_REVISION
from .information_layout import layout_information
from .information_model import SUPPORTED_REVISIONS as INFORMATION_REVISIONS
from .closing_page_layout import layout_closing
from .closing_page_model import SUPPORTED_REVISIONS as CLOSING_REVISIONS, safe_resource_url
from .appendix_layout import layout_appendix
from .appendix_view import SUPPORTED_REVISIONS as APPENDIX_REVISIONS
from .exhibit_masters import (
    prepare as prepare_masters,
    capture as capture_masters,
    reuse as reuse_masters,
)

VERSION = "0.7.0"


def _word_spaces(page):
    return {
        (segment["left"], segment["baseline"]): segment["word_space"]
        for segment in page.segments
        if segment.get("kind") == "justified_line"
    }


def is_page_exhibit(exhibit):
    return exhibit.get("layout_revision") in {
        *VULNERABILITY_REVISIONS,
        ATTRIBUTION_REVISION,
        *INFORMATION_REVISIONS,
        *CLOSING_REVISIONS,
        *APPENDIX_REVISIONS,
    }


def page_layout(exhibit):
    if exhibit.get("layout_revision") in APPENDIX_REVISIONS:
        return layout_appendix
    if exhibit.get("layout_revision") in CLOSING_REVISIONS:
        return layout_closing
    if exhibit.get("layout_revision") in INFORMATION_REVISIONS:
        return layout_information
    return (
        layout_attribution
        if exhibit.get("layout_revision") == ATTRIBUTION_REVISION
        else layout_vulnerabilities
    )


def office_svg(page, standalone=False):
    return (
        svg(page, standalone=standalone)
        .replace(b"Companion Exhibit Sans", b"DejaVu Sans")
        .replace(b"Companion CJK", b"Companion Noto Sans SC")
    )


def prepared_pages(exhibit):
    return prepare_masters(exhibit, page_layout(exhibit), office_svg, png)


def capture_exhibit_masters(content, frozen_exhibits=(), *, sections=None):
    """Reuse verified frozen artwork; capture new artwork only when requested.

    ``sections=None`` captures the complete export. An empty iterable is a
    projection: matching saved artwork is verified, but editable exhibits do
    not incur rasterization. Validation supplies its one section owner.
    """
    selected = None if sections is None else frozenset(sections)
    owners = {
        "summary": "introduction",
        "vulnerability": "vulnerabilities",
        "attribution": "attribution",
    }
    for exhibit in content.get("exhibits", []):
        if is_page_exhibit(exhibit):
            if "rendered_masters" not in exhibit:
                frozen = next((e for e in frozen_exhibits if e["id"] == exhibit["id"]), {})
                reuse_masters(exhibit, frozen)
            owner = exhibit.get(
                "owner", exhibit.get("section_owner", owners.get(exhibit.get("type")))
            )
            if "rendered_masters" in exhibit or selected is None or owner in selected:
                capture_masters(exhibit, prepared_pages(exhibit))


def layout(exhibit, policy=None, width=WIDTH, max_height=586):
    """Paginate rather than ellipsize. Larger cases retain all labeled groups."""
    if is_page_exhibit(exhibit):
        if "rendered_masters" in exhibit:
            return [item.page for item in prepared_pages(exhibit)]
        return page_layout(exhibit)(exhibit)
    policy = policy or {}
    brand = policy.get("brand_profile") or {}
    accent = "#002d61" if brand.get("id") == "usss" else "#195FA0"
    adverse = "#B42318"
    pale = "#EEF3F8"
    line = "#D4DCE3"
    pages = []
    elements = []
    segments = []
    y = 0
    margin = 12
    inner = width - margin * 2

    def rect(x, top, w, h, fill):
        elements.append(("rect", x, top, w, h, fill))

    def text(x, baseline, value, size=10, bold=False):
        elements.append(("text", x, baseline, _value(value), size, bold, "#000000"))

    def new_page():
        nonlocal elements, segments, y
        elements = []
        segments = []
        y = 15
        rect(0, 0, 4, 34, accent)
        text(margin, y, exhibit.get("title", "Exhibit"), 15, True)
        y += 17
        text(
            margin,
            y,
            exhibit.get("id", "Exhibit")
            + " | Revision "
            + str(exhibit.get("report_revision") or "Draft")
            + (" | Continued" if pages else ""),
            10,
        )
        y += 16

    def finish():
        if elements:
            pages.append(
                ExhibitPage(
                    exhibit["id"],
                    len(pages) + 1,
                    width,
                    y + 10,
                    list(elements),
                    exhibit.get("alt_text", ""),
                    list(segments),
                )
            )

    def ensure(height):
        if y + height > max_height and y > 60:
            finish()
            new_page()

    def paragraph(value, bold=False, indent=0, size=10):
        nonlocal y
        rows, endings = wrapped_paragraphs(value, inner - indent, size, bold)
        for row, final in zip(rows, endings, strict=True):
            ensure(13)
            text(margin + indent, y + 10, row, size, bold)
            mark_line(
                segments,
                margin + indent,
                y + 10,
                row,
                size,
                inner - indent,
                final=final,
                justify=enabled(exhibit),
                bold=bold,
            )
            y += 13

    def rule():
        nonlocal y
        ensure(8)
        rect(margin, y + 3, inner, 0.6, line)
        y += 8

    new_page()
    counts = exhibit.get("counts") or []
    # Counts are distinct dimensions. Each has a readable label, never icon-only.
    for start in range(0, len(counts), 3):
        chunk = counts[start : start + 3]
        cw = (inner - 16) / 3
        labels = [_wrap(c.get("label", ""), cw - 16, 10) for c in chunk]
        h = 35 + 14 * max(map(len, labels), default=1)
        ensure(h + 8)
        for i, c in enumerate(chunk):
            x = margin + i * (cw + 8)
            rect(x, y, cw, h, pale)
            text(x + 8, y + 24, c.get("value", 0), 20, True)
            for j, label in enumerate(labels[i]):
                text(x + 8, y + 40 + j * 14, label, 10)
        y += h + 10
    if exhibit.get("reporting_period"):
        period = exhibit["reporting_period"]
        paragraph(
            "Reporting period: "
            + str(period.get("first") or "Not supplied")
            + " to "
            + str(period.get("last") or "Not supplied")
        )
    if exhibit.get("report_types"):
        paragraph("Report types: " + ", ".join(exhibit["report_types"]))
    if exhibit.get("source_workbooks"):
        paragraph("Source: " + ", ".join(exhibit["source_workbooks"]))
    groups = exhibit.get("groups") or []

    def appendix_reference(refs):
        by_part = {}
        for ref in refs:
            by_part.setdefault(str(ref).split("-")[0], []).append(ref)
        return "; ".join(
            (
                ", ".join(values)
                if len(values) <= 2
                else part + " — " + str(len(values)) + " linked records"
            )
            for part, values in by_part.items()
        )

    if groups:
        paragraph("Reported scope", True)
        y += 3
        numeric = [g.get("value") for g in groups if isinstance(g.get("value"), (int, float))]
        max_value = max([1, *numeric])
        for group in groups:
            label = _value(group.get("label", ""))
            value = _value(group.get("value", ""))
            ensure(42)
            paragraph(label + (" · " + value if value else ""), True)
            if isinstance(group.get("value"), (int, float)):
                rect(margin, y + 3, inner, 5, pale)
                rect(
                    margin,
                    y + 3,
                    max(0, inner * float(group["value"]) / max_value),
                    5,
                    adverse if exhibit.get("type") == "vulnerability" else accent,
                )
                y += 13
            if group.get("detail"):
                paragraph(group["detail"])
            refs = group.get("appendix_entry_ids") or []
            if refs and exhibit.get("include_appendix", True):
                paragraph("Appendix: " + appendix_reference(refs))
            rule()
    items = exhibit.get("items") or []
    if exhibit.get("type") == "vulnerability" and len(items) > 6:
        grouped = {}
        for item in items:
            key = (item.get("finding_type", "cve"), tuple(item.get("reported_versions", [])))
            group = grouped.setdefault(
                key,
                {
                    "label": ", ".join(key[1])
                    or ("EOL conditions" if key[0] == "eol" else "Product/version not supplied"),
                    "members": [],
                    "appendix_entry_ids": [],
                    "citations": [],
                },
            )
            group["members"].append(item)
            group["appendix_entry_ids"] += item.get("appendix_entry_ids", [])
            group["citations"] += item.get("citations", [])
        items = []
        for group in grouped.values():
            members = group.pop("members")
            group["detail"] = str(len(members)) + (
                " distinct finding records; all identifiers, source-specific metrics and conditions are available upon request."
                if exhibit.get("include_appendix") is False
                else " distinct finding records; all identifiers, source-specific metrics and conditions are listed in Appendix C."
            )
            signals = {}
            for member in members:
                for signal in set(member.get("signals", [])):
                    signals[signal] = signals.get(signal, 0) + 1
            group["detail"] += "\n" + "; ".join(
                str(count) + " finding(s): " + label for label, count in sorted(signals.items())
            )
            group["appendix_entry_ids"] = list(dict.fromkeys(group["appendix_entry_ids"]))
            group["citations"] = list(dict.fromkeys(group["citations"]))
            items.append(group)
    for item in items:

        def cited(key, index=None):
            values = item.get("claim_citations", {}).get(key, [])
            if index is not None:
                values = values[index : index + 1]
            return (
                ""
                if not any(values)
                else " "
                + " ".join("[" + str(value) + "]" for value in dict.fromkeys(values) if value)
            )

        ensure(42)
        # Blue and red bars communicate confirmation and risk without coloring text.
        bar = (
            accent
            if exhibit.get("type") == "attribution"
            else adverse
            if exhibit.get("type") == "vulnerability"
            else line
        )
        rect(0, y + 1, 4, 14, bar)
        paragraph(item.get("label", ""), True)
        if item.get("detail") is not None:
            paragraph(item["detail"])
        if exhibit.get("type") == "attribution":
            paragraph("Method: " + str(item.get("method") or "Not supplied"))
            paragraph(
                "Matched field: "
                + str(item.get("matched_field") or "Not supplied")
                + " = "
                + str(item.get("matched_value") or "Not supplied")
            )
            paragraph("Source retrieved: " + str(item.get("retrieved_at") or "Not recorded"))
            paragraph(
                "Validated: "
                + str(item.get("decision_at") or "Not recorded")
                + " | Author: "
                + str(item.get("decision_by") or "Not recorded")
            )
        if item.get("finding_type") == "cve":
            paragraph(
                "Reported: "
                + (", ".join(item.get("reported_versions") or []) or "Version not supplied")
                + " | "
                + str(item.get("exposure_count", 0))
                + " reported IPs"
            )
            assessments = item.get("cvss_assessments") or []
            for metric_index, metric in enumerate(assessments):
                paragraph(
                    "CVSS "
                    + str(metric.get("version") or "?")
                    + ": "
                    + str(
                        metric.get("score") if metric.get("score") is not None else "Not supplied"
                    )
                    + " "
                    + str(metric.get("severity") or "")
                    + " | "
                    + str(metric.get("source") or "Contributor not supplied")
                    + cited("cvss", metric_index)
                )
            if not assessments:
                paragraph("CVSS: Not supplied")
            if item.get("epss") is not None:
                paragraph(
                    "EPSS: "
                    + format(float(item["epss"]) * 100, ".2f")
                    + "% probability | Score date: "
                    + str(item.get("epss_date") or "Not supplied")
                    + cited("epss")
                )
                if item.get("epss_percentile") is not None:
                    paragraph(
                        "EPSS percentile: " + format(float(item["epss_percentile"]) * 100, ".2f")
                    )
        elif item.get("finding_type") == "eol":
            paragraph("Lifecycle finding; no CVSS score assigned.")
        for impact_index, impact in enumerate(item.get("impacts") or []):
            if impact.get("source_text") and impact.get("basis"):
                paragraph(
                    "Potential impact: "
                    + str(impact.get("label") or "Source-supported consequence")
                )
                if impact.get("conditions"):
                    paragraph("Conditions: " + _value(impact["conditions"]))
                paragraph("Basis: " + str(impact["source_text"]) + cited("impacts", impact_index))
        references = item.get("appendix_entry_ids") or []
        citations = item.get("citations") or []
        if references and exhibit.get("include_appendix", True):
            paragraph("Appendix: " + appendix_reference(references))
        if citations:
            paragraph("Sources: " + ", ".join("[" + str(c) + "]" for c in citations))
        rule()
    if not groups and not exhibit.get("items"):
        paragraph("No additional exhibit details were supplied.")
    if exhibit.get("count_note"):
        paragraph(exhibit["count_note"])
    alt = exhibit.get("alt_text")
    if alt:
        paragraph(alt)
    finish()
    return pages


class ExhibitFlowable(Flowable):
    def __init__(self, page, allowed_targets=()):
        Flowable.__init__(self)
        self.page = page
        self.allowed_targets = set(allowed_targets)
        self.width = page.width
        self.height = page.height

    def draw(self):
        c = self.canv
        p = self.page
        spacing = _word_spaces(p)
        c.saveState()
        if p.page == 1:
            c.bookmarkHorizontal(p.id, 0, p.height)
        for segment in p.segments:
            if segment.get("kind") == "anchor":
                c.bookmarkHorizontal(segment["name"], 0, p.height - segment["top"])
        for item in p.elements:
            if item[0] == "rect":
                _, x, y, w, h, fill = item
                c.setFillColor(colors.HexColor(fill))
                c.rect(x, p.height - y - h, w, h, fill=1, stroke=0)
            elif item[0] == "text":
                _, x, y, value, size, bold, fill = item
                extra = spacing.get((x, y), 0)
                c.setFillColor(colors.HexColor(fill))
                for font, run in font_runs(value, "ExhibitSans-Bold" if bold else "ExhibitSans"):
                    c.setFont(font, size)
                    if extra:
                        c.drawString(x, p.height - y, run, wordSpace=extra)
                    else:
                        c.drawString(x, p.height - y, run)
                    x += pdfmetrics.stringWidth(run, font, size) + extra * run.count(" ")
        for segment in p.segments:
            if segment.get("kind") == "link" and safe_resource_url(segment.get("url")):
                x, y, w, h = (segment[k] for k in ("left", "top", "width", "height"))
                c.linkURL(
                    segment["url"],
                    (x, p.height - y - h, x + w, p.height - y),
                    relative=1,
                    thickness=0,
                )
            elif segment.get("kind") == "link" and segment.get("target") in self.allowed_targets:
                x, y, w, h = (segment[k] for k in ("left", "top", "width", "height"))
                c.linkRect(
                    "",
                    segment["target"],
                    (x, p.height - y - h, x + w, p.height - y),
                    relative=1,
                    thickness=0,
                )
        c.restoreState()


def svg(page, standalone=False):
    check_deadline()
    spacing = _word_spaces(page)
    pad = 32 if standalone else 0
    height = page.height + 2 * pad
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{page.width}pt" height="{height}pt" viewBox="0 0 {page.width} {height}" role="img">',
        "<title>" + escape(page.id) + "</title><desc>" + escape(page.alt_text) + "</desc>",
        f'<rect width="{page.width}" height="{height}" fill="#FFFFFF"/>',
    ]
    needs_cjk = any(
        any(
            font == FALLBACK
            for font, value in font_runs(e[3], "ExhibitSans-Bold" if e[5] else "ExhibitSans")
        )
        for e in page.elements
        if e[0] == "text"
    )
    parts.append(svg_font_style(needs_cjk))
    if standalone:
        for y in (1, height - 22):
            parts += [
                f'<rect x="{page.width - 100}" y="{y}" width="100" height="20" fill="#000000"/>',
                f'<text x="{page.width - 95}" y="{y + 14}" font-family="Arial,sans-serif" font-size="12" font-weight="700" fill="#FFC000">TLP:AMBER</text>',
            ]
    for element in page.elements:
        if element[0] == "rect":
            _, x, y, w, h, fill = element
            parts.append(f'<rect x="{x}" y="{y + pad}" width="{w}" height="{h}" fill="{fill}"/>')
        else:
            _, x, y, value, size, bold, fill = element
            extra = spacing.get((x, y), 0)
            preserved_space = ' xml:space="preserve"' if extra else ""
            spans = []
            cursor = x
            for font, run in font_runs(value, "ExhibitSans-Bold" if bold else "ExhibitSans"):
                family = "Companion CJK" if font == FALLBACK else "Companion Exhibit Sans"
                # Office's SVG importer ignores word-spacing. Position each
                # word explicitly so its drawing matches the PDF geometry.
                for chunk in re.split(r"( +)", run) if extra else (run,):
                    if not chunk:
                        continue
                    position = f' x="{cursor}"' if extra else ""
                    spans.append(f'<tspan font-family="{family}"{position}>{escape(chunk)}</tspan>')
                    cursor += pdfmetrics.stringWidth(chunk, font, size) + extra * chunk.count(" ")
            parts.append(
                f'<text x="{x}" y="{y + pad}" font-family="Companion Exhibit Sans" font-size="{size}" font-weight="{700 if bold else 400}" fill="{fill}"{preserved_space}>'
                + "".join(spans)
                + "</text>"
            )
    for segment in page.segments:
        if segment.get("kind") == "link" and safe_resource_url(segment.get("url")):
            url = escape(segment["url"], {'"': "&quot;"})
            parts.append(
                f'<a href="{url}"><rect x="{segment["left"]}" y="{segment["top"] + pad}" '
                f'width="{segment["width"]}" height="{segment["height"]}" fill="transparent"/></a>'
            )
    parts.append("</svg>")
    return "".join(parts).encode("utf-8")


def png(page, scale=3):
    check_deadline()
    spacing = _word_spaces(page)
    image = Image.new("RGB", (round(page.width * scale), round(page.height * scale)), "white")
    draw = ImageDraw.Draw(image)
    fonts = {}
    for item in page.elements:
        if item[0] == "rect":
            _, x, y, w, h, fill = item
            draw.rectangle(
                (
                    round(x * scale),
                    round(y * scale),
                    round((x + w) * scale),
                    round((y + h) * scale),
                ),
                fill=fill,
            )
        else:
            _, x, y, value, size, bold, fill = item
            extra = spacing.get((x, y), 0)
            for font, run in font_runs(value, "ExhibitSans-Bold" if bold else "ExhibitSans"):
                key = (size, font)
                path = (
                    "NotoSansSC-Regular.ttf"
                    if font == FALLBACK
                    else "DejaVuSans-Bold.ttf"
                    if bold
                    else "DejaVuSans.ttf"
                )
                if key not in fonts:
                    fonts[key] = ImageFont.truetype(str(FONT_ROOT / path), round(size * scale))
                for chunk in re.split(r"( +)", run) if extra else (run,):
                    draw.text(
                        (round(x * scale), round(y * scale)),
                        chunk,
                        font=fonts[key],
                        fill=fill,
                        anchor="ls",
                    )
                    x += pdfmetrics.stringWidth(chunk, font, size) + extra * chunk.count(" ")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def add_docx_exhibit(doc, page, *, office_font_names=False, rendered=None):
    """PNG fallback + Office SVG extension. Other DOCX viewers retain the fallback."""
    from docx.shared import Inches
    from docx.opc.part import Part
    from docx.opc.constants import RELATIONSHIP_TYPE
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from lxml import etree

    picture = doc.add_picture(
        BytesIO(rendered.png if rendered else png(page)),
        width=Inches(page.width / 72),
        height=Inches(page.height / 72),
    )
    picture._inline.docPr.set("descr", page.alt_text)
    picture._inline.docPr.set("title", page.id)
    package = doc.part.package
    vector = rendered.svg if rendered else svg(page)
    if office_font_names:
        # Office/LibreOffice do not consistently load CSS webfonts inside SVG.
        # These families are also embedded as OpenType fonts in this DOCX.
        vector = vector.replace(b"Companion Exhibit Sans", b"DejaVu Sans").replace(
            b"Companion CJK", b"Companion Noto Sans SC"
        )
    # New DOCX files carry each OpenType face once in fontTable.xml. Their
    # vector drawings use those same families and retain a PNG fallback.
    # Saved master SVG bytes are never modified.
    from .svg_resources import without_webfonts
    from .document_fonts import embed_report_fonts

    vector = vector.replace(b"Companion Exhibit Sans", b"DejaVu Sans").replace(
        b"Companion CJK", b"Companion Noto Sans SC"
    )
    embed_report_fonts(doc, include_cjk=b"Companion Noto Sans SC" in vector)
    vector = without_webfonts(vector)
    part = Part(
        package.next_partname("/word/media/exhibit%d.svg"), "image/svg+xml", vector, package
    )
    rid = doc.part.relate_to(part, RELATIONSHIP_TYPE.IMAGE)
    blip = picture._inline.xpath(".//a:blip")[0]
    extlst = OxmlElement("a:extLst")
    ext = OxmlElement("a:ext")
    ext.set("uri", "{96DAC541-7B7A-43D3-8B79-37D633B846F1}")
    svgblip = etree.Element(
        "{http://schemas.microsoft.com/office/drawing/2016/SVG/main}svgBlip",
        nsmap={"asvg": "http://schemas.microsoft.com/office/drawing/2016/SVG/main"},
    )
    svgblip.set(qn("r:embed"), rid)
    ext.append(svgblip)
    extlst.append(ext)
    blip.append(extlst)
    return picture


def export_exhibits(content, folder, policy=None, *, standalone=True):
    """Export requested variants from verified masters.

    Certification retains embedded SVG/PNG files plus complete reviewed masters
    in the compact snapshot. Marked standalone variants are explicit exports,
    not redundant files eagerly added to every new certified package.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for exhibit in content.get("exhibits", []):
        masters = prepared_pages(exhibit) if is_page_exhibit(exhibit) else []
        pages = [item.page for item in masters] if masters else layout(exhibit, policy)
        standalone_name = exhibit["id"].lower() + "-standalone.pdf"
        if standalone:
            from reportlab.platypus import SimpleDocTemplate, PageBreak
            from .print_policy import decorate_pdf

            flow = []
            for index, page in enumerate(pages):
                if index:
                    flow.append(PageBreak())
                flow.append(ExhibitFlowable(page))

            def decorate(canvas, doc):
                decorate_pdf(
                    canvas,
                    doc,
                    left_text="SHADOWSERVER COMPANION",
                    footer_text=exhibit["id"],
                    marking_font="ExhibitSans-Bold" if masters else "Helvetica-Bold",
                )

            SimpleDocTemplate(
                str(folder / standalone_name),
                pagesize=(612, 792),
                leftMargin=61.2,
                rightMargin=61.2,
                topMargin=58,
                bottomMargin=62,
                title=exhibit.get("title", exhibit["id"]),
            ).build(flow, onFirstPage=decorate, onLaterPages=decorate)
        for page in pages:
            master = masters[page.page - 1] if masters else None
            name = exhibit["id"].lower() + "-" + str(page.page)
            (folder / (name + ".svg")).write_bytes(master.svg if master else svg(page))
            (folder / (name + ".png")).write_bytes(master.png if master else png(page))
            artifact = {
                "exhibit_id": exhibit["id"],
                "page": page.page,
                "svg": name + ".svg",
                "png": name + ".png",
                "purpose": "embedded exhibit masters",
                "renderer_version": exhibit.get("layout_revision", VERSION),
            }
            if standalone:
                (folder / (name + "-standalone.svg")).write_bytes(
                    master.standalone_svg if master else svg(page, standalone=True)
                )
                artifact.update(
                    standalone_svg=name + "-standalone.svg",
                    standalone_pdf=standalone_name,
                    purpose="embedded exhibit masters and marked standalone copies",
                )
            artifacts.append(artifact)
    return artifacts


def add_docx_page_exhibit(doc, rendered, *, bookmark=None):
    """Place the reviewed page at the same content origin as the PDF frame."""
    if rendered.page.id.startswith("EX-APPENDIX-"):
        from .appendix_renderers import add_docx_appendix_page

        return add_docx_appendix_page(doc, rendered, bookmark=bookmark)
    if rendered.page.page != 1:
        bookmark = None
    if rendered.page.id == "EX-CLOSING":
        from .closing_page_renderers import add_docx_closing_page

        return add_docx_closing_page(doc, rendered, bookmark=bookmark)
    from docx.shared import Pt
    from .document_fonts import embed_report_fonts

    picture = add_docx_exhibit(doc, rendered.page, rendered=rendered)
    for side in ("distL", "distR", "distT", "distB"):
        picture._inline.set(side, "0")
    paragraph = doc.paragraphs[-1]
    fmt = paragraph.paragraph_format
    fmt.left_indent = Pt(6)
    fmt.space_before = Pt(6)
    fmt.space_after = Pt(0)
    fmt.line_spacing = 1
    fmt.keep_together = True
    for run in paragraph.runs:
        run.font.size = Pt(1)
    if bookmark is not None:
        bookmark(paragraph, rendered.page.id)
    embed_report_fonts(doc, include_cjk=b"Companion Noto Sans SC" in rendered.svg)


def svg_pages(exhibit, policy=None, standalone=False):
    if is_page_exhibit(exhibit):
        if "rendered_masters" not in exhibit:
            # Fingerprinting or SVG display must not create unused PNGs.
            return [
                office_svg(page, standalone=standalone).decode("utf-8")
                for page in page_layout(exhibit)(exhibit)
            ]
        return [
            (item.standalone_svg if standalone else item.svg).decode("utf-8")
            for item in prepared_pages(exhibit)
        ]
    return [svg(page, standalone=standalone).decode("utf-8") for page in layout(exhibit, policy)]
