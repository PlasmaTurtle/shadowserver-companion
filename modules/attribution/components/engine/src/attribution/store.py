"""SQLite persistence shared by the CLI and importing applications."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path

from .models import AttributionResult, ResponseSnapshot, json_bytes
from .migrations import migrate, result_metadata


class EvidenceStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys=ON")
        try:
            migrate(self._db, self.path)
            self._db.execute("PRAGMA journal_mode=WAL")
        except Exception:
            self._db.close()
            raise

    def close(self):
        with self._lock:
            self._db.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def save_snapshot(self, snapshot: ResponseSnapshot):
        with self._lock, self._db:
            self._db.execute("INSERT INTO snapshots VALUES(?,?,?)", (
                snapshot.snapshot_id, json_bytes(snapshot.metadata()).decode(), snapshot.body))

    def snapshot(self, snapshot_id: str) -> ResponseSnapshot:
        with self._lock:
            row = self._db.execute("SELECT * FROM snapshots WHERE id=?", (snapshot_id,)).fetchone()
        if row is None:
            raise KeyError(f"Snapshot not found: {snapshot_id}")
        meta = json.loads(row["metadata"])
        size = meta.pop("body_size")
        body = bytes(row["body"])
        if len(body) != size or hashlib.sha256(body).hexdigest() != meta["body_sha256"]:
            raise ValueError(f"Evidence integrity check failed: {snapshot_id}")
        return ResponseSnapshot(body=body, **meta)

    def cached(self, key: str) -> list[ResponseSnapshot] | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM cache WHERE key=?", (key,)).fetchone()
        if row is None or row["expires"] <= time.time():
            return None
        return [self.snapshot(sid) for sid in json.loads(row["snapshot_ids"])]

    def cache(self, key: str, snapshots: list[ResponseSnapshot], ttl: float):
        with self._lock, self._db:
            if ttl <= 0:
                self._db.execute("DELETE FROM cache WHERE key=?", (key,))
            else:
                self._db.execute("INSERT OR REPLACE INTO cache VALUES(?,?,?)", (
                    key, json.dumps([s.snapshot_id for s in snapshots]), time.time() + ttl))

    def cooldown(self, authority: str) -> float:
        with self._lock:
            row = self._db.execute("SELECT retry_at FROM cooldowns WHERE authority=?", (authority,)).fetchone()
        return row[0] if row else 0.0

    def set_cooldown(self, authority: str, retry_at: float):
        with self._lock, self._db:
            self._db.execute("""INSERT INTO cooldowns VALUES(?,?)
              ON CONFLICT(authority) DO UPDATE SET retry_at=max(retry_at,excluded.retry_at)""",
                             (authority, retry_at))

    def save_result(self, result: AttributionResult):
        payload = json_bytes(result.to_dict()).decode()
        with self._lock, self._db:
            self._db.execute("INSERT INTO results(id,created_at,payload,root_domain,status,policy_version) VALUES(?,?,?,?,?,?)", (
                result.result_id, result.evaluated_at, payload, *result_metadata(payload)))

    def result(self, result_id: str) -> dict:
        with self._lock:
            row = self._db.execute("SELECT payload FROM results WHERE id=?", (result_id,)).fetchone()
        if row is None:
            raise KeyError(f"Result not found: {result_id}")
        return json.loads(row[0])

    def stats(self) -> dict:
        with self._lock:
            return {table: self._db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                    for table in ("snapshots", "cache", "results")}

    def history(self, limit=20, *, root_domain=None, status=None) -> list[dict]:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("History limit must be between 1 and 1000")
        clauses, args = [], []
        if root_domain is not None:
            from .matching import normalize_domain
            clauses.append('root_domain=?')
            args.append(normalize_domain(root_domain))
        if status is not None:
            if status not in ('matched','review','no_match','incomplete','deferred','no_eligible_ip'):
                raise ValueError('Unknown attribution status')
            clauses.append('status=?')
            args.append(status)
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        sql = """SELECT id AS result_id,root_domain,status,created_at AS evaluated_at,
          json_extract(payload,'$.matched_entry_id') AS matched_entry_id,
          json_extract(payload,'$.matched_ip') AS matched_ip
          FROM results""" + where + ' ORDER BY created_at DESC,rowid DESC LIMIT ?'
        with self._lock:
            return [dict(row) for row in self._db.execute(sql, (*args, limit))]
