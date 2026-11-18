"""Adversarial ownership episodes: late evidence, replays, and new-owner work."""

import json

import pytest

from test_workbench import app, client, observations, FakeRegistry
from test_lead_queue_098 import queue_import
from test_entity_lifecycle_0110 import setup_entities, plan_transfer, transfer
from workbench.awareness import associate, asset_key, digest, timestamp
from workbench.eclipse import Eclipse
from workbench.lead_queue import LeadQueue
from workbench.ownership import context


class ThirdRegistry(FakeRegistry):
    def lookup(self, ip):
        record = super().lookup(ip)
        return type(record)(
            record.ip,
            record.registry,
            record.source_url,
            record.retrieved_at,
            {"contact": "security@third-company.com"},
        )


def three_owners(client, app, monkeypatch):
    source, middle = setup_entities(client, app)
    store = app.state.store
    pending = next(row for row in LeadQueue(store).list() if row["entity_id"] == source)
    LeadQueue(store).disposition(pending["id"], pending["revision"], "dismissed")
    app.state.intake.lookup_factory = ThirdRegistry
    queue_import(
        client, app, [{**observations()[0], "hostname": "portal.third-company.com"}], "third.csv"
    )
    target = store.one("SELECT id FROM leads WHERE domain='third-company.com'")["id"]
    app.state.intake.lookup_factory = lambda: app.state.fake
    from workbench.services import entity_lifecycle

    monkeypatch.setattr(entity_lifecycle, "now", lambda: "2026-11-05T12:00:00.123456Z")
    first = transfer(client, source, plan_transfer(client, source, middle))
    assert first.status_code == 200, first.text
    monkeypatch.setattr(entity_lifecycle, "now", lambda: "2026-11-10T12:00:00.123456Z")
    second = transfer(client, middle, plan_transfer(client, middle, target))
    assert second.status_code == 200, second.text
    return source, middle, target, first.json()["event_id"], second.json()["event_id"]


@pytest.mark.parametrize("hostname", ["mail.example.com", "new.example.com"])
@pytest.mark.parametrize(
    "reported,owner_index,approved",
    [
        ("2026-11-04 02:00:00", 0, False),
        ("2026-11-07 02:00:00", 1, False),
        ("2026-11-11 02:00:00", 2, True),
        ("", None, False),
    ],
)
def test_two_transfers_keep_exact_history_and_allow_only_dated_current_work(
    client, app, monkeypatch, hostname, reported, owner_index, approved
):
    owners = three_owners(client, app, monkeypatch)
    store, current_owner = app.state.store, owners[2]
    with store.transaction() as db:
        db.execute(
            "INSERT OR REPLACE INTO entity_profiles VALUES(?,?)",
            (current_owner, json.dumps({"city": "Asheville", "state": "NC"})),
        )
    before_map = Eclipse(store).view(include_undated=True)["intelligence"]["atlas"]
    baseline = next(
        node["observation_count"]
        for node in before_map["nodes"]
        if current_owner in node["entity_ids"]
    )
    receipt, _ = queue_import(
        client,
        app,
        [{**observations()[2], "hostname": hostname, "timestamp": reported, "version": "7.3.99"}],
        "ownership-interval.csv",
    )
    assert store.one("SELECT status FROM imports WHERE id=?", (receipt["id"],))["status"] == (
        "done" if approved else "needs_retry"
    )
    assert store.one("SELECT status FROM jobs WHERE import_id=?", (receipt["id"],))["status"] == (
        "qualified" if approved else "deferred"
    )
    row = store.one(
        """SELECT o.*,s.import_id,s.source_key occurrence_key,s.source_sha256,s.sheet,s.row_number,
        w.entity_id recorded_owner,w.ownership_episode,w.basis
        FROM awareness_sources s JOIN awareness_observations o ON o.id=s.observation_id
        JOIN awareness_observation_owners w ON w.observation_id=o.id WHERE s.import_id=?""",
        (receipt["id"],),
    )
    expected_owner = owners[owner_index] if owner_index is not None else None
    assert row["recorded_owner"] == expected_owner
    assert row["admitted"] == int(approved)
    pair = store.one(
        "SELECT m.admission_state,f.entity_id,f.workflow FROM awareness_memberships m JOIN awareness_findings f ON f.id=m.finding_id WHERE m.observation_id=?",
        (row["id"],),
    )
    assert pair["admission_state"] == ("admitted" if approved else "observed")
    assert pair["entity_id"] == expected_owner
    if approved:
        assert row["ownership_episode"] == owners[4]
        assert pair["workflow"] == "unworked"
        assert any(
            lead["entity_id"] == current_owner and lead["can_start"]
            for lead in LeadQueue(store).list()
        )
    # Even a final-qualification caller cannot clear the source's historical review.
    entry = {
        "source": {
            "fields": json.loads(row["summary"]),
            "sheet": row["sheet"],
            "row": row["row_number"],
        },
        "ip": row["ip"],
        "normalized": {
            **json.loads(row["normalized"]),
            "observation_ref": row["occurrence_key"],
            "source_sha256": row["source_sha256"],
        },
    }
    with store.transaction() as db:
        associate(
            db,
            entry,
            import_id=row["import_id"],
            entity_id=current_owner,
            admitted=True,
            reason="adversarial replay",
        )
    assert store.one("SELECT admitted FROM awareness_observations WHERE id=?", (row["id"],))[
        "admitted"
    ] == int(approved)
    assert (
        store.one(
            "SELECT entity_id FROM awareness_observation_owners WHERE observation_id=?",
            (row["id"],),
        )["entity_id"]
        == expected_owner
    )
    if owner_index is None:
        detail = Eclipse(store).observation(row["id"])
        assert detail["entity_id"] is None and detail["recorded_entity_id"] is None
        after_map = Eclipse(store).view(include_undated=True)["intelligence"]["atlas"]
        assert (
            next(
                node["observation_count"]
                for node in after_map["nodes"]
                if current_owner in node["entity_ids"]
            )
            == baseline
        )
    assert (
        store.one(
            "SELECT workflow FROM awareness_findings f JOIN awareness_assets a ON a.id=f.asset_id WHERE a.hostname='mail.example.com' AND f.ownership_episode=''"
        )["workflow"]
        == "ignored"
    )
    assert not store.all("PRAGMA foreign_key_check")


@pytest.mark.parametrize(
    "instant,current",
    [
        ("2026-11-10T12:00:00.123455+00:00", False),
        ("2026-11-10T12:00:00.123456+00:00", True),
        ("2026-11-10T12:00:00.123457+00:00", True),
        ("2026-11-10T07:00:00.123456-05:00", True),
    ],
)
def test_transfer_boundary_compares_utc_instants(client, app, monkeypatch, instant, current):
    owners = three_owners(client, app, monkeypatch)
    key, name, _ = asset_key({"source": {"fields": observations()[2]}})
    with app.state.store.read_snapshot() as db:
        result = context(db, digest(["asset", key]), name, timestamp(instant))
    assert result["historical_review"] is not current
    assert result["entity_id"] == owners[2 if current else 1]
