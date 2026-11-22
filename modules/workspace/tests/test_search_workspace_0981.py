"""Read-only search and saved-workflow overview through authenticated routes."""

from contextlib import contextmanager
from datetime import date
import hashlib
import io
import json
from pathlib import Path
import socket
import sqlite3

import pytest

from tests.support.workbench import app, client, import_rows
from modules.workspace.components.search import search_records
from modules.workspace.components.workspace_brief import workspace_brief


@pytest.fixture
def searchable(client, app):
    imported, _ = import_rows(client, app, name="Needle_100%_source.csv")
    store = app.state.store
    entity = store.one("SELECT * FROM leads WHERE merged_into IS NULL")
    case = store.one("SELECT * FROM cases WHERE entity_id=?", (entity["id"],))
    with store.transaction() as db:
        db.execute("UPDATE leads SET company=? WHERE id=?", ("Needle_100%", entity["id"]))
        db.execute(
            "UPDATE cases SET title=?,entity_snapshot=? WHERE id=?",
            ("Needle_100% notification", json.dumps({"company": "Pinned Needle_100%"}), case["id"]),
        )
        db.execute(
            "INSERT INTO explainers(id,title,body,sources,revision,updated_at) VALUES(?,?,?,?,?,?)",
            (
                "needle-library",
                "Needle_100% library",
                "Hidden explanatory phrase",
                "[]",
                2,
                "2099-01-01",
            ),
        )
    imported = store.one("SELECT * FROM imports WHERE id=?", (imported["id"],))
    return store, imported, entity, case


def items(result, kind):
    return next((group["items"] for group in result["groups"] if group["kind"] == kind), [])


def test_search_routes_require_session_and_bound_inputs(client):
    for params in ({"q": "x" * 121}, {"limit": 0}, {"limit": 11}, {"limit": "bad"}):
        assert client.get("/api/search", params=params).status_code == 422
    assert client.get("/api/workspace/brief?as_of=not-a-date").status_code == 422
    client.cookies.clear()
    assert client.get("/api/search?q=needle").status_code == 401
    assert client.get("/api/workspace/brief").status_code == 401


def test_search_finds_entity_case_source_and_library_with_minimal_links(client, searchable):
    store, imported, entity, case = searchable
    response = client.get("/api/search", params={"q": "needle_100%"})
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    result = response.json()
    expected = {
        "entity": (entity["id"], "#entity/" + entity["id"]),
        "notification": (case["id"], "#workspace/notifications/" + case["id"]),
        "import": (imported["id"], ""),
        "explainer": ("needle-library", "#library?item=needle-library"),
    }
    for kind, (identifier, href) in expected.items():
        found = items(result, kind)
        assert len(found) == 1
        assert found[0]["id"] == identifier
        assert found[0]["href"] == href
        assert set(found[0]) == {"id", "kind", "title", "detail", "updated_at", "href"}
    assert "Pinned Needle_100%" == items(result, "notification")[0]["title"]
    assert "Hidden explanatory phrase" not in response.text
    assert imported["path"] not in response.text
    assert imported["sha256"] not in response.text
    assert (
        "needle-library" == items(search_records(store, "explanatory phrase"), "explainer")[0]["id"]
    )


@pytest.mark.parametrize("query", ["mail.example.com", "8.8.8.8", "eol-php"])
def test_search_finds_host_ip_and_finding_in_entity_notification_and_intake(searchable, query):
    store, _, entity, case = searchable
    result = search_records(store, query)
    assert entity["id"] in {r["id"] for r in items(result, "entity")}
    assert case["id"] in {r["id"] for r in items(result, "notification")}
    assert items(result, "lead"), (
        "Retained incoming observations should be searchable before assignment"
    )


def test_search_wildcards_and_sql_syntax_are_literal(searchable):
    store, _, _, _ = searchable
    assert search_records(store, "_%")["total"] == 0
    assert search_records(store, "%' OR 1=1 --")["total"] == 0
    with store.transaction() as db:
        db.execute(
            "INSERT INTO explainers(id,title,body,sources,revision,updated_at) VALUES(?,?,?,?,?,?)",
            ("literal", "A \\ % _ phrase", "Only literal", "[]", 1, "2099-02-01"),
        )
    assert [r["id"] for r in items(search_records(store, "\\ % _"), "explainer")] == ["literal"]
    assert search_records(store, "q")["minimum_length"] == 2
    assert search_records(store, "q")["total"] == 0


def test_recent_and_result_limits_are_bounded_without_search_bodies(searchable):
    store, _, _, _ = searchable
    with store.transaction() as db:
        for number in range(14):
            db.execute(
                "INSERT INTO explainers(id,title,body,sources,revision,updated_at) VALUES(?,?,?,?,?,?)",
                (
                    f"batch-{number:02}",
                    "Batch result " + "x" * 400,
                    "large " * 10000,
                    "[]",
                    1,
                    "2099-02-01",
                ),
            )
    assert {g["kind"] for g in search_records(store)["groups"]} <= {
        "entity",
        "notification",
        "lead",
    }
    result = search_records(store, "Batch result", 10)
    group = next(g for g in result["groups"] if g["kind"] == "explainer")
    assert len(group["items"]) == 10 and group["has_more"] is True
    assert all(len(row["title"]) == 250 for row in group["items"])
    assert all(len(row["detail"]) <= 300 for row in group["items"])
    assert len(json.dumps(result)) < 6000
    assert len(items(search_records(store, "Batch result", 2), "explainer")) == 2


def test_notification_with_empty_company_falls_back_to_domain(searchable):
    store, _, entity, case = searchable
    with store.transaction() as db:
        db.execute("UPDATE leads SET company='' WHERE id=?", (entity["id"],))
        db.execute("UPDATE cases SET entity_snapshot='{}' WHERE id=?", (case["id"],))
    assert (
        items(search_records(store, "example.com"), "notification")[0]["title"] == entity["domain"]
    )


def test_search_and_brief_do_not_read_artifacts_hash_fetch_or_write(searchable, monkeypatch):
    store, _, _, _ = searchable
    with store.read_snapshot() as db:
        before = list(db.iterdump())
    opened = []
    real_open = io.open

    def bounded_open(path, *args, **kwargs):
        if isinstance(path, (str, Path)):
            opened.append(str(path))
            if any(part in {"reports", "evidence", "originals"} for part in Path(path).parts):
                raise AssertionError("Search and summary must not open source or report artifacts")
        return real_open(path, *args, **kwargs)

    def prohibited(*args, **kwargs):
        raise AssertionError("Search and summary must not hash, fetch or mutate records")

    real_snapshot = store.read_snapshot
    statements = []

    @contextmanager
    def read_only_snapshot():
        with real_snapshot() as db:
            db.set_trace_callback(statements.append)
            assert db.execute("PRAGMA query_only").fetchone()[0] == 1
            yield db

    monkeypatch.setattr(store, "read_snapshot", read_only_snapshot)
    monkeypatch.setattr(store, "transaction", prohibited)
    monkeypatch.setattr(io, "open", bounded_open)
    monkeypatch.setattr(hashlib, "sha256", prohibited)
    monkeypatch.setattr(socket, "create_connection", prohibited)
    assert search_records(store, "private-query-not-persisted")["total"] == 0
    assert workspace_brief(store, date(2026, 11, 10))["counts"]["entities"] >= 1
    with real_snapshot() as db:
        assert list(db.iterdump()) == before
    assert statements and not any(
        s.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for s in statements
    )
    assert opened == []


def test_brief_counts_saved_workflow_and_honors_as_of(client, searchable):
    store, _, entity, first = searchable
    samples = [
        ("in_progress", "2026-11-10", None),
        ("pending_notification", "2026-11-11", None),
        ("notification_completed", "2026-11-12", "2026-11-09T00:00:00Z"),
        ("closed", "2026-01-01", None),
        ("closed", "2026-01-01", "2026-11-08T00:00:00Z"),
    ]
    with store.transaction() as db:
        for index, (stage, followup, delivered) in enumerate(samples):
            if index == 0:
                db.execute(
                    "UPDATE cases SET stage=?,follow_up_date=?,delivered_at=? WHERE id=?",
                    (stage, followup, delivered, first["id"]),
                )
            else:
                db.execute(
                    "INSERT INTO cases(id,entity_id,title,stage,created_at,updated_at,follow_up_date,delivered_at) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        f"brief-{index}",
                        entity["id"],
                        f"Synthetic {index}",
                        stage,
                        "2026-11-01",
                        "2026-11-01",
                        followup,
                        delivered,
                    ),
                )
    response = client.get("/api/workspace/brief?as_of=2026-11-11")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    result = response.json()
    workflow = result["workflow"]
    assert {
        k: workflow[k]
        for k in ("in_progress", "pending_notification", "notification_completed", "closed")
    } == {
        "in_progress": 1,
        "pending_notification": 1,
        "notification_completed": 1,
        "closed": 2,
    }
    assert workflow["due"] == 2
    assert workflow["delivered_total"] == 2
    assert workflow["closed_without_delivery"] == 1
    assert client.get("/api/workspace/brief?as_of=2026-11-09").json()["workflow"]["due"] == 0
    assert client.get("/api/workspace/brief?as_of=2026-11-12").json()["workflow"]["due"] == 3
    assert len(result["events"]) <= 5 and len(result["imports"]) <= 3
    assert all(
        not {"path", "sha256", "config", "payload"} & row.keys() for row in result["imports"]
    )
    assert not {"source_observations", "observations", "assets"} & result["counts"].keys()
    assert result["counts"]["leads"] == len(client.get("/api/pending-leads").json())
    assert len(result["leads"]) <= 4
