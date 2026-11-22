"""Qualification reads current ownership without rechecking migrated schema."""

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

import pytest

from tests.support.workbench import app, client
from modules.entities.tests.support.entity_lifecycle import setup_entities, plan_transfer, transfer
from modules.accretion.components.intake import CandidateGroup, restore_observation
from modules.accretion.components.qualification import local_scope


def test_local_qualification_preserves_transfer_rules_without_schema_probes(
    client, app, monkeypatch
):
    source, target = setup_entities(client, app)
    store = app.state.store
    original = json.loads(
        store.one("SELECT payload FROM jobs WHERE domain='example.com'")["payload"]
    )[0]
    queries = []
    read_snapshot = store.read_snapshot

    @contextmanager
    def traced_snapshot():
        with read_snapshot() as db:
            db.set_trace_callback(queries.append)
            try:
                yield db
            finally:
                db.set_trace_callback(None)

    def scope(root="example.com", observed="2026-11-04 01:02:03"):
        entries = []
        for index in range(64):
            entry = deepcopy(original)
            entry["source"]["row"] = 1000 + index
            entry["normalized"].pop("observation_ref", None)
            entry["source"]["fields"].update(hostname=f"new-{index}.{root}", timestamp=observed)
            entries.append(restore_observation(entry))
        queries.clear()
        with monkeypatch.context() as patch:
            patch.setattr(store, "read_snapshot", traced_snapshot)
            result = local_scope(store, CandidateGroup(root, entries))
        schema_probes = [
            query
            for query in queries
            if "sqlite_master" in query.lower() or "pragma" in query.lower()
        ]
        assert not schema_probes, schema_probes
        return result

    recognized, findings, reason = scope()
    assert recognized["state"] == "known" and recognized["entity_id"] == source
    assert recognized["saved_proof"]["result_id"]
    assert len(findings) == 64 and reason is None

    unknown, findings, reason = scope("unknown-example.org")
    assert unknown["state"] == "new" and unknown["saved_proof"] is None
    assert len(findings) == 64 and reason is None

    assert transfer(client, source, plan_transfer(client, source, target)).status_code == 200
    for observed in ("2026-11-04 01:02:03", ""):
        recognized, findings, reason = scope(observed=observed)
        assert recognized["state"] == "review" and recognized["entity_id"] is None
        assert findings == () and reason == "association_conflict"

    current = (datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat()
    recognized, findings, reason = scope(observed=current)
    assert recognized["state"] == "known" and recognized["entity_id"] == target
    assert recognized["saved_proof"] == {}
    assert len(findings) == 64 and reason is None


def test_qualification_token_detects_transfer_away_and_back_but_ignores_proof_refresh(client, app):
    from modules.entities.components.ownership import (
        OwnershipChanged,
        check_qualification_context,
        qualification_context,
    )

    source, target = setup_entities(client, app)
    store = app.state.store
    entry = json.loads(store.one("SELECT payload FROM jobs WHERE domain='example.com'")["payload"])[
        0
    ]
    entry["normalized"].pop("observation_ref", None)
    entry["source"]["row"] = 1000
    entry["source"]["fields"].update(
        hostname="new.example.com",
        timestamp=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    )
    entries = [entry]
    with store.read_snapshot() as db:
        original = qualification_context(db, "example.com", entries)
        assert original["entity_id"] == source and original["ownership_token"]
        assert (
            check_qualification_context(db, "example.com", entries, original["ownership_token"])[0]
            == source
        )

    # Attribution is a separate owner. Changing its stored reference must not
    # make a stable ownership snapshot stale or authorize another business.
    with store.transaction() as db:
        saved = db.execute(
            "SELECT attribution FROM entity_domain_associations WHERE root_domain=? AND entity_id=?",
            ("example.com", source),
        ).fetchone()[0]
        db.execute(
            "UPDATE entity_domain_associations SET attribution=? WHERE root_domain=? AND entity_id=?",
            ('{"result_id":"synthetic-refreshed-proof"}', "example.com", source),
        )
        refreshed = qualification_context(db, "example.com", entries)
        assert refreshed["saved_proof"] != original["saved_proof"]
        assert refreshed["ownership_token"] == original["ownership_token"]
        assert (
            check_qualification_context(db, "example.com", entries, original["ownership_token"])[0]
            == source
        )
        db.execute(
            "UPDATE entity_domain_associations SET attribution=? WHERE root_domain=? AND entity_id=?",
            (saved, "example.com", source),
        )

    assert transfer(client, source, plan_transfer(client, source, target)).status_code == 200
    with store.read_snapshot() as db:
        moved = qualification_context(db, "example.com", entries)
        assert moved["entity_id"] == target
        with pytest.raises(
            OwnershipChanged, match="Ownership changed while this group was qualifying"
        ):
            check_qualification_context(db, "example.com", entries, original["ownership_token"])

    assert transfer(client, target, plan_transfer(client, target, source)).status_code == 200
    with store.read_snapshot() as db:
        returned = qualification_context(db, "example.com", entries)
        assert returned["entity_id"] == original["entity_id"]
        assert returned["ownership_token"] not in {
            original["ownership_token"],
            moved["ownership_token"],
        }
        with pytest.raises(OwnershipChanged, match="retry qualification"):
            check_qualification_context(db, "example.com", entries, original["ownership_token"])
