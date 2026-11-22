"""Real API corrections retain original evidence and separate unrelated owners."""

import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest
from tests.support.workbench import app, client, observations, ready
from modules.leads.tests.support.lead_queue import queue_import
from modules.leads.components.lead_queue import LeadQueue
from modules.entities.components.services.entity_lifecycle import EntityLifecycle

from modules.entities.tests.support.entity_lifecycle import (
    plan_transfer,
    setup_entities,
    transfer,
)


def snapshot(store):
    return {
        t: store.all("SELECT * FROM " + t)
        for t in (
            "cases",
            "case_entries",
            "case_groups",
            "reports",
            "section_validations",
            "entries",
            "awareness_findings",
            "awareness_observation_owners",
            "awareness_admission_events",
        )
    }


def test_reactivation_is_reasoned_exact_and_not_triggered_by_reimport(client, app):
    queue_import(client, app, [observations()[2]], "original.csv")
    store = app.state.store
    row = LeadQueue(store).list()[0]
    LeadQueue(store).disposition(row["id"], row["revision"], "dismissed")
    fid = store.one("SELECT id FROM awareness_findings")["id"]
    approved = store.all("SELECT * FROM awareness_admission_events")
    queue_import(
        client, app, [{**observations()[2], "timestamp": "2026-11-05 01:02:03"}], "repeat.csv"
    )
    assert LeadQueue(store).list() == []
    assert store.one("SELECT workflow FROM awareness_findings")["workflow"] == "ignored"
    endpoint = f"/api/entities/{row['entity_id']}/findings/{fid}/reactivation"
    review = client.get(endpoint)
    assert review.status_code == 200, review.text
    plan = review.json()
    body = {
        "expected_revision": plan["entity_revision"],
        "review_token": plan["review_token"],
        "reason": "Dismissed the finding by mistake; resume review",
    }
    before = store.all("SELECT * FROM awareness_admission_events")
    assert client.post(endpoint, json={**body, "reason": " "}).status_code == 422
    result = client.post(endpoint, json=body)
    assert result.status_code == 200, result.text
    assert store.all("SELECT * FROM awareness_admission_events") == before
    assert store.one("SELECT workflow FROM awareness_findings")["workflow"] == "unworked"
    pending = LeadQueue(store).list()
    assert len(pending) == 1 and pending[0]["can_start"]
    assert len(approved) > 0
    assert client.post(endpoint, json=body).status_code == 422
    case = LeadQueue(store).start(pending[0]["id"], pending[0]["revision"])
    assert (
        store.one("SELECT entity_id FROM cases WHERE id=?", (case["case_id"],))["entity_id"]
        == row["entity_id"]
    )
    assert not store.all("PRAGMA foreign_key_check")


def test_transfer_preserves_old_case_scope_and_creates_fresh_findings(client, app):
    source, target = setup_entities(client, app)
    store = app.state.store
    pending = next(r for r in LeadQueue(store).list() if r["entity_id"] == source)
    old_case = LeadQueue(store).start(pending["id"], pending["revision"])["case_id"]
    before = snapshot(store)
    plan = plan_transfer(client, source, target)
    assert [r["id"] for r in plan["retained_cases"]] == [old_case]
    assert transfer(client, source, plan).status_code == 200
    assert snapshot(store) == before
    assert (
        store.one("SELECT entity_id FROM domain_groups WHERE root_domain='example.com'")[
            "entity_id"
        ]
        == target
    )
    own = client.get(f"/api/entities/{target}").json()
    assert not any(g["root_domain"] == "example.com" for g in own["domain_groups"])
    assert (
        store.one(
            "SELECT attribution_entry_id FROM entity_domain_associations WHERE root_domain=? AND entity_id=?",
            ("example.com", target),
        )["attribution_entry_id"]
        is None
    )
    # A post-transfer observation obtains its own proof and starts a new workflow episode.
    stamp = (datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat()
    original_results = {
        row["attribution_result_id"] for row in store.all("SELECT attribution_result_id FROM jobs")
    }
    receipt, _ = queue_import(
        client,
        app,
        [{**observations()[2], "timestamp": stamp, "version": "7.3.26"}],
        "new-owner.csv",
    )
    job = store.one("SELECT * FROM jobs WHERE import_id=?", (receipt["id"],))
    assert job["status"] == "qualified"
    assert job["attribution_result_id"] not in original_results
    transferred = json.loads(
        store.one(
            "SELECT attribution FROM entity_domain_associations WHERE root_domain=? AND entity_id=?",
            ("example.com", target),
        )["attribution"]
    )
    # The current owner has a new checked decision. Its immutable RDAP response
    # may come from the source cache; that is not reuse of the old owner's proof.
    assert transferred["result_id"] == job["attribution_result_id"]
    assert not transferred.get("reuse")
    findings = store.all("SELECT * FROM awareness_findings WHERE condition='eol-php:7.3'")
    assert len(findings) == 3  # old owner, target's own initial domain, transferred domain
    moved = store.all(
        "SELECT f.* FROM awareness_findings f JOIN awareness_assets a ON a.id=f.asset_id WHERE a.hostname='mail.example.com'"
    )
    assert {r["entity_id"] for r in moved} == {source, target}
    assert len({r["id"] for r in moved}) == 2
    assert next(r for r in moved if r["entity_id"] == source)["workflow"] == "handled"
    assert next(r for r in moved if r["entity_id"] == target)["workflow"] == "unworked"
    assert store.one("SELECT * FROM cases WHERE id=?", (old_case,)) == before["cases"][0]
    current = next(r for r in LeadQueue(store).list() if r["entity_id"] == target)
    started = LeadQueue(store).start(current["id"], current["revision"])
    case_entries = store.all(
        "SELECT e.lead_id FROM case_entries ce JOIN entries e ON e.id=ce.entry_id WHERE ce.case_id=?",
        (started["case_id"],),
    )
    assert {r["lead_id"] for r in case_entries} == {target}
    assert not store.all("PRAGMA foreign_key_check")


def test_transfer_stale_review_collision_and_rollback(client, app, monkeypatch):
    source, target = setup_entities(client, app)
    store = app.state.store
    plan = plan_transfer(client, source, target)
    with store.transaction() as db:
        db.execute("UPDATE leads SET draft_revision=draft_revision+1 WHERE id=?", (target,))
    assert transfer(client, source, plan).status_code == 422
    fresh = plan_transfer(client, source, target)
    assert transfer(client, source, fresh, reason="").status_code == 422
    before = store.all("SELECT * FROM awareness_assets")
    original = store.log

    def fail(*args, **kwargs):
        raise RuntimeError("simulated journal failure")

    monkeypatch.setattr(store, "log", fail)
    with pytest.raises(RuntimeError, match="journal failure"):
        EntityLifecycle(store).transfer(
            source,
            fresh["hostname"],
            target,
            fresh["source_revision"],
            fresh["target_revision"],
            fresh["review_token"],
            "Test rollback",
        )
    assert store.all("SELECT * FROM awareness_assets") == before
    assert not store.all("SELECT * FROM entity_lifecycle_events")
    monkeypatch.setattr(store, "log", original)
    assert transfer(client, source, fresh).status_code == 200
    assert transfer(client, source, fresh).status_code == 422
    assert (
        client.get(
            f"/api/entities/{source}/ownership-transfer",
            params={"hostname": "example.com", "target_entity_id": target},
        ).status_code
        == 422
    )


def test_exact_hostname_transfer_and_historical_import_stays_unapproved(client, app):
    source, target = setup_entities(client, app)
    store = app.state.store
    plan = plan_transfer(client, source, target, "mail.example.com")
    assert plan["scope"] == "hostname"
    assert transfer(client, source, plan).status_code == 200
    assert (
        store.one("SELECT entity_id FROM domain_groups WHERE root_domain='example.com'")[
            "entity_id"
        ]
        == source
    )
    queue_import(
        client,
        app,
        [{**observations()[2], "timestamp": "2026-11-03 01:00:00", "version": "7.3.24"}],
        "old-dated.csv",
    )
    assert (
        store.one(
            "SELECT count(*) n FROM awareness_findings WHERE entity_id=? AND asset_id=(SELECT id FROM awareness_assets WHERE hostname='mail.example.com')",
            (target,),
        )["n"]
        == 0
    )
    assert (
        store.one(
            "SELECT count(*) n FROM entries WHERE lead_id=? AND hostname='mail.example.com'",
            (target,),
        )["n"]
        == 0
    )
    stamp = (datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat()
    queue_import(client, app, [{**observations()[2], "timestamp": stamp}], "host-new-owner.csv")
    current = next(r for r in LeadQueue(store).list() if r["entity_id"] == target)
    started = LeadQueue(store).start(current["id"], current["revision"])
    assert (
        store.one("SELECT entity_id FROM cases WHERE id=?", (started["case_id"],))["entity_id"]
        == target
    )
    assert store.one(
        "SELECT attribution_entry_id FROM entity_domain_associations WHERE root_domain=? AND entity_id=?",
        ("example.com", target),
    )["attribution_entry_id"]
    assert not store.all("PRAGMA foreign_key_check")


def test_transfer_then_business_merge_preserves_alias_history(client, app):
    source, target = setup_entities(client, app)
    store = app.state.store
    plan = plan_transfer(client, source, target)
    assert transfer(client, source, plan).status_code == 200
    a = client.get(f"/api/entities/{source}").json()
    b = client.get(f"/api/entities/{target}").json()
    response = client.post(
        f"/api/entities/{source}/merge",
        json={
            "target_id": target,
            "source_revision": a["entity_revision"],
            "target_revision": b["entity_revision"],
        },
    )
    assert response.status_code == 200, response.text
    detail = client.get(f"/api/entities/{target}").json()
    assert detail["awareness"]["observations"] == 2
    assert {r["entity_id"] for r in store.all("SELECT * FROM awareness_observation_owners")} == {
        source,
        target,
    }
    restored_proof = store.one(
        "SELECT attribution_entry_id FROM entity_domain_associations WHERE root_domain='example.com' AND entity_id=?",
        (target,),
    )
    assert restored_proof["attribution_entry_id"]
    opened = client.post(f"/api/leads/{target}/start")
    assert opened.status_code == 200, opened.text
    assert {
        r["root_domain"]
        for r in store.all(
            "SELECT root_domain FROM case_groups WHERE case_id=?", (opened.json()["case_id"],)
        )
    } == {"example.com", "unrelated.com"}
    assert not store.all("PRAGMA foreign_key_check")


def test_transfer_retains_certified_package_bytes_and_current_history_counts(client, app):
    from tests.support.workbench import ready
    import hashlib

    source, target = setup_entities(client, app)
    store = app.state.store
    pending = next(r for r in LeadQueue(store).list() if r["entity_id"] == source)
    LeadQueue(store).start(pending["id"], pending["revision"])
    ready(client, source)
    response = client.post(f"/api/leads/{source}/finalize")
    assert response.status_code == 200, response.text
    report = response.json()
    root = store.path(report["path"])
    artifacts = {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }
    before = snapshot(store)
    plan = plan_transfer(client, source, target)
    assert plan["retained_cases"][0]["certified_report_id"] == report["id"]
    assert transfer(client, source, plan).status_code == 200
    assert snapshot(store) == before
    assert artifacts == {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }
    source_detail = client.get(f"/api/entities/{source}").json()
    target_detail = client.get(f"/api/entities/{target}").json()
    assert source_detail["awareness"]["observations"] == 1
    assert target_detail["awareness"]["observations"] == 1
    assert len(source_detail["reports"]) == 1 and target_detail["reports"] == []


def test_reactivation_missing_pruned_source_rolls_back(client, app):
    queue_import(
        client, app, [observations()[2], {**observations()[2], "ip": "9.9.9.9"}], "initial.csv"
    )
    store = app.state.store
    row = LeadQueue(store).list()[0]
    LeadQueue(store).disposition(row["id"], row["revision"], "dismissed")
    finding = store.one("SELECT * FROM awareness_findings")
    endpoint = f"/api/entities/{row['entity_id']}/findings/{finding['id']}/reactivation"
    plan = client.get(endpoint).json()
    source = next(
        s
        for s in plan["sources"]
        if not store.one("SELECT id FROM entries WHERE id=?", (s["entry_id"],))
    )
    path = store.path(
        store.one("SELECT path FROM imports WHERE id=?", (source["import_id"],))["path"]
    )
    path.unlink()
    result = client.post(
        endpoint,
        json={
            "expected_revision": plan["entity_revision"],
            "review_token": plan["review_token"],
            "reason": "Review missing original",
        },
    )
    assert result.status_code == 422, result.text
    assert store.one("SELECT workflow FROM awareness_findings")["workflow"] == "ignored"
    assert not store.all("SELECT * FROM entity_lifecycle_events WHERE event_type='reactivation'")


def test_ownership_and_lifecycle_audit_reject_replace(client, app):
    import sqlite3

    source, target = setup_entities(client, app)
    store = app.state.store
    plan = plan_transfer(client, source, target)
    assert transfer(client, source, plan).status_code == 200
    for table in ("entity_lifecycle_events", "awareness_observation_owners"):
        before = store.all("SELECT * FROM " + table)
        row = before[0]
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            with store.transaction() as db:
                db.execute(
                    "INSERT OR REPLACE INTO "
                    + table
                    + " VALUES("
                    + ",".join("?" for _ in row)
                    + ")",
                    tuple(row.values()),
                )
        assert store.all("SELECT * FROM " + table) == before


@pytest.mark.parametrize("reported", ["2026-11-03 00:00:00", "", None])
def test_new_hostname_uses_root_history_and_cannot_bypass_review_on_retry(client, app, reported):
    from modules.accretion.components.awareness import associate
    from modules.entities.components.ownership import entry_context
    from modules.observatory.components.eclipse import Eclipse

    source, target = setup_entities(client, app)
    store = app.state.store
    assert transfer(client, source, plan_transfer(client, source, target)).status_code == 200
    before = snapshot(store)
    stamp = (
        reported
        if reported is not None
        else (datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat()
    )
    receipt, _ = queue_import(
        client,
        app,
        [{**observations()[2], "hostname": "new.example.com", "timestamp": stamp}],
        "new-host.csv",
    )
    rows = store.all(
        "SELECT f.* FROM awareness_findings f JOIN awareness_assets a ON a.id=f.asset_id WHERE a.hostname='new.example.com'"
    )
    if reported is None:
        assert rows
        assert all(
            r["admitted"] and r["entity_id"] == target and r["ownership_episode"] for r in rows
        )
        assert store.one(
            "SELECT id FROM entries WHERE lead_id=? AND hostname='new.example.com'", (target,)
        )
        return
    # Qualify holds historical/undated rows before any canonical association.
    assert rows == []
    assert snapshot(store) == before
    assert not store.one(
        "SELECT id FROM entries WHERE lead_id=? AND hostname='new.example.com'", (target,)
    )
    job = store.one("SELECT * FROM jobs WHERE import_id=?", (receipt["id"],))
    assert job["status"] == "deferred"
    entry = json.loads(job["payload"])[0]
    retained = store.dark_matter.get(entry["normalized"]["observation_ref"])
    assert retained["outcome"] == "deferred" and retained["reason"] == "association_conflict"
    assert retained["record_id"] == entry["normalized"]["observation_ref"]
    assert not store.one("SELECT 1 FROM awareness_sources WHERE import_id=?", (receipt["id"],))
    imported = store.one("SELECT * FROM imports WHERE id=?", (receipt["id"],))
    assert (
        hashlib.sha256(store.path(imported["path"]).read_bytes()).hexdigest() == imported["sha256"]
    )
    with store.read_snapshot() as db:
        context = entry_context(db, entry)
    assert context["historical_review"]
    assert context["entity_id"] == (source if reported else None)
    dark = client.get("/api/dark-matter?q=new.example.com").json()["items"]
    assert len(dark) == 1
    detail = Eclipse(store).observation(dark[0]["record_id"])
    for item in (dark[0], detail):
        assert item.get("entity_id") is None
        assert item.get("recorded_entity_id") is None
        assert item.get("current_entity_id") is None
    assert snapshot(store) == before  # Opening retained evidence performs no writes.
    calls = len(app.state.fake.calls)
    app.state.intake.retry_group(job["id"], job["attribution_result_id"])
    app.state.intake.process(receipt["id"])
    assert store.one("SELECT status,payload FROM jobs WHERE id=?", (job["id"],)) == {
        "status": "deferred",
        "payload": job["payload"],
    }
    assert len(app.state.fake.calls) == calls
    assert snapshot(store) == before
    # A lower-level caller still cannot promote historical evidence by claiming qualification.
    with store.transaction() as db:
        result = associate(
            db,
            entry,
            import_id=receipt["id"],
            source_sha256=imported["sha256"],
            entity_id=target,
            admitted=True,
        )
    assert result["entity_id"] == (source if reported else None)
    assert not store.one(
        "SELECT 1 FROM awareness_admission_events WHERE import_id=? AND state='admitted'",
        (receipt["id"],),
    )
    owner = store.one(
        "SELECT * FROM awareness_observation_owners WHERE observation_id=?",
        (result["observation_id"],),
    )
    assert owner["entity_id"] == (source if reported else None)
    assert owner["basis"] == "ownership_history_review"
    dark = client.get("/api/dark-matter?q=new.example.com").json()["items"]
    assert len(dark) == 1
    assert dark[0]["record_id"] == retained["record_id"]
    assert dark[0]["raw_fields"] == retained["raw_fields"]
    assert dark[0].get("entity_id") is None
    assert dark[0].get("current_entity_id") is None


def test_lifecycle_identity_columns_reject_null(client, app):
    import sqlite3

    source, target = setup_entities(client, app)
    store = app.state.store
    plan = plan_transfer(client, source, target)
    assert transfer(client, source, plan).status_code == 200
    for table, key in (
        ("entity_lifecycle_events", "id"),
        ("awareness_observation_owners", "observation_id"),
    ):
        row = store.one("SELECT * FROM " + table)
        row[key] = None
        with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
            with store.transaction() as db:
                db.execute(
                    "INSERT INTO " + table + " VALUES(" + ",".join("?" for _ in row) + ")",
                    tuple(row.values()),
                )
