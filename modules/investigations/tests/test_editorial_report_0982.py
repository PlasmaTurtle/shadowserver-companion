"""The new unknown-severity styling cannot alter historical or justified output."""

from copy import deepcopy
import hashlib

from modules.ui.components.exhibit_rendering import is_page_exhibit, office_svg
from modules.investigations.components.vulnerability_layout import (
    BLACK,
    RED,
    layout_vulnerabilities,
)
from modules.investigations.components.vulnerability_model import CURRENT_REVISION, REVISION
from modules.investigations.components.report_layouts import CURRENT_LAYOUTS


def model(revision=REVISION, severity="Not supplied"):
    return {
        "id": "EX-VULNERABILITY",
        "type": "vulnerability",
        "title": "Vulnerabilities",
        "layout_revision": revision,
        "severity": severity,
        "paragraph_alignment": "justify",
        "compact_appendix": True,
        "narrative": " ".join(
            ["The reported observation must be interpreted within its recorded source scope."] * 8
        ),
        "items": [
            {
                "label": "Reported service",
                "finding_type": "observation",
                "detail": "An observed service condition",
                "observation_scope": "mail.example.test · 192.0.2.1 · TCP 443",
            }
        ],
    }


def severity_element(page):
    return next(
        element
        for element in page.elements
        if element[0] == "text" and element[3].startswith("Reported severity:")
    )


def test_historical_render_matches_prechange_svg_bytes():
    historic = model()
    before = deepcopy(historic)
    pages = layout_vulnerabilities(historic)
    assert len(pages) == 1
    assert (
        hashlib.sha256(office_svg(pages[0])).hexdigest()
        == "fa05b8b1cc500857d1935a31bfd27b875ee5db08010ef4123aa903811bed5b76"
    )
    assert severity_element(pages[0])[-1] == RED
    assert historic == before


def test_new_unknown_severity_changes_only_ink_and_keeps_justified_prose():
    old = layout_vulnerabilities(model())[0]
    new = layout_vulnerabilities(model(CURRENT_REVISION))[0]
    assert severity_element(new)[-1] == BLACK
    assert old.segments == new.segments
    assert any(
        segment["kind"] == "justified_line" and segment["word_space"] > 0
        for segment in new.segments
    )
    differences = [(a, b) for a, b in zip(old.elements, new.elements, strict=True) if a != b]
    assert differences == [(severity_element(old), severity_element(new))]
    assert severity_element(old)[:-1] == severity_element(new)[:-1]
    assert old.alt_text == new.alt_text
    assert is_page_exhibit(model()) and is_page_exhibit(model(CURRENT_REVISION))
    assert CURRENT_LAYOUTS["vulnerability_revision"] == CURRENT_REVISION


def test_reported_critical_severity_retains_emphasis_in_new_revision():
    assert (
        severity_element(layout_vulnerabilities(model(CURRENT_REVISION, "Critical"))[0])[-1] == RED
    )
