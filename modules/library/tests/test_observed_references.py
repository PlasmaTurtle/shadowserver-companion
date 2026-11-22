"""Workspace reference counts preserve source identity, scope and coverage."""

import sqlite3

from fastapi.testclient import TestClient

from modules.accretion.components.awareness import associate
from modules.library.tests.support.catalog_outreach import CRITICAL_KEV, seed_catalog
from modules.entities.tests.support.contacts import entity_only
from tests.support.workbench import app, client, csv_bytes, observations


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


def source(client, store, fields, *, entity_id=None, normalized=None, archive=False):
    receipt = client.post(
        "/api/imports", files={"files": ("fixture.csv", csv_bytes([fields]), "text/csv")}
    )
    assert receipt.status_code == 200, receipt.text
    record = store.one("SELECT id,sha256,name FROM imports WHERE id=?", (receipt.json()[0]["id"],))
    if archive:
        store.dark_matter.record_batch(
            {"import_id": record["id"], "sha256": record["sha256"], "name": record["name"]},
            [{"row": 2, "sheet": "CSV", "fields": fields}],
            stage="associate",
            reason="retained source",
        )
    entry = {"source": {"fields": fields, "row": 2, "sheet": "CSV"}, "normalized": normalized or {}}
    with store.transaction() as db:
        return associate(db, entry, import_id=record["id"], entity_id=entity_id)


def matched(client, kind, value, **params):
    result = client.get(URL + "/entities", params={"kind": kind, "value": value, **params})
    assert result.status_code == 200, result.text
    return result.json()


def test_empty_auth_failure_and_query_bounds(client, app):
    unauthenticated = TestClient(app, base_url="http://127.0.0.1")
    for url in [URL, URL + "/entities?kind=cves&value=CVE-2026-1234"]:
        assert unauthenticated.get(url).status_code == 401
    result = client.get(URL)
    assert result.status_code == 200
    data = result.json()
    assert data["coverage_complete"] and not data["warnings"]
    for key in ("cves", "products"):
        assert data[key] == {"items": [], "total": 0, "limit": 10, "offset": 0}
    for query in ("limit=101", "limit=0", "cve_offset=-1", "product_offset=-1"):
        assert client.get(URL + "?" + query).status_code == 422
    for params in ({"kind": "other", "value": "x"}, {"kind": "products", "value": ""}):
        assert client.get(URL + "/entities", params=params).status_code == 422
    assert matched(client, "products", "missing")["total"] == 0


def test_openapi_describes_entity_count_and_membership_contract(app):
    spec = app.openapi()
    schemas = spec["components"]["schemas"]

    def resolve(reference):
        return schemas[reference["$ref"].rsplit("/", 1)[1]]

    def response(url):
        return resolve(
            spec["paths"][url]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        )

    summary = response(URL)
    assert set(summary["required"]) == {
        "revision",
        "coverage_complete",
        "warnings",
        "cves",
        "products",
    }
    assert summary["properties"]["products"] == summary["properties"]["cves"]
    page = resolve(summary["properties"]["cves"])
    assert set(page["required"]) == {"items", "total", "limit", "offset"}
    item = resolve(page["properties"]["items"]["items"])
    assert set(item["required"]) == {"value", "entity_count"}
    assert item["properties"]["entity_count"]["minimum"] == 1
    entities = response(URL + "/entities")
    assert resolve(entities["properties"]["items"]["items"])["required"] == ["id", "name"]


def test_multiple_source_rows_multiple_sightings_and_hosts_count_one_entity(client, app):
    first, second = "CVE-2025-1234", "CVE-2025-12345"
    row = {
        **observations()[0],
        "tag": first,
        "version": "Widget/1.0;Widget/2.0",
        "product": "Gateway",
    }
    store = app.state.store
    one = "first"
    entity_only(store, one, "example.com")
    for fields in (
        row,
        {**row, "tag": second},
        {**row, "hostname": "unit.example.com"},
        {**row, "timestamp": "2026-11-07 01:02:03"},
    ):
        source(client, store, fields, entity_id=one, archive=True)
    entity_only(store, "second", "separate.test")
    with store.transaction() as db:
        db.execute("UPDATE leads SET company='Alpha' WHERE id=?", (one,))
        db.execute("UPDATE leads SET company='Beta' WHERE id='second'")
    source(
        client,
        store,
        {**row, "hostname": "mail.separate.test", "product": "gateway"},
        entity_id="second",
    )
    source(client, store, {**row, "hostname": "unassociated.test", "product": "Unassigned product"})
    archive_rows(
        app, [{"tag": second, "hostname": "mail.example.com", "product": "Standalone archive"}]
    )
    result = client.get(URL).json()
    assert result["coverage_complete"] and not result["warnings"]
    assert result["cves"]["items"] == [
        {"value": first, "entity_count": 2},
        {"value": second, "entity_count": 1},
    ]
    assert result["products"]["items"] == [
        {"value": "Gateway", "entity_count": 2},
        {"value": "Widget", "entity_count": 2},
    ]
    page = client.get(URL, params={"limit": 1, "cve_offset": 1}).json()
    assert (
        page["revision"] == result["revision"]
        and page["cves"]["items"] == result["cves"]["items"][1:]
    )
    for kind, values in (("cves", result["cves"]), ("products", result["products"])):
        for ranked in values["items"]:
            members = matched(client, kind, ranked["value"].lower())
            assert (
                members["revision"] == result["revision"]
                and members["total"] == ranked["entity_count"]
            )
            assert members["items"][0] == {"id": one, "name": "Alpha"}
    assert matched(client, "cves", first, limit=1, offset=1)["items"] == [
        {"id": "second", "name": "Beta"}
    ]
    for ranked in result["cves"]["items"]:
        identifier = ranked["value"]
        detail = client.get(f"/api/cve-catalog/records/{identifier}/observations?limit=1&offset=1")
        assert detail.status_code == 200, detail.text
        evidence = detail.json()
        assert evidence["offset"] == 1
        assert evidence["reported_entities"] == matched(client, "cves", identifier)
        assert evidence["reported_entities"]["total"] == ranked["entity_count"]
    revisions = {
        row["id"]: row["draft_revision"] for row in store.all("SELECT id,draft_revision FROM leads")
    }
    store.merge_entities("second", one, revisions["second"], revisions[one])
    merged = client.get(URL).json()
    assert merged["revision"] != result["revision"]
    assert all(row["entity_count"] == 1 for k in ("cves", "products") for row in merged[k]["items"])
    assert matched(client, "cves", first)["items"] == [{"id": one, "name": "Alpha"}]


def test_recorded_owner_beats_asset_transfer_and_unknown_cannot_be_reassigned(client, app):
    store = app.state.store
    entity_only(store, "previous", "old.test")
    entity_only(store, "current", "new.test")
    original = {"hostname": "host.old.test", "tag": "CVE-2025-1111"}
    row = source(client, store, original, entity_id="previous")
    with store.transaction() as db:
        db.execute("UPDATE awareness_assets SET entity_id='current' WHERE id=?", (row["asset_id"],))
    assert matched(client, "cves", original["tag"])["items"] == [
        {"id": "previous", "name": "old.test"}
    ]
    # A legacy measurement can acquire an asset association later. An explicit
    # historical unknown remains unknown even when that asset now has an owner.
    for number, reserve_unknown in [(2, True), (3, False)]:
        tag = f"CVE-2025-200{number}"
        unknown = source(client, store, {"hostname": f"host{number}.unassociated.test", "tag": tag})
        with store.transaction() as db:
            if reserve_unknown:
                db.execute(
                    "INSERT INTO awareness_observation_owners VALUES(?,NULL,'','ownership_history_review','2026-11-11')",
                    (unknown["observation_id"],),
                )
            db.execute(
                "UPDATE awareness_assets SET entity_id='current' WHERE id=?", (unknown["asset_id"],)
            )
        assert matched(client, "cves", tag)["items"] == (
            [] if reserve_unknown else [{"id": "current", "name": "new.test"}]
        )


def test_archived_rows_without_entity_links_do_not_contribute(client, app, monkeypatch):
    archive_rows(app, [{"tag": "CVE-2025-1234", "product": "Widget"}])

    def unexpected(*args, **kwargs):
        raise AssertionError("Entity rankings must not enumerate standalone archives")

    monkeypatch.setattr(app.state.store.dark_matter, "iter_records", unexpected)
    result = client.get(URL).json()
    assert (
        result["coverage_complete"] and result["cves"]["total"] == result["products"]["total"] == 0
    )

    def unavailable():
        raise sqlite3.OperationalError("private storage path")

    monkeypatch.setattr(app.state.store.dark_matter, "revision", unavailable)
    for url in (URL, URL + "/entities?kind=products&value=Widget"):
        failed = client.get(url)
        assert failed.status_code == 503 and "private storage path" not in failed.text


def test_catalog_and_protocol_do_not_supply_observed_products(client, app, tmp_path):
    store = app.state.store
    seed_catalog(store.root, tmp_path)
    entity_only(store, "one", "unit.test")
    for row in [
        {"tag": CRITICAL_KEV},
        {"report_type": "scan_isakmp", "version": "IKE/10", "service": "ISAKMP"},
        {"report_type": "scan_http_vulnerable", "version": "Widget/3.2"},
    ]:
        source(client, store, {**row, "hostname": "unit.test"}, entity_id="one")
    data = client.get(URL).json()
    assert data["products"]["items"] == [
        {"value": "ISAKMP", "entity_count": 1},
        {"value": "Widget", "entity_count": 1},
    ]
    assert data["cves"]["items"] == [{"value": CRITICAL_KEV, "entity_count": 1}]


def test_clipped_and_oversize_source_values_are_never_new_identities(client, app):
    store = app.state.store
    entity_only(store, "one", "unit.test")
    real = "CVE-2026-123456"
    prefix = " " * (4096 - len(real) + 2)
    source(
        client,
        store,
        {"tag": prefix + real, "product": "w" * 201, "hostname": "unit.test"},
        entity_id="one",
        normalized={"findings": [{"id": real, "source_field": "tag"}]},
    )
    data = client.get(URL).json()
    assert not data["coverage_complete"] and data["products"]["items"] == []
    assert data["cves"]["items"] == [{"value": real, "entity_count": 1}]
    assert any("200 characters" in warning for warning in data["warnings"])


def test_revision_retries_instead_of_returning_mixed_counts(client, monkeypatch):
    from modules.observatory.components import observed_references

    revisions = iter(["first", "second", "second"])
    monkeypatch.setattr(observed_references, "_revision", lambda eclipse: next(revisions))
    assert client.get(URL).json()["revision"] == "second"
    revisions = iter(["third", "fourth", "fifth"])
    assert client.get(URL).status_code == 503


def test_cve_evidence_remains_available_when_entity_membership_is_unreadable(
    client, app, monkeypatch
):
    from modules.observatory.components import observed_references

    identifier = "CVE-2026-1234"
    path = f"/api/cve-catalog/records/{identifier}/observations"
    # CVE-based reads require only retained reports, including when catalog startup failed.
    monkeypatch.setattr(app.state.cve_catalog, "manager", None)
    before = client.get(path)
    assert before.status_code == 200, before.text
    assert before.json()["reported_entities"]["total"] == 0

    def unreadable(*args, **kwargs):
        raise sqlite3.OperationalError("private filename")

    monkeypatch.setattr(observed_references, "reference_entities", unreadable)
    result = client.get(path)
    assert result.status_code == 200 and result.json() == (
        before.json() | {"reported_entities": None}
    )
    assert "private filename" not in result.text
