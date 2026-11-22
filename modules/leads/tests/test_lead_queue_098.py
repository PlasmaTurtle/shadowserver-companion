"""Intake/entity/workflow separation, using complete synthetic source reports."""

from tests.support.qualification import registry_factory

import copy
import json

from tests.support.workbench import app, client, import_rows, observations
from modules.investigations.components.cases import Cases
from modules.workspace.components.store import Store

from modules.leads.tests.support.lead_queue import (
    SharedRegistry,
    queue_import,
)


def test_import_and_entity_maintenance_do_not_open_notifications(client, app, monkeypatch):
    queue_import(client, app)
    store = app.state.store
    assert not store.all("SELECT * FROM cases")
    row = client.get("/api/pending-leads").json()[0]
    assert row["association_state"] == "new" and row["can_start"]
    assert row["observations"] == 4 and row["attribution_status"] == "qualified"
    entity = client.get("/api/entities/" + row["entity_id"]).json()
    assert entity["cases"] == []
    assert entity["entity_review"]["required"]
    response = client.put(
        "/api/entities/" + entity["id"] + "/profile",
        json={
            "expected_revision": entity["entity_revision"],
            "contact_email": "support@example.com",
            "contact_phone": "555-0101",
            "notes": "Known technical contact",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["entity_profile"]["notes"] == "Known technical contact"
    assert not store.all("SELECT * FROM cases")
    assert client.get("/api/navigation-counts").json() == {
        "entities_review": 1,
        "leads": 1,
        "attribution_review": 0,
    }
    queue_import(client, app)
    assert len(client.get("/api/pending-leads").json()) == 1
    assert not store.all("SELECT * FROM cases")


def test_explicit_start_consumes_only_selected_scope_and_replay_is_rejected(client, app):
    queue_import(client, app)
    row = client.get("/api/pending-leads").json()[0]
    result = client.post(
        "/api/pending-leads/" + row["id"] + "/start", json={"expected_revision": row["revision"]}
    )
    assert result.status_code == 200, result.text
    case_id = result.json()["case_id"]
    assert client.get("/api/pending-leads").json() == []
    assert len(app.state.store.all("SELECT * FROM cases")) == 1
    replay = client.post(
        "/api/pending-leads/" + row["id"] + "/start", json={"expected_revision": row["revision"]}
    )
    assert replay.status_code == 422
    assert client.get("/api/cases/" + case_id).json()["case_id"] == case_id


def test_new_observations_wait_until_explicitly_added(client, app):
    queue_import(client, app)
    first = client.get("/api/pending-leads").json()[0]
    result = client.post(
        "/api/pending-leads/" + first["id"] + "/start",
        json={"expected_revision": first["revision"]},
    ).json()
    before = app.state.store.one("SELECT * FROM cases WHERE id=?", (result["case_id"],))
    count = len(
        app.state.store.all("SELECT * FROM case_entries WHERE case_id=?", (result["case_id"],))
    )
    rows = [{**r, "timestamp": "2026-11-09 12:00:00", "version": "8.0.1"} for r in observations()]
    queue_import(client, app, rows, "new.csv")
    assert app.state.store.one("SELECT * FROM cases WHERE id=?", (result["case_id"],)) == before
    assert (
        len(app.state.store.all("SELECT * FROM case_entries WHERE case_id=?", (result["case_id"],)))
        == count
    )
    lead = client.get("/api/pending-leads").json()[0]
    assert lead["association_state"] == "known" and lead["entity_id"] == first["entity_id"]
    add = client.post(
        "/api/pending-leads/" + lead["id"] + "/start",
        json={
            "expected_revision": lead["revision"],
            "case_id": result["case_id"],
            "expected_case_version": before["version"],
        },
    )
    assert add.status_code == 200, add.text
    assert (
        len(app.state.store.all("SELECT * FROM case_entries WHERE case_id=?", (result["case_id"],)))
        == count + 4
    )
    assert client.get("/api/pending-leads").json() == []


def test_entity_contacts_and_identity_do_not_mutate_case_snapshot(client, app):
    queue_import(client, app)
    row = client.get("/api/pending-leads").json()[0]
    start = client.post(
        "/api/pending-leads/" + row["id"] + "/start", json={"expected_revision": row["revision"]}
    ).json()
    before = app.state.store.one("SELECT * FROM cases WHERE id=?", (start["case_id"],))
    entity = client.get("/api/entities/" + row["entity_id"]).json()
    renamed = client.put(
        "/api/entities/" + entity["id"] + "/name",
        json={"name": "Example Business", "expected_revision": entity["entity_revision"]},
    ).json()
    saved = client.put(
        "/api/entities/" + entity["id"] + "/profile",
        json={
            "expected_revision": renamed["entity_revision"],
            "contact_email": "it@example.com",
            "address": "42 Main Street",
            "city": "Asheville",
            "state": "NC",
        },
    )
    assert saved.status_code == 200, saved.text
    assert app.state.store.one("SELECT * FROM cases WHERE id=?", (start["case_id"],)) == before
    case = Cases(app.state.store).view(start["case_id"])
    assert case["company"] != renamed["company"]
    assert case["current_entity"]["company"] == "Example Business"
    assert case["entity_profile"] == {}
    adopted = client.post(
        "/api/cases/" + start["case_id"] + "/entity-details",
        json={"expected_version": before["version"]},
    )
    assert adopted.status_code == 200, adopted.text
    assert adopted.json()["company"] == "Example Business"
    assert adopted.json()["entity_profile"]["city"] == "Asheville"


def test_shared_ip_is_informational_and_explicit_choice_preserves_rows(client, app):
    app.state.intake.attribution_factory = registry_factory(SharedRegistry)
    queue_import(client, app)
    first = client.get("/api/pending-leads").json()[0]
    queue_import(
        client,
        app,
        [{**observations()[0], "hostname": "mail.another.com", "ip": "8.8.8.8"}],
        "other.csv",
    )
    row = next(x for x in client.get("/api/pending-leads").json() if x["domain"] == "another.com")
    assert row["association_state"] == "new" and row["can_start"]
    assert row["entity_id"] != first["entity_id"]
    detail = client.get("/api/pending-leads/" + row["id"]).json()
    assert detail["candidate_entities"] == []
    assert [x["entity_id"] for x in detail["shared_ip_associations"]] == [first["entity_id"]]
    original = app.state.store.all("SELECT id,payload FROM entries ORDER BY id")
    resolved = client.post(
        "/api/pending-leads/" + row["id"] + "/associate",
        json={"expected_revision": row["revision"], "entity_id": first["entity_id"]},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["entity_id"] == first["entity_id"] and resolved.json()["can_start"]
    assert app.state.store.all("SELECT id,payload FROM entries ORDER BY id") == original
    assert not app.state.store.all("PRAGMA foreign_key_check")
    assert not app.state.store.all("SELECT * FROM cases")


def test_saved_ip_association_does_not_merge_unrelated_hosts_and_dispositions_persist(client, app):
    app.state.intake.attribution_factory = registry_factory(SharedRegistry)
    queue_import(client, app)
    first = client.get("/api/pending-leads").json()[0]
    entity = client.get("/api/entities/" + first["entity_id"]).json()
    saved = client.post(
        "/api/entities/" + entity["id"] + "/ip-associations",
        json={"expected_revision": entity["entity_revision"], "ip": "8.8.8.8"},
    )
    assert saved.status_code == 200, saved.text
    queue_import(
        client,
        app,
        [{**observations()[0], "hostname": "mail.another.com", "ip": "8.8.8.8"}],
        "other.csv",
    )
    row = next(x for x in client.get("/api/pending-leads").json() if x["domain"] == "another.com")
    assert row["association_state"] == "new" and row["entity_id"] != first["entity_id"]
    deferred = client.post(
        "/api/pending-leads/" + row["id"] + "/disposition",
        json={"expected_revision": row["revision"], "status": "deferred"},
    )
    assert deferred.status_code == 200, deferred.text
    assert deferred.json()["status"] == "deferred"
    assert len(client.get("/api/pending-leads").json()) == 1
    assert client.get("/api/pending-leads?status=deferred").json()[0]["id"] == row["id"]
    Store(app.state.store.root)
    assert client.get("/api/pending-leads/" + row["id"]).json()["status"] == "deferred"


def test_unqualified_findings_stay_outside_leads(client, app):
    from modules.leads.helpers.queue_identity import queue_id

    app.state.fake.fail = True
    imported, original = queue_import(client, app)
    assert client.get("/api/entities").json() == []
    leads = client.get("/api/pending-leads").json()
    assert leads == []
    store = app.state.store
    assert store.all("SELECT * FROM lead_queue") == []
    assert store.all("SELECT * FROM entries") == []
    for table in ("awareness_assets", "awareness_observations", "awareness_findings"):
        assert store.all(f"SELECT * FROM {table}") == []
    jobs = store.all("SELECT domain,status,payload FROM jobs WHERE import_id=?", (imported["id"],))
    assert jobs and all(job["status"] != "qualified" for job in jobs)
    assert all(
        entry["source"]["fields"]["unknown_extension"] == "KEEP THIS FIELD"
        for job in jobs
        for entry in json.loads(job["payload"])
    )
    assert client.get(f"/api/imports/{imported['id']}/original").content == original
    # Failed qualification retains its source and decision, but never creates a
    # queue record that can be opened or used to start notification work.
    absent_id = queue_id(imported["id"], jobs[0]["domain"])
    assert client.get("/api/pending-leads/" + absent_id).status_code == 422
    assert (
        client.post(
            "/api/pending-leads/" + absent_id + "/start",
            json={"expected_revision": 0},
        ).status_code
        == 422
    )
    assert not app.state.store.all("SELECT * FROM cases")


def test_global_entity_edits_preserve_frozen_section_and_adoption_is_explicit(client, app):
    from tests.support.workbench import ready, resolve_observation_scope

    import_rows(client, app)
    entity_id = client.get("/api/entities").json()[0]["id"]
    lead = ready(client, entity_id, validate=False)
    lead = resolve_observation_scope(client, lead)
    frozen = client.post(
        "/api/cases/" + lead["case_id"] + "/sections/introduction/validate",
        json={"expected_revision": lead["draft_revision"]},
    )
    assert frozen.status_code == 200, frozen.text
    before = frozen.json()
    record = copy.deepcopy(
        app.state.store.one("SELECT * FROM cases WHERE id=?", (lead["case_id"],))
    )
    entity = client.get("/api/entities/" + entity_id).json()
    result = client.put(
        "/api/entities/" + entity_id + "/profile",
        json={
            "expected_revision": entity["entity_revision"],
            "contact_email": "new@example.com",
            "address": "New address",
        },
    )
    assert result.status_code == 200, result.text
    assert app.state.store.one("SELECT * FROM cases WHERE id=?", (lead["case_id"],)) == record
    after = client.get("/api/cases/" + lead["case_id"]).json()
    current = next(r for r in after["section_reviews"] if r["key"] == "introduction")
    prior = next(r for r in before["section_reviews"] if r["key"] == "introduction")
    assert current["status"] == "validated" and current["content_hash"] == prior["content_hash"]
    blocked = client.post(
        "/api/cases/" + lead["case_id"] + "/entity-details",
        json={"expected_version": after["case"]["version"]},
    )
    assert blocked.status_code == 422
