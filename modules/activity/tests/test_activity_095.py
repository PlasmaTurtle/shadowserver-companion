"""Chronology retains recorded identity and has stable, bounded read-only pages."""

import json

from tests.support.workbench import app as app, client as client


def test_recorded_profile_survives_settings_change_and_read_does_not_write(client, app):
    store = app.state.store
    with store.transaction() as db:
        profile = json.loads(
            db.execute("SELECT value FROM settings WHERE key='profile'").fetchone()[0]
        )
        profile["analyst_name"] = "Original Operator"
        db.execute("UPDATE settings SET value=? WHERE key='profile'", (json.dumps(profile),))
        store.log(
            db, "reviewed", "100% retained evidence", metadata={"source_id": "fixture-source"}
        )
        profile["analyst_name"] = "Later Operator"
        db.execute("UPDATE settings SET value=? WHERE key='profile'", (json.dumps(profile),))
    before = store.one("SELECT count(*) n FROM events")["n"]
    response = client.get("/api/activity", params={"q": "100%"}).json()
    assert response["total"] == 1
    event = response["items"][0]
    assert event["actor"] == "Original Operator"
    assert event["metadata"]["source_id"] == "fixture-source"
    assert event["metadata"]["actor_basis"] == "configured_operator_profile"
    assert client.get("/api/activity", params={"q": "100_"}).json()["total"] == 0
    assert store.one("SELECT count(*) n FROM events")["n"] == before


def test_cursor_does_not_skip_older_rows_when_new_events_arrive(client, app):
    store = app.state.store
    with store.transaction() as db:
        for n in range(5):
            db.execute(
                "INSERT INTO events(action,detail,created_at) VALUES('legacy',?,'2026-11-01')",
                (f"Legacy {n}",),
            )
    first = client.get("/api/activity?limit=2&action=legacy").json()
    with store.transaction() as db:
        store.log(db, "legacy", "Newly recorded")
    second = client.get(
        "/api/activity", params={"limit": 2, "action": "legacy", "before": first["next_before"]}
    ).json()
    assert {r["id"] for r in first["items"]}.isdisjoint(r["id"] for r in second["items"])
    assert [r["detail"] for r in second["items"]] == ["Legacy 2", "Legacy 1"]
    assert all(not r["actor_recorded"] and r["actor"] == "" for r in second["items"])
    assert client.get("/api/activity?limit=201").status_code == 422
    assert client.get("/api/activity?before=0").status_code == 422


def test_undated_cases_are_not_due(client, app):
    from tests.support.workbench import import_rows

    import_rows(client, app)
    dashboard = client.get("/api/dashboard").json()
    assert dashboard["workflow"]["due"] == 0
    assert dashboard["units"]["workflow"] == "notification cases"
