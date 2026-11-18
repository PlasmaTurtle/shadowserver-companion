"""Accretion snapshots rank admission and survive the notification boundary."""

import copy
import json

import pytest

from test_workbench import app, client, observations
from test_lead_queue_098 import queue_import
from workbench.cases import Cases
from workbench.lead_queue import LeadQueue, register_group
from workbench.store import Store


def decision(value, temperature="hot"):
    return {
        "schema_version": 1,
        "policy_version": 1,
        "policy_hash": "synthetic-policy",
        "scored_at": "2026-11-12T01:00:00Z",
        "quality": value,
        "urgency": value,
        "aggregate": value,
        "temperature": temperature,
        "factors": {"quality": [], "urgency": []},
        "cves": [],
        "warnings": [],
    }


def put_score(store, lead_id, score):
    with store.transaction() as db:
        db.execute("UPDATE lead_queue SET intake_score=? WHERE id=?", (json.dumps(score), lead_id))


def new_import(client, app, day, root="example.com"):
    from test_workbench import FakeRegistry

    class Registry(FakeRegistry):
        def lookup(self, ip):
            record = super().lookup(ip)
            return type(record)(
                record.ip,
                record.registry,
                record.source_url,
                record.retrieved_at,
                {"contact": "it@" + root},
            )

    app.state.intake.lookup_factory = Registry
    queue_import(
        client,
        app,
        [
            {
                **row,
                "timestamp": f"2026-11-{day:02d} 01:02:03",
                # A new unsupported release line is a new condition. Patch-only
                # changes to an already handled finding do not create work.
                "version": f"7.{day}.25",
                "hostname": "mail." + root,
            }
            for row in observations()[:4]
        ],
        f"observations-{day}.csv",
    )
    return app.state.store.one("SELECT * FROM lead_queue ORDER BY rowid DESC LIMIT 1")


def test_pending_rank_is_aggregate_then_existing_order_with_legacy_last(client, app):
    first = new_import(client, app, 1)
    second = new_import(client, app, 2, "another.com")
    legacy = new_import(client, app, 3, "third.com")
    put_score(app.state.store, first["id"], decision(90, "blazing"))
    put_score(app.state.store, second["id"], decision(55, "warm"))
    put_score(app.state.store, legacy["id"], {})
    items = client.get("/api/pending-leads").json()
    assert [item["id"] for item in items] == [first["id"], second["id"], legacy["id"]]
    assert items[-1]["intake_score"] is None
    assert items[0]["qualified"] == 1 and items[0]["intake_score"]["quality"] == 90


@pytest.mark.parametrize("via_queue", [True, False])
def test_case_creation_pins_score_for_both_supported_routes(client, app, via_queue):
    row = new_import(client, app, 1)
    score = decision(85, "blazing")
    put_score(app.state.store, row["id"], score)
    if via_queue:
        result = client.post(
            "/api/pending-leads/" + row["id"] + "/start",
            json={"expected_revision": row["revision"]},
        )
        assert result.status_code == 200, result.text
        case_id = result.json()["case_id"]
    else:
        case_id = Cases(app.state.store).create(row["entity_id"])["case_id"]
    view = Cases(app.state.store).view(case_id)
    pinned = copy.deepcopy(view["intake_score"])
    assert pinned["aggregate"] == score["aggregate"]
    assert pinned["source_scores"][0]["intake_score"] == score
    assert view["case"]["intake_score"] == pinned
    # Later policy, catalog or even a repaired intake record cannot silently
    # change the decision recorded by a notification that already exists.
    put_score(app.state.store, row["id"], decision(40, "warm"))
    assert Cases(app.state.store).view(case_id)["intake_score"] == pinned
    assert app.state.store.export_lead(row["entity_id"], case_id)["intake_score"] == pinned
    assert client.get("/api/cases").json()[0]["intake_score"] == pinned


def test_new_scope_retains_each_original_score_and_uses_strongest(client, app):
    row = new_import(client, app, 1)
    put_score(app.state.store, row["id"], decision(55, "warm"))
    result = LeadQueue(app.state.store).start(row["id"], row["revision"])
    case = app.state.store.one("SELECT * FROM cases WHERE id=?", (result["case_id"],))
    next_row = new_import(client, app, 2)
    put_score(app.state.store, next_row["id"], decision(90, "blazing"))
    LeadQueue(app.state.store).start(
        next_row["id"],
        next_row["revision"],
        case_id=case["id"],
        expected_case_version=case["version"],
    )
    score = Cases(app.state.store).view(case["id"])["intake_score"]
    assert score["aggregate"] == 90 and score["temperature"] == "blazing"
    assert {source["lead_id"] for source in score["source_scores"]} == {
        row["id"],
        next_row["id"],
    }
    assert {source["intake_score"]["aggregate"] for source in score["source_scores"]} == {55, 90}


def test_attribution_support_row_does_not_import_unselected_old_priority(client, app):
    store = app.state.store
    old = new_import(client, app, 1)
    put_score(store, old["id"], decision(95, "blazing"))
    old_case = LeadQueue(store).start(old["id"], old["revision"])["case_id"]
    proof = store.one("SELECT attribution_entry_id FROM domain_groups")["attribution_entry_id"]
    with store.transaction() as db:
        db.execute("UPDATE cases SET stage='closed' WHERE id=?", (old_case,))
    new = new_import(client, app, 2)
    put_score(store, new["id"], decision(50, "warm"))
    with store.transaction() as db:
        db.execute("UPDATE domain_groups SET attribution_entry_id=?", (proof,))
    new_case = LeadQueue(store).start(new["id"], new["revision"])["case_id"]
    assert store.one("SELECT * FROM case_entries WHERE case_id=? AND entry_id=?", (new_case, proof))
    score = Cases(store).view(new_case)["intake_score"]
    assert score["aggregate"] == 50
    assert [source["lead_id"] for source in score["source_scores"]] == [new["id"]]


def test_retry_preserves_original_score_and_reads_never_invoke_scoring(client, app, monkeypatch):
    row = new_import(client, app, 1)
    score = decision(85, "blazing")
    put_score(app.state.store, row["id"], score)
    with app.state.store.transaction() as db:
        register_group(
            db,
            row["import_id"],
            row["root_domain"],
            json.loads(row["payload"]),
            entity_id=row["entity_id"],
            qualified=True,
            intake_score=decision(45, "warm"),
        )
    import workbench.accretion as accretion

    def forbidden(*args, **kwargs):
        raise AssertionError("Read endpoint rescored intake")

    monkeypatch.setattr(accretion, "score_lead", forbidden)
    assert LeadQueue(app.state.store).detail(row["id"])["intake_score"] == score
    assert LeadQueue(app.state.store).list()[0]["intake_score"] == score


def test_schema_eleven_upgrade_preserves_history_without_backfilling_scores(client, app):
    row = new_import(client, app, 1)
    case_id = LeadQueue(app.state.store).start(row["id"], row["revision"])["case_id"]
    store = app.state.store
    from test_lead_frontier_0991 import remove_frontier_schema

    with store.transaction() as db:
        remove_frontier_schema(db)
        db.execute("DROP TABLE intake_observations")
        db.execute("ALTER TABLE lead_queue DROP COLUMN intake_score")
        db.execute("ALTER TABLE cases DROP COLUMN intake_score")
        db.execute("PRAGMA user_version=11")
    before = {
        name: store.all("SELECT * FROM " + name)
        for name in ("entries", "events", "cases", "lead_queue")
    }
    upgraded = Store(store.root)
    for name, rows in before.items():
        after = upgraded.all("SELECT * FROM " + name)
        assert [
            {key: value for key, value in item.items() if key in rows[0]} for item in after
        ] == rows
    assert LeadQueue(upgraded).detail(row["id"])["intake_score"] is None
    assert Cases(upgraded).view(case_id)["intake_score"] is None
    assert "intake_score" not in upgraded.export_lead(row["entity_id"], case_id)
    assert not upgraded.all("PRAGMA foreign_key_check")
    from workbench.migrations import SCHEMA_VERSION

    assert (
        len(list((store.root / "backups").glob(f"before-schema-{SCHEMA_VERSION}-*.sqlite3"))) == 1
    )
    Store(store.root)
    assert (
        len(list((store.root / "backups").glob(f"before-schema-{SCHEMA_VERSION}-*.sqlite3"))) == 1
    )


def test_workspace_priority_respects_due_work_and_outreach_holds(client, app):
    store = app.state.store
    cases = []
    for day, aggregate in ((1, 45), (2, 85), (3, 95)):
        row = new_import(client, app, day)
        put_score(store, row["id"], decision(aggregate))
        case_id = LeadQueue(store).start(row["id"], row["revision"])["case_id"]
        cases.append(case_id)
        with store.transaction() as db:
            db.execute("UPDATE cases SET stage='closed' WHERE id=?", (case_id,))
    with store.transaction() as db:
        db.execute("UPDATE cases SET stage='in_progress'")
        db.execute("UPDATE cases SET follow_up_date='2026-11-01' WHERE id=?", (cases[0],))
        db.execute(
            "INSERT INTO case_outreach_policy VALUES(?,?,?,?,?,?)",
            (cases[2], "do_not_contact", "Recipient request", None, "Test Analyst", "2026-11-12"),
        )
    before = store.all("SELECT * FROM cases ORDER BY id")
    result = client.get("/api/workspace/queue?as_of=2026-11-12").json()
    assert [item["id"] for item in result["items"]] == cases[:2]
    assert result["held"] == 1
    assert result["items"][0]["intake_score"]["aggregate"] == 45
    assert store.all("SELECT * FROM cases ORDER BY id") == before
    with store.transaction() as db:
        db.execute("UPDATE cases SET follow_up_date=NULL WHERE id=?", (cases[0],))
    assert [
        item["id"] for item in client.get("/api/workspace/queue?as_of=2026-11-12").json()["items"]
    ] == [
        cases[1],
        cases[0],
    ]


def test_reevaluated_queue_decision_wins_over_original_entry_import(client, app):
    store = app.state.store
    original = new_import(client, app, 1)
    put_score(store, original["id"], decision(45, "warm"))
    source = store.one("SELECT * FROM imports WHERE id=?", (original["import_id"],))
    re_evaluation = {**source, "id": "reevaluated-import", "fingerprint": "new-policy-fingerprint"}
    columns = ",".join(re_evaluation)
    marks = ",".join("?" for _ in re_evaluation)
    with store.transaction() as db:
        db.execute(f"INSERT INTO imports({columns}) VALUES({marks})", tuple(re_evaluation.values()))
        new_id = register_group(
            db,
            re_evaluation["id"],
            original["root_domain"],
            json.loads(original["payload"]),
            entity_id=original["entity_id"],
            qualified=True,
            intake_score=decision(90, "blazing"),
        )
    assert {row["import_id"] for row in store.all("SELECT import_id FROM entries")} == {
        original["import_id"]
    }
    created = LeadQueue(store).start(new_id, LeadQueue(store).detail(new_id)["revision"])
    pinned = Cases(store).view(created["case_id"])["intake_score"]
    assert pinned["aggregate"] == 90
    assert pinned["source_lead_id"] == new_id
    assert [source["lead_id"] for source in pinned["source_scores"]] == [new_id]
