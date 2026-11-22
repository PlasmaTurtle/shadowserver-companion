"""Actual API acceptance for one scoped, read-only Observatory presentation."""

import hashlib
import json
import socket

import pytest
from fastapi.testclient import TestClient as UnauthenticatedClient

from modules.observatory.tests.support.observations import base
from modules.observatory.tests.support.observations import add
from tests.support.workbench import app, client, import_rows, observations


def view(client, **params):
    response = client.get("/api/eclipse/view", params={"include_undated": True, **params})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["revision"]
    assert body["snapshot"]["revision"] == body["revision"]
    assert body["intelligence"]["revision"] == body["revision"]
    assert body["records"]["total"] == body["snapshot"]["counts"]["findings"]
    return body


def test_scoped_view_requires_local_session(app):
    public = UnauthenticatedClient(app, base_url="http://127.0.0.1")
    try:
        assert public.get("/api/eclipse/view").status_code == 401
    finally:
        public.close()


def test_scoped_view_is_authenticated_local_read_only_and_preserves_source(
    client, app, monkeypatch
):
    imported, source_bytes = import_rows(client, app, start_notifications=False)
    store = app.state.store
    tables = (
        "jobs",
        "cases",
        "events",
        "contact_runs",
        "lead_queue",
        "awareness_observations",
        "awareness_findings",
    )
    before = {table: store.all(f"SELECT * FROM {table} ORDER BY rowid") for table in tables}

    def forbidden(*args, **kwargs):
        pytest.fail("Observatory inspection must not initiate a network lookup")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    response = client.get("/api/eclipse/view", params={"include_undated": True})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "default-src 'self'" in response.headers["content-security-policy"]
    current = view(client)
    assert current["records"]["items"]
    assert current["snapshot"]["counts"]["observations"] == len(observations())
    first = current["records"]["items"][0]
    detail = client.get("/api/eclipse/observations/" + first["id"])
    assert detail.status_code == 200, detail.text
    detail = detail.json()
    assert detail["source"]["sha256"] == hashlib.sha256(source_bytes).hexdigest()
    assert detail["original_url"] == f"/api/imports/{imported['id']}/original"
    assert client.get(detail["original_url"]).content == source_bytes
    assert detail["fields"]["unknown_extension"] == "KEEP THIS FIELD"
    for table, rows in before.items():
        assert store.all(f"SELECT * FROM {table} ORDER BY rowid") == rows


def test_records_pagination_is_complete_without_repeating_observations(client, app):
    for number in range(7):
        add(
            app.state.store,
            base(
                hostname=f"host{number}.example.com",
                ip=f"8.8.8.{number + 1}",
                tag=f"CVE-2026-{11000 + number}",
                timestamp="2026-11-01 01:00:00",
            ),
            filename=f"page-{number}.csv",
        )
    pages = [view(client, limit=3, offset=offset) for offset in (0, 3, 6)]
    assert all(page["records"]["total"] == 7 for page in pages)
    assert len({page["revision"] for page in pages}) == 1
    identities = [row["id"] for page in pages for row in page["records"]["items"]]
    assert len(identities) == len(set(identities)) == 7
    assert [len(page["records"]["items"]) for page in pages] == [3, 3, 1]
    assert all(page["snapshot"]["counts"]["observations"] == 7 for page in pages)
    response = client.get(
        "/api/eclipse/view",
        params={"include_undated": True, "limit": 3, "offset": 3, "records_only": True},
    )
    assert response.status_code == 200
    compact_page = response.json()
    assert compact_page["revision"] == pages[0]["revision"]
    assert compact_page["records"] == pages[1]["records"]
    assert compact_page["counts"] == pages[0]["snapshot"]["counts"]
    assert "snapshot" not in compact_page and "intelligence" not in compact_page


def test_historical_endpoint_scope_and_background_import_revision(client, app):
    old = base(tag="CVE-2026-10001", timestamp="2026-11-01 01:00:00")
    add(app.state.store, old, filename="old.csv")
    before = view(client)
    add(
        app.state.store,
        {**old, "ip": "1.1.1.1", "timestamp": "2026-11-10 01:00:00"},
        filename="later.csv",
    )
    current = view(client)
    historical = view(client, date_to="2026-11-05")
    assert before["revision"] != current["revision"]
    assert current["revision"] == historical["revision"]
    assert current["records"]["total"] == historical["records"]["total"] == 1
    assert current["records"]["items"][0]["ip"] == "1.1.1.1"
    record = historical["records"]["items"][0]
    assert record["ip"] == "8.8.8.8"
    assert record["observed_day"] == "2026-11-01"
    evidence = client.get(record["detail_url"]).json()
    assert evidence["fields"]["ip"] == "8.8.8.8"
    assert evidence["fields"]["timestamp"].startswith("2026-11-01")
    assert historical["snapshot"]["counts"]["observations"] == 1
    assert current["snapshot"]["counts"]["observations"] == 2


def test_paired_admission_filters_do_not_promote_dark_matter(client, app):
    old = base(tag="CVE-2026-10001", timestamp="2026-11-01 01:00:00")
    add(app.state.store, old, filename="approved.csv")
    add(
        app.state.store,
        {**old, "tag": "CVE-2026-10002", "timestamp": "2026-11-02 01:00:00"},
        filename="unadmitted.csv",
        admitted=False,
        reason="pending",
    )
    all_data, approved, dark = (
        view(client),
        view(client, intake="lead"),
        view(client, intake="dark_matter"),
    )
    assert all_data["records"]["total"] == 2
    assert approved["records"]["total"] == dark["records"]["total"] == 1
    assert all(row["admitted"] for row in approved["records"]["items"])
    assert all(not row["admitted"] and row["dark_matter"] for row in dark["records"]["items"])
    assert approved["records"]["items"][0]["tag"] == "CVE-2026-10001"
    assert dark["records"]["items"][0]["tag"] == "CVE-2026-10002"


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"offset": 10000001},
        {"date_to": "2026-02-30"},
        {"date_from": "2026-11-12", "date_to": "2026-11-01"},
        {"lens": "imaginary"},
        {"status": "remediated-by-us"},
        {"network": "4294967296"},
        {"ip": "not-an-address"},
        {"intelligence": "compromised"},
        {"asset_id": "x" * 101},
        {"city": "x" * 301},
    ],
)
def test_view_rejects_invalid_queries_before_projection(client, params, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Validate query semantics before building a canonical projection")

    monkeypatch.setattr("modules.observatory.components.eclipse.Eclipse._build", forbidden)
    response = client.get("/api/eclipse/view", params=params)
    assert response.status_code == 422, response.text


def test_view_returns_compact_summaries_and_resolves_full_evidence_on_demand(client, app):
    field = "Evidence retained on demand. " * 1000
    add(app.state.store, base(extra_source_field=field))
    body = view(client)
    assert field not in json.dumps(body)
    assert len(json.dumps(body)) < 250000
    row = body["records"]["items"][0]
    detail = client.get("/api/eclipse/observations/" + row["id"]).json()
    assert detail["fields"]["extra_source_field"] == field


def test_complementary_finding_records_keep_their_exact_supporting_source(client, app):
    first = base(tag="CVE-2026-10001", extra_source_field="first supporting report")
    add(app.state.store, first, filename="first-condition.csv")
    add(
        app.state.store,
        {**first, "tag": "CVE-2026-10002", "extra_source_field": "second supporting report"},
        filename="second-condition.csv",
    )
    body = view(client)
    records = {record["tag"]: record for record in body["records"]["items"]}
    assert body["snapshot"]["counts"]["observations"] == 1
    assert records["CVE-2026-10001"]["source"]["workbook"] == "first-condition.csv"
    assert records["CVE-2026-10002"]["source"]["workbook"] == "second-condition.csv"
    for cve, source_name in (
        ("CVE-2026-10001", "first-condition.csv"),
        ("CVE-2026-10002", "second-condition.csv"),
    ):
        detail = client.get(records[cve]["detail_url"])
        assert detail.status_code == 200
        assert detail.json()["fields"]["tag"] == cve
        assert detail.json()["source"]["workbook"] == source_name
