"""Behavioral acceptance checks for frozen report sections and audit packages."""

import hashlib
import io
import json
from modules.workspace.components import compact_json
import sqlite3

import pytest
from PIL import Image

from tests.support.workbench import (
    app,
    client,
    validate_sections,
    reopen_sections,
    resolve_observation_scope,
)
from modules.workspace.databases.migrations import SCHEMA_VERSION
from modules.workspace.components.store import Store

from modules.investigations.tests.support.section_reviews import (
    prepared,
    save,
    status,
)


def test_freeze_blocks_content_writes_preserves_unrelated_notes_and_requires_reason(client, app):
    lead = prepared(client, app)
    frozen = status(lead, "introduction")
    assert frozen["validated_by"] == "Test Analyst" and frozen["validated_at"].endswith("Z")
    assert frozen["snapshot"]["nodes"] and frozen["frozen_fields"]["sender_name"] == "Test Analyst"
    denied = save(client, lead, report_date="2026-01-01")
    assert denied.status_code == 422 and "Introduction" in denied.text
    saved = save(client, lead, notes="Administrative research only")
    assert saved.status_code == 200, saved.text
    lead = saved.json()
    assert status(lead, "introduction")["validation_id"] == frozen["validation_id"]
    bad = client.post(
        f"/api/cases/{lead['case_id']}/sections/introduction/reopen",
        json={"expected_revision": lead["draft_revision"], "reason": "  "},
    )
    assert bad.status_code == 422
    lead = reopen_sections(client, lead, "Correct the notification date", ["introduction"])
    reviewed_findings = status(lead, "vulnerabilities")
    assert reviewed_findings["status"] == "validated"
    # The document date is not an observation/receipt date. Its correction only
    # requires Introduction review; the date-free finding narrative stays frozen.
    changed = save(client, lead, report_date="2026-01-01")
    assert changed.status_code == 200, changed.text
    lead = changed.json()
    current_findings = status(lead, "vulnerabilities")
    assert current_findings["status"] == "validated"
    assert current_findings["validation_id"] == reviewed_findings["validation_id"]
    assert current_findings["frozen_fields"] == reviewed_findings["frozen_fields"]
    assert lead["draft"]["narrative"] == reviewed_findings["frozen_fields"]["narrative"]
    # A real finding-text change is still blocked until Vulnerabilities is
    # explicitly reopened, even though the Introduction is already editable.
    key = lead["narrative_groups"][0]["key"]
    values = {key: {"software": "Reviewed PHP product"}}
    denied = save(client, lead, narrative_values=values)
    assert denied.status_code == 422 and "Vulnerabilities" in denied.text
    lead = reopen_sections(
        client, lead, "Review the product named in the finding", ["vulnerabilities"]
    )
    changed = save(client, lead, narrative_values=values)
    assert changed.status_code == 200, changed.text
    lead = validate_sections(client, changed.json())
    assert status(lead, "introduction")["revision"] == 2
    assert status(lead, "vulnerabilities")["revision"] == 2
    old = app.state.store.one(
        "SELECT * FROM section_validations WHERE id=?", (frozen["validation_id"],)
    )
    assert old["validated_at"] == frozen["validated_at"]
    assert compact_json.loads(old["snapshot_json"])["frozen_fields"]["report_date"] != "2026-01-01"
    assert any(
        e["reason"] == "Correct the notification date" and e["actor"] == "Test Analyst"
        for e in lead["section_history"]
    )


def test_validation_actor_is_server_settings_and_audit_rows_are_append_only(client, app):
    lead = prepared(client, app, validate=False)
    lead = resolve_observation_scope(client, lead)
    url = f"/api/cases/{lead['case_id']}/sections/introduction/validate"
    assert (
        client.post(
            url, json={"expected_revision": lead["draft_revision"], "actor": "Someone else"}
        ).status_code
        == 422
    )
    response = client.post(url, json={"expected_revision": lead["draft_revision"]})
    assert response.status_code == 200, response.text
    reviewed = status(response.json(), "introduction")
    assert reviewed["validated_by"] == "Test Analyst"
    assert client.post(url, json={"expected_revision": lead["draft_revision"]}).status_code == 422
    for statement in (
        "UPDATE section_validations SET validated_by=? WHERE id=?",
        "DELETE FROM section_validations WHERE validated_by=? AND id=?",
    ):
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            with app.state.store.transaction() as db:
                db.execute(statement, ("Test Analyst", reviewed["validation_id"]))
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        with app.state.store.transaction() as db:
            db.execute("DELETE FROM section_events WHERE case_id=?", (lead["case_id"],))


def test_settings_dependency_becomes_stale_with_old_content_and_system_chronology(client, app):
    lead = prepared(client, app, validate=False)
    # Saved drafts predating pinned sender profiles retain their original
    # dependency behavior until explicit presentation adoption.
    with app.state.store.transaction() as db:
        legacy = json.loads(
            db.execute("SELECT draft FROM cases WHERE id=?", (lead["case_id"],)).fetchone()[0]
        )
        legacy.pop("sender_profile", None)
        db.execute("UPDATE cases SET draft=? WHERE id=?", (json.dumps(legacy), lead["case_id"]))
    lead = validate_sections(client, lead)
    original = {r["key"]: r for r in lead["section_reviews"]}
    settings = client.get("/api/bootstrap").json()["settings"]
    settings["analyst_name"] = "Second Analyst"
    assert client.put("/api/settings", json=settings).status_code == 200
    lead = client.get("/api/cases/" + lead["case_id"]).json()
    assert {r["key"] for r in lead["section_reviews"] if r["status"] == "stale"} == {
        "introduction",
        "closing",
    }
    assert status(lead, "introduction")["frozen_fields"]["sender_name"] == "Test Analyst"
    assert status(lead, "introduction")["validated_at"] == original["introduction"]["validated_at"]
    events = [e for e in lead["section_history"] if e["action"] == "stale"]
    assert len(events) == 2 and all(e["actor"] == "System" for e in events)
    again = client.get("/api/cases/" + lead["case_id"]).json()
    assert len(again["section_history"]) == len(lead["section_history"])
    assert client.get("/api/leads/" + lead["id"] + "/preview.pdf").status_code == 422
    assert client.post("/api/leads/" + lead["id"] + "/finalize").status_code == 422
    # Restoring the previous setting cannot silently discard an observed stale review.
    settings["analyst_name"] = "Test Analyst"
    client.put("/api/settings", json=settings)
    lead = client.get("/api/cases/" + lead["case_id"]).json()
    assert status(lead, "introduction")["status"] == "stale"
    lead = reopen_sections(
        client, lead, "Review the configured sender", ["introduction", "closing"]
    )
    lead = validate_sections(client, lead)
    assert all(r["status"] == "validated" for r in lead["section_reviews"])
    assert status(lead, "information")["validation_id"] == original["information"]["validation_id"]


def test_screenshot_api_and_disk_changes_cannot_modify_frozen_output(client, app):
    lead = prepared(client, app)
    evidence = lead["evidence"][0]
    denied = client.put(
        "/api/evidence/" + evidence["id"],
        json={
            "included": True,
            "caption": "Different caption",
            "source_url": evidence["source_url"],
            "captured_at": evidence["captured_at"],
        },
    )
    assert denied.status_code == 422 and "Attribution" in denied.text
    stream = io.BytesIO()
    Image.new("RGB", (20, 20), "red").save(stream, "PNG")
    denied = client.post(
        "/api/leads/" + lead["id"] + "/evidence",
        files={"file": ("new.png", stream.getvalue(), "image/png")},
    )
    assert denied.status_code == 422
    assert len(app.state.store.all("SELECT * FROM evidence")) == 1
    # Directly replaced preview pixels are a stale dependency, even when original
    # file metadata and the original screenshot hash are unchanged.
    app.state.store.path(evidence["preview_path"]).write_bytes(stream.getvalue())
    lead = client.get("/api/cases/" + lead["case_id"]).json()
    assert status(lead, "attribution")["status"] == "stale"
    assert client.get("/api/leads/" + lead["id"] + "/preview.pdf").status_code == 422
    assert client.post("/api/leads/" + lead["id"] + "/finalize").status_code == 422


def test_certification_has_complete_offline_work_log_and_revisions_keep_prior_package(client, app):
    lead = prepared(client, app, validate=False)
    # The legacy reviewed boolean alone no longer certifies the report.
    assert lead["draft"]["reviewed"] is True
    assert client.post("/api/leads/" + lead["id"] + "/finalize").status_code == 422
    lead = validate_sections(client, lead)
    response = client.post("/api/leads/" + lead["id"] + "/finalize")
    assert response.status_code == 200, response.text
    report = response.json()
    folder = app.state.store.path(report["path"])
    before = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file()
    }
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert {"work-log.pdf", "chronology.json"} <= set(manifest["files"])
    chronology = json.loads((folder / "chronology.json").read_text(encoding="utf-8"))["events"]
    assert len([e for e in chronology if e["action"] == "validated"]) == 5
    assert any(
        e["source_kind"] == "certification" and e["actor"] == "Test Analyst" for e in chronology
    )
    assert any(e["context"].get("validation_id") for e in chronology if e["action"] == "validated")
    package = compact_json.loads((folder / "snapshot.json").read_text(encoding="utf-8"))
    assert len(package["section_validations"]) == 5
    assert client.get("/api/reports/" + report["id"] + "/work-log").content.startswith(b"%PDF")
    assert (
        client.get("/api/reports/" + report["id"] + "/chronology").json()["report_id"]
        == report["id"]
    )
    lead = client.get("/api/cases/" + lead["case_id"]).json()
    assert lead["reports"][0]["work_log_available"] is True
    assert client.post("/api/leads/" + lead["id"] + "/start").status_code == 409
    assert (
        client.post(
            "/api/cases/" + lead["case_id"] + "/revise",
            json={"expected_version": lead["case"]["version"]},
        ).status_code
        == 422
    )
    revised = client.post(
        "/api/cases/" + lead["case_id"] + "/revise",
        json={
            "expected_version": lead["case"]["version"],
            "reason": "Add an exhibit after supervisor review",
        },
    )
    assert revised.status_code == 200, revised.text
    # A new output revision alone does not change reviewed content. Existing
    # content locks and the prior package's exact bytes remain preserved.
    assert all(r["status"] == "validated" for r in revised.json()["section_reviews"])
    assert before == {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file()
    }


def test_recovery_records_package_but_does_not_activate_stale_dependencies(client, app):
    lead = prepared(client, app, validate=False)
    with app.state.store.transaction() as db:
        legacy = json.loads(
            db.execute("SELECT draft FROM cases WHERE id=?", (lead["case_id"],)).fetchone()[0]
        )
        legacy.pop("sender_profile", None)
        db.execute("UPDATE cases SET draft=? WHERE id=?", (json.dumps(legacy), lead["case_id"]))
    lead = validate_sections(client, lead)
    report = client.post("/api/leads/" + lead["id"] + "/finalize").json()
    # Model a crash after the atomic package rename but before report DB commit.
    manifest = json.loads(
        app.state.store.path(report["path"] + "/manifest.json").read_text(encoding="utf-8")
    )
    with app.state.store.transaction() as db:
        db.execute(
            "UPDATE cases SET stage='in_progress',certified_report_id=NULL,version=? WHERE id=?",
            (manifest["expected_version"], lead["case_id"]),
        )
        from tests.artifact_helpers import remove_artifact_commit

        remove_artifact_commit(db, "report", report["id"])
        profile = app.state.store.settings()
        profile["analyst_name"] = "New Sender"
        db.execute("UPDATE settings SET value=? WHERE key=?", (json.dumps(profile), "profile"))
    recovered = Store(app.state.store.root)
    assert recovered.one("SELECT id FROM reports WHERE id=?", (report["id"],))
    case = recovered.one("SELECT * FROM cases WHERE id=?", (lead["case_id"],))
    assert case["stage"] == "in_progress" and case["certified_report_id"] is None
    assert case["version"] == manifest["expected_version"]


def test_no_legacy_section_certification_is_invented_on_migration(client, app):
    from tests.schema_helpers import restore_schema

    lead = prepared(client, app, validate=False)
    assert not app.state.store.all("SELECT * FROM section_validations")
    db = app.state.store.connect()
    try:
        restore_schema(db, 5)
        db.execute("PRAGMA user_version=5")
        db.commit()
    finally:
        db.close()
    upgraded = Store(app.state.store.root)
    assert not upgraded.all("SELECT * FROM section_validations")
    assert upgraded.one("SELECT id FROM cases WHERE id=?", (lead["case_id"],))
    assert list((upgraded.root / "backups").glob(f"before-schema-{SCHEMA_VERSION}-*.sqlite3"))
