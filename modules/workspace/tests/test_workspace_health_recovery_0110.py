"""Offline recovery and cleanup preserve evidence, including damaged originals."""

from contextlib import closing

import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading

import pytest
from attribution import EvidenceStore
from attribution.models import ResponseSnapshot
from modules.attribution.tests.support.attribution_review import review_app
from tests.support.workbench import app, client

from modules.workspace.databases.migrations import SCHEMA_VERSION
from modules.workspace.components.store import Store
from modules.workspace.components.workspace_data import export_workspace, write_state_json
from modules.workspace.components.workspace_health import inspect_workspace, InspectionStopped
from modules.workspace.components.workspace_maintenance import plan, cleanup
from modules.workspace.components.workspace_recovery import (
    restore,
    rollback,
    compact,
    _marker,
    guard_interrupted_recovery,
)
from modules.workspace.components.workspace_lock import acquire_lock


def test_recovery_state_keeps_its_sorted_json_encoding(tmp_path):
    value = {"z": "Café\nSecond line", "a": [None, 1, False]}
    reference = tmp_path / "reference.json"
    with reference.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True)
    destination = tmp_path / "journal.json"
    write_state_json(destination, value)
    assert destination.read_bytes() == reference.read_bytes()
    assert json.loads(destination.read_bytes()) == value


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def saved_archive(tmp_path):
    source = Store(tmp_path / "source")
    (source.root / "inbox" / "original.txt").write_bytes(b"verified backup content")
    return export_workspace(source)


def test_health_readonly_no_migration_and_independent_bad_reference_store(tmp_path, monkeypatch):
    store = Store(tmp_path / "data")
    before = sha(store.db)
    monkeypatch.setattr(Store, "__init__", lambda *args: pytest.fail("health initialized Store"))
    health = inspect_workspace(store.root)
    assert health["ok"], health
    assert sha(store.db) == before
    reference = Path(str(store.root) + "-reference") / "nvd"
    reference.mkdir(parents=True)
    (reference / "risk.sqlite3").write_bytes(b"damaged SQLite")
    health = inspect_workspace(store.root)
    assert health["stores"][0]["status"] == "ok"
    assert next(item for item in health["stores"] if item["store"] == "risk")["status"] == "error"
    assert not health["ok"]
    assert sha(store.db) == before


def test_health_future_main_is_not_migrated_and_cancellable(tmp_path):
    store = Store(tmp_path / "data")
    with closing(sqlite3.connect(store.db)) as db, db:
        db.execute(f"PRAGMA user_version={SCHEMA_VERSION + 10}")
    before = sha(store.db)
    health = inspect_workspace(store.root)
    assert health["stores"][0]["status"] == "incompatible"
    assert sha(store.db) == before
    with pytest.raises(InspectionStopped, match="cancelled"):
        inspect_workspace(store.root, cancelled=lambda: True)
    with pytest.raises(InspectionStopped, match="time budget"):
        inspect_workspace(store.root, timeout=0)


def test_cleanup_plan_matches_apply_and_keeps_all_snapshots(tmp_path):
    root = Store(tmp_path / "data").root
    with EvidenceStore(root / "attribution.sqlite3") as evidence:
        snapshot = ResponseSnapshot.create(
            "https://example.test", "https://example.test", 200, {}, b"retained"
        )
        evidence.save_snapshot(snapshot)
        evidence.cache("expired", [snapshot], 100)
        evidence.cache("current", [snapshot], 10000)
        evidence._db.execute("UPDATE cache SET expires=1 WHERE key='expired'")
        evidence._db.commit()
        before = tuple(evidence._db.execute("SELECT id,metadata,body FROM snapshots").fetchone())
    reviewed = plan(root)
    assert reviewed["lookup_pointers"] == 1
    assert reviewed["files_removed"] == 0
    applied = cleanup(root, cutoff=reviewed["cutoff"], token=reviewed["token"])
    assert applied["removed"] == applied["lookup_pointers"] == 1
    assert applied["estimated_payload_bytes"] == reviewed["estimated_payload_bytes"]
    with closing(sqlite3.connect(root / "attribution.sqlite3")) as db, db:
        assert db.execute("SELECT key FROM cache").fetchall() == [("current",)]
        assert tuple(db.execute("SELECT id,metadata,body FROM snapshots").fetchone()) == before


def test_cleanup_rejects_stale_review_and_rolls_back_trigger_failure(tmp_path):
    root = Store(tmp_path / "data").root
    with EvidenceStore(root / "attribution.sqlite3") as evidence:
        evidence._db.execute("INSERT INTO cache VALUES ('a','[]',1)")
        evidence._db.commit()
    reviewed = plan(root)
    with closing(sqlite3.connect(root / "attribution.sqlite3")) as db, db:
        db.execute("INSERT INTO cache VALUES ('b','[]',1)")
    with pytest.raises(ValueError, match="changed"):
        cleanup(root, cutoff=reviewed["cutoff"], token=reviewed["token"])
    reviewed = plan(root)
    with closing(sqlite3.connect(root / "attribution.sqlite3")) as db, db:
        db.execute(
            "CREATE TRIGGER stop_cleanup BEFORE DELETE ON cache WHEN OLD.key='b' BEGIN SELECT RAISE(ABORT,'stop'); END"
        )
    with pytest.raises(sqlite3.IntegrityError):
        cleanup(root, cutoff=reviewed["cutoff"], token=reviewed["token"])
    with closing(sqlite3.connect(root / "attribution.sqlite3")) as db, db:
        assert db.execute("SELECT count(*) FROM cache").fetchone()[0] == 2


@pytest.mark.parametrize("damaged", [True, False])
def test_restore_preserves_damaged_or_future_tree(tmp_path, damaged):
    archive = saved_archive(tmp_path)
    target = tmp_path / "target"
    target.mkdir()
    original = target / "workbench.sqlite3"
    if damaged:
        original.write_bytes(b"damaged bytes must survive")
    else:
        with closing(sqlite3.connect(original)) as db, db:
            db.execute(f"PRAGMA user_version={SCHEMA_VERSION + 10}")
    (target / "private-note.txt").write_bytes(b"keep everything")
    before = sha(original)
    try:
        result = restore(target, archive, confirmation="RESTORE")
        assert inspect_workspace(target)["ok"]
        preserved = Path(result["preserved_workspace"])
        assert sha(preserved / "workbench.sqlite3") == before
        assert (preserved / "private-note.txt").read_bytes() == b"keep everything"
        assert (target / "inbox" / "original.txt").is_file()
        assert not _marker(target).exists()
    finally:
        archive.unlink()


def test_restore_rejects_in_use_invalid_backup_and_wrong_confirmation(tmp_path):
    target = Store(tmp_path / "target").root
    archive = tmp_path / "invalid.zip"
    archive.write_bytes(b"invalid")
    before = sha(target / "workbench.sqlite3")
    with pytest.raises(ValueError, match="confirm RESTORE"):
        restore(target, archive, confirmation="wrong")
    guard = acquire_lock(target.parent, "." + target.name + "-companion.lock")
    try:
        with pytest.raises(SystemExit, match="already open"):
            restore(target, archive, confirmation="RESTORE")
    finally:
        guard.close()
    with pytest.raises(Exception):
        restore(target, archive, confirmation="RESTORE")
    assert sha(target / "workbench.sqlite3") == before


@pytest.mark.parametrize("cancel_after", [1, 2])
def test_restore_cancel_before_or_after_original_move_rolls_back(tmp_path, cancel_after):
    archive = saved_archive(tmp_path)
    target = tmp_path / "target"
    target.mkdir()
    (target / "workbench.sqlite3").write_bytes(b"damaged but preserved")
    calls = 0

    def cancelled():
        nonlocal calls
        calls += 1
        return calls == cancel_after

    try:
        with pytest.raises(InterruptedError):
            restore(target, archive, confirmation="RESTORE", cancelled=cancelled)
        assert (target / "workbench.sqlite3").read_bytes() == b"damaged but preserved"
        assert not _marker(target).exists()
    finally:
        archive.unlink()


def test_crash_marker_blocks_empty_startup_and_offline_rollback_preserves_partial_install(tmp_path):
    target = tmp_path / "target"
    folder = tmp_path / ("target-recovery-" + "a" * 32)
    preserved = folder / "preserved"
    preserved.mkdir(parents=True)
    (preserved / "workbench.sqlite3").write_bytes(b"damaged original")
    write_state_json(
        _marker(target), {"format": 1, "workspace": str(target), "recovery_folder": folder.name}
    )
    with pytest.raises(ValueError, match="interrupted"):
        guard_interrupted_recovery(target)
    target.mkdir()
    (target / "workbench.sqlite3").write_bytes(b"interrupted new install")
    rollback(target, confirmation="ROLLBACK")
    assert (target / "workbench.sqlite3").read_bytes() == b"damaged original"
    assert (
        folder / "interrupted-install" / "workbench.sqlite3"
    ).read_bytes() == b"interrupted new install"
    guard_interrupted_recovery(target)


def test_offline_compaction_keeps_records_and_verified_restore_point(tmp_path):
    store = Store(tmp_path / "data")
    with store.transaction() as db:
        db.execute("CREATE TABLE disposable_test(payload TEXT)")
        db.executemany("INSERT INTO disposable_test VALUES (?)", [("x" * 4000,)] * 200)
        db.execute("DELETE FROM disposable_test")
    before = store.settings()
    result = compact(store.root, confirmation="COMPACT")
    assert result["ok"]
    assert result["reclaimed_database_bytes"] > 0
    assert Store(store.root).settings() == before
    assert inspect_workspace(store.root)["restore_point_count"] >= 1


def test_health_api_background_job_cancel_and_maintenance_admission(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from modules.workspace.components.api import create_app
    from modules.workspace.components import workspace_health_jobs

    entered, release = threading.Event(), threading.Event()

    def blocked(root, *, progress, cancelled):
        entered.set()
        release.wait(5)
        if cancelled():
            raise InspectionStopped("cancelled")
        return {"ok": True}

    monkeypatch.setattr(workspace_health_jobs, "inspect_workspace", blocked)
    app = create_app(tmp_path / "data", worker=False)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        from modules.workspace.tests.support.workspace_data import login

        login(client, app)
        assert client.post("/api/data/health").json()["status"] == "running"
        assert entered.wait(1)
        assert client.get("/api/data/status").status_code == 200
        reviewed = client.get("/api/data/maintenance").json()
        body = {key: reviewed[key] for key in ("cutoff", "token")}
        body["confirmation"] = "CLEAN"
        assert client.post("/api/data/maintenance", json=body).status_code == 422
        assert client.delete("/api/data/health").status_code == 200
        release.set()
        app.state.workspace_health_jobs.thread.join(2)
        assert client.get("/api/data/health").json()["status"] == "cancelled"
        assert client.post("/api/data/maintenance", json=body).json()["removed"] == 0
        body["confirmation"] = "wrong"
        assert client.post("/api/data/maintenance", json=body).status_code == 422


@pytest.mark.parametrize("attributed", [False, True])
def test_health_checks_retained_contact_files_without_opening_mutable_evidence_store(
    tmp_path, monkeypatch, attributed
):
    from modules.entities.tests.support.contacts import entity_only
    from modules.entities.tests.support.contacts import attributed_entity, contact_result
    from modules.entities.components.contact_records import ContactRecords

    store = Store(tmp_path / "data")
    identity = attributed_entity(store)["id"] if attributed else entity_only(store)
    contacts = ContactRecords(store)
    contacts.save_run(contacts.scope(identity), contact_result())
    before = sha(store.db)
    monkeypatch.setattr(
        EvidenceStore,
        "__init__",
        lambda *args: pytest.fail("Health opened mutable attribution store"),
    )
    health = inspect_workspace(store.root)
    assert health["ok"], health
    assert sha(store.db) == before
    run = store.one("SELECT * FROM contact_runs")
    snapshot = json.loads(run["payload"])["snapshots"][0]
    (store.root / snapshot["path"]).unlink()
    health = inspect_workspace(store.root)
    assert not health["ok"]
    assert health["stores"][0]["status"] == "error"


def test_health_detects_changed_registered_report_and_evidence_capture(tmp_path):
    from modules.workspace.tests.support.workspace_data import workspace_with_report
    from modules.workspace.tests.support.workspace_data import captured, bank_record

    store, folder = workspace_with_report(tmp_path, b'{"draft":{},"evidence":[]}')
    proof = captured(store)
    bank_record(store, "cve-version:retained", {"id": "CVE-2026-1234", "sources": [proof]})
    assert inspect_workspace(store.root)["ok"]
    saved = (store.root / proof["record_path"]).read_bytes()
    (store.root / proof["record_path"]).write_bytes(b"changed provider bytes")
    assert not inspect_workspace(store.root)["ok"]
    (store.root / proof["record_path"]).write_bytes(saved)
    (folder / "notification.pdf").write_bytes(b"changed report bytes")
    assert not inspect_workspace(store.root)["ok"]


@pytest.mark.parametrize("future", [False, True])
def test_offline_cli_checks_unopenable_workspace_without_normal_startup(tmp_path, future):
    root = tmp_path / "data"
    root.mkdir()
    path = root / "workbench.sqlite3"
    if future:
        with closing(sqlite3.connect(path)) as db, db:
            db.execute(f"PRAGMA user_version={SCHEMA_VERSION + 10}")
    else:
        path.write_bytes(b"corrupt SQLite bytes")
    before = sha(path)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "modules.workspace.components.workspace_recovery",
            "--data-dir",
            str(root),
            "check",
        ],
        text=True,
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 1, result.stderr
    health = json.loads(result.stdout)
    assert health["stores"][0]["status"] == ("incompatible" if future else "error")
    assert sha(path) == before


def test_health_accepts_retained_prior_owner_after_domain_transfer(client, app):
    from modules.entities.tests.support.entity_lifecycle import (
        setup_entities,
        plan_transfer,
        transfer,
    )
    from modules.leads.components.lead_queue import LeadQueue

    source, target = setup_entities(client, app)
    store = app.state.store
    pending = next(row for row in LeadQueue(store).list() if row["entity_id"] == source)
    LeadQueue(store).start(pending["id"], pending["revision"])
    before = store.all("SELECT * FROM entries")
    reviewed = plan_transfer(client, source, target)
    assert transfer(client, source, reviewed).status_code == 200
    assert store.all("SELECT * FROM entries") == before
    health = inspect_workspace(store.root)
    assert health["ok"], health


def test_health_incompatible_analytical_layout_does_not_offer_rebuild(tmp_path):
    store = Store(tmp_path / "data")
    with store.transaction() as db:
        db.execute("ALTER TABLE analytical_observations ADD COLUMN future_column TEXT")
    before = sha(store.db)
    result = inspect_workspace(store.root)["stores"][0]
    assert result["status"] == "incompatible"
    assert "rebuilding cannot repair" in result["message"]
    assert sha(store.db) == before


def test_health_cross_store_snapshot_does_not_mislabel_concurrent_valid_publication(
    review_app, monkeypatch
):
    from contextlib import contextmanager
    from attribution.models import AttributionResult
    from modules.workspace.components import workspace_health

    app, _, group, _, _ = review_app
    store = app.state.store
    path = store.root / "attribution.sqlite3"
    original_readonly = workspace_health.readonly
    published = False
    old_result_count = None

    @contextmanager
    def publish_after_attribution_snapshot_opens(selected):
        nonlocal published, old_result_count
        with original_readonly(selected) as db:
            if Path(selected) == path and not published:
                # Pin the earlier evidence snapshot, then publish normally:
                # immutable result first, main-store pointer second. A checker
                # must not compare that later pointer with this older snapshot.
                old_result_count = db.execute("SELECT count(*) FROM results").fetchone()[0]
                published = True
                with EvidenceStore(path) as evidence:
                    evidence.save_result(
                        AttributionResult(
                            "c" * 32,
                            "example.com",
                            "review",
                            "2026-11-13T00:00:00Z",
                            (),
                            None,
                            None,
                            (),
                            (),
                            {"id": "root-domain-v2"},
                            {},
                        )
                    )
                with store.transaction() as writer:
                    writer.execute(
                        "UPDATE jobs SET attribution_result_id=? WHERE id=?",
                        ("c" * 32, group["id"]),
                    )
            yield db

    monkeypatch.setattr(workspace_health, "readonly", publish_after_attribution_snapshot_opens)
    health = inspect_workspace(store.root)
    assert published
    assert health["ok"], health
    assert health["stores"][1]["counts"]["results"] == old_result_count
    current = inspect_workspace(store.root)
    assert current["ok"], current
    assert current["stores"][1]["counts"]["results"] == old_result_count + 1
    # Ordering must not mask genuine corruption captured before the check.
    with store.transaction() as writer:
        writer.execute("UPDATE jobs SET attribution_result_id='missing' WHERE id=?", (group["id"],))
    failed = inspect_workspace(store.root)
    assert not failed["ok"]
    assert failed["stores"][1]["status"] == "error"
    assert "missing result" in failed["stores"][1]["message"]
