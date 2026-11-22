"""Saved outreach survives real workspace transfer; corrupt metadata fails closed."""

from contextlib import closing
import json
import sqlite3

import pytest

from modules.workspace.databases import migrations
from modules.workspace.components.store import Store
from modules.workspace.components.workspace_data import (
    WorkspaceData,
    apply_pending_workspace,
    export_workspace,
)
from tests.support.workbench import app, client, import_rows, observations
from tests.schema_helpers import restore_schema


def save_preparation(client, app):
    row = {**observations()[0], "ip": "8.8.8.8"}
    import_rows(client, app, [row])
    case_id = app.state.store.one("SELECT id FROM cases")["id"]
    handoff = client.get(f"/api/cases/{case_id}/outreach-handoff").json()
    response = client.put(
        f"/api/cases/{case_id}/outreach-preparation",
        json={
            "expected_revision": 0,
            "expected_context": handoff["context_hash"],
            "subject": "Saved subject — synthetic",
            "message": "Specific recipient explanation.\nNo message was sent.",
            "call_outline": "Ask for the responsible IT contact.",
        },
    )
    assert response.status_code == 200, response.text
    return case_id


def test_saved_stale_preparation_survives_export_restore_and_restart(client, app, tmp_path):
    case_id = save_preparation(client, app)
    store = app.state.store
    saved = store.one("SELECT * FROM outreach_preparations WHERE case_id=?", (case_id,))
    case = client.get(f"/api/cases/{case_id}").json()["case"]
    response = client.put(
        f"/api/cases/{case_id}/plan",
        json={"expected_version": case["version"], "contact_email": "changed@example.com"},
    )
    assert response.status_code == 200, response.text
    assert client.get(f"/api/cases/{case_id}/outreach-handoff").json()["preparation_stale"]
    archive = export_workspace(store)
    try:
        destination = Store(tmp_path / "restored")
        data = WorkspaceData(app, destination)
        assert data.stage("import", archive)["pending"] == "import"
        apply_pending_workspace(destination.root)
        reopened = Store(destination.root)
        assert reopened.one("SELECT * FROM outreach_preparations") == saved
        assert reopened.one("SELECT * FROM cases WHERE id=?", (case_id,))["contact_email"] == (
            "changed@example.com"
        )
        assert reopened.all("PRAGMA foreign_key_check") == []
        assert Store(destination.root).one("SELECT * FROM outreach_preparations") == saved
    finally:
        archive.unlink(missing_ok=True)


@pytest.mark.parametrize("column,value", [("context_hash", "0" * 64), ("context_json", "[]")])
def test_export_rejects_invalid_preparation_without_rewriting_work(client, app, column, value):
    case_id = save_preparation(client, app)
    store = app.state.store
    statement = f"UPDATE outreach_preparations SET {column}=? WHERE case_id=?"
    if column == "context_json":
        # Normal application writes must still reject the wrong JSON shape.
        with pytest.raises(sqlite3.IntegrityError, match="server-owned JSON"):
            with store.transaction() as db:
                db.execute(statement, (value, case_id))
        # Inject offline corruption in this isolated fixture, then restore the
        # exact guard before testing the independent export validation boundary.
        with closing(store.connect()) as db:
            guard = db.execute(
                "SELECT sql FROM sqlite_master WHERE name='valid_json_outreach_preparations_context_json_update'"
            ).fetchone()[0]
            db.execute("BEGIN IMMEDIATE")
            db.execute("DROP TRIGGER valid_json_outreach_preparations_context_json_update")
            db.execute(statement, (value, case_id))
            db.execute(guard)
            db.commit()
    else:
        with store.transaction() as db:
            db.execute(statement, (value, case_id))
    before = store.one("SELECT * FROM outreach_preparations")
    with pytest.raises(ValueError, match="[Oo]utreach preparation"):
        export_workspace(store)
    assert store.one("SELECT * FROM outreach_preparations") == before


def test_schema_15_upgrade_preserves_case_and_original_payloads(client, app):
    save_preparation(client, app)
    store = app.state.store
    with closing(store.connect()) as db:
        restore_schema(db, 15)
    cases = store.all("SELECT * FROM cases")
    entries = store.all("SELECT id,payload FROM entries ORDER BY id")
    reopened = Store(store.root)
    assert reopened.one("PRAGMA user_version")["user_version"] == migrations.SCHEMA_VERSION
    assert reopened.all("SELECT * FROM cases") == cases
    assert reopened.all("SELECT id,payload FROM entries ORDER BY id") == entries
    assert reopened.all("SELECT * FROM outreach_preparations") == []


def test_interrupted_schema_16_rolls_back_and_can_retry(client, app, monkeypatch):
    save_preparation(client, app)
    store = app.state.store
    with closing(store.connect()) as db:
        restore_schema(db, 15)
    before = store.all("SELECT * FROM cases")
    original = migrations.MIGRATIONS[16]

    def interrupted(db):
        original(db)
        raise RuntimeError("Synthetic migration interruption")

    monkeypatch.setitem(migrations.MIGRATIONS, 16, interrupted)
    with pytest.raises(RuntimeError, match="interruption"):
        Store(store.root)
    assert store.one("PRAGMA user_version")["user_version"] == 15
    assert not store.one("SELECT name FROM sqlite_master WHERE name='outreach_preparations'")
    assert store.all("SELECT * FROM cases") == before
    assert not store.one("SELECT name FROM sqlite_master WHERE name='awareness_admission_events'")
    monkeypatch.setitem(migrations.MIGRATIONS, 16, original)
    assert Store(store.root).one("PRAGMA user_version")["user_version"] == migrations.SCHEMA_VERSION
