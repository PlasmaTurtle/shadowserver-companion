"""Saved research survives reopen and conflicts; grouped search isolates data failures."""

import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.library.components.cve_catalog import Catalog
from modules.library.components.routes.research import register
from modules.library.tests.support.catalog_products import put, record
from modules.workspace.components.workspace import Workspace


def client_for(store, catalog):
    app = FastAPI()
    register(app, store=store, catalog=catalog)
    return TestClient(app)


def test_saved_views_round_trip_and_refuse_stale_replacement(tmp_path):
    store = Workspace(tmp_path / "work")
    catalog = SimpleNamespace(catalog=Catalog(store.root))
    with client_for(store, catalog) as client:
        body = {
            "name": "All mail findings",
            "selection": {"view": "cves", "cveQuery": "mail", "cveSeverity": ""},
        }
        created = client.post("/api/library/views", json=body).json()
        duplicate_name = client.post(
            "/api/library/views", json={**body, "selection": {"view": "cves", "cveQuery": "other"}}
        ).json()
        assert duplicate_name["id"] != created["id"]
        path = "/api/library/views/" + created["id"]
        updated = client.put(path, json={**body, "name": "Renamed", "expected_revision": 1})
        assert updated.status_code == 200
        assert updated.json()["revision"] == 2
        assert client.put(path, json={**body, "expected_revision": 1}).status_code == 409
        assert client.delete(path + "?expected_revision=1").status_code == 409
    reopened = Workspace(store.root)
    with client_for(reopened, catalog) as client:
        saved = next(v for v in client.get("/api/library/views").json() if v["id"] == created["id"])
        assert saved["name"] == "Renamed"
        assert saved["selection"]["cveSeverity"] == ""
        assert saved["selection"]["cveQuery"] == "mail"
        assert client.delete(path + "?expected_revision=2").status_code == 200


def test_browser_view_import_is_idempotent_and_does_not_replace_user_edits(tmp_path):
    store = Workspace(tmp_path / "work")
    with client_for(store, SimpleNamespace(catalog=Catalog(store.root))) as client:
        body = {"views": [{"name": "Legacy", "selection": {"view": "cves", "cveSeverity": ""}}]}
        initial = client.post("/api/library/views/import", json=body).json()
        assert len(initial) == 1
        view = initial[0]
        client.put(
            "/api/library/views/" + view["id"],
            json={"name": "Edited", "selection": view["selection"], "expected_revision": 1},
        )
        repeated = client.post("/api/library/views/import", json=body).json()
        assert len(repeated) == 1 and repeated[0]["name"] == "Edited"
        assert repeated[0]["revision"] == 2
        assert (
            client.post(
                "/api/library/views", json={"name": "Bad", "selection": {"schema_version": 2}}
            ).status_code
            == 422
        )


def test_research_search_returns_typed_results_and_keeps_explainers_if_catalog_fails(
    tmp_path, monkeypatch
):
    store = Workspace(tmp_path / "work")
    catalog = Catalog(store.root)
    put(catalog, record())
    with client_for(store, SimpleNamespace(catalog=catalog)) as client:
        result = client.get("/api/library/search?q=CVE-2026-1234").json()
        assert result["groups"]["cves"]["items"][0]["id"] == "CVE-2026-1234"
        assert all("items" in group and "error" in group for group in result["groups"].values())

        def unavailable(*args, **kwargs):
            raise ValueError("Synthetic optional catalog failure")

        monkeypatch.setattr(catalog, "search", unavailable)
        monkeypatch.setattr(catalog, "products", unavailable)
        result = client.get("/api/library/search?q=Detected%20CVE").json()
        assert result["groups"]["cves"]["error"]
        assert result["groups"]["products"]["error"]
        assert result["groups"]["explainers"]["items"][0]["id"] == "cve"
        assert result["groups"]["explainers"]["error"] is None
        assert client.get("/api/library/search?q=_%25").json()["groups"]["explainers"]["total"] == 0
        with store.read_snapshot() as db:
            assert db.execute("SELECT count(*) FROM cases").fetchone()[0] == 0
