"""Scope, batching and lookup regressions for the measured performance fixes."""

from contextlib import closing
import json
import sqlite3

import pytest

from test_workbench import app, client, observations
from test_lead_queue_098 import queue_import
from workbench.cases import Cases
from workbench.lead_queue import LeadQueue, association
from workbench.intelligence_index import decorate_rows
from workbench.store import Store
from workbench.awareness import digest, link_asset
from workbench.ownership import ensure_asset


@pytest.mark.parametrize("stored_status", ["pending", "deferred", "dismissed"])
def test_assigned_projection_retains_external_scope_changes(client, app, stored_status):
    queue_import(client, app)
    store = app.state.store
    row = LeadQueue(store).list()[0]
    with store.transaction() as db:
        db.execute("UPDATE lead_queue SET status=? WHERE id=?", (stored_status, row["id"]))
    # A notification can consume scope without using the Leads start action.
    Cases(store).create(row["entity_id"], "Independent workflow")
    queue = LeadQueue(store)
    assert not queue.list(stored_status)
    assigned = queue.list("assigned")
    assert [item["id"] for item in assigned] == [row["id"]]
    assert assigned[0]["status"] == "assigned" and not assigned[0]["can_start"]
    assert queue.list("all") == assigned


def test_pending_observation_beyond_batch_boundary_is_not_lost(client, app):
    rows = [
        {**observations()[0], "ip": "8.8.8.8", "hostname": f"host-{i}.example.com"}
        for i in range(1001)
    ]
    queue_import(client, app, rows)
    store = app.state.store
    queue = LeadQueue(store)
    item = queue.list()[0]
    before = queue.detail(item["id"])
    case = Cases(store).create(item["entity_id"], "Large notification")
    assert not queue.list()
    last = before["entries"][-1]["id"]
    with store.transaction() as db:
        db.execute(
            "DELETE FROM case_entries WHERE case_id=? AND entry_id=?", (case["case_id"], last)
        )
    current = queue.detail(item["id"])
    assert current["can_start"] and current["status"] == "pending"
    assert current["entries"] == before["entries"] and len(current["entries"]) == 1001
    assert queue.list()[0]["observations"] == 1001
    assert not store.all("PRAGMA foreign_key_check")


def test_filtered_intelligence_does_not_read_unrequested_drafts():
    from workbench.repositories.records import Records

    with closing(sqlite3.connect(":memory:")) as db:
        db.row_factory = sqlite3.Row
        db.execute("CREATE TABLE cases(id TEXT PRIMARY KEY,draft TEXT)")
        db.executemany(
            "INSERT INTO cases VALUES(?,?)",
            [(f"case-{i}", json.dumps({"cve_records": [{"kev": i == 1000}]})) for i in range(1001)],
        )
        # An unrelated broken historical draft must not be read by this view.
        db.execute("INSERT INTO cases VALUES('unrelated','not-json')")
        selected = [{"id": f"case-{i}"} for i in range(1001)]
        result = decorate_rows(Records(db), selected, kind="cases")
        assert len(result) == 1001
        assert result[-1]["kev"] is True
        assert all(row["kev"] is None for row in result[:-1])
        queries = []
        db.set_trace_callback(queries.append)
        assert decorate_rows(Records(db), [], kind="cases") == [] and not queries


def test_association_work_is_bounded_as_unrelated_history_grows(tmp_path):
    # Exercise the actual canonical schema, including ownership replay/history.
    # The former schema-11 miniature bypassed all modern ownership lookups.
    store = Store(tmp_path / "workspace")
    stamp = "2026-11-13T10:00:00Z"
    with store.transaction() as db:
        db.execute(
            "INSERT INTO imports(id,fingerprint,sha256,name,path,created_at,config) VALUES('history','history',?,'history.csv','originals/history.csv',?,'{}')",
            ("0" * 64, stamp),
        )
    measurements = []
    previous = 0
    for size in (1000, 10000):
        batch = list(range(previous, size))
        with store.transaction() as db:
            db.executemany(
                "INSERT INTO leads(id,company,domain,created_at,updated_at,attribution,attribution_entry_id) VALUES(?,?,?,?,?,'{}',?)",
                [
                    (str(i), "Synthetic", f"example{i}.invalid", stamp, stamp, f"entry-{i}")
                    for i in batch
                ],
            )
            db.executemany(
                "INSERT INTO entries(id,lead_id,import_id,payload,ip,hostname,tag,version,root_domain) VALUES(?,?,'history','{}',?,?,'','',?)",
                [
                    (
                        f"entry-{i}",
                        str(i),
                        f"192.0.2.{i}",
                        f"MAIL.example{i}.invalid",
                        f"example{i}.invalid",
                    )
                    for i in batch
                ],
            )
            db.executemany(
                "INSERT INTO domain_groups(root_domain,entity_id,attribution_entry_id,attribution) VALUES(?,?,?,'{}')",
                [(f"example{i}.invalid", str(i), f"entry-{i}") for i in batch],
            )
            db.executemany(
                "INSERT INTO hostnames(name,root_domain) VALUES(?,?)",
                [(f"MAIL.example{i}.invalid", f"example{i}.invalid") for i in batch],
            )
            assets = {i: digest(["asset", f"hostname:mail.example{i}.invalid"]) for i in batch}
            db.executemany(
                "INSERT INTO awareness_assets VALUES(?,?,?,?,?,'synthetic',?,?)",
                [
                    (
                        assets[i],
                        f"hostname:mail.example{i}.invalid",
                        f"mail.example{i}.invalid",
                        f"example{i}.invalid",
                        str(i),
                        stamp,
                        stamp,
                    )
                    for i in batch
                ],
            )
            db.executemany(
                "INSERT INTO asset_ownership_episodes VALUES(?,'',?,'',NULL,'synthetic','')",
                [(assets[i], str(i)) for i in batch],
            )
            db.executemany(
                "INSERT INTO awareness_observations VALUES(?,?,?,0,'','{}','{}',?,?,?,?,?)",
                [
                    (
                        f"observation-{i}",
                        assets[i],
                        stamp,
                        f"192.0.2.{i}",
                        f"endpoint-{i}",
                        stamp,
                        stamp,
                        f"source-{i}",
                    )
                    for i in batch
                ],
            )
            db.executemany(
                "INSERT INTO awareness_observation_owners VALUES(?,?,'','synthetic',?)",
                [(f"observation-{i}", str(i), stamp) for i in batch],
            )
            db.executemany(
                "INSERT INTO awareness_sources VALUES('history',?,?,?,'CSV',?,?,'history.csv')",
                [(f"source-{i}", f"observation-{i}", "0" * 64, i + 2, f"entry-{i}") for i in batch],
            )
            if not previous:
                link_asset(db, "example.com", "7")
            violations = [tuple(row) for row in db.execute("PRAGMA foreign_key_check")]
            assert not violations, violations[:5]
        previous = size
        with store.read_snapshot() as db:
            # The old in-memory fixture measured on its already-used seeding
            # connection. Prepare this new connection's schema for parity.
            db.execute("SELECT id FROM awareness_assets LIMIT 1").fetchone()
            steps, lookup_work = [], []
            db.set_progress_handler(lambda: steps.append(1) or 0, 100)

            def lookup(root, entries):
                before = len(steps)
                result = association(db, root, entries)
                lookup_work.append((len(steps) - before) * 100)
                return result

            assert lookup(
                "unregistered.invalid",
                [{"ip": "192.0.2.7", "source": {"fields": {"hostname": "MAIL.example7.invalid"}}}],
            )[:3] == ("7", "known", "Stored hostname association")
            assert lookup("other.invalid", [{"ip": "192.0.2.7"}])[1:] == ("new", "", [])
            # A new child hostname inherits the current root's episode without
            # scanning every unrelated asset or every retained source mapping.
            assert lookup(
                "example.com",
                [{"ip": "192.0.2.7", "source": {"fields": {"hostname": "new.example.com"}}}],
            )[:3] == ("7", "known", "Stored hostname association")
            db.set_progress_handler(None, 0)
            measurements.append(len(steps) * 100)
            # Modern ownership probes add fixed schema checks. Preserve the
            # original VM ceiling per lookup, and separately test growth across
            # ten times as much unrelated canonical and legacy history.
            assert max(lookup_work) < 5000, lookup_work
            plan = [
                row[3]
                for row in db.execute(
                    "EXPLAIN QUERY PLAN SELECT ep.* FROM asset_ownership_episodes ep JOIN awareness_assets a ON a.id=ep.asset_id WHERE a.asset_key=? AND ep.ended_at IS NULL ORDER BY ep.started_at DESC LIMIT 1",
                    ("hostname:example.com",),
                )
            ]
            assert any("asset_key=?" in step for step in plan) and not any(
                "SCAN " in step for step in plan
            ), plan
        with store.transaction() as db:
            key = f"hostname:fresh{size}.example.com"
            identity = digest(["asset", key])
            db.execute(
                "INSERT INTO awareness_assets VALUES(?,?,?,'example.com','7','synthetic',?,?)",
                (identity, key, f"fresh{size}.example.com", stamp, stamp),
            )
            steps = []
            db.set_progress_handler(lambda: steps.append(1) or 0, 100)
            ensure_asset(db, identity, "7")
            db.set_progress_handler(None, 0)
            assert len(steps) * 100 < 5000, "Initial ownership searched unrelated episodes"
            current = db.execute(
                "SELECT entity_id,episode FROM asset_ownership_episodes WHERE asset_id=?",
                (identity,),
            ).fetchone()
            assert tuple(current) == ("7", "")
    assert measurements[-1] <= measurements[0] + 1000, measurements
