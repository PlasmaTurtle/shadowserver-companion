"""Captured-source cache and immutable revisions; transactions belong to callers.

Original revision keys remain stable in the immutable evidence registry.
Provider decisions, deadlines, cancellation and byte capture stay in acquisition.
"""

import json
from modules.workspace.components.primitives import dump, now
from modules.investigations.components.evidence_registry import (
    available,
    get_record,
    register_revision,
    revision_key,
)
from modules.workspace.components.repositories.records import Records
from ..intelligence.selection_identity import same_selection, selection_key


class SourceRepository:
    def __init__(self, store):
        self.store = store

    def get(self, key, db=None):
        if db is not None:
            return get_record(db, key)
        with self.store.read_snapshot() as snapshot:
            return get_record(snapshot, key)

    def payload(self, key):
        row = self.get(key)
        return json.loads(row["payload"]) if row else {}

    def reference_state(self, cve_id):
        """Read last-good evidence and its latest refresh outcome in one snapshot."""
        with self.store.read_snapshot() as db:
            return {
                kind: get_record(db, f"cve-{kind}:{cve_id}") for kind in ("reference", "refresh")
            }

    @staticmethod
    def selection_available(db, record):
        """Check exact saved source selections without taking over case adoption."""
        return any(
            row and same_selection(json.loads(row["payload"]), record)
            for row in (
                get_record(db, selection_key(record)),
                get_record(db, "cve-reference:" + record["id"]),
            )
        )

    @staticmethod
    def current_states(db, cve_ids):
        """Return current reference/intelligence states in the caller's transaction."""
        from ..intelligence_index import bank_index

        cve_ids = tuple(cve_ids)
        bank = bank_index(None, db, cve_ids)
        states = []
        for cve_id in cve_ids:
            row = get_record(db, "cve-reference:" + cve_id)
            if row:
                states.append(json.loads(row["payload"]))
            if cve_id in bank:
                states.append(bank[cve_id])
        return states

    def risk_state(self, key):
        with self.store.read_snapshot() as db:
            records = Records(db)
            return {
                kind: records.one("SELECT * FROM cache WHERE key=?", (kind + ":" + key,))
                for kind in ("risk", "risk-proof", "risk-attempt", "risk-refresh")
            }

    @staticmethod
    def put(db, key, value, stamp=None, *, immutable=False):
        if revision_key(key) and available(db):
            register_revision(db, key, dump(value), stamp or now())
            return
        sql = "INSERT OR IGNORE" if immutable else "INSERT OR REPLACE"
        db.execute(f"{sql} INTO cache VALUES(?,?,?)", (key, dump(value), stamp or now()))

    def record_attempt(self, db, item):
        # Unique acquisition identifiers intentionally reject accidental reuse.
        key = "acquisition-version:" + item["id"]
        if available(db):
            register_revision(db, key, dump(item), item["completed_at"], strict_insert=True)
        else:
            db.execute("INSERT INTO cache VALUES(?,?,?)", (key, dump(item), item["completed_at"]))

    def save_risk(self, db, key, raw, source, attempt):
        stamp = source["retrieved_at"]
        self.put(db, "risk:" + key, raw, stamp)
        self.put(db, "risk-proof:" + key, source, stamp)
        self.put(
            db, "risk-version:" + source["revision_id"], {"source": source}, stamp, immutable=True
        )
        self.put(db, "risk-attempt:" + key, attempt, attempt["completed_at"])
        db.execute("DELETE FROM cache WHERE key=?", ("risk-refresh:" + key,))

    def save_reference(self, db, cve_id, result):
        self.put(db, "cve-reference:" + cve_id, result)
        db.execute("DELETE FROM cache WHERE key=?", ("cve-refresh:" + cve_id,))
        if result.get("revision_id"):
            self.put(
                db,
                "cve-version:" + result["revision_id"],
                result,
                result["retrieved_at"] or now(),
                immutable=True,
            )

    def publish_intelligence(self, db, cve_id, result):
        revision = result["intelligence_revision_id"]
        self.put(db, "intelligence-version:" + revision, result, immutable=True)
        self.put(db, "intelligence-latest:" + cve_id, {"revision_id": revision})
