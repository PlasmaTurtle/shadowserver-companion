"""Archive capabilities reach Observatory without raw/canonical reconstruction."""

import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.accretion.components.dark_matter_store import DarkMatterStore
from modules.observatory.components.eclipse import Eclipse
from modules.observatory.components.routes.eclipse import register
from modules.workspace.components.store import Store


def populate(archive):
    source = {
        "import_id": "report",
        "sha256": "a" * 64,
        "name": "scan_http_vulnerable.csv",
        "report_type": "scan_http_vulnerable",
    }
    return archive.record_batch(
        source,
        [
            {
                "sheet": "CSV",
                "row": 2,
                "fields": {
                    "ip": "broken",
                    "http_code": "503",
                    "future_column": "preserved",
                    "region": "Outside configured scope",
                },
            },
            {
                "sheet": "CSV",
                "row": 3,
                "fields": {
                    "hostname": "example.com",
                    "ip": "8.8.8.8",
                    "http_code": "200",
                    "port": "0443",
                    "timestamp": "2026-11-21 12:00:00",
                    "tag": "CVE-2026-12345",
                },
            },
        ],
        stage="filter",
        reason="invalid_or_out_of_scope",
    )["record_ids"]


def client_for(archive):
    app = FastAPI()
    register(app, eclipse=SimpleNamespace(store=SimpleNamespace(dark_matter=archive)))
    return TestClient(app)


def test_field_queries_and_details_preserve_unusable_rows(tmp_path):
    archive = DarkMatterStore(tmp_path)
    identities = populate(archive)
    client = client_for(archive)
    response = client.get(
        "/api/dark-matter",
        params={"filters": json.dumps([{"field": "http_code", "op": "gte", "value": 500}])},
    )
    assert response.status_code == 200
    record = response.json()["items"][0]
    assert record["record_id"] == identities[0]
    assert record["raw_fields"]["future_column"] == "preserved"
    assert record["normalized_fields"]["http_code"] == 503
    assert "ip" in record["errors"]
    assert (
        client.get(
            "/api/dark-matter",
            params={"filters": json.dumps([{"field": "hostname", "op": "missing"}])},
        ).json()["total"]
        == 1
    )
    assert (
        client.get(
            "/api/dark-matter", params={"filters": json.dumps([{"field": "ip", "op": "invalid"}])}
        ).json()["total"]
        == 1
    )
    detail = client.get("/api/dark-matter/" + identities[0]).json()
    assert detail["outcomes"][0]["stage"] == "filter"
    assert client.get("/api/dark-matter/not-found").status_code == 404


def test_catalog_facets_and_invalid_queries(tmp_path):
    archive = DarkMatterStore(tmp_path)
    populate(archive)
    client = client_for(archive)
    catalog = client.get("/api/dark-matter/fields").json()
    assert len(catalog["fields"]) >= 746
    assert any(field["name"] == "future_column" for field in catalog["fields"])
    assert client.get("/api/dark-matter/facets", params={"field": "http_code"}).json()["items"]
    for predicates in ("{", "{}", '[{"field":"port","op":"arbitrary_sql"}]'):
        assert client.get("/api/dark-matter", params={"filters": predicates}).status_code == 422
    assert client.get("/api/dark-matter", params={"limit": 101}).status_code == 422


def test_archive_projection_is_read_only_and_uses_source_identity(tmp_path):
    store = Store(tmp_path)
    identities = populate(store.dark_matter)
    eclipse = Eclipse(store)
    first_revision = store.dark_matter.revision()
    snapshot = eclipse.snapshot()
    assert {row["id"] for row in snapshot["observations"]} == set(identities)
    assert all(
        row["asset_id"] is None and row["finding_ids"] == [] for row in snapshot["observations"]
    )
    invalid = eclipse.observation(identities[0])
    assert invalid["fields"]["future_column"] == "preserved"
    assert invalid["latitude"] is None and invalid["ip_valid"] is False
    assert invalid["admitted"] is False and invalid["normalization_errors"]["ip"]
    view = eclipse.view(intake="dark_matter", records_only=True)
    assert view["records"]["total"] == 2
    assert store.dark_matter.revision() == first_revision
    assert store.one("SELECT count(*) AS n FROM awareness_assets")["n"] == 0
    assert store.one("SELECT count(*) AS n FROM awareness_findings")["n"] == 0


def test_archive_revision_invalidates_observatory_selection(tmp_path):
    store = Store(tmp_path)
    identities = populate(store.dark_matter)
    eclipse = Eclipse(store)
    first = eclipse.view(intake="dark_matter", records_only=True)
    store.dark_matter.record_outcome(
        [identities[1]], import_id="report", stage="associate", outcome="promoted"
    )
    second = eclipse.view(intake="dark_matter", records_only=True)
    assert first["records"]["total"] == 2
    assert second["records"]["total"] == 1
    assert first["revision"] != second["revision"]
