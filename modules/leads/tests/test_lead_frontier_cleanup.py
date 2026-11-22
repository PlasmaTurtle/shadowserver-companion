"""Current-scope reconciliation reads each candidate once and preserves ranking."""

from collections import Counter
import json

import pytest

from tests.support.workbench import app, client
from modules.accretion.components import accretion
from modules.leads.components import lead_frontier
from modules.leads.tests.support.lead_queue import ingest


@pytest.mark.parametrize("merge", [False, True])
def test_reconcile_reuses_parsed_candidates_and_never_scores(client, app, monkeypatch, merge):
    with monkeypatch.context() as patch:
        patch.setattr(lead_frontier, "reconcile", lambda db, identity, **kwargs: identity)
        first = ingest(client, app)
        incoming = ingest(client, app, hostname="web.example.com") if merge else first
    store = app.state.store
    reads, scores = Counter(), []
    original_origin, original_score = lead_frontier.origin_entries, accretion.score_lead

    def origin(db, row):
        reads[row["id"]] += 1
        return original_origin(db, row)

    def score(*args, **kwargs):
        result = original_score(*args, **kwargs)
        scores.append(result)
        return result

    monkeypatch.setattr(lead_frontier, "origin_entries", origin)
    monkeypatch.setattr(accretion, "score_lead", score)
    with store.transaction() as db:
        current_id = lead_frontier.reconcile(db, incoming["id"])
    current = store.one("SELECT * FROM lead_queue WHERE id=?", (current_id,))
    expected_ids = {first["id"], incoming["id"]}
    assert reads == Counter({identity: 1 for identity in expected_ids})
    assert len(json.loads(current["payload"])) == (2 if merge else 1)
    assert scores == []
    assert json.loads(current["intake_score"]) == json.loads(incoming["intake_score"])
    if merge:
        retired = store.one("SELECT * FROM lead_queue WHERE id=?", (first["id"],))
        assert retired["superseded_by"] == current_id and retired["payload"] == "[]"
    assert store.all("PRAGMA foreign_key_check") == []
