"""Saved research survives reopen and conflicts; grouped search isolates data failures."""

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


def search_groups(client, query):
    response = client.get("/api/library/search", params={"q": query})
    assert response.status_code == 200, response.text
    return response.json()["groups"]


def test_reviewed_guide_discovery_offline_and_exact_lookup(tmp_path):
    from modules.library.components.reviewed_guides import guides

    store = Workspace(tmp_path / "work")
    with client_for(store, SimpleNamespace(catalog=Catalog(store.root))) as client:
        assert client.get("/api/library/guides").json() == {"items": guides()}
        for query in ("scan_rdp", "Accessible RDP"):
            hits = search_groups(client, query)["guides"]["items"]
            report = next(hit for hit in hits if hit["kind"] == "report")
            guide = client.get("/api/library/guides/" + report["id"]).json()
            assert guide["sources"][0]["public_url"].startswith("https://www.shadowserver.org/")
            assert guide["intro"] and "scan_rdp" in guide["report_types"]
        context = client.get("/api/library/guides/scan_http").json()
        condition = client.get("/api/library/guides", params={"q": "rdp_protocol=RDP"}).json()[
            "items"
        ]
        assert len(condition) == 1 and condition[0]["match_rules"][0]["fields"] == {
            "rdp_protocol": "RDP"
        }
        assert context["kind"] == "context" and context["sources"]
        assert client.get("/api/library/guides/does-not-exist").status_code == 404
        assert client.get("/api/library/guides", params={"q": "_%"}).json() == {"items": []}


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


def test_search_distinguishes_absent_and_empty_catalogs_from_a_genuine_miss(tmp_path):
    store = Workspace(tmp_path / "work")
    catalog = Catalog(store.root)
    with client_for(store, SimpleNamespace(catalog=catalog)) as client:

        def expect_empty_catalog():
            groups = search_groups(client, "Detected CVE")
            for group in (groups["cves"], groups["products"]):
                assert group["items"] == [] and group["total"] == 0
                assert group["error"] is None and "catalog download" in group["notice"]
            assert groups["explainers"]["items"][0]["id"] == "cve"
            assert groups["explainers"]["notice"] is None

        expect_empty_catalog()
        assert not catalog.folder.exists()
        catalog.set_enabled(False)  # A catalog can exist before its first record is committed.
        expect_empty_catalog()

        put(catalog, record())
        for query in ("No such reference", "CVE-typo", "%"):
            for group in search_groups(client, query).values():
                assert group == {"items": [], "total": 0, "error": None, "notice": None}


def test_search_keeps_partial_product_results_and_independent_cve_hits(tmp_path):
    store = Workspace(tmp_path / "work")
    catalog = Catalog(store.root)
    put(catalog, record())
    pending = record("CVE-2026-9999")
    pending["affected"][0]["affectedData"][0]["product"] = "Pending product"
    put(catalog, pending)
    with catalog.connection() as db:
        db.execute("DELETE FROM catalog_indexed WHERE cve_id=?", (pending["id"],))
    with client_for(store, SimpleNamespace(catalog=catalog)) as client:
        products = search_groups(client, "PHP")["products"]
        assert products["total"] == 1 and products["items"][0]["id"].startswith("product:")
        assert products["error"] is None and "1 of 2" in products["notice"]
        missing = search_groups(client, "Pending")["products"]
        assert missing["total"] == 0 and missing["notice"] == products["notice"]
        assert search_groups(client, pending["id"])["cves"]["items"][0]["id"] == pending["id"]

        with catalog.connection() as db:
            db.execute("DROP TABLE catalog_product_cves")
        groups = search_groups(client, pending["id"])
        assert groups["products"]["error"] and groups["products"]["notice"] is None
        assert groups["cves"]["items"][0]["id"] == pending["id"]
        assert groups["cves"]["error"] is None and groups["cves"]["notice"] is None


def test_product_coverage_and_results_share_one_committed_snapshot(tmp_path, monkeypatch):
    catalog = Catalog(tmp_path / "work")
    put(catalog, record())
    new_product = record("CVE-2026-9999")
    new_product["affected"][0]["affectedData"][0]["product"] = "New product"
    original = catalog._risk_sql

    def publish_after_coverage_read(db):
        put(catalog, new_product)
        return original(db)

    with monkeypatch.context() as patch:
        patch.setattr(catalog, "_risk_sql", publish_after_coverage_read)
        first = catalog.products("New product", scope="all")
    assert first["index"]["total"] == 1 and first["total"] == 0
    second = catalog.products("New product", scope="all")
    assert second["index"]["total"] == 2 and second["total"] == 1
