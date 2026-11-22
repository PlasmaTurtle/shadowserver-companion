"""Restore validates closing models before startup can consume orphan packages."""

import hashlib
import json
from pathlib import Path

import pytest

from modules.workspace.tests.support.workspace_data import workspace_with_report
from modules.workspace.components import compact_json, workspace_data
from modules.investigations.components import package_files
from modules.investigations.components.services.recovery import recover_closings


def workspace_with_closure(tmp_path, raw, *, recorded=True, register=True):
    store, _ = workspace_with_report(tmp_path, b'{"draft": {}, "evidence": []}')
    case = store.one("SELECT * FROM cases")
    closure_id = "synthetic-closure"
    relative = f"closures/{case['id']}/{closure_id}"
    folder = store.path(relative)
    folder.mkdir(parents=True)
    files = {"closing-report.pdf": b"PDF", "closing-report.docx": b"DOCX", "snapshot.json": raw}
    for name, value in files.items():
        (folder / name).write_bytes(value)
    (folder / "manifest.json").write_text(
        json.dumps(
            {
                "case_id": case["id"],
                "closure_id": closure_id,
                "expected_version": case["version"],
                "files": {name: hashlib.sha256(value).hexdigest() for name, value in files.items()},
            }
        )
    )
    if recorded:
        with store.transaction() as db:
            db.execute(
                "INSERT INTO case_closures VALUES(?,?,?,?,?,?,?,?)",
                (
                    closure_id,
                    case["id"],
                    "2026-11-13",
                    "Synthetic analyst",
                    "notified",
                    "Synthetic conclusion",
                    relative,
                    hashlib.sha256(raw).hexdigest(),
                ),
            )
            if register:
                from modules.investigations.components.artifact_registry import register_artifact

                register_artifact(db, store.root, "closure", closure_id, legacy=True)
    return store, folder


@pytest.mark.parametrize("raw", [b"[]", b'{"case_id": []}', b'{"storage_format": "unknown"}'])
def test_restore_rejects_hash_consistent_unreadable_closure(tmp_path, raw):
    store, _ = workspace_with_closure(tmp_path, raw)
    with pytest.raises(ValueError, match="Backup closing snapshot"):
        workspace_data.validate_workspace(store.root)


def test_oversized_orphan_closure_is_rejected_before_recovery(tmp_path, monkeypatch):
    import modules.workspace.components.store as store_module

    store, _ = workspace_with_closure(tmp_path, b" " * 101, recorded=False)
    monkeypatch.setattr(workspace_data, "MAX_REPORT_SNAPSHOT_BYTES", 100)
    monkeypatch.setattr(
        store_module, "Store", lambda _: pytest.fail("Recovery ran before preflight")
    )
    with pytest.raises(ValueError, match="read limit"):
        workspace_data.validate_workspace(store.root)


@pytest.mark.parametrize("compact", [False, True])
def test_restore_preserves_supported_closing_snapshot_bytes(tmp_path, compact):
    store, folder = workspace_with_closure(tmp_path, b"{}", register=False)
    case = store.one("SELECT * FROM cases")
    model = {
        "case_id": case["id"],
        "created_at": "2026-11-13",
        "closed_by": "Synthetic analyst",
        "disposition": "notified",
        "conclusion": "Synthetic conclusion",
    }
    raw = (compact_json.dumps(model) if compact else json.dumps(model)).encode()
    (folder / "snapshot.json").write_bytes(raw)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    manifest["files"]["snapshot.json"] = hashlib.sha256(raw).hexdigest()
    (folder / "manifest.json").write_text(json.dumps(manifest))
    with store.transaction() as db:
        db.execute("UPDATE case_closures SET snapshot_sha256=?", (hashlib.sha256(raw).hexdigest(),))
        from modules.investigations.components.artifact_registry import register_artifact

        register_artifact(db, store.root, "closure", "synthetic-closure", legacy=True)
    workspace_data.validate_workspace(store.root)
    assert (folder / "snapshot.json").read_bytes() == raw


def test_recovery_skips_oversized_manifest_before_reading_it(tmp_path, monkeypatch):
    store, folder = workspace_with_closure(tmp_path, b"{}", recorded=False)
    manifest = folder / "manifest.json"
    original_bytes = manifest.read_bytes()
    monkeypatch.setattr(package_files, "MAX_PACKAGE_MANIFEST_BYTES", 10)
    original = Path.open

    def no_manifest_read(path, *args, **kwargs):
        if path == manifest:
            pytest.fail("Recovery read oversized manifest bytes")
        return original(path, *args, **kwargs)

    with monkeypatch.context() as reads:
        reads.setattr(Path, "open", no_manifest_read)
        recover_closings(store)
    assert store.one("SELECT COUNT(*) AS total FROM case_closures")["total"] == 0
    assert manifest.read_bytes() == original_bytes


def test_recovery_accepts_bounded_valid_closure_manifest(tmp_path):
    store, folder = workspace_with_closure(tmp_path, b"{}", recorded=False)
    case = store.one("SELECT * FROM cases")
    model = {
        "case_id": case["id"],
        "created_at": "2026-11-13",
        "closed_by": "Synthetic analyst",
        "disposition": "notified",
        "conclusion": "Synthetic conclusion",
    }
    raw = json.dumps(model).encode()
    (folder / "snapshot.json").write_bytes(raw)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    manifest["files"]["snapshot.json"] = hashlib.sha256(raw).hexdigest()
    (folder / "manifest.json").write_text(json.dumps(manifest))
    recover_closings(store)
    assert store.one("SELECT COUNT(*) AS total FROM case_closures")["total"] == 1
    assert store.one("SELECT stage FROM cases WHERE id=?", (case["id"],))["stage"] == "closed"
