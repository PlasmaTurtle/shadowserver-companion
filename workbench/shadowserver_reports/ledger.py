"""Optional local synchronization history. No API keys or download capabilities.

Content revisions and acquisition observations are separate: a refreshed download
identifier is provenance, not a new report revision. An interrupted run remains
visible as ``running``; subsequent runs recheck the catalog and resume safely.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Iterator
import uuid

from .errors import ConfigurationError, StorageError
from .models import DownloadReceipt, ReportDescriptor, ReportSelection


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def selection_key(selection: ReportSelection) -> str:
    """Stable scope identity; allow extending the end while retaining progress.

    The lower bound is included so a later request to backfill an earlier start
    cannot silently inherit a checkpoint that did not cover those dates.
    """
    value = [selection.start.isoformat(), sorted(set(selection.subscriptions)),
             sorted(set(selection.types))]
    return hashlib.sha256(json.dumps(value, separators=(",", ":")).encode()).hexdigest()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, profile TEXT NOT NULL, scope_key TEXT NOT NULL,
    requested_start TEXT NOT NULL, requested_end TEXT NOT NULL,
    effective_start TEXT NOT NULL, effective_end TEXT NOT NULL,
    status TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT,
    reason_code TEXT
);
CREATE TABLE IF NOT EXISTS attempts (
    id TEXT PRIMARY KEY, run_id TEXT REFERENCES runs(id), profile TEXT NOT NULL,
    logical_id TEXT NOT NULL, source_fingerprint TEXT NOT NULL,
    status TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT,
    reason_code TEXT
);
CREATE TABLE IF NOT EXISTS revisions (
    profile TEXT NOT NULL, logical_id TEXT NOT NULL, sha256 TEXT NOT NULL,
    path TEXT NOT NULL, size_bytes INTEGER NOT NULL, original_filename TEXT NOT NULL,
    subscription TEXT NOT NULL, report_type TEXT NOT NULL, report_date TEXT NOT NULL,
    first_retrieved_at TEXT NOT NULL, schema_reference TEXT, validation TEXT NOT NULL,
    PRIMARY KEY (profile, logical_id, sha256)
);
CREATE TABLE IF NOT EXISTS observations (
    id TEXT PRIMARY KEY, profile TEXT NOT NULL, logical_id TEXT NOT NULL,
    sha256 TEXT NOT NULL, source_fingerprint TEXT NOT NULL,
    retrieved_at TEXT NOT NULL, reused INTEGER NOT NULL,
    attempt_id TEXT REFERENCES attempts(id), receipt_json TEXT NOT NULL,
    FOREIGN KEY (profile, logical_id, sha256)
        REFERENCES revisions(profile, logical_id, sha256)
);
CREATE TABLE IF NOT EXISTS checkpoints (
    profile TEXT NOT NULL, scope_key TEXT NOT NULL, scanned_through TEXT NOT NULL,
    updated_at TEXT NOT NULL, run_id TEXT NOT NULL REFERENCES runs(id),
    PRIMARY KEY (profile, scope_key)
);
CREATE INDEX IF NOT EXISTS attempts_profile ON attempts(profile, logical_id);
CREATE INDEX IF NOT EXISTS observations_profile ON observations(profile, logical_id);
"""


class Ledger:
    """SQLite ledger isolated from Companion; usable as a context manager.

    ``profile`` identifies a credential configuration, never an API key. Keep the
    database in the analyst's private data directory alongside downloaded files.
    A profile must not be reassigned to a different organization/account.
    """

    def __init__(self, path: str | Path, profile: str = "default"):
        if not isinstance(profile, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", profile):
            raise ConfigurationError("Invalid ledger profile name.")
        self.path = Path(path)
        self.profile = profile
        self._closed = False
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(self.path, timeout=5)
            self._db.row_factory = sqlite3.Row
            self._db.execute("PRAGMA foreign_keys = ON")
            version = self._db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                self._db.close()
                self._closed = True
                raise StorageError("Unsupported synchronization ledger version.")
            self._db.executescript(_SCHEMA)
            self._db.execute("PRAGMA user_version = 1")
            self._db.commit()
        except (OSError, sqlite3.Error):
            if hasattr(self, "_db"):
                self._db.close()
            self._closed = True
            raise StorageError("Unable to open synchronization ledger.") from None

    def __enter__(self) -> "Ledger":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        if not self._closed:
            try:
                self._db.close()
            except sqlite3.Error:
                raise StorageError("Unable to close synchronization ledger.") from None
            finally:
                self._closed = True

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        if self._closed:
            raise StorageError("Synchronization ledger is closed.")
        try:
            with self._db:
                yield self._db
        except sqlite3.Error:
            raise StorageError("Synchronization ledger operation failed.") from None

    def get_checkpoint(self, selection: ReportSelection) -> str | None:
        with self._transaction() as db:
            row = db.execute(
                "SELECT scanned_through FROM checkpoints WHERE profile=? AND scope_key=?",
                (self.profile, selection_key(selection)),
            ).fetchone()
        return row[0] if row else None

    def begin_run(self, selection: ReportSelection,
                  effective_selection: ReportSelection | None = None) -> str:
        effective = effective_selection or selection
        run_id = uuid.uuid4().hex
        with self._transaction() as db:
            db.execute(
                "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, self.profile, selection_key(selection),
                 selection.start.isoformat(), selection.end.isoformat(),
                 effective.start.isoformat(), effective.end.isoformat(),
                 "running", _utc_now(), None, None),
            )
        return run_id

    def begin_attempt(self, report: ReportDescriptor, run_id: str | None = None) -> str:
        attempt_id = uuid.uuid4().hex
        with self._transaction() as db:
            if run_id is not None:
                self._require_run(db, run_id, "running")
            db.execute(
                "INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?)",
                (attempt_id, run_id, self.profile, report.logical_id,
                 report.source_fingerprint, "running", _utc_now(), None, None),
            )
        return attempt_id

    def record_receipt(self, receipt: DownloadReceipt,
                       attempt_id: str | None = None) -> None:
        """Atomically store a content revision, provenance, and attempt success."""
        with self._transaction() as db:
            if attempt_id is not None:
                row = db.execute(
                    "SELECT logical_id, source_fingerprint, status FROM attempts "
                    "WHERE id=? AND profile=?", (attempt_id, self.profile),
                ).fetchone()
                if (row is None or row[0] != receipt.logical_id or
                        row[1] != receipt.source_fingerprint or row[2] != "running"):
                    raise StorageError("Download receipt does not match an active attempt.")
            db.execute(
                "INSERT OR IGNORE INTO revisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (self.profile, receipt.logical_id, receipt.sha256, receipt.path,
                 receipt.size_bytes, receipt.original_filename, receipt.subscription,
                 receipt.report_type, receipt.report_date, receipt.retrieved_at,
                 receipt.schema_reference, receipt.validation),
            )
            db.execute(
                "INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?)",
                (uuid.uuid4().hex, self.profile, receipt.logical_id, receipt.sha256,
                 receipt.source_fingerprint, receipt.retrieved_at, int(receipt.reused),
                 attempt_id, json.dumps(receipt.public_dict(), ensure_ascii=True, allow_nan=False)),
            )
            if attempt_id is not None:
                db.execute(
                    "UPDATE attempts SET status='complete', finished_at=? WHERE id=? AND profile=?",
                    (_utc_now(), attempt_id, self.profile),
                )

    def fail_attempt(self, attempt_id: str, reason_code: str) -> None:
        code = self._safe_code(reason_code)
        with self._transaction() as db:
            result = db.execute(
                "UPDATE attempts SET status='failed', finished_at=?, reason_code=? "
                "WHERE id=? AND profile=? AND status='running'",
                (_utc_now(), code, attempt_id, self.profile),
            )
            if result.rowcount != 1:
                raise StorageError("Unable to finish the requested download attempt.")

    def finish_run(self, run_id: str, status: str, reason_code: str | None = None) -> None:
        if status not in {"partial", "cancelled"}:
            raise ConfigurationError("Use complete_run to complete a synchronization run.")
        code = self._safe_code(reason_code) if reason_code else None
        with self._transaction() as db:
            self._require_run(db, run_id, "running")
            db.execute(
                "UPDATE runs SET status=?, finished_at=?, reason_code=? WHERE id=? AND profile=?",
                (status, _utc_now(), code, run_id, self.profile),
            )

    def complete_run(self, run_id: str, selection: ReportSelection) -> str:
        """Finish and checkpoint atomically, only after all attempts succeeded.

        The checkpoint denotes a completed scan, not proof that Shadowserver has
        delivered every report for a day. Synchronizers must keep a lookback.
        """
        stamp = _utc_now()
        requested = selection.end.isoformat()
        with self._transaction() as db:
            row = self._require_run(db, run_id, "running")
            if (row["scope_key"] != selection_key(selection) or
                    row["requested_end"] != requested):
                raise StorageError("Synchronization checkpoint does not match its run.")
            unfinished = db.execute(
                "SELECT COUNT(*) FROM attempts WHERE run_id=? AND status!='complete'",
                (run_id,),
            ).fetchone()[0]
            if unfinished:
                raise StorageError("An incomplete synchronization cannot advance its checkpoint.")
            db.execute(
                "UPDATE runs SET status='complete', finished_at=? WHERE id=? AND profile=?",
                (stamp, run_id, self.profile),
            )
            # Historical scans must not move an existing later checkpoint back.
            db.execute(
                "INSERT INTO checkpoints VALUES (?,?,?,?,?) "
                "ON CONFLICT(profile,scope_key) DO UPDATE SET "
                "scanned_through=excluded.scanned_through, updated_at=excluded.updated_at, "
                "run_id=excluded.run_id WHERE excluded.scanned_through>=checkpoints.scanned_through",
                (self.profile, selection_key(selection), requested, stamp, run_id),
            )
            checkpoint = db.execute(
                "SELECT scanned_through FROM checkpoints WHERE profile=? AND scope_key=?",
                (self.profile, selection_key(selection)),
            ).fetchone()[0]
        return checkpoint

    def statistics(self) -> dict[str, int]:
        """Profile-local counts for diagnostics; no capabilities or private payloads."""
        with self._transaction() as db:
            result = {
                name: db.execute(f"SELECT COUNT(*) FROM {name} WHERE profile=?", (self.profile,)).fetchone()[0]
                for name in ("runs", "attempts", "revisions", "observations", "checkpoints")
            }
        return result

    def revisions(self, logical_id: str) -> list[dict]:
        with self._transaction() as db:
            rows = db.execute(
                "SELECT * FROM revisions WHERE profile=? AND logical_id=? ORDER BY first_retrieved_at,sha256",
                (self.profile, logical_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def _require_run(self, db: sqlite3.Connection, run_id: str, status: str) -> sqlite3.Row:
        row = db.execute("SELECT * FROM runs WHERE id=? AND profile=?", (run_id, self.profile)).fetchone()
        if row is None or row["status"] != status:
            raise StorageError("Synchronization run is not active for this profile.")
        return row

    @staticmethod
    def _safe_code(value: str) -> str:
        # Only controlled error codes, never exception text or response payloads.
        permitted = {"authentication_error", "authorization_error", "protocol_error",
                     "transport_error", "download_error", "incomplete_error", "cancelled",
                     "deadline_exceeded", "budget_exceeded", "storage_error",
                     "configuration_error", "partial_catalog", "unknown_catalog",
                     "operation_failed", "interrupted"}
        return value if value in permitted else "operation_failed"
