"""Bounded read work and recoverable, cross-connection analytical projections."""

from contextlib import closing
import json
import sqlite3
import subprocess
import sys

import pytest

from workbench import analytical_index
from workbench.contact_outcomes import contact_summaries, contact_summary
from workbench.eclipse import Eclipse
from workbench.observatory_view import _base, _revision
from workbench.planner_maintenance import run, status
from workbench.store import Store
from workbench.workspace_queue import workspace_queue
from test_eclipse import base
from test_observatory_canonical_0994 import add
from test_workbench import app, client, import_rows, observations


def _copy(db, table, row, **changes):
    value = {**row, **changes}
    db.execute(
        f"INSERT INTO {table}("
        + ",".join(value)
        + ") VALUES("
        + ",".join("?" for _ in value)
        + ")",
        tuple(value.values()),
    )


def _measure(store, monkeypatch, call):
    original = store.connect
    statements, instructions = [], []

    def connect():
        db = original()
        db.set_trace_callback(statements.append)
        db.set_progress_handler(lambda: instructions.append(1) or 0, 100)
        return db

    with monkeypatch.context() as patch:
        patch.setattr(store, "connect", connect)
        result = call()
    reads = [sql for sql in statements if sql.lstrip().upper().startswith(("SELECT", "WITH"))]
    assert not any(
        sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for sql in statements
    )
    return result, len(reads), len(instructions) * 100


def test_workspace_batches_contacts_and_skips_closed_drafts(client, app, monkeypatch):
    import_rows(client, app, [observations()[2]])
    store = app.state.store
    entity = store.one("SELECT * FROM leads")
    case = store.one("SELECT * FROM cases")
    measurements = []
    for size in (20, 100):
        start = store.one("SELECT count(*) n FROM cases")["n"]
        with store.transaction() as db:
            for i in range(start, size):
                identity = f"perf-entity-{i}"
                _copy(db, "leads", entity, id=identity, domain=f"entity{i}.example")
                _copy(db, "cases", case, id=f"perf-case-{i}", entity_id=identity)
        result, count, work = _measure(
            store, monkeypatch, lambda: workspace_queue(store, limit=1000)
        )
        assert result["total"] == size
        measurements.append(count)
    assert measurements[0] == measurements[1], measurements
    assert measurements[1] < 35, measurements
    expected = result
    with store.transaction() as db:
        for i in range(500):
            _copy(
                db,
                "cases",
                case,
                id=f"closed-{i}",
                stage="closed",
                updated_at="2000-01-01",
                draft=json.dumps({"historical_padding": "x" * 10000}),
            )
    result, count, work = _measure(store, monkeypatch, lambda: workspace_queue(store, limit=1000))
    assert result == expected
    assert count == measurements[-1]
    with store.read_snapshot() as db:
        bulk = contact_summaries(store, [entity["id"]], db=db)
        assert bulk[entity["id"]] == contact_summary(store, entity["id"], db=db)


def test_detail_work_is_independent_of_unrelated_observation_history(tmp_path, monkeypatch):
    store = Store(tmp_path / "workspace")
    chosen = add(store, base())
    unrelated = add(store, base(hostname="unrelated.example.net", ip="1.1.1.1"))
    event = store.one(
        "SELECT * FROM awareness_observations WHERE id=?", (unrelated["observation_id"],)
    )
    eclipse = Eclipse(store)
    before, queries, work = _measure(
        store, monkeypatch, lambda: eclipse.observation(chosen["observation_id"])
    )
    with store.transaction() as db:
        for i in range(3000):
            _copy(db, "awareness_observations", event, id=f"unrelated-history-{i}")
    after, later_queries, later_work = _measure(
        store, monkeypatch, lambda: eclipse.observation(chosen["observation_id"])
    )
    assert after == before
    assert later_queries == queries
    assert later_work < work * 1.3 + 2000, (work, later_work)
    assert later_work < 15000, later_work


def test_incremental_counters_reconcile_and_rebuild_without_evidence_changes(tmp_path):
    store = Store(tmp_path / "workspace")
    first = add(store, base(tag="CVE-2026-10001;CVE-2026-10002"))
    add(store, base(timestamp="2026-11-05T01:02:03Z"), admitted=False)
    tables = (
        "awareness_observations",
        "awareness_memberships",
        "awareness_findings",
        "awareness_sources",
    )
    with store.read_snapshot() as db:
        assert analytical_index.reconcile(db)["healthy"]
        facts = {
            table: [tuple(row) for row in db.execute("SELECT * FROM " + table)] for table in tables
        }
        rows = analytical_index.finding_stats(db)
        assert sum(r["approved_observation_count"] for r in rows.values()) == 2
    with store.transaction() as db:
        db.execute("UPDATE analytical_density_days SET approved=approved+10")
    with store.read_snapshot() as db:
        assert not analytical_index.reconcile(db)["healthy"]
    with store.transaction() as db:
        analytical_index.rebuild(db)
    with store.read_snapshot() as db:
        assert analytical_index.reconcile(db)["healthy"]
        assert facts == {
            table: [tuple(row) for row in db.execute("SELECT * FROM " + table)] for table in tables
        }
    # Update the reported day and physical admission independently of immutable
    # pair qualification; both counter families must track their own facts.
    with store.transaction() as db:
        db.execute(
            "UPDATE awareness_observations SET observed_at=?,admitted=0 WHERE id=?",
            ("2026-11-07", first["observation_id"]),
        )
    with store.read_snapshot() as db:
        assert analytical_index.reconcile(db)["healthy"]


def test_unrelated_cache_writes_keep_base_but_other_process_evidence_invalidates(tmp_path):
    store = Store(tmp_path / "workspace")
    event = add(store, base())
    eclipse = Eclipse(store)
    original = _base(eclipse)
    command = """import sqlite3,sys
from contextlib import closing
with closing(sqlite3.connect(sys.argv[1])) as db, db:
 db.execute(sys.argv[2],tuple(sys.argv[3:]))
"""
    subprocess.run(
        [
            sys.executable,
            "-c",
            command,
            str(store.db),
            "INSERT OR REPLACE INTO cache(key,payload,retrieved_at) VALUES(?,?,?)",
            "unrelated:test",
            "{}",
            "2026-11-13",
        ],
        check=True,
    )
    assert _revision(eclipse) == original[0]
    assert _base(eclipse) is original
    subprocess.run(
        [
            sys.executable,
            "-c",
            command,
            str(store.db),
            "UPDATE awareness_observations SET summary=? WHERE id=?",
            json.dumps(base(city="Raleigh")),
            event["observation_id"],
        ],
        check=True,
    )
    assert _revision(eclipse) != original[0]
    assert _base(eclipse) is not original
    with store.read_snapshot() as db:
        assert analytical_index.reconcile(db)["healthy"]


def test_planner_statistics_are_explicit_bounded_and_busy_safe(tmp_path):
    store = Store(tmp_path / "workspace")
    add(store, base())
    result = run(store, force=True)
    assert result["state"] == "complete"
    # SQLite added optimize's all-tables bit (0x10000) in 3.46. Older
    # system builds may legitimately do no work on a fresh connection.
    assert result["stat_rows"] >= 0
    if sqlite3.sqlite_version_info >= (3, 46, 0):
        assert result["stat_rows"] > 0
    with closing(sqlite3.connect(store.db)) as db:
        has_stats = db.execute("SELECT 1 FROM sqlite_master WHERE name='sqlite_stat1'").fetchone()
        actual_rows = (
            db.execute("SELECT count(*) FROM sqlite_stat1").fetchone()[0] if has_stats else 0
        )
        assert result["stat_rows"] == actual_rows
    assert status(store.root)["completed_at"] == result["completed_at"]
    with closing(sqlite3.connect(store.db, timeout=0.25)) as writer:
        writer.execute("BEGIN IMMEDIATE")
        # Statistics may already be adequate: a successful no-op is also safe.
        result = run(store, force=True)
        assert result["state"] in ("complete", "deferred")
        assert result["elapsed_ms"] < 2000
        writer.rollback()


def test_legacy_unknown_finding_remains_visible_without_false_qualification(tmp_path):
    store = Store(tmp_path / "workspace")
    event = add(store, base())
    finding = store.one("SELECT * FROM awareness_findings")
    with store.transaction() as db:
        _copy(
            db,
            "awareness_findings",
            finding,
            id="legacy-condition",
            condition="CVE-2026-99999",
            admitted=1,
        )
        db.execute(
            "INSERT INTO awareness_memberships(finding_id,observation_id) VALUES(?,?)",
            ("legacy-condition", event["observation_id"]),
        )
    snapshot = Eclipse(store).snapshot()
    unknown = next(row for row in snapshot["findings"] if row["id"] == "legacy-condition")
    assert unknown["status"] == "qualification_unknown"
    assert not unknown["admitted"] and not unknown["dark_matter"]
    assert unknown["intake_disposition"] == "qualification_unknown"
    assert unknown["reported_observation_count"] == unknown["legacy_unknown_observation_count"] == 1
    assert unknown["approved_observation_count"] == 0
    physical = snapshot["observations"][0]
    assert (
        physical["density_count"]
        == physical["admitted_density"]
        == physical["legacy_unknown_density"]
        == 1
    )
    assert physical["dark_matter_density"] == 0
    assert "overlap" in physical["qualification_density_basis"]
    with store.read_snapshot() as db:
        assert analytical_index.reconcile(db)["healthy"]


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO analytical_observations VALUES(NULL,'asset:test','2026-11-13',0,0)",
        "INSERT INTO analytical_memberships VALUES(NULL,'finding','2026-11-13','observed')",
        "INSERT INTO analytical_memberships VALUES('observation',NULL,'2026-11-13','observed')",
        "INSERT INTO analytical_density_days VALUES(NULL,'2026-11-13',1,0,0)",
        "INSERT INTO analytical_density_days VALUES('asset:test',NULL,1,0,0)",
        "INSERT INTO analytical_finding_days VALUES(NULL,'2026-11-13',1,0,0)",
        "INSERT INTO analytical_finding_days VALUES('finding',NULL,1,0,0)",
        "UPDATE analytical_revision SET token=NULL WHERE id=1",
    ],
)
def test_projection_identity_rejects_nulls_without_damaging_counters(tmp_path, statement):
    store = Store(tmp_path / "workspace")
    with pytest.raises(sqlite3.IntegrityError, match="NOT NULL constraint failed"):
        with store.transaction() as db:
            db.execute(statement)
    with store.read_snapshot() as db:
        # WITHOUT ROWID makes the single TEXT PRIMARY KEY non-null as well;
        # this protects identity without relying on rowid-table PK behavior.
        for table in (
            "analytical_observations",
            "analytical_memberships",
            "analytical_density_days",
            "analytical_finding_days",
        ):
            keys = [row for row in db.execute("PRAGMA table_info(" + table + ")") if row["pk"]]
            assert keys and all(row["notnull"] for row in keys)
        assert analytical_index.reconcile(db)["healthy"]
