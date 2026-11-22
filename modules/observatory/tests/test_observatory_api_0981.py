"""Observatory discovery exposes offline provenance without opening workflow work."""

import hashlib
import socket

import pytest

from tests.support.workbench import app, client, import_rows, observations


def test_empty_intelligence_endpoint_is_honest_and_local(client):
    response = client.get("/api/eclipse/intelligence")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["counts"]["total_rows"] == data["counts"]["selected_rows"] == 0
    assert data["graph"]["nodes"] == data["graph"]["edges"] == []
    assert data["timeline"] == []
    assert data["coverage"]["complete"]
    assert response.headers["cache-control"] == "no-store"
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["content-type"].startswith("application/json")


def test_discovery_support_links_resolve_to_unchanged_source_without_creating_work(
    client, app, monkeypatch
):
    imported, original = import_rows(client, app, start_notifications=False)
    before = {
        table: app.state.store.all(f"SELECT * FROM {table} ORDER BY rowid")
        for table in (
            "jobs",
            "cases",
            "events",
            "contact_runs",
            "lead_queue",
            "awareness_assets",
            "awareness_observations",
            "awareness_findings",
            "awareness_memberships",
            "awareness_sources",
            "awareness_admission_events",
        )
    }
    archive_before = list(app.state.store.dark_matter.iter_records(include_promoted=True))
    requests_before = list(app.state.fake.calls)

    def forbidden(*args, **kwargs):
        pytest.fail("Discovery must use saved observations only")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    response = client.get("/api/eclipse/intelligence", params={"lens": "ip"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["counts"]["total_rows"] == len(observations())
    assert data["counts"]["selected_rows"] == len(observations())
    legacy = client.get("/api/eclipse").json()
    assert legacy["schema_version"] == 3
    assert legacy["counts"]["rows"] == len(observations())
    source_ids = {row["id"] for row in legacy["observations"]}
    supports = {identity for node in data["graph"]["nodes"] for identity in node["observation_ids"]}
    assert supports and supports <= source_ids
    for identity in supports:
        detail = client.get("/api/eclipse/observations/" + identity).json()
        assert detail["fields"]["unknown_extension"] == "KEEP THIS FIELD"
        assert detail["source"]["sha256"] == hashlib.sha256(original).hexdigest()
        assert detail["original_url"] == f"/api/imports/{imported['id']}/original"
        assert client.get(detail["original_url"]).content == original
    qualified = next(row for row in legacy["observations"] if row["status"] == "qualified")
    assert qualified["case_id"] is None and qualified["lead_id"]
    assert client.get("/api/entities/" + qualified["entity_id"]).status_code == 200
    assert client.get("/api/pending-leads/" + qualified["lead_id"]).status_code == 200
    selected = client.get("/api/eclipse/intelligence", params={"entity_id": qualified["entity_id"]})
    assert selected.status_code == 200, selected.text
    entity_rows = [
        row for row in legacy["observations"] if row["entity_id"] == qualified["entity_id"]
    ]
    assert selected.json()["counts"]["selected_rows"] == len(entity_rows) == 4
    # One row has a usable hostname/IP but lacks the version required
    # for EOL outreach. It remains visible as source evidence, without creating
    # a finding or attaching it to the entity whose other rows qualified.
    archived = [row for row in legacy["observations"] if row["dark_matter"]]
    assert len(archived) == 5
    assert all(row["entity_id"] is None and not row["admitted"] for row in archived)
    residue = [row for row in archived if row["intake_reason"] == "missing_version"]
    assert len(residue) == 1
    assert residue[0]["source"]["row"] == 7
    assert residue[0]["hostname"] == "mail.example.com"
    assert residue[0]["domain"] == qualified["domain"] == "example.com"
    assert residue[0]["version"] == ""
    assert residue[0]["intake_reason"] == "missing_version"
    assert residue[0]["intake_disposition"] == "dark_matter"
    assert residue[0]["entity_association_basis"] == ""
    assert residue[0]["entity_id"] is None and residue[0]["finding_ids"] == []
    assert not residue[0]["admitted"]
    assert residue[0]["status"] == "excluded"
    assert residue[0]["lead_id"] is None and residue[0]["case_id"] is None
    assert residue[0]["individually_attributed"] is False
    assert sum(row["status"] == "qualified" for row in entity_rows) == 4
    assert all(
        row["entity_id"] is None
        for row in legacy["observations"]
        if row["intake_disposition"] == "unclassified"
    )
    assert app.state.fake.calls == requests_before
    for table, saved in before.items():
        assert app.state.store.all(f"SELECT * FROM {table} ORDER BY rowid") == saved
    assert list(app.state.store.dark_matter.iter_records(include_promoted=True)) == archive_before


@pytest.mark.parametrize(
    "params",
    [
        {"max_nodes": -1},
        {"max_edges": -1},
        {"max_nodes": 1000000},
        {"max_edges": 1000000},
        {"lens": "invented-ownership"},
        {"date_from": "not-a-date"},
        {"date_to": "2026-02-30"},
        {"date_from": "2026-11-11", "date_to": "2026-01-01"},
    ],
)
def test_invalid_queries_are_rejected_before_building_unbounded_payloads(client, params):
    response = client.get("/api/eclipse/intelligence", params=params)
    assert response.status_code == 422, response.text


def test_invalid_semantic_queries_are_rejected_before_source_parsing(client, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("An invalid filter must be rejected before parsing source files")

    monkeypatch.setattr("modules.observatory.components.eclipse.Eclipse.snapshot", forbidden)
    for params in (
        {"date_from": "not-a-date"},
        {"date_from": "2026-11-11", "date_to": "2026-01-01"},
        {"status": "implied-remediated"},
        {"network": "AS15169"},
        {"network": "4294967296"},
        {"ip": "not an address"},
        {"intelligence": "guessed-compromise"},
    ):
        response = client.get("/api/eclipse/intelligence", params=params)
        assert response.status_code == 422, response.text
