"""Recipient counts stay near-linear as one notification's scope grows."""

import json

from test_workbench import app, client, import_rows, observations
from workbench.services.case_queries import list_cases
from workbench.workspace_queue import workspace_queue


def test_scope_count_queries_materialize_decisions_once(client, app, monkeypatch):
    import_rows(client, app, [observations()[2]])
    store = app.state.store
    base = store.one("SELECT * FROM entries")
    case = store.one("SELECT * FROM cases")
    original = store.connect
    measurements = {"cases": [], "workspace_queue": []}
    queries, progress = [], []

    def connect():
        db = original()
        db.set_trace_callback(queries.append)
        db.set_progress_handler(lambda: progress.append(1) or 0, 100)
        return db

    prior = 1
    for size in (500, 1000, 2500):
        ids = [base["id"], *[f"scope-growth-{index}" for index in range(1, size)]]
        with store.transaction() as db:
            columns = tuple(base)
            db.executemany(
                "INSERT INTO entries("
                + ",".join(columns)
                + ") VALUES("
                + ",".join("?" for _ in columns)
                + ")",
                [
                    tuple(({**base, "id": ids[index]})[key] for key in columns)
                    for index in range(prior, size)
                ],
            )
            db.executemany(
                "INSERT INTO case_entries VALUES(?,?)",
                [(case["id"], ids[index]) for index in range(prior, size)],
            )
            draft = json.loads(case["draft"])
            draft["observation_scope"] = {
                entry_id: {
                    "decision": "exclude",
                    "reason": "Synthetic scope review",
                    "actor": "Test Analyst",
                    "decided_at": "2026-11-13T00:00:00Z",
                }
                for entry_id in ids[: size // 2]
            }
            db.execute("UPDATE cases SET draft=? WHERE id=?", (json.dumps(draft), case["id"]))
        prior = size
        monkeypatch.setattr(store, "connect", connect)
        for name, read in (
            ("cases", lambda: list_cases(store)),
            ("workspace_queue", lambda: workspace_queue(store)["items"]),
        ):
            queries.clear()
            progress.clear()
            rows = read()
            assert len(rows) == 1
            assert rows[0]["source_observations"] == size
            assert rows[0]["included_source_observations"] == size // 2
            assert rows[0]["observations"] == size // 2 and rows[0]["assets"] == 1
            reads = [q for q in queries if q.lstrip().upper().startswith(("SELECT", "WITH"))]
            measurements[name].append((len(progress) * 100, len(reads)))
            if name == "cases":
                with original() as db:
                    plan = list(db.execute("EXPLAIN QUERY PLAN " + reads[0]))
                assert sum("VIRTUAL TABLE" in row[3] for row in plan) == 1
        monkeypatch.setattr(store, "connect", original)
    for values in measurements.values():
        # Five times as much evidence must not recreate the former ~25x VM
        # work. Allow room for sorting/index setup and SQLite planner changes.
        assert values[-1][0] < values[0][0] * 8 + 10000, values
        assert len({query_count for _, query_count in values}) == 1
