"""Snapshot consistency and atomic publication across the extracted repositories."""

from tests.support.qualification import registry_factory, capture_website

import json
import sqlite3

import pytest

from modules.investigations.components.cases import Cases
from modules.workspace.components.repositories.records import Records
from modules.library.components.repositories.sources import SourceRepository
from modules.entities.components.services.entities import EntityService
from modules.workspace.components.store import Store
from modules.library.components.intelligence import acquisition, service
from tests.support.workbench import app, client, import_rows, observations, FakeRegistry
from modules.investigations.tests.support.cases import opened, certified, attempt
from modules.library.tests.support.cve_sources import ID, nvd, response


def database_state(store):
    tables = [
        row["name"]
        for row in store.all(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    return {
        name: sorted(
            store.all(f'SELECT * FROM "{name}"'), key=lambda row: json.dumps(row, sort_keys=True)
        )
        for name in tables
    }


def test_read_snapshot_is_read_only_and_does_not_reserve_writer(tmp_path):
    store = Store(tmp_path)
    with store.read_snapshot() as db:
        before = db.execute("SELECT count(*) FROM cache").fetchone()[0]
        with store.transaction() as writer:
            SourceRepository.put(writer, "snapshot-test", {"value": "new"})
        assert db.execute("SELECT count(*) FROM cache").fetchone()[0] == before
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            db.execute("DELETE FROM cache")
    assert SourceRepository(store).payload("snapshot-test") == {"value": "new"}


def test_case_projection_cannot_mix_entity_and_case_revisions(client, app, monkeypatch):
    lead = opened(client, app)
    store = app.state.store
    before = Cases(store).view(lead["case_id"])
    original = Records.one
    committed = False

    def read_then_commit(records, sql, args=()):
        nonlocal committed
        row = original(records, sql, args)
        if sql == "SELECT * FROM cases WHERE id=?" and not committed:
            committed = True
            with store.transaction() as writer:
                writer.execute(
                    "UPDATE leads SET company='New business name' WHERE id=?", (lead["id"],)
                )
                writer.execute(
                    "UPDATE cases SET title='New title',version=version+1 WHERE id=?",
                    (lead["case_id"],),
                )
        return row

    monkeypatch.setattr(Records, "one", read_then_commit)
    during = Cases(store).view(lead["case_id"])
    assert committed
    assert during == before
    after = Cases(store).view(lead["case_id"])
    assert after["company"] == before["company"]  # Report identity remains pinned.
    assert after["current_entity"]["company"] == "New business name"
    assert after["case"]["title"] == "New title"
    assert after["case"]["version"] == before["case"]["version"] + 1
    # No observation field, including unknown/blank source columns, is lost.
    assert after["entries"] == before["entries"]
    assert after["entries"][0]["id"] == after["attribution_entry_id"]


@pytest.mark.parametrize("operation", ["rename", "profile", "merge"])
def test_entity_command_rolls_back_all_related_writes(client, app, monkeypatch, operation):
    lead = opened(client, app)
    store = app.state.store
    target = None
    if operation == "merge":

        class Other(FakeRegistry):
            def lookup(self, ip):
                record = super().lookup(ip)
                return type(record)(
                    record.ip,
                    record.registry,
                    record.source_url,
                    record.retrieved_at,
                    {"contact": "support@another.com"},
                )

        app.state.intake.attribution_factory = registry_factory(Other)
        import_rows(
            client,
            app,
            [{**observations()[0], "hostname": "mail.another.com", "ip": "8.8.4.4"}],
            "other.csv",
        )
        target = next(row for row in store.all("SELECT * FROM leads") if row["id"] != lead["id"])
    action = {
        "rename": "entity_renamed",
        "profile": "entity_profile_saved",
        "merge": "entity_merged",
    }[operation]
    with store.transaction() as db:
        db.execute(f"""CREATE TRIGGER fail_entity_event BEFORE INSERT ON events
            WHEN NEW.action='{action}' BEGIN SELECT RAISE(ABORT,'injected entity failure'); END""")
    before = database_state(store)
    exports = []
    monkeypatch.setattr(store, "export_all", lambda: exports.append(True))
    command = EntityService(store)
    revision = store.one("SELECT draft_revision FROM leads WHERE id=?", (lead["id"],))[
        "draft_revision"
    ]
    with pytest.raises(sqlite3.IntegrityError, match="injected entity failure"):
        if operation == "rename":
            command.rename_entity(lead["id"], "Renamed entity", revision)
        elif operation == "profile":
            command.update_entity_profile(lead["id"], {"city": "New city"}, revision)
        else:
            command.merge_entities(lead["id"], target["id"], revision, target["draft_revision"])
    assert database_state(store) == before
    assert exports == []


def test_reference_pointer_and_revision_publish_atomically(tmp_path, monkeypatch):
    store = Store(tmp_path)
    monkeypatch.setattr(acquisition, "_wait_for_nvd", lambda *args: None)
    monkeypatch.setattr(
        acquisition, "_response_get", lambda *a, **kw: response(nvd("First wording"))
    )
    first = service.verify(store, ID)
    previous = SourceRepository(store).get("cve-reference:" + ID)
    with store.transaction() as db:
        db.execute("""CREATE TRIGGER fail_source_version BEFORE INSERT ON evidence_revisions
            WHEN NEW.key LIKE 'cve-version:%'
            BEGIN SELECT RAISE(ABORT,'injected publication failure'); END""")
    monkeypatch.setattr(
        acquisition, "_response_get", lambda *a, **kw: response(nvd("Later wording"))
    )
    with pytest.raises(sqlite3.IntegrityError, match="injected publication failure"):
        service.verify(store, ID, refresh=True)
    assert SourceRepository(store).get("cve-reference:" + ID) == previous
    versions = store.all("SELECT * FROM evidence_revisions WHERE key LIKE 'cve-version:%'")
    assert len(versions) == 1
    assert json.loads(versions[0]["payload"])["revision_id"] == first["revision_id"]
    # The completed acquisition is evidence even when publication fails.
    assert (
        len(store.all("SELECT * FROM evidence_revisions WHERE key LIKE 'acquisition-version:%'"))
        == 2
    )


def test_source_payload_and_proof_use_same_snapshot(tmp_path, monkeypatch):
    store = Store(tmp_path)
    repo = SourceRepository(store)
    with store.transaction() as db:
        repo.put(db, "risk:kev", {"version": "old"})
        repo.put(db, "risk-proof:kev", {"revision_id": "old"})
    original = Records.one
    changed = False

    def switch_after_payload(records, sql, args=()):
        nonlocal changed
        result = original(records, sql, args)
        if args == ("risk:kev",) and not changed:
            changed = True
            with store.transaction() as db:
                repo.put(db, "risk:kev", {"version": "new"})
                repo.put(db, "risk-proof:kev", {"revision_id": "new"})
        return result

    monkeypatch.setattr(Records, "one", switch_after_payload)
    state = repo.risk_state("kev")
    assert json.loads(state["risk"]["payload"])["version"] == "old"
    assert json.loads(state["risk-proof"]["payload"])["revision_id"] == "old"
    assert repo.payload("risk-proof:kev")["revision_id"] == "new"


def test_capture_retains_matching_proof_when_shared_cache_refreshes(tmp_path, monkeypatch):
    store = Store(tmp_path)
    data = {
        "status": "OK",
        "data": [{"cve": ID, "epss": "0.3", "percentile": "0.7", "date": "2026-11-05"}],
    }
    monkeypatch.setattr(acquisition, "_response_get", lambda *a, **kw: response(data))
    first = acquisition.capture_json(store, "epss:" + ID, acquisition.EPSS_URL + ID)
    data["data"][0]["epss"] = "0.9"
    second = acquisition.capture_json(store, "epss:" + ID, acquisition.EPSS_URL + ID, refresh=True)
    assert first.source["revision_id"] != second.source["revision_id"]
    assert first.data["data"][0]["epss"] == "0.3"
    assert second.data["data"][0]["epss"] == "0.9"
    result = {}
    acquisition._append_acquisition(store, "epss:" + ID, result, first.state)
    assert result["acquisition"][0]["source_snapshot_id"] == first.source["revision_id"]
    assert json.loads(store.path(first.source["record_path"]).read_bytes()) == first.data


def test_delivery_failure_rolls_back_contact_case_and_report(client, app):
    lead, report = certified(client, app)
    store = app.state.store
    with store.transaction() as db:
        db.execute("""CREATE TRIGGER fail_delivery_event BEFORE INSERT ON events
            WHEN NEW.action='contact_attempt'
            BEGIN SELECT RAISE(ABORT,'injected delivery failure'); END""")
    before = database_state(store)
    with pytest.raises(sqlite3.IntegrityError, match="injected delivery failure"):
        Cases(store).attempt(lead["case_id"], attempt(lead, report))
    assert database_state(store) == before


def test_repositories_cannot_commit_and_extracted_commands_cannot_execute_sql():
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    repositories = list((root / "modules").glob("*/components/repositories/*.py"))
    assert repositories
    for path in repositories:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        forbidden = [
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("commit", "rollback", "transaction", "executescript")
        ]
        assert not forbidden, (path.name, forbidden)
    for name in (
        "investigations/components/cases.py",
        "entities/components/services/entities.py",
        "investigations/components/services/case_queries.py",
        "library/components/intelligence/acquisition.py",
        "library/components/intelligence/service.py",
    ):
        tree = ast.parse((root / "modules" / name).read_text(encoding="utf-8"))
        assert not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("execute", "executemany", "executescript")
            for node in ast.walk(tree)
        ), name
