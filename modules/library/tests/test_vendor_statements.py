"""Exact Red Hat source wording, product scope and last-good acquisition behavior."""

import hashlib
import json
import threading
from concurrent.futures import Future, ThreadPoolExecutor

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.library.components import vendor_statements
from modules.library.components.intelligence import acquisition, redhat
from modules.library.components.repositories.sources import SourceRepository
from modules.library.components.routes import vendor_statements as vendor_routes
from modules.library.components.vendor_statements import read_redhat, refresh_redhat
from modules.library.tests.support.cve_sources import ID, response
from modules.workspace.components.store import Store
from modules.workspace.components.workspace_data_captures import validate_capture_data


def record():
    return {
        "name": ID,
        "public_date": "2025-11-01T12:00:00Z",
        "statement": "  First paragraph.\r\n\r\nExact <vendor> text.  ",
        "details": ["A different description."],
        "package_state": [
            {
                "product_name": "Example 8",
                "cpe": "cpe:/o:example:os:8",
                "package_name": "sample",
                "fix_state": "Out of support scope",
            },
            {"product_name": "Example 7", "package_name": "sample", "fix_state": "Not affected"},
        ],
        "affected_release": [
            {
                "product_name": "Example 9",
                "advisory": "RHSA-2025:0001",
                "release_date": "2025-12-20T00:00:00Z",
            }
        ],
    }


def test_http_contract_preserves_exact_vendor_evidence(tmp_path, monkeypatch):
    store = Store(tmp_path)
    app = FastAPI()
    vendor_routes.register(app, store=store)
    base = "/api/library/vendor-statements/redhat/{cve_id}"
    route = base.format(cve_id=ID)
    raw = record()
    raw["public_date"] = "2025-11-01T12:00:00+00:00"
    with TestClient(app) as client:
        spec = client.get("/openapi.json").json()
        for path, method in [(base, "get"), (base + "/refresh", "post")]:
            response_schema = spec["paths"][path][method]["responses"]["200"]["content"]
            assert (
                response_schema["application/json"]["schema"]["$ref"]
                == "#/components/schemas/VendorStatementResponse"
            )
        assert client.get(route).json() == read_redhat(store, ID)
        monkeypatch.setattr(acquisition, "_response_get", lambda *a, **kw: response(raw))
        refreshed = client.post(route + "/refresh")
        assert refreshed.status_code == 200
        body = refreshed.json()
        assert body == client.get(route).json() == read_redhat(store, ID)
        assert (
            body["publisher_statement"] == raw["statement"]
            and body["published_at"] == raw["public_date"]
        )
        models = spec["components"]["schemas"]
        assert set(models["VendorStatementResponse"]["required"]) == set(body)
        assert set(models["VendorProductStatement"]["required"]) == set(body["statements"][0])
        assert set(models["VendorAcquisitionAttempt"]["required"]) == set(body["last_attempt"])
        monkeypatch.setattr(acquisition, "_response_get", lambda *a, **kw: response({}, 404))
        failed = client.post(route + "/refresh").json()
        assert failed == read_redhat(store, ID) and failed["last_attempt"]["outcome"] == "not_found"


def test_exact_evidence_and_local_pagination(tmp_path, monkeypatch):
    store = Store(tmp_path)
    raw = record()
    calls = []

    def fetch(url, **kwargs):
        calls.append(url)
        return response(raw)

    monkeypatch.setattr(acquisition, "_response_get", fetch)
    before = read_redhat(store, ID)
    assert before["status"] == "not_retrieved" and before["stale"] is None
    assert before["publisher_statement"] is None and not calls
    result = refresh_redhat(store, ID.lower())
    assert calls == [redhat.source_url(ID)]
    assert result["status"] == "available" and result["total"] == 3
    assert result["publisher_statement"] == raw["statement"]
    assert result["source_url"] == calls[0] and result["publisher"] == redhat.PUBLISHER
    assert result["published_at"] == raw["public_date"] and not result["stale"]
    assert result["retrieved_at"] and result["revision_id"]
    assert result["sha256"] == hashlib.sha256(json.dumps(raw).encode()).hexdigest()
    assert result["last_attempt"]["outcome"] == "success"
    assert [r["status"] for r in result["statements"]] == [
        "Out of support scope",
        "Not affected",
        "Fixed",
    ]
    assert result["statements"][0]["cpe"] == "cpe:/o:example:os:8"
    page = read_redhat(store, ID, offset=2, limit=1)
    assert page["total"] == 3 and page["statements"] == [
        {
            "product": "Example 9",
            "package": None,
            "cpe": None,
            "status": "Fixed",
            "advisory": "RHSA-2025:0001",
            "release_date": "2025-12-20T00:00:00Z",
            "source_pointer": "/affected_release/0",
        }
    ]
    monkeypatch.setattr(acquisition, "_age", lambda stamp: 86400)
    assert read_redhat(store, ID)["stale"] is True
    assert len(calls) == 1
    validate_capture_data(store)


def test_failed_refresh_retains_only_verified_source(tmp_path, monkeypatch):
    store = Store(tmp_path)
    raw = record()
    monkeypatch.setattr(acquisition, "_response_get", lambda *a, **kw: response(raw))
    saved = refresh_redhat(store, ID)
    raw["name"] = "CVE-2025-9876"
    failed = refresh_redhat(store, ID)
    assert failed["status"] == "available" and failed["stale"] is True
    assert failed["last_attempt"]["outcome"] == "invalid_response"
    assert (
        failed["revision_id"] == saved["revision_id"]
        and failed["publisher_statement"] == raw["statement"]
    )
    assert len(list(store.path("evidence/risk").glob("*.json"))) == 1
    source = SourceRepository(store).payload("risk-proof:redhat:" + ID)
    store.path(source["record_path"]).write_bytes(b"{}")
    unavailable = read_redhat(store, ID)
    assert unavailable["status"] == "unavailable" and unavailable["publisher_statement"] is None
    assert unavailable["error"] and not unavailable["statements"]


def test_revision_change_keeps_old_bytes_and_does_not_substitute_description(tmp_path, monkeypatch):
    store = Store(tmp_path)
    raw = record()
    monkeypatch.setattr(acquisition, "_response_get", lambda *a, **kw: response(raw))
    first = refresh_redhat(store, ID)
    del raw["statement"]
    raw["package_state"] = raw["affected_release"] = []
    second = refresh_redhat(store, ID)
    assert second["status"] == "available" and second["publisher_statement"] is None
    assert second["statements"] == [] and second["total"] == 0
    assert second["revision_id"] != first["revision_id"] and second["sha256"] != first["sha256"]
    proof = SourceRepository(store).payload("risk-version:" + first["revision_id"])["source"]
    assert (
        acquisition.retained_risk_data(store, "redhat:" + ID, proof)["statement"]
        == first["publisher_statement"]
    )
    validate_capture_data(store)


@pytest.mark.parametrize(
    ("data", "status", "outcome"),
    [
        ({"message": "Missing"}, 404, "not_found"),
        ({**record(), "name": "CVE-2022-1111"}, 200, "invalid_response"),
        ({**record(), "affected_release": {"product_name": "Example"}}, 200, "invalid_response"),
        ({**record(), "statement": "x" * 65537}, 200, "invalid_response"),
    ],
)
def test_missing_or_invalid_record_retains_metadata_only(
    tmp_path, monkeypatch, data, status, outcome
):
    store = Store(tmp_path)
    monkeypatch.setattr(acquisition, "_response_get", lambda *a, **kw: response(data, status))
    result = refresh_redhat(store, ID)
    assert result["status"] == "unavailable" and result["last_attempt"]["outcome"] == outcome
    assert result["last_attempt"]["http_status"] == status
    if status == 404:
        assert result["last_attempt"]["error"] == "Red Hat returned HTTP 404 for this CVE record"
    assert result["stale"] is None and result["revision_id"] is None
    assert read_redhat(store, ID)["status"] == "unavailable"
    assert not list(store.path("evidence/risk").glob("*.json"))


def test_endpoint_is_derived_only_from_valid_id(tmp_path, monkeypatch):
    store = Store(tmp_path)
    monkeypatch.setattr(
        acquisition, "_response_get", lambda *a, **kw: pytest.fail("unexpected network")
    )
    with pytest.raises(ValueError):
        refresh_redhat(store, ID + "?url=https://example.org")
    with pytest.raises(ValueError):
        acquisition.capture_json(store, "redhat:" + ID, redhat.source_url("CVE-2020-9999"))
    for url in [
        "https://example.org/" + ID + ".json",
        redhat.source_url(ID) + "?other",
        redhat.API + ID,
    ]:
        with pytest.raises(ValueError):
            acquisition._validate_source_url(url, redhat.PUBLISHER)


def test_concurrent_refresh_returns_the_revision_it_acquired(tmp_path, monkeypatch):
    store = Store(tmp_path)
    raw = record()
    original = acquisition.capture_json
    monkeypatch.setattr(acquisition, "_response_get", lambda *a, **kw: response(raw))

    def newer_revision(*args, **kwargs):
        first = original(*args, **kwargs)
        raw["statement"] = "Second publisher statement."
        original(*args, **kwargs)
        return first

    monkeypatch.setattr(acquisition, "capture_json", newer_revision)
    first = refresh_redhat(store, ID)
    second = read_redhat(store, ID)
    assert first["publisher_statement"] == record()["statement"]
    assert second["publisher_statement"] == raw["statement"]
    assert second["revision_id"] != first["revision_id"] and second["sha256"] != first["sha256"]


def test_provider_retry_after_blocks_second_request(tmp_path, monkeypatch):
    store = Store(tmp_path)
    seen = []

    def limited(url, **kwargs):
        seen.append(url)
        return response({}, 429, {"Retry-After": "45"})

    monkeypatch.setattr(acquisition, "_response_get", limited)
    first = refresh_redhat(store, ID)
    second = refresh_redhat(store, ID)
    assert first["last_attempt"]["outcome"] == second["last_attempt"]["outcome"] == "rate_limited"
    assert first["last_attempt"]["retry_after"] == "45"
    assert (
        first["last_attempt"]["http_status"] == 429
        and second["last_attempt"]["http_status"] is None
    )
    assert "retry window" in second["last_attempt"]["error"]
    assert seen == [redhat.source_url(ID)]


@pytest.mark.parametrize("status", [200, 404])
def test_overlapping_manual_refreshes_share_one_request_and_outcome(tmp_path, monkeypatch, status):
    store = Store(tmp_path)
    entered, joined = threading.Event(), threading.Event()
    seen = []

    class ObservedFuture(Future):
        def result(self):
            joined.set()
            return super().result()

    def fetch(url, **kwargs):
        seen.append(url)
        entered.set()
        assert joined.wait(5)
        return response(record(), status)

    monkeypatch.setattr(vendor_statements, "Future", ObservedFuture)
    monkeypatch.setattr(acquisition, "_response_get", fetch)
    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(refresh_redhat, store, ID)
        assert entered.wait(5)
        second = workers.submit(refresh_redhat, store, ID)
        assert first.result() == second.result()
    assert seen == [redhat.source_url(ID)]
    refresh_redhat(store, ID)
    assert seen == [redhat.source_url(ID)] * 2
