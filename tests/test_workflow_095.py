import json

from test_cases import opened
from test_workbench import app, client, import_rows, observations


def test_workspace_due_priority_does_not_mutate_cases(client, app):
    lead = opened(client, app)
    store = app.state.store
    with store.transaction() as db:
        db.execute(
            "UPDATE cases SET follow_up_date=?,next_action=? WHERE id=?",
            ("2026-11-08", "Call the IT team", lead["case_id"]),
        )
    before = store.one("SELECT * FROM cases WHERE id=?", (lead["case_id"],))
    events = store.one("SELECT count(*) n FROM events")["n"]
    result = client.get("/api/workspace/queue?as_of=2026-11-08").json()
    # The former URL is compatibility access to this same Workspace feature.
    legacy = client.get("/api/today?as_of=2026-11-08")
    assert legacy.status_code == 200 and legacy.json() == result
    assert "/api/workspace/queue" in app.openapi()["paths"]
    assert "/api/today" not in app.openapi()["paths"]
    assert result["items"][0]["id"] == lead["case_id"]
    assert "Follow-up due" in result["items"][0]["priority_reasons"]
    assert result["items"][0]["suggested_action"] == "Call the IT team"
    assert store.one("SELECT * FROM cases WHERE id=?", (lead["case_id"],)) == before
    assert store.one("SELECT count(*) n FROM events")["n"] == events


def test_hold_reconsideration_does_not_activate_or_reopen(client, app):
    lead = opened(client, app)
    url = "/api/cases/" + lead["case_id"] + "/outreach-policy"
    result = client.put(
        url,
        json={
            "expected_version": lead["case"]["version"],
            "state": "do_not_contact",
            "reason": "Recipient requested a pause",
            "review_on": "2026-11-10",
        },
    )
    assert result.status_code == 200, result.text
    updated = result.json()
    assert updated["case"]["draft_revision"] == lead["case"]["draft_revision"]
    assert client.get("/api/workspace/queue?as_of=2026-11-09").json()["items"] == []
    with app.state.store.transaction() as db:
        db.execute(
            "UPDATE cases SET stage='closed',disposition='unable_to_contact' WHERE id=?",
            (lead["case_id"],),
        )
    due = client.get("/api/workspace/queue?as_of=2026-11-10").json()["items"][0]
    assert due["stage"] == "closed"
    assert due["reconsideration_due"] is True
    assert due["outreach_policy"]["state"] == "do_not_contact"
    assert "retain the hold" in due["suggested_action"]
    assert (
        client.put(
            url,
            json={
                "expected_version": lead["case"]["version"],
                "state": "active",
                "reason": "Stale save",
            },
        ).status_code
        == 422
    )


def test_defer_requires_reason_and_date(client, app):
    lead = opened(client, app)
    url = "/api/cases/" + lead["case_id"] + "/outreach-policy"
    base = {"expected_version": lead["case"]["version"], "state": "deferred"}
    assert client.put(url, json={**base, "reason": "Wait"}).status_code == 422
    assert (
        client.put(url, json={**base, "reason": "  ", "review_on": "2026-11-10"}).status_code == 422
    )
    assert app.state.store.all("SELECT * FROM case_outreach_policy") == []


def test_recurring_observations_are_one_finding_and_absence_is_unknown(client, app):
    lead = opened(client, app)
    before = client.get("/api/cases/" + lead["case_id"]).json()["finding_history"]
    rows = observations()
    for row in rows:
        row["timestamp"] = "2026-11-05 01:02:03"
    import_rows(client, app, rows, name="next.csv")
    after = client.get("/api/cases/" + lead["case_id"]).json()["finding_history"]
    assert after["total"] == before["total"]
    assert any(
        item["state"] == "seen_again"
        and item["observations"] == 8
        and item["observation_days"] == 2
        for item in after["items"]
    )
    rows[0]["timestamp"] = "2026-11-06 01:02:03"
    rows[0]["version"] = "7.3.26"
    import_rows(client, app, rows, name="changed.csv")
    changed = client.get("/api/cases/" + lead["case_id"]).json()["finding_history"]
    assert changed["counts"]["changed"] >= 1
    assert changed["coverage"] == "unknown"
    assert "does not mean remediated" in changed["basis"]


def test_notification_link_and_new_eol_release_keep_distinct_conditions(client, app):
    lead = opened(client, app)
    store = app.state.store
    with store.transaction() as db:
        db.execute(
            """INSERT INTO reports(id,lead_id,entity_id,case_id,revision,created_at,path,sent_at)
          VALUES('historical-report',?,?,?,1,'2026-11-05T00:00:00Z','missing-synthetic-package','2026-11-05T00:00:00Z')""",
            (lead["id"], lead["id"], lead["case_id"]),
        )
        db.execute("UPDATE cases SET stage='notification_completed' WHERE id=?", (lead["case_id"],))
    rows = observations()
    for row in rows:
        row["timestamp"] = "2026-11-07 01:02:03"
        row["version"] = "7.4.0"
    import_rows(client, app, rows, name="later.csv")
    history = client.get("/api/cases/" + lead["case_id"]).json()["finding_history"]
    prior = next(item for item in history["items"] if item["finding"] == "eol-php:7.3")
    current = next(item for item in history["items"] if item["finding"] == "eol-php:7.4")
    assert prior["notifications"][0]["report_id"] == "historical-report"
    assert current["state"] == "new" and current["notifications"] == []
    assert store.one("SELECT count(*) n FROM cases")["n"] == 1


def test_workspace_missing_contact_does_not_hide_urgent_case(client, app):
    lead = opened(client, app)
    with app.state.store.transaction() as db:
        draft = json.loads(
            db.execute("SELECT draft FROM cases WHERE id=?", (lead["case_id"],)).fetchone()[0]
        )
        draft["cve_records"] = [{"id": "CVE-2026-1234", "severity": "CRITICAL", "kev": True}]
        db.execute(
            "UPDATE cases SET stage='pending_notification',draft=? WHERE id=?",
            (json.dumps(draft), lead["case_id"]),
        )
    item = client.get("/api/workspace/queue").json()["items"][0]
    assert item["urgency"] == "known_exploited"
    assert not item["contact_recorded"]
    assert item["suggested_action"] == "Find or review a suitable contact"


def test_new_case_inherits_hold_until_explicitly_changed(client, app):
    lead = opened(client, app)
    response = client.put(
        "/api/cases/" + lead["case_id"] + "/outreach-policy",
        json={
            "expected_version": lead["case"]["version"],
            "state": "do_not_contact",
            "reason": "IT requested no further contact",
        },
    )
    assert response.status_code == 200
    with app.state.store.transaction() as db:
        db.execute("UPDATE cases SET stage='closed' WHERE id=?", (lead["case_id"],))
    created = client.post("/api/cases", json={"entity_id": lead["id"]})
    assert created.status_code == 200, created.text
    assert created.json()["outreach_policy"]["state"] == "do_not_contact"
    assert created.json()["outreach_policy"]["reason"] == "IT requested no further contact"


def test_material_change_prompts_review_without_overriding_hold(client, app):
    lead = opened(client, app)
    response = client.put(
        "/api/cases/" + lead["case_id"] + "/outreach-policy",
        json={
            "expected_version": lead["case"]["version"],
            "state": "do_not_contact",
            "reason": "Review new exposures only",
        },
    )
    assert response.status_code == 200
    with app.state.store.transaction() as db:
        db.execute("UPDATE cases SET stage='closed' WHERE id=?", (lead["case_id"],))
    rows = observations()
    for row in rows:
        row["timestamp"] = "2026-11-07 01:02:03"
        row["version"] = "7.4.10"
    import_rows(client, app, rows, name="new-version.csv")
    item = client.get("/api/workspace/queue").json()["items"][0]
    assert item["material_change_review"] is True
    assert item["stage"] == "closed"
    assert item["outreach_policy"]["state"] == "do_not_contact"
    assert item["suggested_action"] == "Review changed findings; outreach remains on hold"
