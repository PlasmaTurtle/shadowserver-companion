"""Workday next actions and atomic adoption of revised business identity."""

from contextlib import closing

from copy import deepcopy
import json
import sqlite3

import pytest

from tests.support.workbench import app, client, import_rows, observations, ready
from modules.investigations.tests.support.section_reviews import status
from modules.workspace.components.case_guidance import (
    saved_case_facts,
    working_case_action,
    working_case_signals,
)
from modules.workspace.components.workspace_queue import workspace_queue


def reviewed_case(client, app):
    import_rows(client, app, [observations()[2]])
    entity_id = client.get("/api/leads").json()[0]["id"]
    return ready(client, entity_id)


def rename(client, lead, name="Updated business"):
    entity = client.get("/api/entities/" + lead["id"]).json()
    response = client.put(
        "/api/entities/" + lead["id"] + "/name",
        json={"name": name, "expected_revision": entity["entity_revision"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


def adoption_body(plan, reason="Confirm the identified business before outreach"):
    return {
        "expected_version": plan["expected_version"],
        "expected_entity_revision": plan["expected_entity_revision"],
        "reopen_affected": True,
        "reason": reason,
    }


def test_identity_adoption_reopens_exact_sections_in_one_audited_change(client, app):
    lead = reviewed_case(client, app)
    rename(client, lead)
    url = "/api/cases/" + lead["case_id"] + "/entity-details"
    store = app.state.store
    before = store.one("SELECT * FROM cases WHERE id=?", (lead["case_id"],))
    old_validations = store.all("SELECT * FROM section_validations ORDER BY id")
    plan = client.get(url).json()
    assert plan["changes"] == [
        {
            "key": "company",
            "label": "Business name",
            "before": lead["company"],
            "after": "Updated business",
        }
    ]
    assert plan["reopen_sections"] == ["introduction", "vulnerabilities", "attribution"]
    assert store.one("SELECT * FROM cases WHERE id=?", (lead["case_id"],)) == before
    # Reviewing a plan is read-only; neither stale submissions nor blank reasons
    # can partially reopen sections or repin identity.
    rejected = client.post(url, json=adoption_body(plan, " "))
    assert rejected.status_code == 422
    assert store.one("SELECT * FROM cases WHERE id=?", (lead["case_id"],)) == before
    response = client.post(url, json=adoption_body(plan))
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["draft"]["company"] == "Updated business"
    assert updated["case"]["version"] == before["version"] + 1
    assert updated["draft_revision"] == before["draft_revision"] + 1
    for key in plan["reopen_sections"]:
        assert status(updated, key)["status"] == "draft"
    for key in ("information", "closing"):
        assert status(updated, key)["validation_id"] == status(lead, key)["validation_id"]
        assert status(updated, key)["status"] == "validated"
    assert store.all("SELECT * FROM section_validations ORDER BY id") == old_validations
    reopened = store.all("SELECT * FROM section_events WHERE action='reopened'")
    assert len(reopened) == 3
    assert all("Confirm the identified business" in row["reason"] for row in reopened)
    event = store.one("SELECT * FROM events WHERE action='entity_details_adopted' ORDER BY id DESC")
    assert json.loads(event["detail"])["reopened_sections"] == plan["reopen_sections"]
    assert client.post(url, json=adoption_body(plan)).status_code == 422


def test_entity_change_after_plan_requires_review_again(client, app):
    lead = reviewed_case(client, app)
    rename(client, lead, "Reviewed business")
    url = "/api/cases/" + lead["case_id"] + "/entity-details"
    plan = client.get(url).json()
    rename(client, lead, "Later business edit")
    store = app.state.store
    before = store.one("SELECT * FROM cases WHERE id=?", (lead["case_id"],))
    response = client.post(url, json=adoption_body(plan))
    assert response.status_code == 422 and "Entity details changed" in response.text
    assert store.one("SELECT * FROM cases WHERE id=?", (lead["case_id"],)) == before
    assert store.all("SELECT * FROM section_events WHERE action='reopened'") == []


def test_scope_change_invalidates_old_entity_plan_and_preserves_remaining_locks(
    client, app, monkeypatch
):
    from modules.investigations.tests.support.section_reviews import change

    import_rows(client, app, [observations()[0], observations()[2]])
    entity_id = client.get("/api/leads").json()[0]["id"]
    lead = ready(client, entity_id)
    rename(client, lead)
    url = "/api/cases/" + lead["case_id"] + "/entity-details"
    plan = client.get(url).json()
    excluded = next(entry["id"] for entry in lead["entries"] if entry["ip"] == "1.1.1.1")
    response = change(client, lead, [excluded], reopen_affected=True)
    assert response.status_code == 200, response.text
    scoped = response.json()
    store = app.state.store
    before = store.one("SELECT * FROM cases WHERE id=?", (lead["case_id"],))
    history = store.all("SELECT * FROM section_events ORDER BY id")

    def forbidden(*args, **kwargs):
        raise AssertionError("An entity plan must not load or hash report/evidence files")

    with monkeypatch.context() as restricted:
        restricted.setattr(store, "path", forbidden)
        restricted.setattr(store, "package_available", forbidden)
        assert client.post(url, json=adoption_body(plan)).status_code == 422
        current_plan = client.get(url).json()
    assert store.one("SELECT * FROM cases WHERE id=?", (lead["case_id"],)) == before
    assert store.all("SELECT * FROM section_events ORDER BY id") == history
    frozen = {row["key"] for row in scoped["section_reviews"] if row["status"] == "validated"}
    assert set(current_plan["reopen_sections"]) == frozen & {
        "introduction",
        "vulnerabilities",
        "attribution",
    }
    updated = client.post(url, json=adoption_body(current_plan))
    assert updated.status_code == 200, updated.text
    for key in frozen - set(current_plan["reopen_sections"]):
        assert status(updated.json(), key)["validation_id"] == status(scoped, key)["validation_id"]


def test_adoption_failure_rolls_back_identity_and_reopens(client, app, monkeypatch):
    lead = reviewed_case(client, app)
    rename(client, lead)
    url = "/api/cases/" + lead["case_id"] + "/entity-details"
    plan = client.get(url).json()
    store = app.state.store
    before = store.one("SELECT * FROM cases WHERE id=?", (lead["case_id"],))
    prior_events = store.all("SELECT * FROM section_events ORDER BY id")
    original = store.log

    def fail_log(db, action, *args, **kwargs):
        if action == "entity_details_adopted":
            raise RuntimeError("Simulated disk/write failure")
        return original(db, action, *args, **kwargs)

    monkeypatch.setattr(store, "log", fail_log)
    with pytest.raises(RuntimeError, match="Simulated disk/write failure"):
        client.post(url, json=adoption_body(plan))
    assert store.one("SELECT * FROM cases WHERE id=?", (lead["case_id"],)) == before
    assert store.all("SELECT * FROM section_events ORDER BY id") == prior_events


def test_no_change_and_nonworking_cases_do_not_reopen(client, app):
    lead = reviewed_case(client, app)
    url = "/api/cases/" + lead["case_id"] + "/entity-details"
    store = app.state.store
    plan = client.get(url).json()
    assert plan["changed"] is False and not plan["reopen_sections"]
    before = store.one("SELECT * FROM cases WHERE id=?", (lead["case_id"],))
    response = client.post(url, json=adoption_body(plan))
    assert response.status_code == 200, response.text
    assert store.one("SELECT * FROM cases WHERE id=?", (lead["case_id"],)) == before
    rename(client, lead)
    for stage in ("pending_notification", "notification_completed", "closed"):
        with store.transaction() as db:
            db.execute("UPDATE cases SET stage=? WHERE id=?", (stage, lead["case_id"]))
        assert client.get(url).status_code == 422
        assert client.post(url, json=adoption_body(plan)).status_code == 422
    assert store.all("SELECT * FROM section_events WHERE action='reopened'") == []


def test_workspace_uses_saved_blocker_and_never_opens_report_or_evidence(client, app, monkeypatch):
    row = {**observations()[2], "tag": "CVE-2026-987654"}
    import_rows(client, app, [row])
    store = app.state.store
    before = store.all("SELECT * FROM cases")
    events = store.all("SELECT * FROM events")
    connections = []
    original = store.connect

    def connect():
        connections.append(1)
        return original()

    def forbidden(*args, **kwargs):
        raise AssertionError("Workspace must not open files, render, hash or write")

    monkeypatch.setattr(store, "connect", connect)
    monkeypatch.setattr(store, "path", forbidden)
    monkeypatch.setattr(store, "log", forbidden)
    monkeypatch.setattr(store, "package_available", forbidden)
    result = workspace_queue(store)
    assert len(connections) == 1
    item = result["items"][0]
    assert item["suggested_action"] == "Resolve CVE source or disposition: CVE-2026-987654"
    assert item["action_tab"] == "notification" and item["action_section"] == "Vulnerabilities"
    assert store.all("SELECT * FROM cases") == before
    assert store.all("SELECT * FROM events") == events


def test_workspace_keeps_one_snapshot_during_concurrent_change(client, app, monkeypatch):
    import_rows(client, app, [observations()[2]])
    store = app.state.store
    case_id = store.one("SELECT id FROM cases")["id"]
    import modules.workspace.components.workspace_queue as module

    original = module.list_cases

    def change_after_case_list(*args, **kwargs):
        rows = original(*args, **kwargs)
        with closing(sqlite3.connect(store.db)) as writer, writer:
            writer.execute(
                "UPDATE cases SET next_action='New concurrent plan' WHERE id=?", (case_id,)
            )
            writer.execute(
                "INSERT INTO case_outreach_policy VALUES(?,?,?,?,?,?)",
                (
                    case_id,
                    "do_not_contact",
                    "Concurrent recipient hold",
                    None,
                    "Analyst",
                    "2026-11-13T00:00:00Z",
                ),
            )
        return rows

    monkeypatch.setattr(module, "list_cases", change_after_case_list)
    first = module.workspace_queue(store)
    assert first["items"][0]["outreach_policy"]["state"] == "active"
    assert first["items"][0]["suggested_action"] != "New concurrent plan"
    monkeypatch.setattr(module, "list_cases", original)
    second = module.workspace_queue(store)
    assert second["items"] == [] and second["held"] == 1


def test_workspace_section_progress_stale_and_delivered_route(client, app):
    lead = reviewed_case(client, app)
    item = client.get("/api/workspace/queue").json()["items"][0]
    assert item["action_code"] == "certification"
    store = app.state.store
    with store.transaction() as db:
        from modules.investigations.components.repositories.reviews import SectionReviewRepository

        reviews = SectionReviewRepository(store)
        frozen = reviews.active(lead["case_id"], db)["attribution"]
        reviews.event(
            db,
            lead["case_id"],
            "attribution",
            "stale",
            "System",
            "Changed source",
            frozen["revision"],
            frozen["id"],
        )
    item = client.get("/api/workspace/queue").json()["items"][0]
    assert item["suggested_action"] == "Reopen and review changed section: Attribution"
    assert item["action_section"] == "Attribution"
    with store.transaction() as db:
        db.execute(
            "UPDATE cases SET stage='notification_completed',next_action='Prepare closing report' WHERE id=?",
            (lead["case_id"],),
        )
    item = client.get("/api/workspace/queue").json()["items"][0]
    assert item["action_tab"] == "closing"
    with store.transaction() as db:
        db.execute(
            "UPDATE cases SET next_action='Call recipient about the response' WHERE id=?",
            (lead["case_id"],),
        )
    item = client.get("/api/workspace/queue").json()["items"][0]
    assert item["suggested_action"] == "Call recipient about the response"
    assert item["action_tab"] == "contact"


def test_guidance_bulk_read_count_and_scope_projection(client, app):
    import_rows(client, app, [observations()[2], {**observations()[2], "ip": "10.1.2.3"}])
    store = app.state.store
    case = store.one("SELECT * FROM cases")
    draft = json.loads(case["draft"])
    identity = json.loads(case["entity_snapshot"])
    with store.read_snapshot() as db:
        queries = []
        db.set_trace_callback(queries.append)
        facts = saved_case_facts(db)[case["id"]]
        assert len(queries) == 3
    action = working_case_action(facts, draft, identity, store.settings())
    assert action[3] == "report_scope" and action[2] == "Vulnerabilities"
    private = next(entry for entry in facts["entries"] if entry["ip"] == "10.1.2.3")
    included_with_reason = {
        **draft,
        "observation_scope": {
            private["id"]: {"decision": "include", "reason": "Not evidence of public exposure"}
        },
    }
    assert (
        working_case_action(facts, included_with_reason, identity, store.settings())[3]
        == "report_scope"
    )
    excluded = {
        **draft,
        "observation_scope": {
            private["id"]: {"decision": "exclude", "reason": "Nonpublic scanner row"}
        },
    }
    assert working_case_action(facts, excluded, identity, store.settings())[3] == "section_review"
    excluded["observation_scope"] = {
        entry["id"]: {"decision": "exclude"} for entry in facts["entries"]
    }
    assert (
        "close without notification"
        in working_case_action(facts, excluded, identity, store.settings())[0]
    )
    supporting = deepcopy(next(entry for entry in facts["entries"] if entry["ip"] != "10.1.2.3"))
    supporting["normalized"].update(case_condition_scope=True, active_conditions=[])
    support_only = {**facts, "entries": [supporting]}
    assert (
        "close without notification"
        in working_case_action(support_only, draft, identity, store.settings())[0]
    )
    # Bulk cost remains constant as the workspace grows; no per-case read of
    # evidence or serialized report models is introduced by the guidance.
    with store.transaction() as db:
        for index in range(60):
            copied = f"guidance-load-{index}"
            db.execute(
                "INSERT INTO cases(id,entity_id,title,created_at,updated_at,draft) VALUES(?,?,?,?,?,?)",
                (
                    copied,
                    case["entity_id"],
                    copied,
                    case["created_at"],
                    case["updated_at"],
                    case["draft"],
                ),
            )
            db.execute(
                "INSERT INTO case_entries SELECT ?,entry_id FROM case_entries WHERE case_id=?",
                (copied, case["id"]),
            )
            db.execute(
                "INSERT INTO case_groups SELECT ?,root_domain,attribution_entry_id,attribution FROM case_groups WHERE case_id=?",
                (copied, case["id"]),
            )
    with store.read_snapshot() as db:
        queries = []
        db.set_trace_callback(queries.append)
        expanded = saved_case_facts(db)
        assert len(expanded) == 61
        assert len(queries) == 3


def test_guidance_uses_pinned_sender_and_only_included_source_signals(client, app):
    import_rows(client, app, [observations()[2]])
    store = app.state.store
    case = store.one("SELECT * FROM cases")
    draft = json.loads(case["draft"])
    identity = json.loads(case["entity_snapshot"])
    with store.read_snapshot() as db:
        facts = saved_case_facts(db)[case["id"]]
    from modules.settings.components.sender_identity import capture_profile

    draft["sender_profile"] = capture_profile({**store.settings(), "analyst_name": ""})
    action = working_case_action(facts, draft, identity, store.settings())
    assert action[3] == "sender"
    assert "adopt" in action[0].lower()
    # Current workspace settings cannot silently repair the reviewed sender.
    assert store.settings()["analyst_name"] == "Test Analyst"
    legacy = {key: value for key, value in draft.items() if key != "sender_profile"}
    custom_settings = {**store.settings(), "agency": "Example Response Team", "office": ""}
    legacy_action = working_case_action(facts, legacy, identity, custom_settings)
    assert legacy_action[3] == "sender" and legacy_action[2] == "Introduction"
    assert "adopt" in legacy_action[0].lower()
    entry = facts["entries"][0]
    source = deepcopy(entry)
    source["id"] = "excluded-critical-source"
    source["source"]["fields"].update(tag="CVE-2026-1234", severity="critical")
    source.get("normalized", {}).pop("case_condition_scope", None)
    harmless = deepcopy(entry)
    harmless["source"]["fields"]["severity"] = "medium"
    facts["entries"] = [harmless, source]
    draft["cve_records"] = [{"id": "CVE-2026-1234", "kev": True, "cvss": 9.8}]
    assert working_case_signals(facts, draft)[1] is True
    draft["observation_scope"] = {source["id"]: {"decision": "exclude"}}
    selected, critical = working_case_signals(facts, draft)
    assert selected == [] and critical is False


@pytest.mark.parametrize("scope", ["excluded", "support_only"])
def test_workspace_keeps_unreported_source_severity_out_after_certification(client, app, scope):
    from modules.investigations.tests.support.section_reviews import change
    from modules.investigations.tests.support.cases import attempt, closing_values

    import_rows(
        client,
        app,
        [observations()[2], {**observations()[0], "severity": "medium"}],
    )
    case = client.get("/api/cases").json()[0]
    lead = client.get("/api/cases/" + case["id"]).json()
    source_id = next(entry["id"] for entry in lead["entries"] if entry["ip"] == "8.8.8.8")
    if scope == "excluded":
        response = change(client, lead, [source_id])
        assert response.status_code == 200, response.text
    else:
        # Later notification scopes can retain a prior attribution anchor with
        # no new conditions. It remains proof, not a critical finding to notify.
        with app.state.store.transaction() as db:
            db.execute(
                "INSERT OR REPLACE INTO case_entry_conditions VALUES(?,?,?)",
                (lead["case_id"], source_id, "[]"),
            )
    lead = ready(client, lead["id"])
    assert client.get("/api/workspace/queue").json()["items"][0]["urgency"] == "standard"
    response = client.post("/api/leads/" + lead["id"] + "/finalize")
    assert response.status_code == 200, response.text
    report = response.json()
    pending = client.get("/api/workspace/queue").json()["items"][0]
    assert pending["stage"] == "pending_notification"
    assert pending["urgency"] == "standard"
    assert not any("Critical severity" in reason for reason in pending["priority_reasons"])
    lead = client.get("/api/cases/" + lead["case_id"]).json()
    response = client.post(
        "/api/cases/" + lead["case_id"] + "/attempts", json=attempt(lead, report)
    )
    assert response.status_code == 200, response.text
    delivered = client.get("/api/workspace/queue").json()["items"][0]
    assert delivered["urgency"] == "standard" and delivered["action_tab"] == "closing"
    lead = response.json()
    closed = client.post("/api/cases/" + lead["case_id"] + "/close", json=closing_values(lead))
    assert closed.status_code == 200, closed.text
    assert client.get("/api/workspace/queue").json()["items"] == []


def test_workspace_keeps_excluded_cve_signals_out_after_certification(client, app, monkeypatch):
    from modules.investigations.tests.support.report_api import save, source
    from modules.investigations.tests.support.section_reviews import change

    import_rows(
        client,
        app,
        [
            {**observations()[2], "tag": "CVE-2025-12345", "severity": "medium"},
            observations()[0],
        ],
    )
    entity_id = client.get("/api/leads").json()[0]["id"]
    lead = client.get("/api/leads/" + entity_id).json()
    other = next(entry["id"] for entry in lead["entries"] if entry["ip"] == "1.1.1.1")
    response = change(client, lead, [other])
    assert response.status_code == 200, response.text
    lead = response.json()
    record = {**source(), "kev": True, "severity": "critical", "cvss": 9.8}
    monkeypatch.setattr("modules.workspace.components.api.enrich", lambda *args, **kwargs: record)
    fetched = client.post("/api/cves/CVE-2025-12345/retrieve").json()
    response = save(
        client,
        lead,
        cve_records=[fetched],
        cve_dispositions={"CVE-2025-12345": {"action": "exclude", "reason": "Wrong product"}},
    )
    assert response.status_code == 200, response.text
    lead = ready(client, entity_id)
    assert client.get("/api/workspace/queue").json()["items"][0]["urgency"] == "standard"
    assert not client.get("/api/cases").json()[0]["kev"]
    response = client.post("/api/leads/" + entity_id + "/finalize")
    assert response.status_code == 200, response.text
    pending = client.get("/api/workspace/queue").json()["items"][0]
    assert pending["urgency"] == "standard" and not pending["kev"]
    assert not client.get("/api/cases").json()[0]["kev"]
