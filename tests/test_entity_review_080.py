"""Business-field reminders are persisted, value-bound and independent of reports."""

import json

from test_workbench import FakeRegistry, app, client, import_rows, observations
from workbench.migrations import SCHEMA_VERSION
from workbench.store import Store


def open_entity(client, app):
    import_rows(client, app)
    entity_id = client.get("/api/leads").json()[0]["id"]
    return client.get("/api/leads/" + entity_id).json()


def field(lead, name):
    return next(item for item in lead["entity_review"]["fields"] if item["field"] == name)


def review(client, lead, name, action="confirm", **overrides):
    return client.post(
        f"/api/entities/{lead['id']}/field-review",
        json={
            "field": name,
            "action": action,
            "expected_revision": lead["entity_revision"],
            "value_hash": field(lead, name)["value_hash"],
            **overrides,
        },
    )


def test_missing_details_and_hostname_remain_pending_until_reviewed(client, app):
    lead = open_entity(client, app)
    assert lead["entity_review"]["required"]
    assert [f["field"] for f in lead["entity_review"]["fields"]] == [
        "name",
        "address",
        "city",
        "state",
    ]
    assert all(f["status"] == "pending" for f in lead["entity_review"]["fields"])
    assert field(lead, "name")["reason"] == "Using the reported hostname"
    assert review(client, lead, "address").status_code == 422
    assert review(client, lead, "name").status_code == 200
    for name in ("address", "city", "state"):
        response = review(client, lead, name, "ignore")
        assert response.status_code == 200, response.text
    assert not response.json()["entity_review"]["required"]
    reopened = Store(app.state.store.root).lead(lead["id"])
    assert field(reopened, "name")["status"] == "confirmed"
    assert field(reopened, "address")["status"] == "ignored"
    assert review(client, lead, "name", "pending").json()["entity_review"]["required"]


def test_saved_manual_edits_confirm_only_changed_nonempty_fields(client, app):
    lead = open_entity(client, app)
    response = client.put(
        f"/api/entities/{lead['id']}/profile",
        json={
            "expected_revision": lead["entity_revision"],
            "address": "24 Main Street",
            "city": "Asheville",
        },
    )
    assert response.status_code == 200, response.text
    lead = response.json()
    assert field(lead, "address")["status"] == "confirmed"
    assert field(lead, "city")["status"] == "confirmed"
    assert field(lead, "state")["status"] == "pending"
    assert field(lead, "name")["status"] == "pending"
    lead = client.put(
        f"/api/entities/{lead['id']}/name",
        json={"expected_revision": lead["entity_revision"], "name": "Example Business"},
    ).json()
    assert field(lead, "name")["status"] == "confirmed"
    response = client.put(
        f"/api/entities/{lead['id']}/profile",
        json={"expected_revision": lead["entity_revision"], "address": "", "city": "Asheville"},
    )
    assert field(response.json(), "address")["status"] == "pending"
    assert field(response.json(), "city")["status"] == "confirmed"


def test_review_has_revision_and_value_guards_and_reflags_automated_changes(client, app):
    lead = open_entity(client, app)
    assert (
        review(client, lead, "name", expected_revision=lead["entity_revision"] + 1).status_code
        == 422
    )
    assert review(client, lead, "name", value_hash="0" * 64).status_code == 422
    assert review(client, lead, "name", field="unknown").status_code == 422
    assert review(client, lead, "name").status_code == 200
    store = app.state.store
    with store.transaction() as db:
        db.execute("UPDATE leads SET company='Imported replacement' WHERE id=?", (lead["id"],))
    changed = store.lead(lead["id"])
    assert field(changed, "name")["status"] == "pending"
    assert field(changed, "name")["reason"] == "Changed since review"
    assert review(client, lead, "name").status_code == 422


def test_reminder_decision_preserves_cases_and_skips_report_projection(client, app, monkeypatch):
    lead = open_entity(client, app)
    store = app.state.store
    cases_before = store.all("SELECT * FROM cases ORDER BY id")
    entities_before = store.all("SELECT * FROM leads ORDER BY id")
    validations_before = store.all("SELECT * FROM section_validations ORDER BY id")

    def no_projection(*args, **kwargs):
        raise AssertionError("Field reminders must not load report previews")

    monkeypatch.setattr(store, "lead", no_projection)
    response = review(client, lead, "address", "ignore")
    assert response.status_code == 200, response.text
    assert store.all("SELECT * FROM cases ORDER BY id") == cases_before
    assert store.all("SELECT * FROM leads ORDER BY id") == entities_before
    assert store.all("SELECT * FROM section_validations ORDER BY id") == validations_before
    decision = store.one("SELECT * FROM entity_field_reviews WHERE entity_id=?", (lead["id"],))
    assert decision["reviewed_by"] == "Test Analyst" and decision["reviewed_at"]


def test_schema_six_upgrade_preserves_records_and_existing_manual_details(client, app):
    from schema_helpers import restore_schema

    lead = open_entity(client, app)
    store = app.state.store
    with store.transaction() as db:
        restore_schema(db, 6)
        db.execute("UPDATE leads SET company='Existing business' WHERE id=?", (lead["id"],))
        db.execute(
            "INSERT OR REPLACE INTO entity_profiles VALUES(?,?)",
            (
                lead["id"],
                json.dumps({"address": "24 Main Street", "city": "Asheville", "state": "NC"}),
            ),
        )
        db.execute("PRAGMA user_version=6")
    entries_before = store.all("SELECT * FROM entries ORDER BY id")
    reopened = Store(store.root)
    assert reopened.one("PRAGMA user_version")["user_version"] == SCHEMA_VERSION
    assert reopened.all("SELECT * FROM entries ORDER BY id") == entries_before
    assert not reopened.lead(lead["id"])["entity_review"]["required"]
    assert not reopened.all("PRAGMA foreign_key_check")
    assert list((store.root / "backups").glob(f"before-schema-{SCHEMA_VERSION}-*.sqlite3"))


def test_merging_businesses_reflags_incoming_details_without_copying_decisions(client, app):
    source = open_entity(client, app)
    source = client.put(
        f"/api/entities/{source['id']}/profile",
        json={"expected_revision": source["entity_revision"], "address": "24 Main Street"},
    ).json()
    assert field(source, "address")["status"] == "confirmed"

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

    app.state.intake.lookup_factory = Other
    import_rows(
        client,
        app,
        [{**observations()[0], "hostname": "mail.another.com", "ip": "8.8.4.4"}],
        "other.csv",
    )
    target_id = next(x["id"] for x in client.get("/api/leads").json() if x["id"] != source["id"])
    target = client.get("/api/leads/" + target_id).json()
    assert review(client, target, "address", "ignore").status_code == 200
    response = client.post(
        f"/api/entities/{source['id']}/merge",
        json={
            "target_id": target_id,
            "source_revision": source["entity_revision"],
            "target_revision": target["entity_revision"],
        },
    )
    assert response.status_code == 200, response.text
    assert field(response.json(), "address")["value"] == "24 Main Street"
    assert field(response.json(), "address")["status"] == "pending"
