"""Explainer edits retain history, reject stale writes and preserve case wording."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy

import pytest

from tests.support.workbench import app, client
from modules.investigations.tests.support.report_api import opened, save
from modules.library.components.services.content import ContentService, ExplainerConflict
from modules.library.databases.content_schema import schema
from modules.workspace.components.store import Store


def values(**changes):
    return {
        "title": "Guidance",
        "body": "First complete wording.",
        "sources": "https://example.test/guidance",
        "source_metadata": [
            {
                "url": "https://example.test/guidance",
                "publisher": "Example",
                "title": "Source one",
                "retrieved_at": "2026-11-21",
            }
        ],
        **changes,
    }


def create(client):
    response = client.post("/api/explainers", json=values())
    assert response.status_code == 200, response.text
    return response.json()


def test_two_windows_cannot_lose_wording_or_citation_history(client, app):
    first = create(client)
    assert first["origin"] == "analyst"
    path = "/api/explainers/" + first["id"]
    newer = values(
        body="Window A preserved wording.",
        source_metadata=[{"url": first["sources"], "publisher": "New publisher"}],
    )
    response = client.put(path, json={**newer, "expected_revision": 1})
    assert response.status_code == 200, response.text
    current = response.json()
    conflict = client.put(
        path, json={**values(body="Window B stale wording."), "expected_revision": 1}
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["current"] == current
    assert client.get(path).json() == current
    old = client.get(path + "/revisions/1").json()
    assert old["body"] == first["body"] and old["source_metadata"] == first["source_metadata"]
    assert [r["revision"] for r in client.get(path + "/history").json()["items"]] == [2, 1]
    events = app.state.store.all(
        "SELECT action,metadata FROM events WHERE action LIKE 'explainer_%'"
    )
    assert [row["action"] for row in events] == ["explainer_created", "explainer_updated"]
    assert json.loads(events[-1]["metadata"])["revision"] == 2


def test_archive_and_restore_retain_full_history_and_pinned_case_wording(client, app):
    first = create(client)
    path = "/api/explainers/" + first["id"]
    lead = opened(client, app)
    selected = save(client, lead, selected_explainers=[first["id"]])
    assert selected.status_code == 200, selected.text
    lead = selected.json()
    prior_draft = deepcopy(lead["draft"])
    usage = client.get(path + "/usage").json()
    assert usage["total"] == 1 and usage["items"][0]["explainer_revision"] == 1
    assert usage["items"][0]["id"] == lead["case_id"]
    edited = client.put(
        path, json={**values(body="A later shared wording."), "expected_revision": 1}
    )
    assert edited.status_code == 200
    archived = client.post(path + "/archive", json={"expected_revision": 2, "archived": True})
    assert archived.status_code == 200 and archived.json()["revision"] == 3
    assert archived.json()["archived_at"]
    assert first["id"] not in {b["id"] for b in client.get("/api/explainers").json()}
    assert first["id"] not in {b["id"] for b in client.get("/api/bootstrap").json()["explainers"]}
    assert next(
        b
        for b in client.get("/api/explainers?include_archived=true").json()
        if b["id"] == first["id"]
    )["archived_at"]
    rejected = client.put(path, json={**values(), "expected_revision": 3})
    assert rejected.status_code == 422
    restored = client.post(path + "/restore/1", json={"expected_revision": 3})
    assert restored.status_code == 200, restored.text
    assert restored.json()["revision"] == 4 and restored.json()["archived_at"] == ""
    assert restored.json()["body"] == first["body"]
    assert restored.json()["source_metadata"] == first["source_metadata"]
    assert client.get(path + "/revisions/3").json()["archived_at"]
    assert client.get("/api/leads/" + lead["id"]).json()["draft"] == prior_draft
    history = client.get(path + "/history?limit=2").json()
    assert [r["revision"] for r in history["items"]] == [4, 3]
    next_page = client.get(path + f"/history?limit=2&before={history['next_before']}").json()
    assert [r["revision"] for r in next_page["items"]] == [2, 1]
    assert next_page["next_before"] is None


@pytest.mark.parametrize("source", ["https:", "http:///missing-host", "https://example.test:bad"])
def test_all_citation_representations_reject_malformed_urls(client, source):
    for metadata in ([], [{"url": source}]):
        response = client.post(
            "/api/explainers", json=values(sources=source, source_metadata=metadata)
        )
        assert response.status_code == 422
        assert any(error["loc"][-1] == "sources" for error in response.json()["detail"])


def test_expected_revision_required_and_omitted_citations_preserved(client):
    block = create(client)
    path = "/api/explainers/" + block["id"]
    for bad in ({}, {"expected_revision": True}, {"expected_revision": 0}):
        assert client.put(path, json={**values(), **bad}).status_code == 422
    update = values(body="Editorial update.")
    del update["source_metadata"]
    response = client.put(path, json={**update, "expected_revision": 1})
    assert response.status_code == 200
    assert response.json()["source_metadata"] == block["source_metadata"]
    assert (
        client.post(path + "/archive", json={"expected_revision": 1, "archived": True}).status_code
        == 409
    )
    assert client.post(path + "/restore/999", json={"expected_revision": 2}).status_code == 404


def test_revision_rows_reject_rewrite_and_deletion(client, app):
    block = create(client)
    for statement in (
        "UPDATE explainer_revisions SET body='changed' WHERE block_id=?",
        "DELETE FROM explainer_revisions WHERE block_id=?",
    ):
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            with app.state.store.transaction() as db:
                db.execute(statement, (block["id"],))
    assert client.get(f"/api/explainers/{block['id']}/revisions/1").json()["body"] == block["body"]


def test_current_citations_survive_legacy_cache_eviction_or_tampering(client, app):
    block = create(client)
    key = f"block-sources:{block['id']}:1"
    with app.state.store.transaction() as db:
        db.execute("UPDATE cache SET payload='[]' WHERE key=?", (key,))
    path = "/api/explainers/" + block["id"]
    assert client.get(path).json()["source_metadata"] == block["source_metadata"]
    with app.state.store.transaction() as db:
        db.execute("DELETE FROM cache WHERE key=?", (key,))
    assert client.get(path).json()["source_metadata"] == block["source_metadata"]
    assert (
        next(item for item in client.get("/api/explainers").json() if item["id"] == block["id"])[
            "source_metadata"
        ]
        == block["source_metadata"]
    )


def test_native_writer_transactions_admit_only_one_same_revision_update(tmp_path):
    first_store, second_store = Store(tmp_path / "data"), Store(tmp_path / "data")
    first, second = ContentService(first_store), ContentService(second_store)
    block = first.create(values())

    def write(service, text):
        try:
            return service.update(block["id"], values(body=text), 1)["body"]
        except ExplainerConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(write, first, "Window A"), pool.submit(write, second, "Window B")
        results = [a.result(), b.result()]
    assert results.count("conflict") == 1
    assert first.get(block["id"])["body"] in results
    assert [row["revision"] for row in first.history(block["id"])["items"]] == [2, 1]


def test_bundled_origin_distinguishes_local_edits_from_archival(client):
    block = client.get("/api/explainers/cve").json()
    assert block["origin"] == "bundled"
    archived = client.post(
        "/api/explainers/cve/archive",
        json={"expected_revision": block["revision"], "archived": True},
    ).json()
    assert archived["origin"] == "bundled"
    active = client.post(
        "/api/explainers/cve/archive",
        json={"expected_revision": archived["revision"], "archived": False},
    ).json()
    update = {key: active[key] for key in ("title", "body", "sources", "source_metadata")}
    update.update(body="Local wording with bundled origins.", expected_revision=active["revision"])
    changed = client.put("/api/explainers/cve", json=update)
    assert changed.status_code == 200
    assert changed.json()["origin"] == "bundled_edited"


def test_migration_preserves_current_and_legacy_citations_without_invented_history(tmp_path):
    with closing(sqlite3.connect(tmp_path / "legacy.sqlite3")) as db:
        db.row_factory = sqlite3.Row
        db.execute("CREATE TABLE explainers(id PRIMARY KEY,title,body,sources,revision,updated_at)")
        db.execute("CREATE TABLE cache(key PRIMARY KEY,payload,retrieved_at)")
        row = (
            "legacy",
            "Old title",
            "Old full wording.",
            "https://example.test/old",
            7,
            "2026-10-01",
        )
        db.execute("INSERT INTO explainers VALUES(?,?,?,?,?,?)", row)
        citations = [{"url": row[3], "publisher": "Old publisher"}]
        for number in (4, 7):
            db.execute(
                "INSERT INTO cache VALUES(?,?,?)",
                (f"block-sources:legacy:{number}", json.dumps(citations), row[-1]),
            )
        db.commit()
        db.execute("BEGIN")
        schema(db)
        db.commit()
        assert tuple(db.execute("SELECT * FROM explainers").fetchone()) == row
        retained = db.execute("SELECT * FROM explainer_revisions").fetchall()
        assert len(retained) == 1 and retained[0]["revision"] == 7
        assert retained[0]["action"] == "legacy_current" and retained[0]["actor"] == ""
        assert json.loads(retained[0]["source_metadata"]) == citations
        assert db.execute("SELECT count(*) FROM cache").fetchone()[0] == 2
