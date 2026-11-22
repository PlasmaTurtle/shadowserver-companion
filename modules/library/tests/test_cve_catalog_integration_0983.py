"""Catalog reads become immutable evidence only on explicit CVE retrieval."""

from tests.support.qualification import registry_factory, capture_website

from copy import deepcopy
import hashlib
import json
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient as UnauthenticatedClient
from tests.session_helpers import TestClient

from modules.workspace.components import api as api_module
from modules.library.components.intelligence import acquisition, service
from modules.workspace.components.store import Store
from modules.library.components.cve_catalog import Catalog
from modules.library.tests.support.cve_sources import ID, nvd, response
from tests.support.workbench import FakeRegistry, import_rows, observations, ready
from modules.workspace.components.workspace_data import export_workspace

from modules.library.tests.support.cve_catalog import (
    catalog_record,
)


def test_local_record_retains_provenance_and_does_not_call_api(tmp_path, monkeypatch):
    store = Store(tmp_path / "working")
    record = catalog_record()
    monkeypatch.setattr(acquisition, "catalog_record", lambda *_: record)
    monkeypatch.setattr(acquisition, "_wait_for_nvd", lambda *_: pytest.fail("API budget used"))
    result = service.verify(store, ID, refresh=True)
    assert result["description"] == "Catalog wording" and result["from_catalog"]
    assert result["http_status"] is None and result["stale"] is False
    source = result["sources"][0]
    assert source["transport"] == "local_catalog" and source["network_request"] is False
    assert source["url"] == record["source"]["url"]
    assert source["retrieved_at"] == record["source"]["retrieved_at"]
    assert source["extracted_at"] != source["retrieved_at"]
    assert source["catalog_source"]["feed_sha256"] == "a" * 64
    body = store.path(result["record_path"]).read_bytes()
    assert hashlib.sha256(body).hexdigest() == result["body_sha256"]
    assert json.loads(body)["vulnerabilities"][0]["cve"] == record["cve"]
    assert result["acquisition"][0]["network_request"] is False
    assert result["acquisition"][0]["url"] == record["source"]["url"]


def test_catalog_update_bypasses_reference_ttl_without_rewriting_evidence(tmp_path, monkeypatch):
    store = Store(tmp_path / "working")
    current = {"record": catalog_record("Original catalog wording")}
    monkeypatch.setattr(acquisition, "catalog_record", lambda *_: current["record"])
    first = service.verify(store, ID)
    original = store.path(first["record_path"]).read_bytes()
    assert service.verify(store, ID)["revision_id"] == first["revision_id"]
    current["record"] = catalog_record("Revised catalog wording")
    second = service.verify(store, ID)
    assert second["revision_id"] != first["revision_id"]
    assert second["description"] == "Revised catalog wording"
    assert store.path(first["record_path"]).read_bytes() == original
    prior = json.loads(
        store.one(
            "SELECT payload FROM evidence_revisions WHERE key=?",
            ("cve-version:" + first["revision_id"],),
        )["payload"]
    )
    assert prior["description"] == "Original catalog wording"
    assert store.one("SELECT COUNT(*) AS n FROM cases")["n"] == 0


def test_catalog_changes_preserve_frozen_case_and_selected_capture_in_backup(tmp_path, monkeypatch):
    current = {"record": catalog_record("Wording selected for the frozen notification")}
    monkeypatch.setattr(acquisition, "catalog_record", lambda *_: current["record"])
    monkeypatch.setattr(api_module, "enrich", service.verify)
    app = api_module.create_app(
        tmp_path / "working",
        worker=False,
        report_processes=False,
        attribution_factory=registry_factory(FakeRegistry),
        capture=capture_website,
    )

    with TestClient(app) as client:
        sender = client.get("/api/bootstrap").json()["settings"]
        sender["analyst_name"] = "Test Analyst"
        assert client.put("/api/settings", json=sender).status_code == 200
        import_rows(client, app, [{**observations()[0], "ip": "8.8.8.8", "tag": ID}])
        lead_id = client.get("/api/leads").json()[0]["id"]
        lead = client.get("/api/leads/" + lead_id).json()
        fetched = client.post("/api/cves/" + ID + "/retrieve")
        assert fetched.status_code == 200, fetched.text
        fields = deepcopy(lead["draft"])
        fields["cve_records"] = [fetched.json()]
        adopted = client.put(
            "/api/leads/" + lead_id + "/draft?case_id=" + lead["case_id"],
            json={"expected_revision": lead["draft_revision"], "fields": fields},
        )
        assert adopted.status_code == 200, adopted.text
        frozen = ready(client, lead_id)
        before = app.state.store.one("SELECT * FROM cases WHERE id=?", (frozen["case_id"],))
        reviews = deepcopy(frozen["section_reviews"])
        capture = fetched.json()["record_path"]
        original = app.state.store.path(capture).read_bytes()
        current["record"] = catalog_record("New catalog wording after daily synchronization")
        updated = client.post("/api/cves/" + ID + "/retrieve")
        assert (
            updated.status_code == 200
            and updated.json()["description"] != fetched.json()["description"]
        )
        after = client.get("/api/cases/" + frozen["case_id"]).json()
        assert app.state.store.one("SELECT * FROM cases WHERE id=?", (frozen["case_id"],)) == before
        assert after["section_reviews"] == reviews
        assert all(row["status"] == "validated" for row in after["section_reviews"])
        assert after["draft"]["cve_records"][0]["description"] == fetched.json()["description"]
        assert app.state.store.path(capture).read_bytes() == original
        sidecar = tmp_path / "working-reference" / "nvd"
        sidecar.mkdir(parents=True, exist_ok=True)
        (sidecar / "catalog-only-sentinel.txt").write_text("Reference catalog is not case evidence")
        archive = export_workspace(app.state.store)
        try:
            with ZipFile(archive) as saved:
                assert saved.read("data/" + capture) == original
                assert not any(
                    "catalog-only-sentinel" in name or "-reference/" in name
                    for name in saved.namelist()
                )
        finally:
            archive.unlink()


def test_stale_catalog_remains_explicit_even_through_workspace_cache(tmp_path, monkeypatch):
    store = Store(tmp_path / "working")
    current = {"record": catalog_record()}
    monkeypatch.setattr(acquisition, "catalog_record", lambda *_: current["record"])
    first = service.verify(store, ID)
    current["record"] = catalog_record(stale=True)
    later = service.verify(store, ID)
    assert later["stale"] is True and later["from_cache"] is True
    assert later["retrieved_at"] == first["retrieved_at"]
    assert later["revision_id"] == first["revision_id"]


@pytest.mark.parametrize("record", [None, {"cve": {}, "source": {}}])
def test_missing_or_unusable_catalog_uses_existing_api(tmp_path, monkeypatch, record):
    calls = []
    monkeypatch.setattr(acquisition, "catalog_record", lambda *_: record)
    monkeypatch.setattr(acquisition, "_wait_for_nvd", lambda *a, **k: None)

    def remote(url, **kwargs):
        calls.append(url)
        return response(nvd("Existing API fallback"))

    monkeypatch.setattr(acquisition, "_response_get", remote)
    result = service.verify(Store(tmp_path / "working"), ID)
    assert calls == [acquisition.NVD_URL + ID]
    assert result["description"] == "Existing API fallback"
    assert result["http_status"] == 200


def test_tampered_catalog_record_is_not_promoted_to_evidence(tmp_path, monkeypatch):
    store = Store(tmp_path / "working")
    catalog = Catalog(store.root)
    original = catalog_record()
    with catalog.connection() as db:
        catalog.upsert(db, original["cve"], original["source"])
    assert catalog.get(ID)["cve"]["descriptions"][1]["value"] == "Catalog wording"
    with catalog.connection() as db:
        row = db.execute("SELECT raw_json FROM records WHERE id=?", (ID,)).fetchone()
        altered = json.loads(row[0])
        altered["descriptions"][1]["value"] = "Tampered local wording"
        db.execute("UPDATE records SET raw_json=? WHERE id=?", (json.dumps(altered), ID))
    monkeypatch.setattr(acquisition, "_wait_for_nvd", lambda *a, **k: None)
    calls = []

    def remote(url, **kwargs):
        calls.append(url)
        return response(nvd("Intact API fallback wording"))

    monkeypatch.setattr(acquisition, "_response_get", remote)
    result = service.verify(store, ID)
    assert calls == [acquisition.NVD_URL + ID]
    assert result["description"] == "Intact API fallback wording"
    assert not result.get("from_catalog")
    assert b"Tampered local wording" not in store.path(result["record_path"]).read_bytes()


class FakeCatalog:
    def __init__(self):
        self.enabled = False
        self.searches = []

    def set_enabled(self, enabled):
        self.enabled = enabled

    def search(self, **kwargs):
        self.searches.append(kwargs)
        return {"items": [], "total": 0, "limit": kwargs["limit"], "offset": kwargs["offset"]}

    def get(self, identifier):
        return catalog_record() if identifier == ID else None


class FakeManager:
    def __init__(self, catalog, *, risk=None):
        self.catalog = catalog
        self.risk = risk
        self.started = self.closed = self.syncs = self.cancels = 0

    def start(self):
        self.started += 1

    def close(self):
        self.closed += 1

    def status(self):
        return {"total": 0, "enabled": self.catalog.enabled, "job": {"status": "idle"}}

    def sync(self):
        self.syncs += 1
        self.catalog.set_enabled(True)
        return self.status()

    def cancel(self):
        self.cancels += 1
        return self.status()


@pytest.fixture
def manager_factory(monkeypatch):
    monkeypatch.setattr(api_module, "Catalog", lambda root: FakeCatalog())
    monkeypatch.setattr(api_module, "CatalogManager", FakeManager)
    monkeypatch.setattr(api_module.IntakeService, "start", lambda self: None)
    import modules.workspace.components.demo

    monkeypatch.setattr(modules.workspace.components.demo, "seed_demo", lambda *a: None)


def test_catalog_routes_are_authenticated_and_reads_do_not_sync(
    tmp_path, manager_factory, monkeypatch
):
    app = api_module.create_app(tmp_path / "working", worker=False)
    with UnauthenticatedClient(app, base_url="http://127.0.0.1") as client:
        assert client.get("/api/cve-catalog/status").status_code == 401
        assert client.post("/api/cve-catalog/sync").status_code == 401
    with TestClient(app) as client:
        assert client.get("/api/cve-catalog/status").json()["total"] == 0
        assert client.get("/api/cve-catalog/search?q=Exchange&severity=critical").status_code == 200
        assert app.state.cve_catalog.catalog.searches[-1]["severity"] == "CRITICAL"
        assert client.get("/api/cve-catalog/records/" + ID).json()["cve"]["id"] == ID
        assert client.get("/api/cve-catalog/records/CVE-2025-99999").status_code == 404
        assert client.get("/api/cve-catalog/search?limit=500").status_code == 422
        assert client.get("/api/cve-catalog/search?severity=bad").status_code == 422
        assert app.state.cve_catalog.syncs == 0
        assert client.post("/api/cve-catalog/sync").json()["enabled"] is True
        assert app.state.cve_catalog.syncs == 1
        assert (
            client.post("/api/cve-catalog/settings", json={"enabled": False}).json()["enabled"]
            is False
        )
        assert client.post("/api/cve-catalog/settings", json={"enabled": "yes"}).status_code == 422
        assert client.post("/api/cve-catalog/cancel").status_code == 200
        assert app.state.cve_catalog.cancels == 1
        original_status = app.state.cve_catalog.manager.status
        monkeypatch.setattr(
            app.state.cve_catalog.manager, "status", lambda: {**original_status(), "running": True}
        )
        assert client.post("/api/cve-catalog/settings", json={"enabled": True}).status_code == 409
        assert app.state.cve_catalog.catalog.enabled is False


@pytest.mark.parametrize(
    "worker,demo,preview,starts",
    [
        (False, False, False, 0),
        (True, True, False, 0),
        (True, False, True, 0),
        (True, False, False, 1),
    ],
)
def test_scheduler_runs_only_in_normal_working_application(
    tmp_path, manager_factory, worker, demo, preview, starts
):
    app = api_module.create_app(tmp_path / "working", worker=worker, demo=demo, preview=preview)
    manager = app.state.cve_catalog
    with TestClient(app):
        assert manager.started == starts
        assert manager.syncs == 0
    assert manager.closed == 1


def test_optional_catalog_initialization_failure_cannot_block_workspace(
    tmp_path, manager_factory, monkeypatch
):
    def fail(_root):
        raise PermissionError("Synthetic reference storage is unavailable")

    monkeypatch.setattr(api_module, "Catalog", fail)
    app = api_module.create_app(tmp_path / "working", worker=False)
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/bootstrap").status_code == 200
        assert client.get("/api/cve-catalog/status").json()["last_error"]
        assert client.post("/api/cve-catalog/sync").status_code == 422
        monkeypatch.setattr(api_module, "Catalog", lambda root: FakeCatalog())
        assert client.post("/api/cve-catalog/sync").json()["enabled"] is True


def test_optional_scheduler_start_failure_cannot_block_workspace(
    tmp_path, manager_factory, monkeypatch
):
    def fail(_self):
        raise RuntimeError("Synthetic worker startup failure")

    monkeypatch.setattr(FakeManager, "start", fail)
    app = api_module.create_app(tmp_path / "working", worker=True)
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/bootstrap").status_code == 200
        assert client.get("/api/cve-catalog/status").json()["last_error"]


def test_corrupt_optional_catalog_keeps_core_health_and_working_data_available(tmp_path):
    root = tmp_path / "working"
    folder = tmp_path / "working-reference" / "nvd"
    folder.mkdir(parents=True)
    (folder / "catalog.sqlite3").write_bytes(b"Synthetic invalid SQLite catalog")
    app = api_module.create_app(root, worker=False)
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/bootstrap").status_code == 200
        assert client.get("/api/cve-catalog/status").json()["last_error"]
        assert acquisition.catalog_record(app.state.store, ID) is None
        assert app.state.store.settings()
