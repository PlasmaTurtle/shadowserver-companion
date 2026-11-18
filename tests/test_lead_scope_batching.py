"""Large notification scopes must not perform a SELECT for every observation."""

import sqlite3
import unittest

from workbench.lead_queue import _pending_scope


class PendingScopeTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.addCleanup(self.db.close)
        self.db.executescript(
            "CREATE TABLE entries(id TEXT PRIMARY KEY,root_domain TEXT);"
            "CREATE TABLE case_entries(entry_id TEXT PRIMARY KEY);"
        )

    def test_large_scope_preserves_order_roots_and_excludes_consumed_entries(self):
        ids = [f"observation-{i}" for i in range(1201)]
        self.db.executemany(
            "INSERT INTO entries VALUES(?,?)",
            [(identity, f"root-{i % 3}.example") for i, identity in enumerate(ids)],
        )
        used = {ids[0], ids[499], ids[500], ids[1000], ids[-1]}
        self.db.executemany("INSERT INTO case_entries VALUES(?)", [(i,) for i in used])
        queries = []
        self.db.set_trace_callback(queries.append)
        actual = _pending_scope(self.db, ids[::-1])
        expected = [
            (ids[i], f"root-{i % 3}.example")
            for i in range(len(ids) - 1, -1, -1)
            if ids[i] not in used
        ]
        self.assertEqual(actual, expected)
        self.assertEqual(len(queries), 3)

    def test_empty_scope_does_not_query(self):
        queries = []
        self.db.set_trace_callback(queries.append)
        self.assertEqual(_pending_scope(self.db, []), [])
        self.assertEqual(queries, [])

    def test_only_retained_unassigned_observations_can_enter_case_scope(self):
        self.db.execute("INSERT INTO entries VALUES('retained','example.com')")
        self.assertEqual(
            _pending_scope(self.db, ["missing", "retained"]),
            [("retained", "example.com")],
        )


if __name__ == "__main__":
    unittest.main()
