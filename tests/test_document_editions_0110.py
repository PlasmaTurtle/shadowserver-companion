"""Versioned recipient projections and portable resource integrity."""

from copy import deepcopy
from base64 import b64encode
import hashlib
import zlib

import pytest

from test_workbench import app, client  # noqa: F401

from workbench import compact_json
from workbench.recipient_edition import apply_edition, full_report_snapshot


def test_v1_snapshot_and_v2_round_trip_restore_identical_source_bytes():
    source = "é漢字 unknown source field\n" * 10000
    digest = hashlib.sha256(source.encode()).hexdigest()
    legacy = {
        "storage_format": compact_json.LEGACY_FORMAT,
        "document": {"source": {compact_json.REFERENCE: digest}},
        "strings": {digest: source},
    }
    before = deepcopy(legacy)
    restored = compact_json.unpack(legacy)
    assert legacy == before
    assert restored == compact_json.loads(compact_json.dumps(restored))
    assert len(compact_json.dumps(restored)) < len(source) * 0.05


@pytest.mark.parametrize("fault", ["length", "trailing", "hash", "budget"])
def test_compressed_resource_cannot_bypass_integrity_or_bounds(fault, monkeypatch):
    packed = compact_json.pack({"source": "A" * 5000})
    resource = next(iter(packed["strings"].values()))
    if fault == "length":
        resource["bytes"] = 10
    elif fault == "trailing":
        resource["data"] = b64encode(zlib.compress(b"A" * 5000) + b"trailing").decode()
    elif fault == "hash":
        resource["data"] = b64encode(zlib.compress(b"B" * 5000)).decode()
    else:
        monkeypatch.setattr(compact_json, "MAX_UNIQUE_STRING_BYTES", 100)
    with pytest.raises(ValueError):
        compact_json.unpack(packed)


def test_compact_projection_keeps_full_reviewed_content_and_sources():
    from tools.preview_vulnerabilities import specimen
    from workbench.report_layouts import adopt_current_layouts
    from workbench.report_composition import compose

    data = specimen("Multiple_CVEs")
    adopt_current_layouts(data["draft"])
    full = compose(data)
    data["draft"]["recipient_edition"] = "compact-v1"
    compact = compose(data)
    assert compact["full_edition_sections"] == full["sections"]
    assert compact["citations"] == full["citations"]
    assert compact["appendix"] == full["appendix"]
    assert compact["exhibits"] == full["exhibits"]
    table = next(node for node in compact["sections"] if node.get("keep_rows"))
    assert len(table["rows"]) == len(data["cves"])
    assert all(row[0]["text"].startswith("CVE-") for row in table["rows"])
    restored = full_report_snapshot({**data, "composition": compact})
    assert restored["composition"]["sections"] == full["sections"]


def test_compact_retains_responsibility_and_long_independent_verification():
    from tools.preview_vulnerabilities import specimen
    from workbench.report_layouts import adopt_current_layouts
    from workbench.report_composition import compose

    data = specimen("Multiple_CVEs")
    adopt_current_layouts(data["draft"])
    route = "Independently locate the published office number and ask for the named analyst. " * 4
    data["draft"].setdefault("sender_profile", {})["outreach_verification_route"] = route
    data["draft"]["recipient_edition"] = "compact-v1"
    content = compose(data)
    closing = next(model for model in content["exhibits"] if model["id"] == "EX-CLOSING")
    text = "\n".join(node.get("text", "") for node in content["sections"])
    assert route.strip() in text
    assert closing["responsibility"] in text


def test_default_full_and_unknown_edition_are_explicit():
    content = {"sections": []}
    assert apply_edition({"draft": {}}, content) is content
    assert apply_edition({"draft": {"recipient_edition": "full-v1"}}, content) is content
    with pytest.raises(ValueError, match="Unsupported recipient edition"):
        apply_edition({"draft": {"recipient_edition": "unknown"}}, content)


def test_shared_gallery_is_self_contained_and_masters_remain_unchanged(tmp_path):
    from tools.preview_vulnerabilities import specimen
    from workbench.package_exhibits import export_gallery
    from workbench.exhibit_rendering import capture_exhibit_masters, export_exhibits, prepared_pages

    data = specimen("Multiple_CVEs")
    content = data["composition"]
    capture_exhibit_masters(content)
    original = deepcopy(content)
    artifacts = export_gallery(content, tmp_path / "gallery")
    html = (tmp_path / "gallery/exhibit-gallery.html").read_text()
    assert len(artifacts) == html.count("<section id=")
    assert html.count("@font-face") == 2
    assert "data:font/woff;base64," in html
    assert "Content-Security-Policy" in html
    assert "<script" not in html
    assert content == original
    # Explicit standalone exports still contain self-contained verified SVGs.
    model = next(model for model in content["exhibits"] if model["id"] == "EX-VULNERABILITY")
    export_exhibits({"exhibits": [model]}, tmp_path / "standalone")
    expected = prepared_pages(model)[0]
    assert (tmp_path / "standalone/ex-vulnerability-1.svg").read_bytes() == expected.svg
    assert b"@font-face" in expected.svg
    assert content == original


def test_edition_change_reopens_every_content_review(client, app):
    from test_section_validation_050 import prepared, save
    from test_workbench import validate_sections

    lead = prepared(client, app, validate=False)
    lead = validate_sections(client, lead)
    response = save(client, lead, recipient_edition="compact-v1")
    assert response.status_code == 422, response.text
    assert "Reopen" in response.text
