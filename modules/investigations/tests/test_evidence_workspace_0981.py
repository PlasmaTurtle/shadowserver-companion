"""Offline evidence workspace: bounded views, exact originals and safe enhancement."""

from base64 import b64encode
from copy import deepcopy
import hashlib

from modules.investigations.components.evidence_reader import _generic_overview
from modules.investigations.components.evidence_reader_assets import SCRIPT

from modules.investigations.tests.support.evidence_workspace import (
    evidence_package,
)


def test_reader_has_only_hashed_bundled_script_and_preserves_raw_sources(tmp_path):
    data, files = evidence_package(tmp_path)
    before = deepcopy(data)
    html = (tmp_path / "Evidence_Record.html").read_text(encoding="utf-8")
    expected = b64encode(hashlib.sha256(SCRIPT.encode()).digest()).decode()
    assert "sha256-" + expected in html
    assert "connect-src &#x27;none&#x27;" in html
    assert html.count("<script>") == 1
    assert '<img src="https://example.test/exfil"' not in html
    assert "&lt;img src=" in html
    assert "unknown%23source.json" in html
    assert 'id="evidence-search"' in html and 'id="verify-folder"' in html
    assert "Partial capture" in html and ">200</td>" in html
    assert "A concrete source finding." in html
    assert data == before
    assert all((tmp_path / name).read_bytes() == raw for name, raw in files.items())


def test_large_generic_feeds_are_bounded_but_show_record_count():
    payload = {"data": [{"unfamiliar": str(i)} for i in range(10000)]}
    overview, fields = _generic_overview(payload)
    assert len(fields) == 81
    assert any(field["value"] == 10000 and field["label"] == "Data count" for field in overview)
    assert len(payload["data"]) == 10000


def test_malformed_cve_description_shape_does_not_break_generic_reader():
    overview, fields = _generic_overview(
        {"cveMetadata": {"cveId": "CVE-2099-1"}, "containers": {"cna": {"descriptions": 4}}}
    )
    assert any(field["value"] == "CVE-2099-1" for field in overview)
    assert fields
