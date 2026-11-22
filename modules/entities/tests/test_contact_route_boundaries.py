"""Saved contact choices agree with API adoption and outreach preparation.

All source evidence and destinations are synthetic. No external provider runs.
"""

import json

from modules.entities.tests.support.contacts_api import fixture
from modules.entities.tests.support.contacts import contact_result


def test_ignored_contact_cannot_be_adopted_through_api(fixture):
    app, client, entity, case, calls = fixture
    store = app.state.store
    records = app.state.contact_discovery_jobs.records
    records.save_run(records.scope(entity["id"]), contact_result())
    candidate = records.state(entity["id"])["candidates"][0]
    candidate = records.review(entity["id"], candidate["id"], "ignore", candidate["revision"])[
        "candidates"
    ][0]
    assert not candidate["can_adopt"]
    before = store.one("SELECT * FROM cases WHERE id=?", (case["case_id"],))
    response = client.post(
        f"/api/cases/{case['case_id']}/contacts/{candidate['id']}/use",
        json={
            "expected_version": before["version"],
            "expected_revision": candidate["revision"],
        },
    )
    assert response.status_code == 409
    assert "ignored or unavailable" in response.json()["detail"]
    assert store.one("SELECT * FROM cases WHERE id=?", (case["case_id"],)) == before
    assert not store.all("SELECT * FROM contact_attempts") and not calls


def test_handoff_uses_saved_entity_phone_without_overriding_case_choice(fixture):
    app, client, entity, case, calls = fixture
    store = app.state.store
    with store.transaction() as db:
        db.execute(
            "INSERT INTO entity_profiles VALUES(?,?)",
            (
                entity["id"],
                json.dumps({"contact_name": "IT team", "contact_phone": "+1 828 555 0101"}),
            ),
        )
    before = store.one("SELECT * FROM cases WHERE id=?", (case["case_id"],))
    endpoint = f"/api/cases/{case['case_id']}/outreach-handoff"
    response = client.get(endpoint)
    assert response.status_code == 200, response.text
    selected = response.json()["contact"]
    assert selected["kind"] == "phone" and selected["value"] == "+1 828 555 0101"
    assert selected["usable"]
    assert not any("Choose a usable contact" in b for b in response.json()["blockers"])
    assert store.one("SELECT * FROM cases WHERE id=?", (case["case_id"],)) == before
    with store.transaction() as db:
        db.execute(
            "UPDATE cases SET contact_phone=? WHERE id=?", ("+1 828 555 0199", case["case_id"])
        )
    selected = client.get(endpoint).json()["contact"]
    assert selected["value"] == "+1 828 555 0199"
    assert not store.all("SELECT * FROM contact_attempts") and not calls
