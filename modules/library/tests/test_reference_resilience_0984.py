"""Independent regression checks for optional local reference data under updates."""

import hashlib
import json

from tests.session_helpers import TestClient
from modules.workspace.components import api
from modules.library.components.cve_catalog import Catalog
from modules.library.tests.support.catalog_products import put, record
from modules.library.tests.support.local_risk import ID, epss_bytes, kev_raw, risk


def test_epss_lookup_keeps_row_and_feed_provenance_in_one_snapshot(tmp_path, monkeypatch):
    store, feeds = risk(tmp_path)
    store.sync("epss")
    old_hash = hashlib.sha256(feeds.epss).hexdigest()
    old_state = store._state
    updated = False

    def state(provider, *, db=None):
        nonlocal updated
        value = old_state(provider, db=db)
        if provider == "kev" and db is not None and not updated:
            updated = True
            feeds.epss = epss_bytes("0.2", day="2026-11-11")
            store.sync("epss")
        return value

    monkeypatch.setattr(store, "_state", state)
    score = store.get(ID)["epss"]
    assert updated
    assert score["source"]["sha256"] == old_hash
    assert score["score"] == 0.7
    assert score["score_date"] == score["source"]["score_date"]


def test_kev_extract_keeps_payload_and_feed_provenance_in_one_snapshot(tmp_path, monkeypatch):
    store, feeds = risk(tmp_path)
    store.sync("kev")
    old_hash = hashlib.sha256(feeds.kev).hexdigest()
    old_state = store._state
    updated = False

    def state(provider, *, db=None):
        nonlocal updated
        value = old_state(provider, db=db)
        if provider == "kev" and db is not None and not updated:
            updated = True
            payload = kev_raw()
            payload["catalogVersion"] = "2026.11.11"
            payload["dateReleased"] = "2026-11-11T02:00:00Z"
            payload["vulnerabilities"][0]["requiredAction"] = "New action"
            feeds.kev = json.dumps(payload).encode()
            store.sync("kev")
        return value

    monkeypatch.setattr(store, "_state", state)
    extracted = store.extract("kev")
    assert updated
    assert extracted["source"]["sha256"] == old_hash
    assert extracted["data"]["catalogVersion"] == "2026.11.10"
    assert extracted["data"]["catalogVersion"] == extracted["source"]["catalog_version"]


def test_recent_download_does_not_make_old_epss_scores_fresh(tmp_path):
    store, feeds = risk(tmp_path)
    feeds.epss = epss_bytes(day="2026-10-01")
    store.sync("epss")
    assert store.status()["epss"]["stale"] is True
    assert store.get(ID)["epss"]["stale"] is True


def test_incomplete_optional_kev_index_cannot_hide_nvd_kev(tmp_path):
    store, _ = risk(tmp_path)
    store.sync("kev")
    catalog = Catalog(tmp_path / "working")
    put(catalog, record(ID, kev=True))
    assert catalog.products(scope="kev")["total"] == 1
    with store.connection(write=True) as db:
        db.execute("DELETE FROM kev")
    assert catalog.products(scope="kev")["total"] == 1


def test_corrupt_optional_risk_database_keeps_workspace_and_cve_record_available(tmp_path):
    root = tmp_path / "working"
    catalog = Catalog(root)
    put(catalog, record(ID, kev=True))
    (catalog.folder / "risk.sqlite3").write_bytes(b"Synthetic invalid SQLite risk sidecar")
    app = api.create_app(root, worker=False)
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/bootstrap").status_code == 200
        status = client.get("/api/cve-catalog/status").json()
        assert status["total"] == 1
        assert status["risk"]["epss"]["last_error"]
        detail = client.get("/api/cve-catalog/records/" + ID)
        assert detail.status_code == 200
        assert detail.json()["cve"]["id"] == ID
        assert detail.json()["risk"]["available"] is False
        assert detail.json()["risk"]["epss"] is None
        assert detail.json()["risk"]["kev"] is None
        assert detail.json()["risk"]["error"]
