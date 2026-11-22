"""Risk freshness and schema compatibility agree across database entry points."""

from contextlib import closing

from datetime import timedelta
from copy import deepcopy
import hashlib
import json
import sqlite3

import pytest

from tests.session_helpers import TestClient
from modules.library.tests.support.catalog_products import put, record
from modules.library.tests.support.cve_sources import nvd, program, response
from modules.library.tests.support.cve_catalog import catalog_record
from modules.library.tests.support.local_risk import ID, NOW, epss_bytes, kev_raw, risk
from modules.workspace.components.api import create_app
from modules.library.components.cve_catalog import Catalog
from modules.library.components.cve_catalog.products import identity
from modules.library.components.cve_catalog.risk import UnsupportedRiskSchema
from modules.library.components.intelligence import acquisition, service
from modules.workspace.components.store import Store
from modules.workspace.components.workspace_data_captures import validate_capture_data


def stores(tmp_path, *, day="2026-11-10"):
    reference, feeds = risk(tmp_path)
    feeds.epss = epss_bytes(day=day)
    reference.sync("epss")
    reference.sync("kev")
    catalog = Catalog(tmp_path / "working", clock=lambda: NOW)
    put(catalog, record(ID))
    return reference, catalog


@pytest.mark.parametrize(
    "day,elapsed,expected",
    [
        ("2026-11-10", timedelta(), False),
        ("2026-11-09", timedelta(), False),
        ("2026-11-08", timedelta(), True),
        ("2026-11-01", timedelta(), True),
        ("2026-11-10", timedelta(days=2, seconds=1), True),
    ],
)
def test_catalog_and_direct_risk_share_score_and_retrieval_freshness(
    tmp_path, day, elapsed, expected
):
    reference, catalog = stores(tmp_path, day=day)
    reference.clock = catalog.clock = lambda: NOW + elapsed
    direct = reference.get(ID)["epss"]
    listed = catalog.product(identity("php", "php"))["items"][0]["epss"]
    assert direct["stale"] is listed["stale"] is expected
    assert direct["score_date"] == listed["score_date"] == day
    assert listed["score_age_days"] == reference.status()["epss"]["score_age_days"]
    assert direct["score"] == listed["score"] == 0.7


def test_future_risk_schema_rejected_by_direct_and_attached_reads_without_changes(tmp_path):
    reference, catalog = stores(tmp_path)
    with closing(sqlite3.connect(reference.db)) as db, db:
        db.execute("PRAGMA user_version=2")
    before = hashlib.sha256(reference.db.read_bytes()).hexdigest()
    operations = [
        reference.status,
        lambda: reference.metadata("epss"),
        lambda: reference.get(ID),
        lambda: reference.bulk([ID]),
        lambda: reference.extract("epss:" + ID),
        lambda: reference.extract("kev"),
        lambda: reference.fingerprint("epss:" + ID),
        lambda: reference.put_metadata("enabled", True),
        catalog.products,
        lambda: catalog.product(identity("php", "php")),
        catalog.fields,
        lambda: catalog.field_records("weakness", "CWE-79"),
    ]
    for operation in operations:
        with pytest.raises(UnsupportedRiskSchema, match="newer application"):
            operation()
    assert hashlib.sha256(reference.db.read_bytes()).hexdigest() == before
    # The separately versioned NVD database remains available and intact.
    assert catalog.get(ID)["cve"]["id"] == ID
    assert catalog.search(ID)["total"] == 1
    with closing(sqlite3.connect(reference.db)) as db, db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
        assert db.execute("SELECT score FROM epss WHERE id=?", (ID,)).fetchone()[0] == 0.7


def test_future_risk_schema_is_visible_without_blocking_unrelated_workspace(tmp_path):
    reference, _ = stores(tmp_path)
    with closing(sqlite3.connect(reference.db)) as db, db:
        db.execute("PRAGMA user_version=2")
    app = create_app(tmp_path / "working", worker=False)
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/bootstrap").status_code == 200
        assert client.get("/api/cve-catalog/search", params={"q": ID}).status_code == 200
        unavailable = client.get("/api/cve-catalog/products")
        assert unavailable.status_code == 422
        assert "newer application" in unavailable.json()["detail"]
        state = client.get("/api/cve-catalog/status").json()["risk"]
        assert state["epss"]["stale"] and state["epss"]["last_error"]
        detail = client.get("/api/cve-catalog/records/" + ID)
        assert detail.status_code == 200
        assert detail.json()["risk"]["available"] is False
        assert detail.json()["risk"]["epss"] is None


@pytest.mark.parametrize("provider", ["epss", "kev", "program"])
def test_cache_payload_cannot_replace_facts_under_retained_proof(tmp_path, monkeypatch, provider):
    store = Store(tmp_path / "working")
    if provider == "epss":
        raw = {
            "status": "OK",
            "data": [{"cve": ID, "epss": 0.7, "percentile": 0.99, "date": "2026-11-10"}],
        }
        key, url = "epss:" + ID, acquisition.EPSS_URL + ID
        altered = deepcopy(raw)
        altered["data"][0]["epss"] = 0.1
    elif provider == "kev":
        raw = kev_raw()
        key, url = "kev", acquisition.KEV_URL
        altered = deepcopy(raw)
        altered["vulnerabilities"][0]["requiredAction"] = "Altered cached instruction"
    else:
        raw = program()
        key, url = "program:" + ID, "https://cveawg.mitre.org/api/cve/" + ID
        altered = deepcopy(raw)
        altered["containers"]["cna"]["descriptions"][0]["value"] = "Altered cached quotation"
    monkeypatch.setattr(acquisition, "_response_get", lambda *a, **kw: response(raw))
    first = acquisition.capture_json(store, key, url)
    path = store.path(first.source["record_path"])
    original_bytes = path.read_bytes()
    history = store.all("SELECT * FROM cache WHERE key NOT LIKE 'risk:%' ORDER BY key")
    validate_capture_data(store)
    with store.transaction() as db:
        db.execute("UPDATE cache SET payload=? WHERE key=?", (json.dumps(altered), "risk:" + key))
    monkeypatch.setattr(
        acquisition, "_response_get", lambda *a, **kw: pytest.fail("Unexpected network")
    )
    reused = acquisition.capture_json(store, key, url)
    assert reused.data == raw and reused.data != altered
    assert reused.source == first.source
    assert path.read_bytes() == original_bytes
    assert store.all("SELECT * FROM cache WHERE key NOT LIKE 'risk:%' ORDER BY key") == history
    assert (
        json.loads(store.one("SELECT payload FROM cache WHERE key=?", ("risk:" + key,))["payload"])
        == altered
    )
    with pytest.raises(ValueError, match="cached source differs"):
        validate_capture_data(store)
    # Equivalent JSON formatting is valid; verification never rewrites history.
    with store.transaction() as db:
        db.execute(
            "UPDATE cache SET payload=? WHERE key=?",
            (json.dumps(raw, indent=2, sort_keys=True), "risk:" + key),
        )
    validate_capture_data(store)


def test_verified_risk_decoder_rejects_wrong_identity_and_changed_bytes(tmp_path, monkeypatch):
    store = Store(tmp_path / "working")
    raw = program()
    monkeypatch.setattr(acquisition, "_response_get", lambda *a, **kw: response(raw))
    captured = acquisition.capture_json(
        store, "program:" + ID, "https://cveawg.mitre.org/api/cve/" + ID
    )
    with pytest.raises(ValueError, match="identifier|match"):
        acquisition.retained_risk_data(store, "program:CVE-2026-9999", captured.source)
    path = store.path(captured.source["record_path"])
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="integrity check"):
        acquisition.retained_risk_data(store, "program:" + ID, captured.source)


@pytest.mark.parametrize("transport", ["http", "local_catalog"])
@pytest.mark.parametrize(
    "damage,state",
    [
        ("description", "Analyzed"),
        ("cvss", "Analyzed"),
        ("state", "Analyzed"),
        ("description", "Rejected"),
    ],
)
def test_primary_summary_cache_is_checked_and_reacquired_without_changing_history(
    tmp_path, monkeypatch, transport, damage, state
):
    store = Store(tmp_path / "working")
    raw = nvd("Authoritative captured wording")
    raw["vulnerabilities"][0]["cve"]["vulnStatus"] = state
    monkeypatch.setattr(acquisition, "_wait_for_nvd", lambda *a, **kw: None)
    if transport == "local_catalog":
        local = catalog_record()
        local["cve"] = raw["vulnerabilities"][0]["cve"]
        monkeypatch.setattr(acquisition, "catalog_record", lambda *a, **kw: local)
        monkeypatch.setattr(
            acquisition, "_response_get", lambda *a, **kw: pytest.fail("Unexpected network")
        )
    else:
        monkeypatch.setattr(acquisition, "_response_get", lambda *a, **kw: response(raw))
    first = service.verify(store, ID)
    assert service.verify(store, ID)["revision_id"] == first["revision_id"]
    capture = store.path(first["record_path"])
    original_bytes = capture.read_bytes()
    version_key = "cve-version:" + first["revision_id"]
    original_version = store.one("SELECT * FROM evidence_revisions WHERE key=?", (version_key,))
    validate_capture_data(store)
    altered = deepcopy(first)
    altered[damage] = {
        "description": "Unrelated cached quotation",
        "cvss": 0.1,
        "state": "REJECTED",
    }[damage]
    with store.transaction() as db:
        db.execute(
            "UPDATE cache SET payload=? WHERE key=?", (json.dumps(altered), "cve-reference:" + ID)
        )
    with pytest.raises(ValueError, match="summary differs"):
        validate_capture_data(store)
    recovered = service.verify(store, ID)
    assert recovered[damage] == first[damage]
    assert recovered["revision_id"] != first["revision_id"]
    assert recovered["verification_status"] == first["verification_status"]
    assert capture.read_bytes() == original_bytes
    assert (
        store.one("SELECT * FROM evidence_revisions WHERE key=?", (version_key,))
        == original_version
    )
    validate_capture_data(store)


def test_failed_refresh_cannot_fall_back_to_an_altered_primary_summary(tmp_path, monkeypatch):
    store = Store(tmp_path / "working")
    monkeypatch.setattr(acquisition, "_wait_for_nvd", lambda *a, **kw: None)
    monkeypatch.setattr(acquisition, "_response_get", lambda *a, **kw: response(nvd()))
    first = service.verify(store, ID)
    altered = {**first, "description": "Altered cached quotation"}
    with store.transaction() as db:
        db.execute(
            "UPDATE cache SET payload=? WHERE key=?", (json.dumps(altered), "cve-reference:" + ID)
        )
    monkeypatch.setattr(acquisition, "_response_get", lambda *a, **kw: response({}, status=503))
    result = service.verify(store, ID, refresh=True)
    assert result["description"] != altered["description"]
    assert result["verification_status"] == "unavailable"
    assert result["from_cache"] is False
