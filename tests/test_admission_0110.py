"""Condition qualification is exact, monotonic and backed by source decisions."""

from contextlib import closing
import hashlib
import json
import sqlite3

import pytest

from test_workbench import app, client
from test_awareness_0994 import ingest
from workbench.awareness import associate, finding_ids
from workbench.awareness_history import entity_history
from workbench.awareness_admission_migration import schema
from workbench.awareness_admission import validate
from workbench.lead_queue import _awareness_scope
from schema_helpers import schema_snapshot


def _entry(store):
    return json.loads(
        store.one("SELECT payload FROM entries ORDER BY observed_at DESC LIMIT 1")["payload"]
    )


def _history(store):
    entity = store.one("SELECT id FROM leads")["id"]
    with store.read_snapshot() as db:
        return entity_history(db, entity)


def _old_snapshot(store):
    with closing(store.connect()) as source:
        return schema_snapshot(source, 16)


def test_condition_promotion_does_not_admit_another_conditions_prior_measurement(client, app):
    receipt = ingest(
        client, app, tag="CVE-2024-12345", timestamp="2026-11-01 00:00:00", version="7.3.25"
    )
    store = app.state.store
    original = _entry(store)
    original["normalized"].pop("observation_ref", None)
    original["source"]["row"] = 99
    original["source"]["fields"]["tag"] = "CVE-2024-12345;CVE-2024-23456"
    with store.transaction() as db:
        associate(
            db, original, import_id=receipt["id"], admitted=False, reason="CVE-B not yet qualified"
        )
    assert (
        store.one("SELECT admitted FROM awareness_findings WHERE condition='CVE-2024-23456'")[
            "admitted"
        ]
        == 0
    )
    later = json.loads(json.dumps(original))
    later["source"]["row"] = 100
    later["source"]["fields"].update(
        tag="CVE-2024-23456", timestamp="2026-11-02 00:00:00", version="8.0.0"
    )
    later["normalized"]["raw_version"] = "8.0.0"
    with store.transaction() as db:
        associate(db, later, import_id=receipt["id"], admitted=True)
    item = next(item for item in _history(store)["items"] if item["finding"] == "CVE-2024-23456")
    assert item["first_observed"] == "2026-11-02T00:00:00+00:00"
    assert item["observations"] == item["observation_days"] == 1
    assert item["reported_observation_count"] == 2
    assert item["observed_only_observation_count"] == 1
    assert item["versions"] == ["8.0.0"]
    assert item["state"] == "new"
    with store.read_snapshot() as db:
        scope = _awareness_scope(db, [later])
    assert scope["total"] == 2 and scope["approved"] == scope["days"] == 1


def test_independent_condition_approvals_preserve_one_measurement_and_assertions(client, app):
    receipt = ingest(client, app, tag="CVE-2024-12345")
    store = app.state.store
    entry = _entry(store)
    entry["normalized"].pop("observation_ref", None)
    entry["source"]["row"] = 99
    entry["source"]["fields"]["tag"] = "CVE-2024-23456"
    with store.transaction() as db:
        associate(db, entry, import_id=receipt["id"], admitted=False, reason="pending")
        associate(db, entry, import_id=receipt["id"], admitted=True)
        associate(db, entry, import_id=receipt["id"], admitted=True)
        associate(db, entry, import_id=receipt["id"], admitted=False, reason="pending")
    assert len(store.all("SELECT id FROM awareness_observations")) == 1
    assert [row["admission_state"] for row in store.all("SELECT * FROM awareness_memberships")] == [
        "admitted",
        "admitted",
    ]
    fid = finding_ids(entry)[0]
    events = store.all("SELECT state FROM awareness_admission_events WHERE finding_id=?", (fid,))
    assert sorted(row["state"] for row in events) == ["admitted", "observed"]
    assert len(store.all("SELECT * FROM awareness_sources")) == 2


def test_decisions_and_projection_reject_mutation_and_wrong_sources(client, app):
    ingest(client, app)
    store = app.state.store
    event = store.one("SELECT * FROM awareness_admission_events WHERE state='admitted'")
    for sql in (
        "UPDATE awareness_admission_events SET actor='changed'",
        "DELETE FROM awareness_admission_events",
        "UPDATE awareness_memberships SET admission_state='observed'",
    ):
        with pytest.raises(sqlite3.IntegrityError), store.transaction() as db:
            db.execute(sql)
    with pytest.raises(sqlite3.IntegrityError), store.transaction() as db:
        db.execute(
            "INSERT INTO awareness_admission_events SELECT 'bad',finding_id,observation_id,import_id,'missing',state,contract_version,policy_version,decision_at,recorded_at,authority_kind,authority_ref,actor,reason,evidence_ref,facts_json FROM awareness_admission_events WHERE id=?",
            (event["id"],),
        )
    with pytest.raises(sqlite3.IntegrityError), store.transaction() as db:
        db.execute(
            "INSERT OR REPLACE INTO awareness_admission_events SELECT id,finding_id,observation_id,import_id,source_key,state,contract_version,policy_version,decision_at,recorded_at,authority_kind,authority_ref,'rewritten',reason,evidence_ref,facts_json FROM awareness_admission_events WHERE id=?",
            (event["id"],),
        )
    with pytest.raises(sqlite3.IntegrityError), store.transaction() as db:
        db.execute(
            "INSERT OR REPLACE INTO awareness_admission_events SELECT 'replacement-id',finding_id,observation_id,import_id,source_key,state,contract_version,policy_version,decision_at,recorded_at,authority_kind,authority_ref,actor,reason,evidence_ref,facts_json FROM awareness_admission_events WHERE id=?",
            (event["id"],),
        )
    with pytest.raises(sqlite3.IntegrityError), store.transaction() as db:
        db.execute(
            "INSERT OR REPLACE INTO awareness_memberships SELECT finding_id,observation_id,'observed',admission_projection_version FROM awareness_memberships"
        )
    assert (
        store.one("SELECT state FROM awareness_admission_events WHERE id=?", (event["id"],))[
            "state"
        ]
        == "admitted"
    )


def test_legacy_exact_authority_preserves_bytes_ids_and_unknown_aggregate(client, app):
    ingest(client, app, tag="CVE-2024-12345")
    store = app.state.store
    originals = {
        row["path"]: hashlib.sha256(store.path(row["path"]).read_bytes()).hexdigest()
        for row in store.all("SELECT path FROM imports")
    }
    with closing(_old_snapshot(store)) as db:
        identities = {
            table: [row[0] for row in db.execute("SELECT id FROM " + table)]
            for table in (
                "awareness_assets",
                "awareness_observations",
                "awareness_findings",
                "entries",
            )
        }
        schema(db)
        assert (
            db.execute("SELECT admission_state FROM awareness_memberships").fetchone()[0]
            == "admitted"
        )
        event = db.execute("SELECT * FROM awareness_admission_events").fetchone()
        assert event["authority_kind"] == "legacy_retained_qualified_entry"
        assert event["decision_at"] == "" and event["actor"] == "not_recorded"
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
        assert all(
            ids == [row[0] for row in db.execute("SELECT id FROM " + table)]
            for table, ids in identities.items()
        )
    with closing(_old_snapshot(store)) as db:
        # A compacted source still exists, but its qualified entry no longer does.
        db.execute("UPDATE awareness_sources SET entry_id='retired-entry'")
        db.execute("UPDATE awareness_findings SET workflow='handled',handled_case_id='legacy-case'")
        before = dict(db.execute("SELECT * FROM awareness_findings").fetchone())
        schema(db)
        row = db.execute("SELECT * FROM awareness_findings").fetchone()
        assert row["admitted"] == 1 and row["workflow"] == "handled"
        assert row["first_seen"] == before["first_seen"] and row["last_seen"] == before["last_seen"]
        entity = db.execute("SELECT id FROM leads").fetchone()[0]
        item = entity_history(db, entity)["items"][0]
        assert item["state"] == "qualification_unknown" and not item["material_change"]
        assert item["approved_observation_count"] == 0
        assert item["legacy_unknown_observation_count"] == 1
        assert item["latest_version"] == "" and item["versions"] == []
        entry = _entry(store)
        receipt = db.execute("SELECT id FROM imports").fetchone()[0]
        associate(db, entry, import_id=receipt, admitted=False, reason="retry")
        assert (
            db.execute("SELECT admission_state FROM awareness_memberships").fetchone()[0]
            == "legacy_unknown"
        )
    assert all(
        hashlib.sha256(store.path(path).read_bytes()).hexdigest() == digest
        for path, digest in originals.items()
    )


def test_migration_rollback_leaves_legacy_projection_retryable(client, app):
    ingest(client, app)
    with closing(_old_snapshot(app.state.store)) as db:
        db.execute("BEGIN")
        schema(db)
        db.rollback()
        assert "admission_state" not in {
            row[1] for row in db.execute("PRAGMA table_info(awareness_memberships)")
        }
        schema(db)
        assert (
            db.execute("SELECT admission_state FROM awareness_memberships").fetchone()[0]
            == "admitted"
        )


def test_approved_condition_facts_survive_representative_source_replacement(client, app):
    receipt = ingest(client, app, tag="CVE-2024-12345", version="7.3.25")
    store = app.state.store
    entry = _entry(store)
    # A later condition interpretation of the same retained source must not
    # rewrite the version that was approved for the first condition.
    entry["source"]["fields"].update(tag="CVE-2024-23456", version="8.0.0")
    entry["normalized"]["raw_version"] = "8.0.0"
    with store.transaction() as db:
        associate(db, entry, import_id=receipt["id"], admitted=True)
    items = {item["finding"]: item for item in _history(store)["items"]}
    assert items["CVE-2024-12345"]["versions"] == ["7.3.25"]
    assert items["CVE-2024-23456"]["versions"] == ["8.0.0"]
    assert len(store.all("SELECT id FROM awareness_observations")) == 1


def test_health_rejects_source_mismatch_that_independent_foreign_keys_allow(client, app):
    ingest(client, app, timestamp="2026-11-01 00:00:00")
    ingest(client, app, timestamp="2026-11-02 00:00:00")
    store = app.state.store
    with store.read_snapshot() as db:
        assert validate(db)["admitted"] == 2
    events = store.all(
        "SELECT * FROM awareness_admission_events WHERE state='admitted' ORDER BY observation_id"
    )
    with pytest.raises(ValueError, match="source_mismatch"), store.transaction() as db:
        db.execute("DROP TRIGGER awareness_admission_immutable_update")
        db.execute(
            "UPDATE awareness_admission_events SET import_id=?,source_key=? WHERE id=?",
            (events[-1]["import_id"], events[-1]["source_key"], events[0]["id"]),
        )
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
        validate(db)
    with store.read_snapshot() as db:
        assert validate(db)["admitted"] == 2


def test_dark_matter_counts_unknown_separately_and_preserves_broad_qualification(client, app):
    from workbench.dark_matter import _canonical_browse
    from workbench.awareness import counts
    from workbench.repositories.entity_awareness import detail

    ingest(client, app)
    store = app.state.store
    with closing(_old_snapshot(store)) as db:
        db.execute("UPDATE awareness_sources SET entry_id='retired-entry'")
        schema(db)
        receipt = db.execute("SELECT id FROM imports").fetchone()[0]
        entry = _entry(store)
        entry["normalized"].pop("observation_ref", None)
        for row, version, approved in ((99, "8.0.0", False), (100, "9.0.0", True)):
            entry["source"]["row"] = row
            entry["source"]["fields"]["version"] = version
            entry["normalized"]["raw_version"] = version
            associate(db, entry, import_id=receipt, admitted=approved)
        result = _canonical_browse(db)
        assert result["total"] == 2
        assert result["counts"]["observations"] == 3
        assert (
            result["counts"]["lead"]
            == result["counts"]["dark_matter"]
            == result["counts"]["qualification_unknown"]
            == 1
        )
        assert result["counts"]["known_aggregate_qualified_observations"] == 2
        assert {item["disposition"] for item in result["items"]} == {
            "dark_matter",
            "qualification_unknown",
        }
        unknown = next(
            item for item in result["items"] if item["disposition"] == "qualification_unknown"
        )
        assert (
            unknown["known_aggregate_admitted"] and unknown["admission_state"] == "legacy_unknown"
        )
        assert "unavailable" in unknown["reason_label"]
        summary = counts(db)
        assert summary["observations"] == 3
        assert (
            summary["approved_observations"]
            == summary["dark_matter_observations"]
            == summary["legacy_unknown_observation_count"]
            == 1
        )
        assert summary["known_aggregate_qualified_observations"] == 2
        entity_id = db.execute("SELECT id FROM leads").fetchone()[0]
        entity_summary = detail(db, entity_id)["awareness"]
        assert entity_summary["observations"] == 3
        assert (
            entity_summary["approved_observations"]
            == entity_summary["dark_matter_observations"]
            == entity_summary["legacy_unknown_observation_count"]
            == 1
        )
