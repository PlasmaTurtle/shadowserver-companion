"""A changed owner cannot inherit a lead qualified under the previous owner."""

from datetime import datetime, timedelta, timezone
import json

import pytest

from modules.accretion.components.qualification import Qualifier
from modules.accretion.components import qualification_reconciliation as reconciliation
from modules.attribution.tests.support.attribution_review import review_app
from modules.entities.components.ownership import OwnershipChanged
from modules.entities.tests.support.entity_lifecycle import setup_entities, plan_transfer, transfer
from modules.leads.tests.support.lead_queue import queue_import
from tests.support.workbench import app, client, observations


@pytest.mark.parametrize("stage", ["capture", "attributed", "evaluated"])
def test_ownership_transfer_requires_requalification_before_publication(
    client, app, monkeypatch, stage
):
    source, target = setup_entities(client, app)
    store = app.state.store
    original = store.one(
        "SELECT attribution FROM entity_domain_associations "
        "WHERE root_domain='example.com' AND entity_id=?",
        (source,),
    )
    old_result = json.loads(original["attribution"])["result_id"]
    original_entries = {row["id"] for row in store.all("SELECT id FROM entries")}
    plan = plan_transfer(client, source, target)
    moved = False

    def move_ownership():
        nonlocal moved
        if moved:
            return
        response = transfer(client, source, plan)
        assert response.status_code == 200, response.text
        moved = True

    if stage == "capture":
        capture = app.state.intake.capture

        def during_capture(*args, **kwargs):
            move_ownership()
            return capture(*args, **kwargs)

        monkeypatch.setattr(app.state.intake, "capture", during_capture)
    elif stage == "attributed":
        qualify = Qualifier.qualify

        def after_attribution(self, *args, **kwargs):
            result = qualify(self, *args, **kwargs)
            if not moved:
                assert result.lead.attribution["result_id"] == old_result
                assert result.lead.attribution["reuse"]["fresh_lookup"] is False
                move_ownership()
            return result

        monkeypatch.setattr(Qualifier, "qualify", after_attribution)
    else:
        evaluate = app.state.intake.evaluate_lead

        def after_evaluate(lead, **kwargs):
            result = evaluate(lead, **kwargs)
            if not moved:
                assert lead.attribution["result_id"] == old_result
                assert lead.attribution["reuse"]["fresh_lookup"] is False
                move_ownership()
            return result

        monkeypatch.setattr(app.state.intake, "evaluate_lead", after_evaluate)

    # A later-dated row is eligible for the new ownership episode. This avoids
    # the separate historical-date gate masking a stale proof authorization.
    stamp = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    receipt, _ = queue_import(
        client,
        app,
        [{**observations()[2], "timestamp": stamp, "version": "7.3.26"}],
        "ownership-race.csv",
    )
    assert moved
    job = store.one("SELECT * FROM jobs WHERE import_id=?", (receipt["id"],))
    assert job["status"] == "deferred", job
    assert job["error"] == "ownership_changed", job
    assert {row["id"] for row in store.all("SELECT id FROM entries")} == original_entries
    assert not store.all("SELECT * FROM lead_queue WHERE import_id=?", (receipt["id"],))
    current = store.one(
        "SELECT attribution,attribution_entry_id FROM entity_domain_associations "
        "WHERE root_domain='example.com' AND entity_id=?",
        (target,),
    )
    assert json.loads(current["attribution"]) == {}
    assert current["attribution_entry_id"] is None

    # Explicit retry re-runs qualification under the current owner and obtains
    # its own checked decision, while immutable provider responses may be cached.
    app.state.intake.retry_group(job["id"], job["attribution_result_id"])
    app.state.intake.process(receipt["id"])
    retried = store.one("SELECT * FROM jobs WHERE id=?", (job["id"],))
    assert retried["status"] == "qualified", retried
    assert retried["attribution_result_id"] != old_result
    current = store.one(
        "SELECT attribution FROM entity_domain_associations "
        "WHERE root_domain='example.com' AND entity_id=?",
        (target,),
    )
    proof = json.loads(current["attribution"])
    assert proof["result_id"] == retried["attribution_result_id"]
    assert not proof.get("reuse")
    assert not store.all("PRAGMA foreign_key_check")


def _waiting_review(app, client, *, root="example.com", ip="8.8.8.8"):
    stamp = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    receipt, _ = queue_import(
        client,
        app,
        [{**observations()[2], "hostname": "portal." + root, "ip": ip, "timestamp": stamp}],
        root + "-waiting.csv",
    )
    job = app.state.store.one("SELECT * FROM jobs WHERE import_id=?", (receipt["id"],))
    assert job["status"] == "review", job
    return job


def test_manual_approval_rechecks_owner_created_after_evaluate(review_app, monkeypatch):
    app, client, original, _, _ = review_app
    waiting = _waiting_review(app, client)
    store, intake = app.state.store, app.state.intake
    evaluate = intake.evaluate_lead
    concurrent = {}

    def after_evaluate(lead, **kwargs):
        result = evaluate(lead, **kwargs)
        if lead.report.id == waiting["import_id"] and not concurrent:
            # Model a second operator approving the original while this
            # explicit decision is between evaluation and publication.
            with monkeypatch.context() as interrupted:
                interrupted.setattr(reconciliation, "reconcile_reviews", lambda *a, **k: [])
                concurrent.update(
                    intake.review_group(
                        original["id"], original["attribution_result_id"], 0, "accept"
                    )
                )
            concurrent["entry_ids"] = {row["id"] for row in store.all("SELECT id FROM entries")}
        return result

    monkeypatch.setattr(intake, "evaluate_lead", after_evaluate)
    with pytest.raises(OwnershipChanged, match="Ownership changed"):
        intake.review_group(waiting["id"], waiting["attribution_result_id"], 0, "accept")
    assert concurrent["lead_id"]
    assert store.one("SELECT status FROM jobs WHERE id=?", (waiting["id"],))["status"] == "review"
    assert not store.all("SELECT * FROM attribution_reviews WHERE job_id=?", (waiting["id"],))
    assert {row["id"] for row in store.all("SELECT id FROM entries")} == concurrent["entry_ids"]
    assert not store.all("SELECT * FROM lead_queue WHERE import_id=?", (waiting["import_id"],))

    # A newly explicit decision can bind the now-current owner normally.
    accepted = intake.review_group(waiting["id"], waiting["attribution_result_id"], 0, "accept")
    assert accepted["lead_id"] == concurrent["lead_id"]
    assert (
        store.one("SELECT status FROM jobs WHERE id=?", (waiting["id"],))["status"] == "qualified"
    )


def test_reconciliation_rechecks_episode_when_owner_returns_after_evaluate(review_app, monkeypatch):
    app, client, original, _, _ = review_app
    waiting = _waiting_review(app, client)
    target_job = _waiting_review(app, client, root="unrelated.com", ip="1.1.1.1")
    store, intake = app.state.store, app.state.intake
    target = intake.review_group(
        target_job["id"], target_job["attribution_result_id"], 0, "accept"
    )["lead_id"]
    with monkeypatch.context() as interrupted:
        interrupted.setattr(reconciliation, "reconcile_reviews", lambda *a, **k: [])
        source = intake.review_group(
            original["id"], original["attribution_result_id"], 0, "accept"
        )["lead_id"]
    before = {row["id"] for row in store.all("SELECT id FROM entries")}
    plan = plan_transfer(client, source, target)
    evaluate = intake.evaluate_lead
    moved = False

    def after_evaluate(lead, **kwargs):
        nonlocal moved
        result = evaluate(lead, **kwargs)
        if lead.report.id == waiting["import_id"] and not moved:
            assert transfer(client, source, plan).status_code == 200
            returning = plan_transfer(client, target, source)
            assert transfer(client, target, returning).status_code == 200
            moved = True
        return result

    monkeypatch.setattr(intake, "evaluate_lead", after_evaluate)
    assert reconciliation.reconcile_reviews(intake, "example.com") == []
    assert moved
    assert (
        store.one("SELECT entity_id FROM domain_groups WHERE root_domain='example.com'")[
            "entity_id"
        ]
        == source
    )
    assert store.one("SELECT status FROM jobs WHERE id=?", (waiting["id"],))["status"] == "review"
    assert {row["id"] for row in store.all("SELECT id FROM entries")} == before
    assert not store.all("SELECT * FROM lead_queue WHERE import_id=?", (waiting["import_id"],))
    assert not store.all("SELECT * FROM attribution_reviews WHERE job_id=?", (waiting["id"],))
    assert not store.all("PRAGMA foreign_key_check")
