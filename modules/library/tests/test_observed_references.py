"""Workspace reference counts preserve source identity, scope and coverage."""

import sqlite3

from fastapi.testclient import TestClient

from modules.accretion.components.awareness import associate
from modules.library.tests.support.catalog_outreach import CRITICAL_KEV, seed_catalog
from tests.support.workbench import app, client, csv_bytes, import_rows, observations


URL = "/api/library/observed-references"


def archive_rows(app, rows, digest="a"):
    return app.state.store.dark_matter.record_batch(
        {
            "import_id": "reference-fixture-" + digest,
            "sha256": digest * 64,
            "name": "scan_http_vulnerable.csv",
        },
        [{"sheet": "CSV", "row": i, "fields": fields} for i, fields in enumerate(rows, 2)],
        stage="filter",
        reason="invalid_or_out_of_scope",
    )


def test_empty_auth_failure_and_query_bounds(client, app):
    assert TestClient(app, base_url="http://127.0.0.1").get(URL).status_code == 401
    result = client.get(URL)
    assert result.status_code == 200
    data = result.json()
    assert data["observation_count"] == 0 and data["coverage_complete"]
    assert data["warnings"] == []
    for key in ("cves", "products"):
        assert data[key] == {
            "items": [],
            "total": 0,
            "limit": 10,
            "offset": 0,
            "observations_with_value": 0,
        }
    for query in ("limit=101", "limit=0", "cve_offset=-1", "product_offset=-1"):
        assert client.get(URL + "?" + query).status_code == 422


def test_openapi_describes_nested_count_and_coverage_contract(app):
    spec = app.openapi()
    schemas = spec["components"]["schemas"]
    response = spec["paths"][URL]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ]

    def resolve(reference):
        return schemas[reference["$ref"].rsplit("/", 1)[1]]

    summary = resolve(response)
    assert set(summary["required"]) == {
        "revision",
        "observation_count",
        "coverage_complete",
        "warnings",
        "cves",
        "products",
    }
    assert summary["properties"]["observation_count"]["minimum"] == 0
    assert summary["properties"]["products"] == summary["properties"]["cves"]
    page = resolve(summary["properties"]["cves"])
    assert set(page["required"]) == {"items", "total", "observations_with_value", "limit", "offset"}
    items = page["properties"]["items"]
    assert items["maxItems"] == 100
    item = resolve(items["items"])
    assert set(item["required"]) == {"value", "count"}
    assert item["properties"]["count"]["minimum"] == 1


def test_distinct_observations_and_explicit_products_across_intake_and_archive(client, app):
    first, second = "CVE-2025-1234", "CVE-2025-12345"
    row = {
        **observations()[0],
        "tag": first,
        "version": "Widget/1.0;Widget/2.0",
        "product": "Gateway",
        "hostname": "unit.example.com",
        "ip": "8.8.8.8",
    }
    import_rows(client, app, [row, {**row, "tag": second}], start_notifications=False)
    archive_rows(
        app,
        [
            {"tag": first.lower() + ";" + first + ";X-" + second, "product": "gateway"},
            {"tag": second, "service": "HTTP"},
            {"tag": "unrelated", "product": "unknown"},
        ],
    )
    result = client.get(URL).json()
    assert result["coverage_complete"] and not result["warnings"]
    assert result["observation_count"] == 4
    assert result["cves"]["observations_with_value"] == 3
    assert result["cves"]["items"] == [{"value": first, "count": 2}, {"value": second, "count": 2}]
    assert result["products"]["observations_with_value"] == 3
    assert result["products"]["items"] == [
        {"value": "Gateway", "count": 2},
        {"value": "HTTP", "count": 1},
        {"value": "Widget", "count": 1},
    ]
    page = client.get(URL, params={"limit": 1, "cve_offset": 1, "product_offset": 2}).json()
    assert page["revision"] == result["revision"]
    for name, index in (("cves", 1), ("products", 2)):
        assert page[name]["total"] == len(result[name]["items"])
        assert page[name]["items"] == result[name]["items"][index : index + 1]
    archive_rows(app, [{"tag": first}], digest="b")
    fresh = client.get(URL).json()
    assert fresh["revision"] != page["revision"] and fresh["observation_count"] == 5
    assert fresh["cves"]["items"][0]["count"] == 3


def test_archive_limit_and_unavailable_are_explicit(client, app, monkeypatch):
    monkeypatch.setattr("modules.observatory.components.eclipse.MAX_RECORDS", 1)
    archive_rows(app, [{"tag": "CVE-2025-1234"}, {"tag": "CVE-2025-4567"}])
    data = client.get(URL).json()
    assert data["observation_count"] == 1 and not data["coverage_complete"] and data["warnings"]

    def unavailable():
        raise sqlite3.OperationalError("private storage path")

    monkeypatch.setattr(app.state.store.dark_matter, "revision", unavailable)
    failed = client.get(URL)
    assert failed.status_code == 503 and "private storage path" not in failed.text


def test_catalog_and_protocol_do_not_supply_observed_products(client, app, tmp_path):
    seed_catalog(app.state.store.root, tmp_path)
    archive_rows(
        app,
        [
            {"tag": CRITICAL_KEV},
            {"report_type": "scan_isakmp", "version": "IKE/10", "service": "ISAKMP"},
            {"report_type": "scan_http_vulnerable", "version": "Widget/3.2"},
        ],
    )
    data = client.get(URL).json()
    assert data["observation_count"] == 3
    assert data["products"]["items"] == [
        {"value": "ISAKMP", "count": 1},
        {"value": "Widget", "count": 1},
    ]
    assert data["cves"]["items"] == [{"value": CRITICAL_KEV, "count": 1}]


def test_clipped_and_oversize_source_values_are_never_new_identities(client, app):
    real = "CVE-2026-123456"
    prefix = " " * (4096 - len(real) + 2)
    fields = {"tag": prefix + real, "hostname": "unit.example.test"}
    receipt = client.post(
        "/api/imports", files={"files": ("sample.csv", csv_bytes([fields]), "text/csv")}
    )
    assert receipt.status_code == 200
    with app.state.store.transaction() as db:
        associate(
            db,
            {
                "source": {"fields": fields, "sheet": "CSV", "row": 2},
                "normalized": {"findings": [{"id": real, "source_field": "tag"}]},
            },
            import_id=receipt.json()[0]["id"],
            admitted=False,
        )
    archive_rows(app, [{"product": "w" * 201}])
    data = client.get(URL).json()
    assert data["observation_count"] == 2 and not data["coverage_complete"]
    assert data["cves"]["items"] == [{"value": real, "count": 1}]
    assert data["products"]["items"] == []
    assert any("200 characters" in warning for warning in data["warnings"])


def test_revision_retries_instead_of_returning_mixed_counts(client, monkeypatch):
    from modules.observatory.components import observed_references

    revisions = iter(["first", "second", "second"])
    monkeypatch.setattr(observed_references, "_revision", lambda eclipse: next(revisions))
    assert client.get(URL).json()["revision"] == "second"
    revisions = iter(["third", "fourth", "fifth"])
    assert client.get(URL).status_code == 503
