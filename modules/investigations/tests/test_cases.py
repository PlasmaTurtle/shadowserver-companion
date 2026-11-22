from tests.support.qualification import registry_factory, capture_website
import hashlib
import json
from contextlib import closing
import io
import zipfile

import pytest
from tests.support.workbench import (
    app,
    client,
    import_rows,
    observations,
    ready,
    reopen_sections,
    validate_sections,
)
from tests.schema_helpers import legacy_database
from modules.workspace.databases.migrations import SCHEMA_VERSION
from modules.workspace.components.store import Store

from modules.investigations.tests.support.cases import (
    attempt,
    certified,
    closing_values,
    opened,
)


def test_closing_recovery_backup_and_unchanged_case_guard(client, app):
    lead = opened(client, app)
    before = lead["case"]
    closure = client.post(
        "/api/cases/" + lead["case_id"] + "/close", json=closing_values(lead, "unable_to_contact")
    ).json()
    store = app.state.store
    backup = client.post("/api/backup")
    names = zipfile.ZipFile(io.BytesIO(backup.content)).namelist()
    assert "data/" + closure["path"] + "/closing-report.pdf" in names
    with store.transaction() as db:
        from tests.artifact_helpers import remove_artifact_commit

        remove_artifact_commit(db, "closure", closure["id"])
        db.execute(
            "UPDATE cases SET stage='in_progress',closed_at=NULL,disposition=NULL,version=? WHERE id=?",
            (before["version"] + 2, lead["case_id"]),
        )
    reopened = Store(store.root)
    assert reopened.one("SELECT * FROM case_closures") is None  # Later case activity wins.
    with store.transaction() as db:
        db.execute("UPDATE cases SET version=? WHERE id=?", (before["version"], lead["case_id"]))
    recovered = Store(store.root)
    assert recovered.one("SELECT id FROM case_closures")["id"] == closure["id"]
    assert (
        recovered.one("SELECT stage FROM cases WHERE id=?", (lead["case_id"],))["stage"] == "closed"
    )
    Store(store.root)
    assert recovered.one("SELECT count(*) n FROM case_closures")["n"] == 1


def test_certified_package_integrity_and_evidence_edit_guard(client, app):
    lead, report = certified(client, app)
    from tests.support.workbench import attach

    result = client.put(
        "/api/evidence/" + lead["evidence"][0]["id"],
        json={
            "included": False,
            "caption": "Changed",
            "source_url": "https://example.com",
            "captured_at": "2026-11-06T10:00:00Z",
        },
    )
    assert result.status_code == 409
    (app.state.store.path(report["path"]) / "notification.pdf").write_bytes(b"%PDF changed")
    assert client.get("/api/reports/" + report["id"] + "/pdf").status_code == 409
    assert (
        client.post(
            "/api/cases/" + lead["case_id"] + "/attempts", json=attempt(lead, report)
        ).status_code
        == 422
    )
    assert client.get("/api/dashboard").json()["missing_packages"] == 1


def test_contact_dates_and_stale_activity(client, app):
    lead = opened(client, app)
    payload = attempt(lead, outcome="voicemail")
    payload["occurred_at"] = "2026-11-06T14:30:00"
    assert (
        client.post("/api/cases/" + lead["case_id"] + "/attempts", json=payload).status_code == 422
    )
    payload["occurred_at"] = "2026-11-06T14:30:00-05:00"
    assert (
        client.post("/api/cases/" + lead["case_id"] + "/attempts", json=payload).status_code == 200
    )
    assert (
        client.post("/api/cases/" + lead["case_id"] + "/attempts", json=payload).status_code == 422
    )
    lead = client.get("/api/cases/" + lead["case_id"]).json()
    result = client.put(
        "/api/cases/" + lead["case_id"] + "/plan",
        json={
            "expected_version": lead["case"]["version"],
            "next_action": "Call back",
            "follow_up_date": "2026-11-09",
        },
    )
    assert result.status_code == 200
    assert not client.get("/api/cases?due_before=2026-11-08").json()
    assert len(client.get("/api/cases?due_before=2026-11-09").json()) == 1


def test_legacy_reopened_draft_does_not_replace_report_history(client, app):
    lead, report = certified(client, app)
    original = lead["draft"].copy()
    revised = client.post(
        "/api/cases/" + lead["case_id"] + "/revise",
        json={
            "expected_version": lead["case"]["version"],
            "reason": "Update the notification after analyst review.",
        },
    )
    assert revised.status_code == 200, revised.text
    reopen_sections(
        client, lead, "Revise the working draft while preserving its certified history."
    )
    rows = observations()
    rows[0]["timestamp"] = "2026-12-01 02:00:00"
    for row in rows:
        if row.get("version"):
            row["version"] = "7.3.26"
    import_rows(client, app, rows, "new.csv")
    working = client.get("/api/cases/" + lead["case_id"]).json()
    working["draft"]["narrative"] = "A later working draft."
    assert (
        client.put(
            "/api/leads/" + lead["id"] + "/draft",
            json={"expected_revision": working["draft_revision"], "fields": working["draft"]},
        ).status_code
        == 200
    )
    retained = {
        row["id"]: json.loads(row["payload"])["source"]
        for row in app.state.store.all(
            "SELECT id,payload FROM entries WHERE lead_id=?", (lead["id"],)
        )
    }
    legacy_database(app.state.store, 3)
    upgraded = Store(app.state.store.root)
    from modules.investigations.components.cases import Cases

    cases = upgraded.all("SELECT * FROM cases")
    assert len(cases) == 2
    history = Cases(upgraded).view(
        next(c["id"] for c in cases if c["stage"] == "pending_notification")
    )
    new = Cases(upgraded).view(next(c["id"] for c in cases if c["stage"] == "in_progress"))
    assert history["draft"] == original and len(history["entries"]) == 3
    assert len(history["scope_source_entries"]) == 4
    assert "began reviewing Shadowserver observations" in new["draft"]["narrative"]
    # Repeated findings no longer create another copy of every source row.
    # The legacy migration must still preserve every entry that it received.
    assert {entry["id"]: entry["source"] for entry in new["scope_source_entries"]} == retained
    assert history["reports"][0]["id"] == report["id"]


@pytest.mark.parametrize("stage", ["pristine", "certified", "delivered"])
def test_business_merge_preserves_independent_notification_scopes(client, app, stage):
    from tests.support.workbench import FakeRegistry

    if stage == "pristine":
        first = opened(client, app)
        report = None
    else:
        first, report = certified(client, app)
        if stage == "delivered":
            first = client.post(
                "/api/cases/" + first["case_id"] + "/attempts", json=attempt(first, report)
            ).json()
    original = first["entries"]

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
    second = next(x for x in client.get("/api/leads").json() if x["id"] != first["id"])
    source = client.get("/api/leads/" + first["id"]).json()
    response = client.post(
        "/api/entities/" + first["id"] + "/merge",
        json={
            "target_id": second["id"],
            "source_revision": source["entity_revision"],
            "target_revision": second["draft_revision"],
        },
    )
    assert response.status_code == 200, response.text
    rows = client.get("/api/cases").json()
    assert len(rows) == 2
    prior = client.get("/api/cases/" + first["case_id"]).json()
    assert prior["entries"] == original
    assert (
        prior["case"]["stage"]
        == {
            "pristine": "in_progress",
            "certified": "pending_notification",
            "delivered": "notification_completed",
        }[stage]
    )
    assert prior["company"] == first["company"]
    assert prior["domain_groups"] == first["domain_groups"]
    assert prior["evidence"] == first["evidence"]
    assert [
        (r["key"], r["status"], r["content_hash"], r.get("validation_id"))
        for r in prior["section_reviews"]
    ] == [
        (r["key"], r["status"], r["content_hash"], r.get("validation_id"))
        for r in first["section_reviews"]
    ]
    assert prior["id"] == second["id"]  # Current ownership still follows the merge.
    if report:
        assert client.get("/api/reports/" + report["id"] + "/pdf").status_code == 200
    assert app.state.store.all("PRAGMA foreign_key_check") == []


def test_certify_without_recipient_and_contact_plan_preserves_certification(client, app):
    lead = opened(client, app)
    lead = ready(client, lead["id"], validate=False)
    draft = {**lead["draft"], "contact_name": "", "contact_email": ""}
    saved = client.put(
        "/api/leads/" + lead["id"] + "/draft",
        json={"expected_revision": lead["draft_revision"], "fields": draft},
    )
    assert saved.status_code == 200
    validate_sections(client, saved.json())
    response = client.post("/api/leads/" + lead["id"] + "/finalize")
    assert response.status_code == 200, response.text
    report = response.json()
    lead = client.get("/api/cases/" + lead["case_id"]).json()
    assert (
        lead["case"]["stage"] == "pending_notification" and report["certified_by"] == "Test Analyst"
    )
    plan = dict(
        expected_version=lead["case"]["version"],
        next_action="Awaiting callback",
        follow_up_date="2026-11-09",
        contact_name="IT team",
    )
    changed = client.put("/api/cases/" + lead["case_id"] + "/plan", json=plan)
    assert changed.status_code == 200, changed.text
    assert changed.json()["case"]["certified_report_id"] == report["id"]
    assert client.put("/api/cases/" + lead["case_id"] + "/plan", json=plan).status_code == 422


def test_email_sent_is_pending_and_delivery_names_exact_revision(client, app):
    lead, report = certified(client, app)

    def history():
        return client.get("/api/entities/" + lead["id"]).json()["notification_history"]

    response = client.post(
        "/api/cases/" + lead["case_id"] + "/attempts", json=attempt(lead, report, "email_sent")
    )
    assert response.status_code == 200, response.text
    lead = response.json()
    assert lead["case"]["stage"] == "pending_notification" and lead["case"]["delivered_at"] is None
    assert history()["count"] == 0
    payload = attempt(lead, report)
    payload["recipient"] = ""
    assert (
        client.post("/api/cases/" + lead["case_id"] + "/attempts", json=payload).status_code == 422
    )
    response = client.post(
        "/api/cases/" + lead["case_id"] + "/attempts", json=attempt(lead, report)
    )
    assert response.status_code == 200, response.text
    lead = response.json()
    assert lead["case"]["stage"] == "notification_completed"
    assert lead["attempts"][-1]["report_id"] == report["id"]
    assert lead["case"]["delivered_at"] == "2026-11-06T19:30:00Z"
    original_history = history()
    assert original_history["count"] == 1
    assert original_history["last_notified_at"] == lead["case"]["delivered_at"]
    assert original_history["last_case_id"] == lead["case_id"]
    assert client.get("/api/reports/" + report["id"] + "/pdf").status_code == 200
    followup = client.post(
        "/api/cases/" + lead["case_id"] + "/attempts", json=attempt(lead, report, "acknowledged")
    )
    assert followup.status_code == 200
    assert history() == original_history
    assert client.get("/api/dashboard").json()["workflow"]["delivered_total"] == 1


def test_substantive_revision_requires_certification_and_keeps_old_package(client, app):
    lead, report = certified(client, app)
    path = app.state.store.path(report["path"]) / "snapshot.json"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    response = client.post(
        "/api/cases/" + lead["case_id"] + "/revise",
        json={
            "expected_version": lead["case"]["version"],
            "reason": "Update the notification after analyst review.",
        },
    )
    assert response.status_code == 200, response.text
    lead = response.json()
    assert lead["case"]["stage"] == "in_progress" and lead["case"]["certified_report_id"] is None
    # Opening an output revision keeps unchanged content locked. The analyst's
    # following substantive edit still uses the explicit reasoned reopen.
    assert all(section["status"] == "validated" for section in lead["section_reviews"])
    reopen_sections(client, lead, "Review the substantive notification revision.")
    assert (
        client.post(
            "/api/cases/" + lead["case_id"] + "/attempts", json=attempt(lead, report)
        ).status_code
        == 422
    )
    ready(client, lead["id"])
    second = client.post("/api/leads/" + lead["id"] + "/finalize").json()
    assert second["revision"] == report["revision"] + 1 and second["case_id"] == lead["case_id"]
    lead = client.get("/api/cases/" + lead["case_id"]).json()
    assert (
        client.post(
            "/api/cases/" + lead["case_id"] + "/attempts", json=attempt(lead, report)
        ).status_code
        == 422
    )
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest


def test_canonical_history_keeps_legacy_delivery_across_revisions_and_merge(client, app):
    """An older sent revision, another closed delivery and a pending report count as two."""
    from modules.investigations.components.services.case_queries import completed_notifications
    from modules.leads.tests.support.lead_queue import queue_import
    from modules.leads.components.lead_queue import LeadQueue
    from modules.entities.components.repositories.entities import EntityRepository
    from modules.entities.tests.support.contacts import entity_only
    from modules.workspace.components.primitives import now

    queue_import(client, app)
    store = app.state.store
    pending = LeadQueue(store).list()[0]
    owner = pending["entity_id"]
    entity_only(store, "older-owner", "older.example")
    entity_only(store, "intermediate-owner", "intermediate.example")
    with store.transaction() as db:
        stamp = now()
        # Older workspaces can retain a sent revision even when the latest one is unsent.
        for case_id, entity, stage, delivered in (
            ("historical", "older-owner", "pending_notification", None),
            ("closed", owner, "closed", "2026-11-10T09:00:00Z"),
            ("waiting", owner, "pending_notification", None),
        ):
            db.execute(
                "INSERT INTO cases(id,entity_id,title,stage,created_at,updated_at,delivered_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (case_id, entity, case_id, stage, stamp, stamp, delivered),
            )
        for identity, case_id, revision, sent in (
            ("r1", "historical", 1, "2026-11-09T10:00:00Z"),
            ("r2", "historical", 2, None),
            ("r3", "waiting", 3, None),
        ):
            db.execute(
                "INSERT INTO reports(id,lead_id,entity_id,case_id,revision,created_at,path,sent_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (identity, owner, owner, case_id, revision, stamp, identity, sent),
            )
        EntityRepository.transfer_records(db, "older-owner", "intermediate-owner")
        EntityRepository.transfer_records(db, "intermediate-owner", owner)
        for alias in (owner, "older-owner", "intermediate-owner"):
            assert completed_notifications(db, alias) == {
                "count": 2,
                "last_case_id": "closed",
                "last_notified_at": "2026-11-10T09:00:00Z",
            }
    summary = client.get("/api/pending-leads/" + pending["id"]).json()["notification_history"]
    assert summary["count"] == 2
    assert client.get("/api/pending-leads").json()[0]["notification_history"] == summary
    assert client.get("/api/entities").json()[0]["notification_history"] == summary
    for alias in (owner, "older-owner", "intermediate-owner"):
        history = client.get("/api/entities/" + alias).json()["notification_history"]
        assert {k: history[k] for k in summary} == summary
        assert [c["id"] for c in history["cases"]] == ["closed", "historical"]


def test_closing_report_records_delivery_and_recipient_reported_action(client, app):
    lead, report = certified(client, app)
    lead = client.post(
        "/api/cases/" + lead["case_id"] + "/attempts", json=attempt(lead, report)
    ).json()
    update = attempt(lead, report, "recipient_update")
    update.update(notes="Recipient reported updating PHP.", information_source="recipient_reported")
    lead = client.post("/api/cases/" + lead["case_id"] + "/attempts", json=update).json()
    values = closing_values(lead)
    preview = client.post("/api/cases/" + lead["case_id"] + "/closing-preview", json=values)
    assert preview.status_code == 200 and preview.content.startswith(b"%PDF")
    result = client.post("/api/cases/" + lead["case_id"] + "/close", json=values)
    assert result.status_code == 200, result.text
    data = client.get("/api/cases/" + lead["case_id"] + "/closing/json").json()
    assert data["attempts"][-1]["information_source"] == "recipient_reported"
    assert data["reports"][0]["id"] == report["id"] and data["delivered_at"]
    for fmt, prefix in [("pdf", b"%PDF"), ("docx", b"PK")]:
        response = client.get("/api/cases/" + lead["case_id"] + "/closing/" + fmt)
        assert response.status_code == 200 and response.content.startswith(prefix)
    assert client.post("/api/cases/" + lead["case_id"] + "/close", json=values).status_code == 422
    lead = client.get("/api/cases/" + lead["case_id"]).json()
    assert lead["case"]["stage"] == "closed"
    assert (
        client.post(
            "/api/cases/" + lead["case_id"] + "/attempts", json=attempt(lead, report)
        ).status_code
        == 422
    )
    assert client.get("/api/dashboard").json()["workflow"]["closed"] == 1


def test_closure_without_delivery_is_not_a_successful_notification(client, app):
    lead = opened(client, app)
    assert (
        client.post(
            "/api/cases/" + lead["case_id"] + "/close", json=closing_values(lead)
        ).status_code
        == 422
    )
    response = client.post(
        "/api/cases/" + lead["case_id"] + "/close", json=closing_values(lead, "unable_to_contact")
    )
    assert response.status_code == 200, response.text
    workflow = client.get("/api/dashboard").json()["workflow"]
    assert (
        workflow["closed"] == workflow["closed_without_delivery"] == 1
        and workflow["delivered_total"] == 0
    )
    record = response.json()
    (app.state.store.path(record["path"]) / "closing-report.pdf").unlink()
    data = client.get("/api/dashboard").json()
    assert data["workflow"]["closed"] == 0 and data["missing_closings"] == 1
    assert client.get("/api/cases/" + lead["case_id"] + "/closing/pdf").status_code == 409


def test_new_scan_does_not_reopen_delivered_case_and_new_case_is_separate(client, app):
    lead, report = certified(client, app)
    lead = client.post(
        "/api/cases/" + lead["case_id"] + "/attempts", json=attempt(lead, report)
    ).json()
    client.post("/api/cases/" + lead["case_id"] + "/close", json=closing_values(lead))
    original = client.get("/api/cases/" + lead["case_id"]).json()
    rows = observations()
    for row in rows:
        row["timestamp"] = "2026-12-01 02:00:00"
        if row.get("version"):
            # A different EOL release is fresh work; another sighting of the
            # already-notified release intentionally would not create a lead.
            row["version"] = "7.4.33"
    import_rows(client, app, rows, "december.csv")
    old = client.get("/api/cases/" + lead["case_id"]).json()
    assert (
        old["case"]["stage"] == "closed"
        and old["entries"] == original["entries"]
        and old["domain_groups"] == original["domain_groups"]
    )
    assert len(client.get("/api/cases").json()) == 1
    result = client.post(
        "/api/cases", json={"entity_id": lead["id"], "title": "December notification"}
    )
    assert result.status_code == 200, result.text
    new = result.json()
    assert new["case_id"] != lead["case_id"] and new["case"]["stage"] == "in_progress"
    assert len(new["entries"]) == 4 and not new["reports"] and not new["attempts"]
    assert client.get("/api/dashboard").json()["workflow"]["delivered_total"] == 1
    assert (
        client.post(
            "/api/cases/" + new["case_id"] + "/attempts", json=attempt(new, report)
        ).status_code
        == 422
    )


def test_pending_case_new_observations_preserve_certified_scope(client, app):
    lead, report = certified(client, app)
    rows = observations()
    rows[0]["timestamp"] = "2026-11-07 02:00:00"
    for row in rows:
        if row.get("version"):
            row["version"] = "7.3.26"
    import_rows(client, app, rows, "next.csv")
    updated = client.get("/api/cases/" + lead["case_id"]).json()
    assert (
        updated["case"]["stage"] == "pending_notification"
        and updated["case"]["certified_report_id"] == report["id"]
    )
    assert len(updated["entries"]) == 3 and len(updated["reports"]) == 1
    assert len(updated["scope_source_entries"]) == 4
    assert client.get("/api/leads").json()[0]["unassigned_observations"] == 0
    assert client.get("/api/pending-leads").json() == []
    assert (
        next(
            section for section in updated["section_reviews"] if section["key"] == "vulnerabilities"
        )["status"]
        == "validated"
    )
    assert all(section["validated_at"] for section in updated["section_reviews"])


def test_schema_three_upgrade_keeps_reports_and_creates_cases(client, app):
    lead, report = certified(client, app)
    store = app.state.store
    path = store.path(report["path"]) / "notification.pdf"
    before = path.read_bytes()
    legacy_database(store, version=3)
    migrated = Store(store.root)
    assert migrated.one("PRAGMA user_version")["user_version"] == SCHEMA_VERSION
    report = migrated.one("SELECT * FROM reports WHERE id=?", (report["id"],))
    assert report["case_id"] and report["certification_source"] == "legacy_finalized"
    assert (
        migrated.one("SELECT stage FROM cases WHERE id=?", (report["case_id"],))["stage"]
        == "pending_notification"
    )
    assert path.read_bytes() == before and not migrated.all("PRAGMA foreign_key_check")
    backups = list((store.root / "backups").glob(f"before-schema-{SCHEMA_VERSION}-*"))
    assert len(backups) == 1
    Store(store.root)
    assert list((store.root / "backups").glob(f"before-schema-{SCHEMA_VERSION}-*")) == backups


def test_failed_closing_generation_does_not_close_case(client, app, monkeypatch):
    import modules.investigations.components.closing as closing

    lead = opened(client, app)

    def failure(*args):
        raise ValueError("render failed")

    monkeypatch.setattr(closing, "render_closing", failure)
    assert (
        client.post(
            "/api/cases/" + lead["case_id"] + "/close",
            json=closing_values(lead, "unable_to_contact"),
        ).status_code
        == 422
    )
    assert client.get("/api/cases/" + lead["case_id"]).json()["case"]["stage"] == "in_progress"
    assert not app.state.store.all("SELECT * FROM case_closures")
