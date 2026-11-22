"""An intact orphan is retained; activation uses the same gates as publication."""

import hashlib
import json

import pytest

from tests.support.workbench import app, client, import_rows, observations
from modules.investigations.tests.support.section_reviews import prepared
from tests.artifact_helpers import remove_artifact_commit
from modules.investigations.components.services.recovery import recover_reports
from modules.investigations.components.services import certification, recovery
from modules.workspace.components.store import Store


@pytest.mark.parametrize("change", ["unchanged", "operator", "source", "case"])
def test_schema5_recovery_preserves_package_and_rechecks_readiness(client, app, change):
    lead = prepared(client, app)
    store = app.state.store
    original_lead = store.one("SELECT * FROM leads WHERE id=?", (lead["id"],))
    result = client.post("/api/leads/" + lead["id"] + "/finalize")
    assert result.status_code == 200, result.text
    report = result.json()
    folder = store.path(report["path"])
    manifest_bytes = (folder / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    assert manifest["schema_version"] == 5
    with store.transaction() as db:
        db.execute(
            "UPDATE cases SET stage='in_progress',certified_report_id=NULL,version=? WHERE id=?",
            (manifest["expected_version"], report["case_id"]),
        )
        remove_artifact_commit(db, "report", report["id"])
        # A lost publication commit also leaves the entity in its original state.
        db.execute(
            "UPDATE leads SET status=?,new_observations=?,updated_at=? WHERE id=?",
            (
                original_lead["status"],
                original_lead["new_observations"],
                original_lead["updated_at"],
                lead["id"],
            ),
        )
        if change == "operator":
            # The sender profile is pinned; this does not alter section content
            # or case version. Publication still requires the current certifier.
            profile = store.settings(db)
            profile["analyst_name"] = "Different operator after render"
            db.execute("UPDATE settings SET value=? WHERE key='profile'", (json.dumps(profile),))
        if change == "case":
            db.execute("UPDATE cases SET version=version+1 WHERE id=?", (report["case_id"],))
    if change == "source":
        evidence = store.one("SELECT * FROM evidence WHERE case_id=?", (report["case_id"],))
        store.path(evidence["path"]).write_bytes(b"Changed original screenshot bytes")
    recover_reports(store)
    assert store.one("SELECT id FROM reports WHERE id=?", (report["id"],))
    assert store.one("SELECT artifact_id FROM artifact_records WHERE report_id=?", (report["id"],))
    assert (folder / "manifest.json").read_bytes() == manifest_bytes
    case = store.one("SELECT * FROM cases WHERE id=?", (report["case_id"],))
    entity = store.one("SELECT * FROM leads WHERE id=?", (lead["id"],))
    if change == "unchanged":
        assert case["stage"] == "pending_notification"
        assert case["certified_report_id"] == report["id"]
        assert case["version"] == manifest["expected_version"] + 1
        assert entity["status"] == "completed" and entity["new_observations"] == 0
        assert entity["updated_at"] == case["updated_at"]
    else:
        assert case["stage"] == "in_progress"
        assert case["certified_report_id"] is None
        assert case["version"] == manifest["expected_version"] + (change == "case")
        assert entity == original_lead


def test_interrupted_publication_recovers_case_and_entity_atomically(client, app, monkeypatch):
    lead = prepared(client, app)
    store = app.state.store
    lead_id, case_id = lead["id"], lead["case_id"]
    original_lead = store.one("SELECT * FROM leads WHERE id=?", (lead_id,))
    original_case = store.one("SELECT * FROM cases WHERE id=?", (case_id,))
    assert original_lead["status"] == "in_progress"
    # Refuse the final conditional transition after rename and artifact registration.
    # Certification must roll its entire transaction back, leaving a real orphan.
    with monkeypatch.context() as patch:
        patch.setattr(certification, "activate_report", lambda *args, **kwargs: False)
        result = client.post("/api/leads/" + lead_id + "/finalize")
    assert result.status_code == 422, result.text
    assert "changed during report publication" in result.text
    assert not store.all("SELECT id FROM reports")
    assert not store.all("SELECT artifact_id FROM artifact_records WHERE kind='report'")
    assert store.one("SELECT * FROM leads WHERE id=?", (lead_id,)) == original_lead
    assert store.one("SELECT * FROM cases WHERE id=?", (case_id,)) == original_case
    manifests = list((store.root / "reports").glob("*/v*/manifest.json"))
    assert len(manifests) == 1
    folder = manifests[0].parent
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in folder.iterdir()
        if path.is_file()
    }

    # New findings may arrive outside the reviewed case while publication is
    # interrupted. Recovering the old case must retain that independent work.
    rows = [
        {**row, "timestamp": "2026-11-09 12:00:00", "version": "8.0.1"} for row in observations()
    ]
    import_rows(client, app, rows, "later.csv", start_notifications=False)
    pending = client.get("/api/pending-leads").json()
    assert pending
    directory_row = next(row for row in client.get("/api/leads").json() if row["id"] == lead_id)
    pending_count = directory_row["unassigned_observations"]
    assert pending_count > 0
    case_entries = store.all("SELECT * FROM case_entries WHERE case_id=?", (case_id,))
    original_lead = store.one("SELECT * FROM leads WHERE id=?", (lead_id,))
    assert store.one("SELECT * FROM cases WHERE id=?", (case_id,)) == original_case

    # A failure on the second write must also roll back case activation and the
    # recovered report/artifact registrations. The intact files remain retryable.
    with store.transaction() as db:
        db.execute(
            """CREATE TRIGGER probe_lead_write_failure BEFORE UPDATE OF status ON leads
            WHEN NEW.status='completed' BEGIN SELECT RAISE(ABORT,'synthetic lead write failure'); END"""
        )
    Store(store.root)
    assert not store.all("SELECT id FROM reports")
    assert not store.all("SELECT artifact_id FROM artifact_records WHERE kind='report'")
    assert store.one("SELECT * FROM leads WHERE id=?", (lead_id,)) == original_lead
    assert store.one("SELECT * FROM cases WHERE id=?", (case_id,)) == original_case
    with store.transaction() as db:
        db.execute("DROP TRIGGER probe_lead_write_failure")

    recovered_at = "2100-01-01T00:00:00+00:00"
    monkeypatch.setattr(recovery, "now", lambda: recovered_at)
    Store(store.root)
    case = store.one("SELECT * FROM cases WHERE id=?", (case_id,))
    entity = store.one("SELECT * FROM leads WHERE id=?", (lead_id,))
    assert case["stage"] == "pending_notification"
    assert case["certified_report_id"] == manifest["report_id"]
    assert case["version"] == manifest["expected_version"] + 1
    assert entity["status"] == "completed" and entity["new_observations"] == 0
    assert case["updated_at"] == entity["updated_at"] == recovered_at
    assert store.one("SELECT id FROM reports WHERE id=?", (manifest["report_id"],))
    assert store.one(
        "SELECT artifact_id FROM artifact_records WHERE report_id=?", (manifest["report_id"],)
    )
    assert lead_id in {row["id"] for row in client.get("/api/leads?status=completed").json()}
    assert lead_id not in {row["id"] for row in client.get("/api/leads?status=in_progress").json()}
    counts = client.get("/api/dashboard").json()["counts"]
    assert counts["completed"] == 1 and counts["in_progress"] == 0
    assert client.get("/api/cases/" + case_id).json()["status"] == "completed"
    directory_row = next(row for row in client.get("/api/leads").json() if row["id"] == lead_id)
    assert directory_row["unassigned_observations"] == pending_count
    assert directory_row["new_observations"] == pending_count
    assert client.get("/api/pending-leads").json() == pending
    assert store.all("SELECT * FROM case_entries WHERE case_id=?", (case_id,)) == case_entries
    events = store.all("SELECT * FROM events WHERE action='recovered'")
    Store(store.root)
    assert store.one("SELECT * FROM cases WHERE id=?", (case_id,)) == case
    assert store.one("SELECT * FROM leads WHERE id=?", (lead_id,)) == entity
    assert store.all("SELECT * FROM events WHERE action='recovered'") == events

    # Once registered, recovery must not rewrite later administrative state.
    with store.transaction() as db:
        db.execute(
            "UPDATE leads SET status='in_progress',new_observations=7,updated_at='later' WHERE id=?",
            (lead_id,),
        )
    later = store.one("SELECT * FROM leads WHERE id=?", (lead_id,))
    Store(store.root)
    assert store.one("SELECT * FROM leads WHERE id=?", (lead_id,)) == later
    assert hashes == {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in folder.iterdir()
        if path.is_file()
    }
