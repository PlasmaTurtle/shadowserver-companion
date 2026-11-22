"""Archive durability follows workspace commits, recovery and portable backups."""

import csv
import hashlib
import io
import json
import sqlite3
from zipfile import ZipFile

import pytest

from modules.accretion.components.dark_matter import enqueue_batch
from modules.workspace.components import store as store_module
from modules.workspace.components.store import Store
from modules.workspace.components.workspace_data import export_workspace, unpack_workspace
from modules.workspace.components.workspace_health import inspect_workspace
from modules.workspace.components.workspace_recovery import compact


def source(store):
    fields = {
        "hostname": "",
        "ip": "not-an-address",
        "tag": "independent-detector",
        "region": "Outside the selected jurisdiction",
        "port": "invalid-port",
        "http_code": "403",
        "future_provider_field": "complete original value " * 400,
    }
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(fields))
    writer.writeheader()
    writer.writerow(fields)
    original = stream.getvalue().encode()
    digest = hashlib.sha256(original).hexdigest()
    path = store.root / "originals" / "scan_http_vulnerable.csv"
    path.write_bytes(original)
    with store.transaction() as db:
        db.execute(
            "INSERT INTO imports(id,fingerprint,sha256,name,path,created_at,config) "
            "VALUES(?,?,?,?,?,?,?)",
            (
                "report",
                digest,
                digest,
                path.name,
                "originals/" + path.name,
                "2026-11-21T00:00:00Z",
                '{"report_type":"scan_http_vulnerable"}',
            ),
        )
    return {"source": {"sheet": "", "row": 2, "fields": fields}}


def retain(store, row):
    with store.transaction() as db:
        enqueue_batch(db, "report", [row], stage="filter", reason="invalid_hostname")


def test_full_field_archive_survives_backup_and_restore(tmp_path):
    store = Store(tmp_path / "workspace")
    row = source(store)
    retain(store, row)
    before = store.dark_matter.query()["items"]
    archive = export_workspace(store)
    try:
        with ZipFile(archive) as saved:
            assert "data/dark_matter.sqlite3" in saved.namelist()
        target = tmp_path / "restored"
        unpack_workspace(archive, target)
        restored = Store(target)
        assert restored.dark_matter.query()["items"] == before
        assert before[0]["raw_fields"] == row["source"]["fields"]
        assert len(before[0]["raw_fields"]["future_provider_field"]) > 4096
        assert (
            restored.dark_matter.get(before[0]["record_id"])["outcomes"]
            == (store.dark_matter.get(before[0]["record_id"])["outcomes"])
        )
        assert (target / "originals" / "scan_http_vulnerable.csv").read_bytes() == (
            store.root / "originals" / "scan_http_vulnerable.csv"
        ).read_bytes()
    finally:
        archive.unlink()


def test_secondary_failure_preserves_committed_outbox_for_startup_replay(tmp_path, monkeypatch):
    store = Store(tmp_path / "workspace")
    row = source(store)

    def unavailable(_root, **_kwargs):
        raise sqlite3.OperationalError("synthetic secondary database unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(store_module, "drain", unavailable)
        with store.transaction() as db:
            db.execute("UPDATE imports SET status='done' WHERE id='report'")
            enqueue_batch(db, "report", [row], stage="filter", reason="invalid_hostname")
    assert store.one("SELECT status FROM imports WHERE id='report'")["status"] == "done"
    assert store.one("SELECT count(*) n FROM dark_matter_outbox")["n"] == 1
    assert store.dark_matter.query()["total"] == 0
    reopened = Store(store.root)
    assert reopened.one("SELECT count(*) n FROM dark_matter_outbox")["n"] == 0
    saved = reopened.dark_matter.query()["items"]
    assert len(saved) == 1 and saved[0]["raw_fields"] == row["source"]["fields"]
    assert len(reopened.dark_matter.get(saved[0]["record_id"])["outcomes"]) == 1


def test_primary_rollback_never_delivers_archive_records(tmp_path):
    store = Store(tmp_path / "workspace")
    row = source(store)
    with pytest.raises(RuntimeError, match="publication failed"):
        with store.transaction() as db:
            enqueue_batch(db, "report", [row], stage="filter", reason="invalid_hostname")
            raise RuntimeError("publication failed")
    assert store.one("SELECT count(*) n FROM dark_matter_outbox")["n"] == 0
    assert store.dark_matter.query()["total"] == 0


def test_backup_replays_delivered_but_unacknowledged_event_once(tmp_path):
    store = Store(tmp_path / "workspace")
    row = source(store)
    store.after_commit.clear()  # Model the durable state at interrupted delivery.
    retain(store, row)
    event = store.one("SELECT * FROM dark_matter_outbox")
    store.dark_matter.record_batch(
        **json.loads(event["payload"]),
        event_id=event["event_id"],
        recorded_at=event["recorded_at"],
    )
    original = store.dark_matter.query()["items"][0]
    archive = export_workspace(store)
    try:
        target = tmp_path / "restored"
        unpack_workspace(archive, target)
        restored = Store(target)
        assert restored.one("SELECT count(*) n FROM dark_matter_outbox")["n"] == 0
        assert restored.dark_matter.query()["items"] == [original]
        assert len(restored.dark_matter.get(original["record_id"])["outcomes"]) == 1
        assert store.one("SELECT count(*) n FROM dark_matter_outbox")["n"] == 1
    finally:
        archive.unlink()


def test_health_and_compaction_include_archive_without_changing_records(tmp_path):
    store = Store(tmp_path / "workspace")
    retain(store, source(store))
    original = store.dark_matter.query()["items"]
    health = inspect_workspace(store.root)
    archived = next(item for item in health["stores"] if item["store"] == "dark_matter")
    assert archived["status"] == "ok", archived
    assert compact(store.root, confirmation="COMPACT")["ok"]
    assert store.dark_matter.query()["items"] == original
