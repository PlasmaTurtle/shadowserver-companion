"""Preserve immutable revisions, reject invalid upgrades, and bind package bytes."""

from contextlib import closing
import hashlib
import json
import sqlite3

import pytest

from workbench import migrations
from workbench.evidence_registry import validate_registry
from workbench.repositories.sources import SourceRepository
from workbench.store import Store


def old_store(tmp_path, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(migrations, "SCHEMA_VERSION", 16)
        return Store(tmp_path)


def upgrade(store):
    from workbench.evidence_registry_migration import schema

    with closing(store.connect()) as db:
        db.execute("PRAGMA foreign_keys=OFF")
        db.execute("BEGIN IMMEDIATE")
        try:
            schema(db)
            assert not db.execute("PRAGMA foreign_key_check").fetchall()
            db.commit()
        except Exception:
            db.rollback()
            raise


def test_legacy_revision_bytes_and_ids_survive_registry_migration(tmp_path, monkeypatch):
    store = old_store(tmp_path, monkeypatch)
    path = "evidence/cve/original.json"
    store.path(path).parent.mkdir(parents=True)
    store.path(path).write_bytes(b"original bytes")
    digest = hashlib.sha256(b"original bytes").hexdigest()
    raw = (
        '{ "id": "CVE-2026-1234", "sources": [{"record_path": "'
        + path
        + '", "sha256": "'
        + digest
        + '"}] }'
    )
    with store.transaction() as db:
        db.execute("INSERT INTO cache VALUES(?,?,?)", ("cve-version:stable", raw, "original time"))
        db.execute(
            "INSERT INTO cache VALUES(?,?,?)",
            ("risk-version:old", '{"source":{"record_path":"evidence/old.json"}}', "old"),
        )
    store.path("evidence/old.json").write_bytes(b"legacy")
    upgrade(store)
    row = SourceRepository(store).get("cve-version:stable")
    assert row == {"key": "cve-version:stable", "payload": raw, "retrieved_at": "original time"}
    assert store.one("SELECT count(*) n FROM cache")["n"] == 0
    with store.read_snapshot() as db:
        assert validate_registry(db, root=store.root) == {
            "available": True,
            "revisions": 2,
            "captures": 2,
            "legacy_unknown": 1,
        }
    assert store.path(path).read_bytes() == b"original bytes"
    for sql in (
        "UPDATE evidence_revisions SET provider='changed'",
        "DELETE FROM evidence_captures",
        "UPDATE evidence_revision_captures SET capture_id='bad'",
    ):
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            with store.transaction() as db:
                db.execute(sql)


def test_new_revision_writer_keeps_first_snapshot_and_rejects_duplicate_attempt(
    tmp_path, monkeypatch
):
    store = old_store(tmp_path, monkeypatch)
    upgrade(store)
    repo = SourceRepository(store)
    with store.transaction() as db:
        repo.put(
            db, "intelligence-version:stable", {"id": "CVE-2026-1234", "retrieved_at": "first"}
        )
        repo.put(
            db, "intelligence-version:stable", {"id": "CVE-2026-1234", "retrieved_at": "later"}
        )
        repo.record_attempt(
            db, {"id": "attempt", "completed_at": "first", "outcome": "network_error"}
        )
    assert repo.payload("intelligence-version:stable")["retrieved_at"] == "first"
    with pytest.raises(sqlite3.IntegrityError):
        with store.transaction() as db:
            repo.record_attempt(
                db, {"id": "attempt", "completed_at": "later", "outcome": "network_error"}
            )
    with pytest.raises(sqlite3.IntegrityError, match="evidence registry"):
        with store.transaction() as db:
            db.execute("INSERT INTO cache VALUES('risk-version:bad','{}','now')")


def test_invalid_legacy_revision_rolls_back_schema_and_payloads(tmp_path, monkeypatch):
    store = old_store(tmp_path, monkeypatch)
    with store.transaction() as db:
        db.execute("INSERT INTO cache VALUES('cve-version:bad','[]','old')")
    with pytest.raises(ValueError):
        upgrade(store)
    assert store.one("SELECT payload FROM cache")["payload"] == "[]"
    assert not store.one("SELECT name FROM sqlite_master WHERE name='evidence_revisions'")
    assert not store.one("SELECT name FROM sqlite_master WHERE name='section_validation_identity'")


def test_registry_verification_detects_capture_loss_and_out_of_band_corruption(
    tmp_path, monkeypatch
):
    store = old_store(tmp_path, monkeypatch)
    upgrade(store)
    source = {"record_path": "evidence/missing.json", "sha256": "0" * 64}
    with store.transaction() as db:
        SourceRepository.put(db, "risk-version:one", {"source": source})
    with store.read_snapshot() as db, pytest.raises(ValueError, match="missing a captured"):
        validate_registry(db, root=store.root)
    with store.transaction() as db:
        db.execute("DROP TRIGGER immutable_evidence_revisions_update")
        db.execute("UPDATE evidence_revisions SET payload=?", (json.dumps({"source": {}}),))
    with store.read_snapshot() as db, pytest.raises(ValueError, match="saved digest"):
        validate_registry(db)


def test_case_condition_and_section_event_ownership_are_database_enforced(tmp_path):
    from test_backup_snapshot_decode_095 import workspace_with_report

    store, _ = workspace_with_report(tmp_path, b'{"draft": {}, "evidence": []}', persist=False)
    case = store.one("SELECT * FROM cases")
    entry = store.one("SELECT entry_id FROM case_entries WHERE case_id=?", (case["id"],))[
        "entry_id"
    ]
    with store.transaction() as db:
        values = {**case, "id": "another-case"}
        db.execute(
            "INSERT INTO cases("
            + ",".join(values)
            + ") VALUES("
            + ",".join("?" for _ in values)
            + ")",
            tuple(values.values()),
        )
        db.execute(
            "INSERT INTO section_validations VALUES(?,?,?,?,?,?,?,?)",
            ("validation", case["id"], "summary", 1, "now", "Analyst", "hash", "{}"),
        )
    with pytest.raises(sqlite3.IntegrityError):
        with store.transaction() as db:
            db.execute("INSERT INTO case_entry_conditions VALUES('another-case',?,'[]')", (entry,))
    for case_id, section in (("another-case", "summary"), (case["id"], "findings")):
        with pytest.raises(sqlite3.IntegrityError):
            with store.transaction() as db:
                db.execute(
                    "INSERT INTO section_events(case_id,section_key,action,actor,created_at,revision,validation_id) VALUES(?,?,'validated','Analyst','now',1,'validation')",
                    (case_id, section),
                )
    with store.transaction() as db:
        db.execute(
            "INSERT INTO section_events(case_id,section_key,action,actor,created_at,revision,validation_id) VALUES(?,'summary','validated','Analyst','now',1,'validation')",
            (case["id"],),
        )
    with store.transaction() as db:
        db.execute(
            "INSERT OR IGNORE INTO case_entry_conditions VALUES(?,?,'[]')", (case["id"], entry)
        )
    for sql in (
        "UPDATE cases SET draft='[]'",
        "UPDATE cases SET entity_snapshot='not JSON'",
        "UPDATE case_entry_conditions SET conditions='{}'",
    ):
        with pytest.raises(sqlite3.IntegrityError):
            with store.transaction() as db:
                db.execute(sql)
    assert not store.all("PRAGMA foreign_key_check")


def test_report_manifest_digest_detects_hash_consistent_replacement_and_paths_are_unique(tmp_path):
    from test_backup_snapshot_decode_095 import workspace_with_report
    from workbench.repositories.artifacts import ArtifactRepository

    store, folder = workspace_with_report(tmp_path, b'{"draft": {}, "evidence": []}')
    report = store.one("SELECT * FROM reports")
    saved = store.one("SELECT * FROM artifact_records")
    assert (
        saved["manifest_sha256"]
        == hashlib.sha256((folder / "manifest.json").read_bytes()).hexdigest()
    )
    # An unavailable render file does not hide a correctly bound historical snapshot.
    (folder / "notification.pdf").unlink()
    assert (
        ArtifactRepository(store).snapshot_inventory(report)[1] == b'{"draft": {}, "evidence": []}'
    )
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        with store.transaction() as db:
            db.execute("UPDATE reports SET certification_source='analyst'")
    with pytest.raises(sqlite3.IntegrityError):
        with store.transaction() as db:
            db.execute(
                "INSERT INTO reports(id,lead_id,entity_id,case_id,revision,created_at,path) VALUES('another',?,?,?,2,'now',?)",
                (report["lead_id"], report["entity_id"], report["case_id"], report["path"]),
            )
    manifest = json.loads((folder / "manifest.json").read_text())
    manifest["created_at"] = "rewritten"
    (folder / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="manifest differs"):
        ArtifactRepository(store).snapshot_inventory(report)


def test_selected_intelligence_reads_ignore_unrelated_bank_and_use_prefix_index(tmp_path):
    from workbench.intelligence_index import bank_index

    store = Store(tmp_path)
    with store.transaction() as db:
        for suffix in ("1234", "9999"):
            SourceRepository.put(db, "intelligence-version:" + suffix, {"id": "CVE-2026-" + suffix})
            SourceRepository.put(
                db, "intelligence-latest:CVE-2026-" + suffix, {"revision_id": suffix}
            )
        db.execute("DROP TRIGGER immutable_evidence_revisions_update")
        db.execute(
            "UPDATE evidence_revisions SET payload_sha256=? WHERE revision_id='9999'", ("0" * 64,)
        )
    with store.read_snapshot() as db:
        statements = []
        db.set_trace_callback(statements.append)
        assert set(bank_index(store, db, {"CVE-2026-1234"})) == {"CVE-2026-1234"}
        assert bank_index(store, db, set()) == {}
        assert len([sql for sql in statements if "JOIN evidence_revisions" in sql]) == 1
        plan = " ".join(
            r[3]
            for r in db.execute(
                "EXPLAIN QUERY PLAN SELECT key FROM cache WHERE key GLOB 'intelligence-latest:*'"
            )
        )
        assert "SEARCH" in plan and "key>" in plan
    with pytest.raises(ValueError, match="payload digest"):
        bank_index(store)


@pytest.mark.parametrize("damage", ["scope", "section", "json", "duplicate_path"])
def test_upgrade_preflight_retains_invalid_legacy_data_for_review(tmp_path, damage):
    from test_backup_snapshot_decode_095 import workspace_with_report
    from schema_helpers import restore_schema

    store, folder = workspace_with_report(tmp_path, b'{"draft": {}, "evidence": []}')
    report = store.one("SELECT * FROM reports")
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    with closing(store.connect()) as db:
        restore_schema(db, 16)
    with store.transaction() as db:
        if damage == "scope":
            case = dict(db.execute("SELECT * FROM cases").fetchone())
            case["id"] = "unowned-case"
            db.execute(
                "INSERT INTO cases("
                + ",".join(case)
                + ") VALUES("
                + ",".join("?" for _ in case)
                + ")",
                tuple(case.values()),
            )
            entry = db.execute("SELECT id FROM entries LIMIT 1").fetchone()[0]
            db.execute("INSERT INTO case_entry_conditions VALUES('unowned-case',?,'[]')", (entry,))
        elif damage == "section":
            db.execute(
                "INSERT INTO section_validations VALUES('legacy-validation',?,'summary',1,'then','Analyst','hash','{}')",
                (report["case_id"],),
            )
            db.execute(
                "INSERT INTO section_events(case_id,section_key,action,actor,created_at,revision,validation_id) VALUES(?,'findings','validated','Analyst','then',1,'legacy-validation')",
                (report["case_id"],),
            )
        elif damage == "json":
            db.execute("UPDATE cases SET draft='[]'")
        else:
            db.execute(
                "INSERT INTO reports(id,lead_id,entity_id,case_id,revision,created_at,path) VALUES('duplicate-path',?,?,?,2,'then',?)",
                (report["lead_id"], report["entity_id"], report["case_id"], report["path"]),
            )
    with pytest.raises(ValueError, match="Cannot upgrade"):
        Store(store.root)
    assert store.one("PRAGMA user_version")["user_version"] == 16
    assert not store.one("SELECT name FROM sqlite_master WHERE name='evidence_revisions'")
    assert before == {p.name: p.read_bytes() for p in folder.iterdir()}
    backups = list((store.root / "backups").glob("before-schema-*.sqlite3"))
    assert backups
    with closing(sqlite3.connect(backups[-1])) as backup:
        assert backup.execute("PRAGMA user_version").fetchone()[0] == 16


@pytest.mark.parametrize("manifest_state", ["identifierless", "missing", "incomplete"])
def test_artifact_legacy_backfill_preserves_bytes_and_explicit_unknowns(tmp_path, manifest_state):
    from test_backup_snapshot_decode_095 import workspace_with_report
    from schema_helpers import restore_schema
    from workbench.artifact_registry import validate_registry as validate_artifacts

    store, folder = workspace_with_report(tmp_path, b'{"draft": {}, "evidence": []}')
    manifest = folder / "manifest.json"
    if manifest_state == "missing":
        manifest.unlink()
    elif manifest_state == "incomplete":
        value = json.loads(manifest.read_text())
        value["schema_version"] = 4
        manifest.write_text(json.dumps(value))
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    with closing(store.connect()) as db:
        restore_schema(db, 16)
    upgraded = Store(store.root)
    row = upgraded.one("SELECT * FROM artifact_records")
    assert row["binding_state"] == (
        "legacy_manifest" if manifest_state == "identifierless" else "legacy_unverified"
    )
    assert (row["manifest_sha256"] is None) == (manifest_state != "identifierless")
    assert before == {p.name: p.read_bytes() for p in folder.iterdir()}
    with upgraded.read_snapshot() as db:
        summary = validate_artifacts(upgraded.root, db)
    assert summary["legacy_unverified"] == int(manifest_state != "identifierless")
    before_backups = list((store.root / "backups").iterdir())
    Store(store.root)
    assert list((store.root / "backups").iterdir()) == before_backups


def test_replace_cannot_bypass_immutable_registry_guards(tmp_path):
    from test_backup_snapshot_decode_095 import workspace_with_report

    store, _ = workspace_with_report(tmp_path, b'{"draft": {}, "evidence": []}')
    with store.transaction() as db:
        SourceRepository.put(db, "risk-version:stable", {"source": {}})
    for table in ("reports", "artifact_records", "evidence_revisions"):
        original = store.all(f"SELECT * FROM {table}")
        with pytest.raises(sqlite3.IntegrityError, match="immutable|Immutable"):
            with store.transaction() as db:
                assert not db.execute("PRAGMA recursive_triggers").fetchone()[0]
                db.execute(f"INSERT OR REPLACE INTO {table} SELECT * FROM {table}")
        assert store.all(f"SELECT * FROM {table}") == original


def test_new_registry_identity_keys_cannot_be_null(tmp_path):
    store = Store(tmp_path)
    writes = (
        (
            "INSERT INTO evidence_revisions VALUES(NULL,'risk-version','null-test','','{}',?,'now')",
            (hashlib.sha256(b"{}").hexdigest(),),
        ),
        (
            "INSERT INTO evidence_captures VALUES(NULL,'evidence/null-test.json',NULL,'','','','legacy_unknown')",
            (),
        ),
        (
            "INSERT INTO artifact_records VALUES('report','unbound',NULL,NULL,'reports/unbound',NULL,'{}','legacy_unverified')",
            (),
        ),
    )
    for sql, args in writes:
        with pytest.raises(sqlite3.IntegrityError, match="NOT NULL|CHECK"):
            with store.transaction() as db:
                db.execute(sql, args)
    for table in ("evidence_revisions", "evidence_captures", "artifact_records"):
        assert store.one(f"SELECT count(*) n FROM {table}")["n"] == 0
