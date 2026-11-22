"""Contact publication never overrides known delivery outcomes or outreach holds."""

import json
from hashlib import sha256

import pytest

from modules.entities.tests.support.contacts import attributed_entity, contact_result
from modules.investigations.components.cases import Cases
from modules.entities.components.contact_jobs import ContactDiscoveryJobs
from modules.entities.components.contact_outcomes import contact_summary, route_key
from modules.entities.components.contact_records import ContactConflict, ContactRecords
from modules.entities.components.contact_discovery import candidate_key
from modules.workspace.components.primitives import now
from modules.workspace.components.store import Store
from modules.workspace.components.workspace_data import export_workspace, unpack_workspace
from modules.entities.tests.support.contacts_api import fixture

from modules.entities.tests.support.contacts import (
    attempt,
    report,
)


@pytest.fixture
def saved(tmp_path):
    store = Store(tmp_path / "data")
    # Sender identity is pinned when a notification is created.
    with store.transaction() as db:
        settings = store.settings()
        settings["analyst_name"] = "Test Analyst"
        db.execute("UPDATE settings SET value=? WHERE key='profile'", (json.dumps(settings),))
    entity = attributed_entity(store)
    records = ContactRecords(store)
    records.save_run(records.scope(entity["id"]), contact_result())
    candidate = records.state(entity["id"])["candidates"][0]
    candidate = records.review(entity["id"], candidate["id"], "confirm", candidate["revision"])[
        "candidates"
    ][0]
    case = Cases(store).create(entity["id"])
    return store, records, entity, candidate, case["case_id"]


def test_bounce_blocks_confirmed_candidate_manual_plan_and_adoption(saved):
    store, records, entity, candidate, case_id = saved
    with store.transaction() as db:
        db.execute("UPDATE cases SET contact_email=? WHERE id=?", (candidate["value"], case_id))
        db.execute(
            "INSERT INTO entity_profiles VALUES(?,?)",
            (entity["id"], json.dumps({"contact_email": candidate["value"]})),
        )
    attempt(store, case_id, "bounced", "Security@Example.com")
    current = records.state(entity["id"])["candidates"][0]
    assert current["decision"] == "confirmed" and current["unusable"] and not current["usable"]
    assert not contact_summary(store, entity["id"])["has_usable_contact"]
    with pytest.raises(ContactConflict, match="adverse contact outcome"):
        records.use(
            Cases(store),
            case_id,
            candidate["id"],
            store.one("SELECT version FROM cases WHERE id=?", (case_id,))["version"],
            current["revision"],
        )
    # Merely confirming that the address is still published does not erase a bounce.
    current = records.review(entity["id"], current["id"], "confirm", current["revision"])[
        "candidates"
    ][0]
    assert current["unusable"]
    assert (
        store.one("SELECT contact_email FROM cases WHERE id=?", (case_id,))["contact_email"]
        == candidate["value"]
    )


def test_no_answer_does_not_invalidate_and_other_destinations_do_not_leak(saved):
    store, records, entity, candidate, case_id = saved
    attempt(store, case_id, "no_answer")
    attempt(store, case_id, "bounced", "other@example.com")
    status = contact_summary(store, entity["id"])
    assert status["has_usable_contact"]
    assert status["candidate_status"][candidate["id"]]["attempt_count"] == 1
    assert not records.state(entity["id"])["candidates"][0]["unusable"]


def test_explicit_restore_and_preference_survive_refresh_and_backup(saved, tmp_path):
    store, records, entity, candidate, case_id = saved
    attempt(store, case_id, "bounced")
    current = records.route_decision(
        entity["id"],
        candidate["id"],
        "restore",
        "Recipient confirmed the mailbox is working",
        candidate["revision"],
    )["candidates"][0]
    current = records.route_decision(
        entity["id"], current["id"], "prefer", "IT team confirmed this route", current["revision"]
    )["candidates"][0]
    with pytest.raises(ContactConflict, match="changed"):
        records.route_decision(
            entity["id"], current["id"], "unusable", "stale decision", current["revision"] - 1
        )
    records.save_run(records.scope(entity["id"]), contact_result())
    current = records.state(entity["id"])["candidates"][0]
    assert current["preferred"] and current["usable"]
    before = records.export_projection(entity["id"])
    backup = export_workspace(store)
    unpack_workspace(backup, tmp_path / "restored")
    assert ContactRecords(Store(tmp_path / "restored")).export_projection(entity["id"]) == before
    backup.unlink()


def test_latest_success_reenables_route_and_later_source_change_stays_informational(saved):
    store, records, entity, candidate, case_id = saved
    report_id = report(store, case_id, entity["id"])
    attempt(store, case_id, "bounced")
    attempt(store, case_id, "delivered", occurred="2026-02-01T10:00:00Z", report_id=report_id)
    attempt(store, case_id, "no_answer", occurred="2026-03-01T10:00:00Z")
    status = contact_summary(store, entity["id"])["candidate_status"][candidate["id"]]
    assert status["usable"] and status["last_successful_use"] == "2026-02-01T10:00:00Z"
    changed = contact_result()
    changed["candidates"][0]["purpose"] = "general"
    records.save_run(records.scope(entity["id"]), changed)
    assert contact_summary(store, entity["id"])["has_usable_contact"]
    assert records.state(entity["id"])["candidates"][0]["source_changed"]


def test_batch_researches_unusable_route_and_does_not_reuse_cache(saved, monkeypatch):
    store, records, entity, candidate, case_id = saved
    jobs = ContactDiscoveryJobs(store)
    monkeypatch.setattr(
        jobs, "_enqueue", lambda scopes, www, refresh, skipped=(): (scopes, refresh, skipped)
    )
    try:
        scopes, refresh, skipped = jobs.batch([entity["id"]])
        assert len(scopes) == 1 and refresh and not skipped
        attempt(store, case_id, "bounced")
        scopes, refresh, skipped = jobs.batch([entity["id"]])
        assert len(scopes) == 1 and refresh and not skipped
    finally:
        jobs.close()


def test_wrong_recipient_and_preference_are_explicit_and_entity_scoped(saved):
    store, records, entity, candidate, _ = saved
    attributed_entity(store, "other.example", "other")
    with pytest.raises(ValueError, match="does not belong"):
        records.route_decision(
            "other", candidate["id"], "unusable", "Wrong recipient", candidate["revision"]
        )
    with pytest.raises(ValueError, match="reason"):
        records.route_decision(
            entity["id"], candidate["id"], "unusable", " ", candidate["revision"]
        )
    current = records.route_decision(
        entity["id"],
        candidate["id"],
        "unusable",
        "Contact has left the business",
        candidate["revision"],
    )["candidates"][0]
    assert current["unusable"] and current["decision"] == "confirmed"
    with pytest.raises(ContactConflict, match="available contact"):
        records.route_decision(
            entity["id"],
            candidate["id"],
            "prefer",
            "Cannot choose blocked route",
            current["revision"],
        )


def test_route_matching_normalizes_phone_and_email_without_dropping_extensions():
    assert route_key("phone", "+1 (828) 555-0101 ext. 12") == route_key("phone", "828-555-0101 x12")
    assert route_key("phone", "8285550101") != route_key("phone", "8285550101 x12")
    assert route_key("email", "Security@Example.COM ") == route_key("email", "security@example.com")


def test_named_contact_can_fill_plan_without_claiming_a_delivery_route(saved):
    store, records, entity, existing, case_id = saved
    records.review(entity["id"], existing["id"], "ignore", existing["revision"])
    result = contact_result(value="Alex Example")
    found = result["candidates"][0]
    found.update(
        kind="person",
        key=candidate_key("person", "Alex Example"),
        name="Alex Example",
        role="IT Director",
        purpose="it",
    )
    body = b"<p>Alex Example, IT Director</p>"
    result["snapshots"][0].update(body=body, sha256=sha256(body).hexdigest())
    result["bytes_received"] = len(body)
    records.save_run(records.scope(entity["id"]), result)
    person = next(c for c in records.state(entity["id"])["candidates"] if c["kind"] == "person")
    current = records.review(entity["id"], person["id"], "confirm", person["revision"])
    person = next(c for c in current["candidates"] if c["kind"] == "person")
    assert person["can_adopt"] and not person["usable"]
    adopted = records.use(Cases(store), case_id, person["id"], 0, person["revision"])
    assert adopted["contact_plan"]["contact_name"] == "Alex Example"
    assert not contact_summary(store, entity["id"])["has_usable_contact"]


def test_handoff_is_read_only_configured_and_honors_outreach_holds(saved, monkeypatch):
    store, records, entity, candidate, case_id = saved
    records.route_decision(
        entity["id"], candidate["id"], "prefer", "Confirmed route", candidate["revision"]
    )
    report_id = report(store, case_id, entity["id"])
    monkeypatch.setattr(store, "package_available", lambda item: item["id"] == report_id)
    with store.transaction() as db:
        settings = store.settings()
        settings["analyst_name"] = "Test Analyst"
        db.execute("UPDATE settings SET value=? WHERE key='profile'", (json.dumps(settings),))
    first = records.handoff(case_id)
    assert not first["ready"] and first["verification_route"] == ""
    assert "[Add an independently accessible" in first["message"]
    records.configure_verification("https://office.example/verify", "")
    event_count = len(store.all("SELECT * FROM events"))
    handoff = records.handoff(case_id)
    assert handoff["ready"] and handoff["report"]["id"] == report_id
    assert "https://office.example/verify" in handoff["message"]
    assert "SHA-256" in handoff["source_explanation"]
    assert records.handoff(case_id) == handoff
    assert len(store.all("SELECT * FROM events")) == event_count
    with store.transaction() as db:
        db.execute(
            "INSERT INTO case_outreach_policy VALUES(?,?,?,?,?,?)",
            (
                case_id,
                "do_not_contact",
                "Recipient requested no further outreach",
                None,
                "Test Analyst",
                now(),
            ),
        )
    held = records.handoff(case_id)
    assert not held["ready"] and any("do not contact" in b for b in held["blockers"])
    assert (
        store.one("SELECT state FROM case_outreach_policy WHERE case_id=?", (case_id,))["state"]
        == "do_not_contact"
    )


def test_verification_route_is_revision_checked_and_rejects_credentials(saved):
    _, records, _, _, _ = saved
    with pytest.raises(ValueError, match="credentials"):
        records.configure_verification("https://user:secret@office.example/", "")
    records.configure_verification("Office public switchboard: (828) 555-0101", "")
    with pytest.raises(ContactConflict, match="changed"):
        records.configure_verification("https://office.example/verify", "")


def test_route_and_handoff_api_validate_revisions_and_never_send(fixture):
    app, client, entity, case, calls = fixture
    records = app.state.contact_discovery_jobs.records
    records.save_run(records.scope(entity["id"]), contact_result())
    candidate = records.state(entity["id"])["candidates"][0]
    candidate = records.review(entity["id"], candidate["id"], "confirm", candidate["revision"])[
        "candidates"
    ][0]
    route = f"/api/entities/{entity['id']}/contacts/{candidate['id']}/route"
    body = {
        "action": "prefer",
        "reason": "Confirmed security team",
        "expected_revision": candidate["revision"],
    }
    response = client.post(route, json=body)
    assert response.status_code == 200 and response.json()["candidates"][0]["preferred"]
    assert client.post(route, json=body).status_code == 409
    assert client.post(route, json={**body, "action": "send"}).status_code == 422
    config = client.put(
        "/api/contact-discovery/verification-route",
        json={"value": "https://office.example/contact", "expected_value": ""},
    )
    assert config.status_code == 200
    handoff = client.get(f"/api/cases/{case['case_id']}/outreach-handoff")
    assert handoff.status_code == 200 and not handoff.json()["ready"]
    assert not calls and not app.state.store.all("SELECT * FROM contact_attempts")


@pytest.mark.parametrize(
    "value", ["Office switchboard\x7f", "Office\nSwitchboard", "\nOffice switchboard", "A" * 1001]
)
def test_verification_api_rejects_invalid_text_without_changing_shared_settings(fixture, value):
    app, client, _, _, _ = fixture
    before = app.state.store.settings()
    response = client.put(
        "/api/contact-discovery/verification-route",
        json={"value": value, "expected_value": ""},
    )
    assert response.status_code == 422, response.text
    assert app.state.store.settings() == before


def test_verification_route_accepts_optional_blank_and_normalizes_plain_spaces(saved):
    store, records, _, _, _ = saved
    assert records.configure_verification("  Office switchboard  ", "") == {
        "verification_route": "Office switchboard"
    }
    assert records.configure_verification("   ", "Office switchboard") == {"verification_route": ""}
    assert store.settings()["outreach_verification_route"] == ""
