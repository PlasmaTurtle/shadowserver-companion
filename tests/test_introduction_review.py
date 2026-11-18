"""First-page acceptance: original evidence, finite layout and export agreement."""

from copy import deepcopy
from io import BytesIO
import socket
import subprocess
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from PIL import Image
import pytest

from tools.preview_introduction import specimen
from workbench.report_composition import compose
from workbench.report_renderers import render_docx, render_pdf
from workbench.introduction_model import INTRO, SUBJECT, build_introduction, display_time
from workbench.introduction_layout import RED, layout_introduction
from workbench.exhibit_rendering import svg, png
from workbench.unicode_fonts import width as text_width


@pytest.mark.parametrize("ips,products,repeats", [(1, 1, 1), (8, 3, 3), (70, 8, 3)])
def test_one_page_preserves_wording_counts_and_source_rows(
    tmp_path, monkeypatch, ips, products, repeats
):
    monkeypatch.setattr(
        socket, "create_connection", lambda *a, **k: pytest.fail("Unexpected network call")
    )
    data = specimen(ips, products, repeats)
    original = deepcopy(data["qualified_lead"])
    intro = data["composition"]["sections"][0]
    assert intro["model"]["intro"] == INTRO
    assert intro["model"]["subject"] == SUBJECT
    assert [c["value"] for c in intro["model"]["counts"]] == [ips, ips, ips * repeats, products]
    assert len(intro["model"]["appendix_entry_ids"]) == ips * repeats
    assert (
        len([e for e in data["composition"]["appendix"]["entries"] if e["kind"] == "observation"])
        == ips * repeats
    )
    plan = layout_introduction(intro["model"])
    assert sum(b.height for b in plan.blocks) + plan.summary.height == pytest.approx(plan.height)
    for element in plan.summary.elements:
        if element[0] == "text":
            _, x, y, text, size, bold, color = element
            assert size >= 10
            assert 0 <= y <= plan.summary.height
            assert (
                x + text_width(text, "ExhibitSans-Bold" if bold else "ExhibitSans", size)
                <= plan.width + 0.01
            )
    data["composition"]["sections"] = [intro]
    render_pdf(data, tmp_path / "intro.pdf", tmp_path)
    render_docx(data, tmp_path / "intro.docx", tmp_path)
    text = subprocess.check_output(
        ["pdftotext", "-layout", str(tmp_path / "intro.pdf"), "-"]
    ).decode()
    pages = [p for p in text.split("\f") if p.strip()]
    assert len(pages) == 1
    collapsed = " ".join(text.split())
    assert INTRO in collapsed
    assert "192.0.2.14 | " in collapsed
    assert text.count("TLP:AMBER") == 2
    assert "Summary Exhibit" in text
    assert data["qualified_lead"] == original
    with ZipFile(tmp_path / "intro.docx") as package:
        root = ET.fromstring(package.read("word/document.xml"))
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        body = " ".join(n.text or "" for n in root.findall(".//w:t", ns))
        assert INTRO in " ".join(body.split())
        assert any(
            n.attrib.get("{" + ns["w"] + "}val") == RED[1:] for n in root.findall(".//w:color", ns)
        )
        assert any(
            n.attrib.get("{" + ns["w"] + "}name") == "EX-SUMMARY"
            for n in root.findall(".//w:bookmarkStart", ns)
        )
        assert "word/fonts/DejaVuSerif.ttf.odttf" in package.namelist()
        vector = next(package.read(n) for n in package.namelist() if n.endswith(".svg"))
        assert RED.encode() in vector and b"DejaVu Sans" in vector
    image = Image.open(BytesIO(png(plan.summary)))
    assert any(rgb == (165, 42, 42) for _, rgb in image.getcolors(image.width * image.height))
    assert RED.encode() in svg(plan.summary)


def test_existing_copy_and_later_pages_are_unchanged():
    data = specimen(8, 3, 3)
    new = data["composition"]
    data["draft"].pop("introduction_revision")
    old = compose(data)
    assert old["sections"][0]["kind"] == "text"
    first_break = next(i for i, n in enumerate(old["sections"]) if n["kind"] == "page_break")
    assert new["sections"][1:] == old["sections"][first_break:]
    assert new["appendix"] == old["appendix"]
    assert new["citations"] == old["citations"]


@pytest.mark.parametrize("kev,citations", [(False, [1]), (None, [1]), (True, []), (True, [None])])
def test_missing_or_negative_kev_is_not_promoted(kev, citations):
    data = specimen(1)
    exhibits = deepcopy(data["composition"]["exhibits"])
    vulnerability = next(e for e in exhibits if e["type"] == "vulnerability")
    vulnerability["items"][0].update(kev=kev, claim_citations={"kev": citations})
    model = build_introduction(data, exhibits)
    assert model["kev"] == []
    assert not any(
        "Known exploited" in e[3]
        for e in layout_introduction(model).summary.elements
        if e[0] == "text"
    )


def test_primary_attributed_ip_and_excluded_cve_are_respected():
    data = specimen(8, 3, 3)
    data["qualified_lead"]["whois"][0]["ip"] = "192.0.2.16"
    cve = data["cves"][0]
    data["draft"]["cve_dispositions"] = {
        cve: {"action": "exclude", "reason": "Synthetic test exclusion"}
    }
    model = compose(data)["sections"][0]["model"]
    assert model["asset_line"] == "192.0.2.16 | service03.harborhealth.example"
    assert all(item["id"] != cve for item in model["findings"] + model["kev"])
    assert model["counts"][3]["value"] == 3  # Reported IDs still exist in original rows.


def test_long_data_wraps_or_fails_explicitly_instead_of_clipping():
    model = specimen(8, 3, 3)["composition"]["sections"][0]["model"]
    model["asset_line"] = "2001:db8:1234:5678::10 | " + "long-hostname-" * 5 + ".example"
    model["groups"][0]["label"] = "A long product description with a retained exact version " * 5
    plan = layout_introduction(model)
    assert any(len(b.lines) > 1 for b in plan.blocks if b.color == RED)
    assert plan.summary.height > 160
    assert any("Appendix A" in e[3] for e in plan.summary.elements if e[0] == "text")
    model["to"] += "\n" + "Long address line\n" * 25
    with pytest.raises(ValueError, match="leaves less than 160 points"):
        layout_introduction(model)


def test_eol_without_cve_is_not_given_a_kev_label_or_cve_claim():
    data = specimen(1)
    data["cves"] = []
    data["draft"]["cve_records"] = []
    row = data["qualified_lead"]["validated_leads"][0]["entries"][0]
    row["source"]["fields"]["tag"] = "eol-example"
    data["assets"][0]["tag"] = "eol-example"
    model = compose(data)["sections"][0]["model"]
    text = " ".join(e[3] for e in layout_introduction(model).summary.elements if e[0] == "text")
    assert "Reported end-of-life software" in text
    assert "CISA KEV" not in text and "Appendix C" not in text


def test_timezone_is_explicit_and_unknown_zone_is_not_invented():
    assert display_time("2026-11-05T05:58:00Z") == "Nov 5, 2026 · 12:58 AM EST"
    assert display_time("2026-07-05T05:58:00Z").endswith("01:58 AM EDT")
    assert "zone not supplied" in display_time("2026-11-05 05:58:00")


def test_windows_without_system_tzdata_uses_bundled_zone(monkeypatch):
    from zoneinfo import ZoneInfo as RealZoneInfo, ZoneInfoNotFoundError
    import workbench.introduction_model as model

    class NoSystemTimezones:
        def __new__(cls, *args):
            raise ZoneInfoNotFoundError("No system IANA database")

        from_file = RealZoneInfo.from_file

    model.office_timezone.cache_clear()
    monkeypatch.setattr(model, "ZoneInfo", NoSystemTimezones)
    try:
        assert model.display_time("2026-11-05T05:58:00Z").endswith("12:58 AM EST")
        assert model.display_time("2026-07-05T05:58:00Z").endswith("01:58 AM EDT")
    finally:
        model.office_timezone.cache_clear()
