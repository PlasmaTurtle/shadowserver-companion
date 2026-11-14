"""An analyst decides once; already-waiting duplicates retain their provenance."""

import json

import pytest

from attribution import EvidenceStore
from test_attribution_review import accept_payload, review_app
from test_workbench import csv_bytes, observations
from workbench.attribution_reconciliation import reconcile_backlog, reconcile_reviews


def waiting_report(app, client, *, day=3, hostname="remote2.example.com", port="443"):
    rows = [
        {
            **row,
            "hostname": hostname,
            "timestamp": f"2026-11-{day:02d} 01:02:03",
            "port": port,
        }
        for row in observations()[:4]
    ]
    content = csv_bytes(rows)
    imported = client.post(
        "/api/imports", files=[("files", (f"pending-{day}-{hostname}.csv", content, "text/csv"))]
    ).json()[0]
    app.state.intake.process(imported["id"])
    detail = client.get("/api/imports/" + imported["id"]).json()
    assert detail["status"] == "done", detail["error"]
    job = client.get("/api/groups/" + detail["groups"][0]["id"]).json()
    assert job["status"] == "review"
    return job, content


def approve(client, group):
    response = client.post("/api/groups/" + group["id"] + "/review", json=accept_payload(group))
    assert response.status_code == 200, response.text
    return response.json()


def test_approval_reconciles_waiting_repeat_and_preserves_original_result(review_app):
    app, client, original, state, _ = review_app
    waiting, content = waiting_report(app, client)
    old_result = waiting["attribution_result"]["result_id"]
    calls = list(state["calls"])
    # Even old jobs without detailed attempts must retain their result reference
    # for evidence export and workspace restore verification.
    with app.state.store.transaction() as db:
        db.execute("UPDATE jobs SET attempts='[]' WHERE id=?", (waiting["id"],))
    approval = approve(client, original)
    assert client.get("/api/reviews").json() == []
    assert state["calls"] == calls, "Reconciliation must not make external requests"
    assert len(app.state.store.all("SELECT * FROM attribution_reviews")) == 1
    detail = client.get("/api/groups/" + waiting["id"]).json()
    assert detail["status"] == "qualified"
    assert detail["reviews"] == [], "Reusing a decision is not another analyst decision"
    assert detail["attribution_result_id"] in {original["attribution_result_id"], old_result}
    assert any(attempt.get("result_id") == old_result for attempt in detail["attempts"])
    inherited = next(
        attempt
        for attempt in detail["attempts"]
        if attempt.get("reason") == "established_review_reconciled"
    )
    assert inherited["source_result_id"] == original["attribution_result_id"]
    with EvidenceStore(app.state.store.root / "attribution.sqlite3") as evidence:
        assert evidence.result(old_result)["status"] == "review"
    imported = client.get("/api/imports/" + waiting["import_id"]).json()
    assert imported["qualified"] == 1
    assert imported["groups_done"] == 1
    assert imported["message"] == "All groups processed"
    progress = json.loads(imported["config"])["intake_progress"]
    assert progress["associated_groups"] == 1
    assert progress["reused_groups"] == 1
    assert client.get("/api/imports/" + waiting["import_id"] + "/original").content == content
    assert app.state.store.one("SELECT count(*) n FROM leads")["n"] == 1
    assert app.state.store.one("SELECT sum(admitted) n FROM awareness_observations")["n"] == 8
    assert (
        app.state.store.one("SELECT entity_id FROM domain_groups")["entity_id"]
        == approval["lead_id"]
    )
    assert reconcile_reviews(app.state.intake, original["domain"]) == []
    assert not app.state.store.all("PRAGMA foreign_key_check")


@pytest.mark.parametrize("status", ["running", "error", "paused", "queued"])
def test_summary_refresh_preserves_import_lifecycle(review_app, status):
    app, client, original, _, _ = review_app
    waiting, _ = waiting_report(app, client)
    with app.state.store.transaction() as db:
        db.execute(
            "UPDATE imports SET status=?,stage='Original stage',message='Original progress',error='Original diagnostic' WHERE id=?",
            (status, waiting["import_id"]),
        )
    approve(client, original)
    imported = app.state.store.one("SELECT * FROM imports WHERE id=?", (waiting["import_id"],))
    assert imported["status"] == status
    assert imported["stage"] == "Original stage"
    assert imported["error"] == "Original diagnostic"
    assert imported["qualified"] == 1
    assert imported["message"] == (
        "All groups processed" if status == "queued" else "Original progress"
    )
    progress = json.loads(imported["config"])["intake_progress"]
    assert progress["associated_groups"] == 1 and progress["reused_groups"] == 1


@pytest.mark.parametrize("state", ["dismissed", "refresh", "refreshed", "deferred"])
def test_reconciliation_does_not_override_rejection_refresh_or_deferred(review_app, state):
    app, client, original, _, _ = review_app
    waiting, _ = waiting_report(app, client)
    if state == "dismissed":
        payload = {**accept_payload(waiting), "decision": "dismiss", "evidence_index": None}
        response = client.post("/api/groups/" + waiting["id"] + "/review", json=payload)
        assert response.status_code == 200, response.text
    else:
        with app.state.store.transaction() as db:
            if state == "refresh":
                db.execute("UPDATE jobs SET refresh_requested=1 WHERE id=?", (waiting["id"],))
            elif state == "refreshed":
                db.execute(
                    "UPDATE jobs SET attempts=? WHERE id=?",
                    (
                        json.dumps([{"reason": "explicit_attribution_refresh"}]),
                        waiting["id"],
                    ),
                )
            else:
                db.execute("UPDATE jobs SET status='deferred' WHERE id=?", (waiting["id"],))
    approve(client, original)
    expected = "review" if state in {"refresh", "refreshed"} else state
    assert (
        app.state.store.one("SELECT status FROM jobs WHERE id=?", (waiting["id"],))["status"]
        == expected
    )
    assert (
        app.state.store.one("SELECT qualified FROM imports WHERE id=?", (waiting["import_id"],))[
            "qualified"
        ]
        == 0
    )


def test_reconciliation_does_not_follow_shared_ip_into_another_domain(review_app):
    app, client, original, _, _ = review_app
    unrelated, _ = waiting_report(app, client, hostname="remote2.example.org")
    approve(client, original)
    assert [job["id"] for job in client.get("/api/reviews").json()] == [unrelated["id"]]
    assert app.state.store.one("SELECT count(*) n FROM leads")["n"] == 1


def test_reconciliation_rechecks_concurrent_analyst_decision(review_app, monkeypatch):
    import workbench.intake_reuse as reuse

    app, client, original, _, _ = review_app
    waiting, _ = waiting_report(app, client)
    recognize = reuse.recognize_group

    def concurrent_dismissal(*args, **kwargs):
        recognized = recognize(*args, **kwargs)
        with app.state.store.transaction() as db:
            db.execute("UPDATE jobs SET status='dismissed' WHERE id=?", (waiting["id"],))
        return recognized

    monkeypatch.setattr(reuse, "recognize_group", concurrent_dismissal)
    approve(client, original)
    job = app.state.store.one("SELECT * FROM jobs WHERE id=?", (waiting["id"],))
    assert job["status"] == "dismissed"
    assert job["attribution_result_id"] == waiting["attribution_result_id"]
    assert not any(
        attempt.get("reason") == "established_review_reconciled"
        for attempt in json.loads(job["attempts"])
    )


def test_reconciliation_leaves_conflicting_ownership_for_review(review_app, monkeypatch):
    import workbench.intake_reuse as reuse

    app, client, original, _, _ = review_app
    waiting, _ = waiting_report(app, client)
    recognize = reuse.recognize_group

    def conflicting_ownership(*args, **kwargs):
        return {**recognize(*args, **kwargs), "state": "review"}

    monkeypatch.setattr(reuse, "recognize_group", conflicting_ownership)
    approve(client, original)
    assert [job["id"] for job in client.get("/api/reviews").json()] == [waiting["id"]]


def replace_waiting_evidence(app, waiting, *, malformed=False):
    """Model a fresh same-address response from a different registrant."""
    from attribution.models import ResponseSnapshot

    with EvidenceStore(app.state.store.root / "attribution.sqlite3") as evidence:
        result = evidence.result(waiting["attribution_result_id"])
        partial = result["partial_evidence"][0]
        snapshot = evidence.snapshot(partial["snapshot_id"])
        record = snapshot.record()
        record["handle"] = "CHANGED-NETWORK"
        record["entities"][0]["handle"] = "CHANGED-REGISTRANT"
        record["entities"][0]["vcardArray"][1][0][3] = "Example Unrelated Organization"
        replacement = ResponseSnapshot.create(
            snapshot.requested_url,
            snapshot.source_url,
            200,
            snapshot.headers,
            json.dumps(record).encode(),
        )
        evidence.save_snapshot(replacement)
        partial["snapshot_id"] = "missing-response" if malformed else replacement.snapshot_id
        partial["retrieved_at"] = replacement.retrieved_at
        partial["match"]["entity_handle"] = "CHANGED-REGISTRANT"
        partial["match"]["value"] = "Example Unrelated Organization"
        with evidence._db:
            evidence._db.execute(
                "UPDATE results SET payload=? WHERE id=?",
                (json.dumps(result), result["result_id"]),
            )


@pytest.mark.parametrize("malformed", [False, True])
def test_changed_or_missing_saved_evidence_is_not_blanket_approved(review_app, malformed):
    app, client, original, _, _ = review_app
    waiting, _ = waiting_report(app, client)
    replace_waiting_evidence(app, waiting, malformed=malformed)
    approve(client, original)
    assert [job["id"] for job in client.get("/api/reviews").json()] == [waiting["id"]]
    assert (
        app.state.store.one("SELECT qualified FROM imports WHERE id=?", (waiting["import_id"],))[
            "qualified"
        ]
        == 0
    )
    assert len(app.state.store.all("SELECT * FROM attribution_reviews")) == 1


def prepare_legacy_backlog(app, client, original, monkeypatch):
    import workbench.attribution_approval as approval
    import workbench.intake_reuse as reuse

    approve(client, original)
    recognize = reuse.recognize_group

    def old_recognition(*args, **kwargs):
        return {**recognize(*args, **kwargs), "attribution": None, "candidate_indices": None}

    # Import through the old behavior that repeated registration-name reviews,
    # then repair the persisted queue with the current startup reconciler.
    with monkeypatch.context() as old:
        old.setattr(reuse, "recognize_group", old_recognition)
        old.setattr(approval, "reusable_review", lambda *args, **kwargs: None)
        first, _ = waiting_report(app, client, day=2)
        second, _ = waiting_report(app, client, day=3)
    return first, second


def test_backlog_repairs_existing_duplicates_without_another_decision(review_app, monkeypatch):
    app, client, original, state, _ = review_app
    waiting = prepare_legacy_backlog(app, client, original, monkeypatch)
    calls = list(state["calls"])
    exports = []
    monkeypatch.setattr(app.state.store, "export_all", lambda: exports.append(True))
    promoted = reconcile_backlog(app.state.intake)
    assert set(promoted) == {job["id"] for job in waiting}
    assert client.get("/api/reviews").json() == []
    assert state["calls"] == calls
    assert exports == [True]
    assert len(app.state.store.all("SELECT * FROM attribution_reviews")) == 1
    assert reconcile_backlog(app.state.intake) == []
    assert exports == [True]


@pytest.mark.parametrize("pause", ["stop", "maintenance"])
def test_backlog_respects_shutdown_and_maintenance(review_app, monkeypatch, pause):
    app, client, original, _, _ = review_app
    waiting = prepare_legacy_backlog(app, client, original, monkeypatch)
    event = app.state.intake.stop_event if pause == "stop" else app.state.store.maintenance
    event.set()
    try:
        assert reconcile_backlog(app.state.intake) == []
        assert {
            job["id"] for job in app.state.store.all("SELECT id FROM jobs WHERE status='review'")
        } == {job["id"] for job in waiting}
    finally:
        event.clear()


def test_worker_reconciles_existing_reviews_on_startup(review_app, monkeypatch):
    app, client, original, _, _ = review_app
    prepare_legacy_backlog(app, client, original, monkeypatch)
    intake = app.state.intake
    monkeypatch.setattr(intake.wake, "wait", lambda timeout: intake.stop_event.set())
    try:
        intake._loop()
        assert client.get("/api/reviews").json() == []
        assert len(app.state.store.all("SELECT * FROM attribution_reviews")) == 1
    finally:
        intake.stop_event.clear()
