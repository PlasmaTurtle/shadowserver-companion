"""Case rows and their selected-source flags are one read-only projection."""

import json
import sqlite3

from test_workbench import app, client, import_rows, observations
from workbench.repositories.cases import CaseRepository
from workbench.services.case_queries import list_cases


def test_case_list_does_not_mix_workflow_and_source_revisions(client, app, monkeypatch):
    import_rows(client, app, [observations()[2]])
    store = app.state.store
    before = list_cases(store)
    original = CaseRepository.list

    def commit_after_case_rows(repository, *args, **kwargs):
        rows = original(repository, *args, **kwargs)
        with store.transaction() as writer:
            case = writer.execute("SELECT id,draft FROM cases").fetchone()
            draft = json.loads(case["draft"])
            draft["cve_records"] = [{"id": "CVE-2099-1000", "kev": True}]
            writer.execute(
                "UPDATE cases SET stage='closed',draft=? WHERE id=?",
                (json.dumps(draft), case["id"]),
            )
        return rows

    monkeypatch.setattr(CaseRepository, "list", commit_after_case_rows)
    during = list_cases(store)
    assert during == before
    monkeypatch.setattr(CaseRepository, "list", original)
    after = list_cases(store)
    assert after[0]["stage"] == "closed" and after[0]["kev"] is True
    assert before[0]["stage"] == "in_progress" and before[0]["kev"] is None


def test_case_list_uses_one_read_only_connection_and_two_bulk_reads(client, app, monkeypatch):
    import_rows(client, app, [observations()[2]])
    store = app.state.store
    before = store.all("SELECT * FROM cases")
    original = store.connect
    connections, queries = [], []

    def connect():
        db = original()
        connections.append(db)
        db.set_trace_callback(queries.append)
        db.set_authorizer(
            lambda operation, *_: (
                sqlite3.SQLITE_DENY
                if operation
                in {sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE}
                else sqlite3.SQLITE_OK
            )
        )
        return db

    monkeypatch.setattr(store, "connect", connect)
    result = list_cases(store)
    assert result and len(connections) == 1
    assert len([q for q in queries if q.lstrip().upper().startswith(("SELECT", "WITH"))]) == 2
    assert "PRAGMA query_only=ON" in queries
    monkeypatch.setattr(store, "connect", original)
    assert store.all("SELECT * FROM cases") == before
