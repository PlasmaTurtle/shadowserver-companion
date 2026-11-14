"""Saved preparation survives interruptions without sending or widening case scope."""

from copy import deepcopy
import json

import pytest

from test_contacts_api_090 import fixture
from test_contacts_invariants_090 import attributed_entity, contact_result
from test_contact_outcomes_095 import attempt, report
from workbench.cases import Cases
from workbench.contact_records import ContactRecords
from workbench.outreach_preparation import preparation, validate_saved_preparation
from workbench.store import Store


def setup(fixture):
    app, client, entity, case, calls = fixture
    records = app.state.contact_discovery_jobs.records
    records.save_run(records.scope(entity["id"]), contact_result())
    candidate = records.state(entity["id"])["candidates"][0]
    records.use(
        Cases(app.state.store),
        case["case_id"],
        candidate["id"],
        app.state.store.one("SELECT version FROM cases WHERE id=?", (case["case_id"],))["version"],
        candidate["revision"],
    )
    return app.state.store, records, client, entity, case["case_id"], calls


def payload(data, **changes):
    return {
        "expected_revision": data["preparation"]["revision"],
        "expected_context": data["context_hash"],
        **{key: data["preparation"][key] for key in ("subject", "message", "call_outline")},
        **changes,
    }


def version(data):
    return {
        "expected_revision": data["preparation"]["revision"],
        "expected_context": data["context_hash"],
    }


def test_save_reopen_copy_and_reset_preserve_case_and_contact_history(fixture):
    store, records, client, entity, case_id, calls = setup(fixture)
    url = f"/api/cases/{case_id}"
    before = store.one("SELECT * FROM cases WHERE id=?", (case_id,))
    first = client.get(url + "/outreach-handoff").json()
    assert first["preparation"]["revision"] == 0 and not first["report"]
    assert not first["ready"] and first["copy_allowed"], "Research may precede certification"
    assert any("verification" in value for value in first["blockers"])
    assert client.post(url + "/outreach-preparation/copy", json=version(first)).status_code == 409
    saved = client.put(
        url + "/outreach-preparation",
        json=payload(
            first,
            subject="Callback tomorrow",
            message="Operator's tailored introduction",
            call_outline="Ask for Alex; verify the office",
        ),
    ).json()
    assert saved["preparation"]["revision"] == 1
    reopened_store = Store(store.root)
    reopened = preparation(reopened_store, ContactRecords(reopened_store), case_id)
    assert reopened["preparation"] == saved["preparation"]
    copied = client.post(url + "/outreach-preparation/copy", json=version(saved))
    assert copied.status_code == 200, copied.text
    assert copied.json()["text"] == "Subject: Callback tomorrow\n\nOperator's tailored introduction"
    assert copied.json()["call_outline"] == "Ask for Alex; verify the office"
    reset = client.post(url + "/outreach-preparation/reset", json=version(saved))
    assert reset.status_code == 200, reset.text
    assert reset.json()["preparation"]["revision"] == 2
    assert reset.json()["preparation"]["message"] == first["message"]
    assert store.one("SELECT * FROM cases WHERE id=?", (case_id,)) == before
    assert not store.all("SELECT * FROM contact_attempts") and not calls


def test_stale_window_cannot_overwrite_or_copy_another_saved_revision(fixture):
    store, records, client, entity, case_id, _ = setup(fixture)
    url = f"/api/cases/{case_id}"
    first = client.get(url + "/outreach-handoff").json()
    assert (
        client.put(
            url + "/outreach-preparation", json=payload(first, message="Window one")
        ).status_code
        == 200
    )
    stale = client.put(url + "/outreach-preparation", json=payload(first, message="Window two"))
    assert stale.status_code == 409 and "another window" in stale.text
    assert client.post(url + "/outreach-preparation/copy", json=version(first)).status_code == 409
    assert client.post(url + "/outreach-preparation/reset", json=version(first)).status_code == 409
    assert client.get(url + "/outreach-handoff").json()["preparation"]["message"] == "Window one"
    second_entity = attributed_entity(store, root="other.example.com", entity_id="other")
    second = Cases(store).create(second_entity["id"])["case_id"]
    other = client.get(f"/api/cases/{second}/outreach-handoff").json()
    assert other["preparation"]["revision"] == 0 and other["preparation"]["message"] != "Window one"


def test_changed_verification_report_and_research_require_context_review(fixture, monkeypatch):
    store, records, client, entity, case_id, _ = setup(fixture)
    url = f"/api/cases/{case_id}"
    first = client.get(url + "/outreach-handoff").json()
    saved = client.put(
        url + "/outreach-preparation", json=payload(first, message="Retain this wording")
    ).json()
    records.configure_verification("https://office.example/verify", "")
    report_id = report(store, case_id, entity["id"])
    monkeypatch.setattr(store, "package_available", lambda item: item["id"] == report_id)
    changed = client.get(url + "/outreach-handoff").json()
    assert changed["preparation_stale"] and "Certified report" in changed["context_changes"]
    assert changed["preparation"]["message"] == "Retain this wording"
    assert client.put(url + "/outreach-preparation", json=payload(saved)).status_code == 409
    assert client.post(url + "/outreach-preparation/copy", json=version(changed)).status_code == 409
    assert client.put(url + "/outreach-preparation", json=payload(changed)).status_code == 409
    reviewed = client.put(
        url + "/outreach-preparation", json=payload(changed, reviewed_context=True)
    ).json()
    assert (
        not reviewed["preparation_stale"]
        and reviewed["preparation"]["message"] == "Retain this wording"
    )
    assert (
        client.post(url + "/outreach-preparation/copy", json=version(reviewed)).status_code == 200
    )
    # Ordinary no-answer history does not make the saved recipient unusable.
    attempt(store, case_id, "no_answer")
    assert client.get(url + "/outreach-handoff").json()["copy_allowed"]
    refreshed = contact_result()
    refreshed["candidates"][0]["purpose"] = "general"
    records.save_run(records.scope(entity["id"]), refreshed)
    changed = client.get(url + "/outreach-handoff").json()
    assert changed["preparation"]["message"] == "Retain this wording"
    assert changed["preparation_stale"] and "Contact research" in changed["context_changes"]


@pytest.mark.parametrize("blocked", ["bounced", "deferred", "do_not_contact", "closed"])
def test_copy_rechecks_adverse_route_hold_and_closure(fixture, blocked):
    store, records, client, entity, case_id, _ = setup(fixture)
    url = f"/api/cases/{case_id}"
    first = client.get(url + "/outreach-handoff").json()
    saved = client.put(url + "/outreach-preparation", json=payload(first)).json()
    if blocked == "bounced":
        attempt(store, case_id, "bounced")
    else:
        with store.transaction() as db:
            if blocked == "closed":
                db.execute("UPDATE cases SET stage='closed' WHERE id=?", (case_id,))
            else:
                db.execute(
                    "INSERT INTO case_outreach_policy VALUES(?,?,?,?,?,?)",
                    (
                        case_id,
                        blocked,
                        "Exercise hold",
                        "2026-12-01",
                        "Analyst",
                        "2026-11-13T12:00:00Z",
                    ),
                )
    assert client.post(url + "/outreach-preparation/copy", json=version(saved)).status_code == 409
    current = client.get(url + "/outreach-handoff").json()
    assert not current["copy_allowed"] and current["copy_blockers"]
    if blocked == "closed":
        assert (
            client.put(
                url + "/outreach-preparation", json=payload(current, reviewed_context=True)
            ).status_code
            == 409
        )
    else:
        # Reviewing wording does not overrule a hold or known bad route.
        reviewed = client.put(
            url + "/outreach-preparation", json=payload(current, reviewed_context=True)
        )
        assert reviewed.status_code == 200, reviewed.text
        assert (
            client.post(
                url + "/outreach-preparation/copy", json=version(reviewed.json())
            ).status_code
            == 409
        )


def test_input_and_backup_validation_are_bounded_but_accept_stale_context(fixture):
    store, records, client, entity, case_id, _ = setup(fixture)
    url = f"/api/cases/{case_id}"
    first = client.get(url + "/outreach-handoff").json()
    for change in (
        {"message": "x" * 20001},
        {"subject": "x" * 1001},
        {"call_outline": "x" * 10001},
        {"send": True},
    ):
        assert (
            client.put(url + "/outreach-preparation", json=payload(first, **change)).status_code
            == 422
        )
    assert client.put(url + "/outreach-preparation", json=payload(first)).status_code == 200
    row = store.one("SELECT * FROM outreach_preparations WHERE case_id=?", (case_id,))
    assert validate_saved_preparation(row)
    records.configure_verification("https://office.example/verify", "")
    assert validate_saved_preparation(row), "Saved old context remains valid backup evidence"
    for change in (
        {"context_json": "{"},
        {"context_json": "x" * 262145},
        {"context_hash": "0" * 64},
        {"revision": 0},
        {"context_json": "[" * 2000 + "0" + "]" * 2000},
    ):
        with pytest.raises(ValueError):
            validate_saved_preparation({**deepcopy(row), **change})


def test_entity_merge_and_placeholder_combination_keep_prepared_case(fixture):
    app, client, entity, case, _ = fixture
    store = app.state.store
    case_id = case["case_id"]
    first = client.get(f"/api/cases/{case_id}/outreach-handoff").json()
    saved = client.put(
        f"/api/cases/{case_id}/outreach-preparation",
        json=payload(first, message="Keep this first-contact preparation"),
    )
    assert saved.status_code == 200, saved.text
    before = store.one("SELECT * FROM outreach_preparations WHERE case_id=?", (case_id,))
    current = store.one("SELECT * FROM cases WHERE id=?", (case_id,))
    assert current["version"] == current["draft_revision"] == 0
    other = attributed_entity(store, root="another.com", entity_id="other")
    other_case_id = Cases(store).create(other["id"])["case_id"]
    merged = client.post(
        f"/api/entities/{entity['id']}/merge",
        json={"target_id": other["id"], "source_revision": 0, "target_revision": 0},
    )
    assert merged.status_code == 200, merged.text
    # The supported entity merge retains both independent notification cases.
    assert {row["id"] for row in store.all("SELECT id FROM cases")} == {case_id, other_case_id}
    assert store.one("SELECT * FROM outreach_preparations WHERE case_id=?", (case_id,)) == before
    # The retained placeholder-combination service must also recognize saved
    # preparation as analyst work, even though it does not revise report content.
    with store.transaction() as db:
        Cases(store).combine_unworked(db, other["id"], other_case_id)
    assert [row["id"] for row in store.all("SELECT id FROM cases")] == [case_id]
    assert store.one("SELECT * FROM outreach_preparations WHERE case_id=?", (case_id,)) == before
    assert not store.all("PRAGMA foreign_key_check")
