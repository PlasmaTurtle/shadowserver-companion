"""An intact orphan is retained; activation uses the same gates as publication."""

import json

import pytest

from test_workbench import app, client
from test_section_validation_050 import prepared
from artifact_helpers import remove_artifact_commit
from workbench.services.recovery import recover_reports


@pytest.mark.parametrize("change", ["unchanged", "operator", "source"])
def test_schema5_recovery_preserves_package_and_rechecks_readiness(client, app, change):
    lead = prepared(client, app)
    result = client.post("/api/leads/" + lead["id"] + "/finalize")
    assert result.status_code == 200, result.text
    report = result.json()
    store = app.state.store
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
        if change == "operator":
            # The sender profile is pinned; this does not alter section content
            # or case version. Publication still requires the current certifier.
            profile = store.settings(db)
            profile["analyst_name"] = "Different operator after render"
            db.execute("UPDATE settings SET value=? WHERE key='profile'", (json.dumps(profile),))
    if change == "source":
        evidence = store.one("SELECT * FROM evidence WHERE case_id=?", (report["case_id"],))
        store.path(evidence["path"]).write_bytes(b"Changed original screenshot bytes")
    recover_reports(store)
    assert store.one("SELECT id FROM reports WHERE id=?", (report["id"],))
    assert store.one("SELECT artifact_id FROM artifact_records WHERE report_id=?", (report["id"],))
    assert (folder / "manifest.json").read_bytes() == manifest_bytes
    case = store.one("SELECT * FROM cases WHERE id=?", (report["case_id"],))
    if change == "unchanged":
        assert case["stage"] == "pending_notification"
        assert case["certified_report_id"] == report["id"]
        assert case["version"] == manifest["expected_version"] + 1
    else:
        assert case["stage"] == "in_progress"
        assert case["certified_report_id"] is None
        assert case["version"] == manifest["expected_version"]
