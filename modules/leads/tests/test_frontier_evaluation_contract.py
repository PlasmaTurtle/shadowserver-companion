"""Pending work is evaluated before publication, including retained findings."""

import json

from tests.support.workbench import app, client, observations
from modules.accretion.components import accretion, awareness, evaluation, intake_filter
from modules.accretion.tests.support.scoring import vetted
from modules.leads.components.lead_frontier import preview_current
from modules.leads.tests.support.lead_queue import ingest, queue_import


def test_evaluate_combines_pending_findings_before_associate(client, app, monkeypatch):
    store = app.state.store
    calls = []
    original = accretion.score_lead

    def score(entries, **kwargs):
        calls.append(
            {
                "versions": {entry["source"]["fields"]["version"] for entry in entries},
                "canonical_rows": store.one("SELECT count(*) n FROM entries")["n"],
                "phase": json.loads(
                    store.one("SELECT config FROM imports ORDER BY rowid DESC LIMIT 1")["config"]
                )["intake_progress"]["phase"],
            }
        )
        return original(entries, **kwargs)

    monkeypatch.setattr(accretion, "score_lead", score)
    ingest(client, app, version="7.3.25")
    current = ingest(client, app, version="8.0.1")
    assert calls == [
        {"versions": {"7.3.25"}, "canonical_rows": 0, "phase": "evaluate"},
        {"versions": {"7.3.25", "8.0.1"}, "canonical_rows": 1, "phase": "evaluate"},
    ]
    assert len(json.loads(current["payload"])) == 2
    assert json.loads(current["intake_score"])["evaluation_scope"]["fingerprint"]


def test_finding_change_after_evaluate_prevents_stale_association(client, app, monkeypatch):
    store, intake = app.state.store, app.state.intake
    first = ingest(client, app, version="7.3.25")
    old_finding = store.one("SELECT id FROM awareness_findings")["id"]
    original = intake.evaluate_lead

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        with store.transaction() as db:
            db.execute(
                "UPDATE awareness_findings SET workflow='ignored' WHERE id=?", (old_finding,)
            )
        return result

    monkeypatch.setattr(intake, "evaluate_lead", changed)
    result, _ = queue_import(
        client, app, [{**observations()[2], "version": "8.0.1"}], "scan_http_vulnerable.csv"
    )
    imported = store.one("SELECT * FROM imports WHERE id=?", (result["id"],))
    assert imported["status"] == "error"
    assert "changed after Evaluate" in imported["error"]
    assert (
        store.one("SELECT status FROM jobs WHERE import_id=?", (result["id"],))["status"]
        == "pending"
    )
    assert store.one("SELECT count(*) n FROM entries")["n"] == 1
    assert (
        store.one("SELECT payload FROM lead_queue WHERE id=?", (first["id"],))["payload"]
        == first["payload"]
    )


def test_ignored_cve_does_not_score_or_rewrite_mixed_source_row(client, app, monkeypatch):
    high, low = "CVE-2026-1234", "CVE-2026-2345"
    tag = f"{high};{low}"
    records = {
        high: vetted(high, score=10, kev=True, epss=1),
        low: vetted(low, score=4, epss=0),
    }
    monkeypatch.setattr(intake_filter, "vet_cves", lambda *args, **kwargs: records)
    queued = ingest(client, app, tag=tag)
    store = app.state.store
    assert json.loads(queued["intake_score"])["urgency"] == 90
    source = store.one("SELECT payload FROM entries")["payload"]
    assert json.loads(source)["source"]["fields"]["tag"] == tag
    ignored = store.one("SELECT id FROM awareness_findings WHERE condition=?", (high,))["id"]

    with store.transaction() as db:
        awareness.ignore_findings(db, [ignored])
        evaluation.evaluate_pending(db, queued["id"])

    current = store.one("SELECT * FROM lead_queue WHERE id=?", (queued["id"],))
    score = json.loads(current["intake_score"])
    assert score["urgency"] == 16
    assert score["strongest_finding"]["id"] == low
    assert [record["id"] for record in score["cves"]] == [low]
    entry = json.loads(current["payload"])[0]
    assert entry["normalized"]["active_conditions"] == [low]
    assert entry["source"]["fields"]["tag"] == tag
    assert store.one("SELECT payload FROM entries")["payload"] == source


def test_old_evaluation_version_refreshes_once_for_unchanged_scope(client, app, monkeypatch):
    queued = ingest(client, app)
    store = app.state.store
    original_score = json.loads(queued["intake_score"])
    cached = json.loads(queued["intake_score"])
    with store.transaction() as db:
        scope = preview_current(db, queued["id"])
        cached["evaluation_scope"] = {"version": 1, "fingerprint": scope["fingerprint"]}
        cached["urgency"] = -1
        db.execute(
            "UPDATE lead_queue SET intake_score=? WHERE id=?",
            (json.dumps(cached), queued["id"]),
        )

    calls = []
    original = accretion.score_lead

    def score(entries, **kwargs):
        calls.append(entries)
        return original(entries, **kwargs)

    monkeypatch.setattr(accretion, "score_lead", score)
    with store.transaction() as db:
        evaluation.evaluate_pending(db, queued["id"])
    refreshed = store.one("SELECT intake_score FROM lead_queue WHERE id=?", (queued["id"],))
    result = json.loads(refreshed["intake_score"])
    assert len(calls) == 1
    assert result["evaluation_scope"] == {
        "version": evaluation.VERSION,
        "fingerprint": cached["evaluation_scope"]["fingerprint"],
    }
    assert result["urgency"] == original_score["urgency"]

    with store.transaction() as db:
        evaluation.evaluate_pending(db, queued["id"])
    assert len(calls) == 1
    assert store.one("SELECT intake_score FROM lead_queue WHERE id=?", (queued["id"],)) == refreshed


def test_newer_rejected_cve_snapshot_cannot_revive_reported_severity(client, app, monkeypatch):
    withdrawn, active = "CVE-2026-1234", "CVE-2026-2345"
    old = vetted(withdrawn, score=10, epss=0)
    old["captured_at"] = "2026-11-10T00:00:00Z"
    monkeypatch.setattr(intake_filter, "vet_cves", lambda *args, **kwargs: {withdrawn: old})
    first = ingest(client, app, tag=withdrawn, hostname="mail.example.com", severity="critical")
    assert json.loads(first["intake_score"])["urgency"] == 40
    store = app.state.store
    source = store.one("SELECT id,payload FROM entries")

    rejected = vetted(withdrawn, status="rejected", score=None, epss=0)
    critical = vetted(active, score=9, epss=0)
    for record in (rejected, critical):
        record["captured_at"] = "2026-11-12T00:00:00Z"
    records = {withdrawn: rejected, active: critical}
    monkeypatch.setattr(intake_filter, "vet_cves", lambda *args, **kwargs: records)
    current = ingest(
        client, app, tag=f"{withdrawn};{active}", hostname="web.example.com", severity=""
    )
    score = json.loads(current["intake_score"])
    assert score["urgency"] == 36
    assert score["strongest_finding"]["id"] == active
    assert [(record["id"], record["status"]) for record in score["cves"]] == [
        (withdrawn, "rejected"),
        (active, "available"),
    ]
    assert len(json.loads(current["payload"])) == 2
    assert (
        store.one("SELECT payload FROM entries WHERE id=?", (source["id"],))["payload"]
        == (source["payload"])
    )
