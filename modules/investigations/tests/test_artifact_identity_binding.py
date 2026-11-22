"""Intact package hashes cannot authorize a different database report or case."""

from copy import deepcopy
import hashlib
import json
import sqlite3

import pytest

from tests.session_helpers import TestClient
from modules.workspace.tests.support.workspace_data import workspace_with_report
from modules.workspace.components.api import create_app
from modules.workspace.components.workspace_data import export_workspace


@pytest.fixture
def saved(tmp_path, request):
    store, folder = workspace_with_report(
        tmp_path, b'{"draft": {}, "evidence": []}', register=False
    )
    report = store.one("SELECT * FROM reports")
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    manifest.update(
        schema_version=4,
        report_id=report["id"],
        case_id=report["case_id"],
        notification_id=report["case_id"],
        entity_id=report["lead_id"],
        revision=report["revision"],
        created_at=report["created_at"],
    )
    options = getattr(request, "param", {})
    if options.get("legacy_manifest"):
        manifest = {"files": manifest["files"]}
    elif "schema_version" in options:
        manifest["schema_version"] = options["schema_version"]
    if options.get("analyst"):
        with store.transaction() as db:
            db.execute("UPDATE reports SET certification_source='analyst'")
        report = store.one("SELECT * FROM reports")
    (folder / "manifest.json").write_text(json.dumps(manifest))
    from modules.investigations.components.artifact_registry import register_artifact

    with store.transaction() as db:
        register_artifact(db, store.root, "report", report["id"], legacy=True)
    app = create_app(store.root, worker=False, report_processes=False)
    with TestClient(app) as client:
        yield app.state.store, client, report, folder, manifest


@pytest.mark.parametrize("field", ["id", "case_id", "lead_id", "entity_id", "revision"])
def test_report_inventory_rejects_cross_bound_identity(saved, field):
    store, _, report, _, _ = saved
    assert store.package_available(report)
    changed = {**report, field: 2 if field == "revision" else "another-identity"}
    assert not store.package_available(changed)
    with pytest.raises(ValueError, match="identity|business"):
        store.package_inventory(changed)


def test_transplanted_intact_package_is_not_served_or_accepted_for_transfer(saved):
    store, client, report, folder, manifest = saved
    foreign = folder.parent / "v999"
    foreign.mkdir()
    for name in manifest["files"]:
        (foreign / name).write_bytes((folder / name).read_bytes())
    replacement = {
        **deepcopy(manifest),
        "report_id": "another-report",
        "case_id": "another-case",
        "notification_id": "another-case",
        "revision": 999,
    }
    (foreign / "manifest.json").write_text(json.dumps(replacement))
    before_bytes = (folder / "notification.pdf").read_bytes()
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        with store.transaction() as db:
            db.execute(
                "UPDATE reports SET path=? WHERE id=?",
                (foreign.relative_to(store.root).as_posix(), report["id"]),
            )
    # Simulate external database corruption to test the independent read guard.
    with store.transaction() as db:
        db.execute("DROP TRIGGER immutable_reports_identity")
        db.execute(
            "UPDATE reports SET path=? WHERE id=?",
            (foreign.relative_to(store.root).as_posix(), report["id"]),
        )
    before_rows = store.all("SELECT * FROM reports")
    assert client.get(f"/api/reports/{report['id']}/pdf").status_code == 409
    assert not client.get("/api/reports").json()[0]["files_available"]
    # Export exercises real unpack/restore validation on an isolated copy.
    with pytest.raises(ValueError, match="package identity|registry"):
        export_workspace(store)
    assert store.all("SELECT * FROM reports") == before_rows
    assert (folder / "notification.pdf").read_bytes() == before_bytes


@pytest.mark.parametrize("damage", ["digest", "closure_id", "case_id"])
def test_closing_binding_blocks_serving_and_transfer_without_rewriting_files(saved, damage):
    store, client, report, _, _ = saved
    case_id, closure_id = report["case_id"], "synthetic-closure"
    relative = f"closures/{case_id}/{closure_id}"
    folder = store.path(relative)
    folder.mkdir(parents=True)
    snapshot = json.dumps(
        {
            "case_id": case_id,
            "created_at": "2026-11-13T00:00:00Z",
            "closed_by": "Test Analyst",
            "disposition": "out_of_scope",
            "conclusion": "Synthetic closure",
        }
    ).encode()
    content = {
        "snapshot.json": snapshot,
        "closing-report.pdf": b"SYNTHETIC PDF",
        "closing-report.docx": b"SYNTHETIC DOCX",
    }
    for name, body in content.items():
        (folder / name).write_bytes(body)
    digest = hashlib.sha256(snapshot).hexdigest()
    manifest = {
        "closure_id": closure_id,
        "case_id": case_id,
        "expected_version": 0,
        "files": {name: hashlib.sha256(body).hexdigest() for name, body in content.items()},
    }
    if damage != "digest":
        manifest[damage] = "different-identity"
    (folder / "manifest.json").write_text(json.dumps(manifest))
    with store.transaction() as db:
        db.execute(
            "INSERT INTO case_closures VALUES(?,?,?,?,?,?,?,?)",
            (
                closure_id,
                case_id,
                "2026-11-13T00:00:00Z",
                "Test Analyst",
                "out_of_scope",
                "Synthetic closure",
                relative,
                "0" * 64 if damage == "digest" else digest,
            ),
        )
    # Model an old package whose declared identity cannot be retroactively repaired.
    from modules.investigations.components.artifact_registry import register_artifact

    with store.transaction() as db:
        register_artifact(db, store.root, "closure", closure_id, legacy=True)
    before_rows = store.all("SELECT * FROM case_closures")
    assert client.get(f"/api/cases/{case_id}/closing/pdf").status_code == 409
    with pytest.raises(ValueError, match="Closing package"):
        export_workspace(store)
    assert store.all("SELECT * FROM case_closures") == before_rows
    assert (folder / "snapshot.json").read_bytes() == snapshot


@pytest.mark.parametrize("saved", [{"legacy_manifest": True}], indirect=True)
def test_manifest_without_modern_identifiers_preserves_legacy_contract(saved):
    store, _, report, folder, manifest = saved
    assert store.package_available(report)
    archive = export_workspace(store)
    archive.unlink()


@pytest.mark.parametrize("saved", [{"analyst": True}], indirect=True)
def test_analyst_report_cannot_downgrade_to_identifier_free_legacy_package(saved):
    store, client, report, folder, manifest = saved
    assert store.package_available(report)
    # A hash-consistent old package cannot satisfy a newer row's identity
    # contract merely by lacking schema and identity declarations.
    (folder / "manifest.json").write_text(json.dumps({"files": manifest["files"]}))
    assert not store.package_available(report)
    assert client.get(f"/api/reports/{report['id']}/pdf").status_code == 409
    with pytest.raises(ValueError, match="required identity|manifest differs"):
        export_workspace(store)


@pytest.mark.parametrize("saved", [{"analyst": True, "schema_version": 2}], indirect=True)
def test_older_case_based_analyst_manifest_keeps_its_identity_contract(saved):
    store, _, report, folder, manifest = saved
    assert store.package_available(report)
    archive = export_workspace(store)
    archive.unlink()
