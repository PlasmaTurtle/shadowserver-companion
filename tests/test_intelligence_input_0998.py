"""Rejected provider responses never become retained source payloads."""

import hashlib
import json
from unittest.mock import Mock

import pytest

from test_cve_sources_040 import ID, nvd, program
from workbench.intelligence import acquisition, service
from workbench.source_capture import capture_sources
from workbench.store import Store


def response(body, *, status=200, content_type="application/json"):
    headers = {} if content_type is None else {"Content-Type": content_type}
    result = Mock(status_code=status, headers=headers)
    result.__enter__ = Mock(return_value=result)
    result.__exit__ = Mock(return_value=False)
    result.iter_content.return_value = [body]
    return result


@pytest.fixture(autouse=True)
def no_pacing(monkeypatch):
    monkeypatch.setattr(acquisition, "_wait_for_nvd", lambda *args, **kwargs: None)


@pytest.mark.parametrize(
    "body,media,status",
    [
        (
            b'<html><script src="https://inert.example/fixture.js"></script></html>',
            "text/html",
            200,
        ),
        (
            b'<html><script src="https://inert.example/fixture.js"></script></html>',
            "application/json",
            200,
        ),
        (b"MZ\x00fixture executable", "application/json", 200),
        (b'{"vulnerabilities":[],"vulnerabilities":[]}', "application/json", 200),
        (b'{"vulnerabilities":[],"value":NaN}', "application/json", 200),
        (b'{"unexpected":"object"}', "application/json", 200),
        (json.dumps(nvd()).encode(), "text/html", 200),
        (json.dumps(nvd()).encode(), None, 200),
        (json.dumps(nvd()).encode("utf-16"), "application/json", 200),
        (b"<html>inert error page</html>", "text/html", 429),
        (b"<html>inert error page</html>", "text/html", 503),
    ],
)
def test_rejected_provider_response_metadata_only(tmp_path, monkeypatch, body, media, status):
    store = Store(tmp_path / "data")
    monkeypatch.setattr(
        acquisition,
        "_response_get",
        lambda *a, **k: response(body, status=status, content_type=media),
    )
    retained, source = acquisition._capture(
        store, acquisition.NVD_URL + ID, "NVD", "https://nvd.nist.gov/vuln/detail/" + ID, ID
    )
    assert retained == b""
    assert source["record_path"] == ""
    assert source["response_retention"] == "metadata-only"
    assert source["sha256"] == hashlib.sha256(body).hexdigest()
    assert source["captured_bytes"] == len(body)
    assert source["validation_error"]
    assert not list((store.root / "evidence").rglob("*"))


def test_invalid_response_does_not_leak_via_fallback_or_attempts(tmp_path, monkeypatch):
    marker = b"INERT_REJECTED_RESPONSE_CANARY_0998"
    invalid = b"<html>" + marker + b"</html>"
    valid = json.dumps(program()).encode()
    monkeypatch.setattr(
        acquisition,
        "_response_get",
        lambda url, **k: (
            response(invalid, content_type="text/html") if "nist.gov" in url else response(valid)
        ),
    )
    store = Store(tmp_path / "data")
    result = service.verify(store, ID)
    assert result["verification_status"] == "published"
    assert result["source"] == "CVE Program"
    assert result["attempts"][0]["record_path"] == ""
    assert result["acquisition"][0]["outcome"] == "invalid_response"
    assert result["acquisition"][0]["source_snapshot_id"] is None
    assert store.path(result["record_path"]).read_bytes() == valid
    assert marker not in json.dumps(result).encode()
    for file in store.root.rglob("*"):
        if file.is_file():
            assert marker not in file.read_bytes(), file


def test_invalid_refresh_keeps_verified_prior_record(tmp_path, monkeypatch):
    store = Store(tmp_path / "data")
    good = json.dumps(nvd()).encode()
    monkeypatch.setattr(acquisition, "_response_get", lambda *a, **k: response(good))
    prior = service.verify(store, ID)
    invalid = b"<html>INERT_REFRESH_CANARY_0998</html>"
    monkeypatch.setattr(acquisition, "_response_get", lambda *a, **k: response(invalid))
    current = service.verify(store, ID, refresh=True)
    assert current["record_path"] == prior["record_path"]
    assert current["retrieved_at"] == prior["retrieved_at"]
    assert current["stale"] is True
    assert store.path(current["record_path"]).read_bytes() == good
    assert all(item["record_path"] == "" for item in current["refresh_attempts"])


def test_valid_source_preserves_complete_record_and_unknown_fields(tmp_path, monkeypatch):
    raw = nvd()
    raw["extension"] = {
        "values": [None, False, 0],
        "text": "CVE documentation may discuss <script> syntax.",
    }
    body = json.dumps(raw).encode()
    monkeypatch.setattr(acquisition, "_response_get", lambda *a, **k: response(body))
    store = Store(tmp_path / "data")
    retained, source = acquisition._capture(
        store, acquisition.NVD_URL + ID, "NVD", "https://nvd.nist.gov/vuln/detail/" + ID, ID
    )
    assert retained == body
    assert store.path(source["record_path"]).read_bytes() == body
    assert source["response_retention"] == "validated-provider-json"


def test_legacy_html_not_reintroduced_into_report_snapshot(tmp_path):
    store = Store(tmp_path / "data")
    raw = b"<html>INERT_LEGACY_HTML_CANARY_0998</html>"
    path = store.path("old-response.json")
    path.write_bytes(raw)
    source = {
        "publisher": "NVD",
        "record_path": "old-response.json",
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    data = {
        "cves": [ID],
        "draft": {"cve_records": [{"id": ID, "sources": [source]}]},
        "qualified_lead": {},
    }
    capture_sources(store, data)
    assert data["source_snapshots"][0]["record"] is None
    assert data["source_snapshots"][0]["availability"] == "unavailable"
    assert "INERT_LEGACY_HTML_CANARY_0998" not in json.dumps(data)
    assert path.read_bytes() == raw  # Existing evidence is never silently rewritten.


def test_rejected_risk_feed_records_attempt_without_body(tmp_path, monkeypatch):
    body = b"<html>INERT_EPSS_CANARY_0998</html>"
    monkeypatch.setattr(acquisition, "_response_get", lambda *a, **k: response(body))
    store = Store(tmp_path / "data")
    with pytest.raises(ValueError, match="JSON"):
        acquisition.capture_json(store, "epss:" + ID, acquisition.EPSS_URL + ID)
    assert not list((store.root / "evidence").rglob("*"))
    proof = acquisition.SourceRepository(store).payload("risk-attempt:epss:" + ID)
    assert proof["response"]["sha256"] == hashlib.sha256(body).hexdigest()
    assert proof["response"]["response_retention"] == "metadata-only"
