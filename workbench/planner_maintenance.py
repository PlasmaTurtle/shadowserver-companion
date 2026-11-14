"""Bounded, best-effort planner statistics maintenance after committed writes."""

from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import threading
import time

_MIN_CHANGES = 10000
_MIN_INTERVAL = 60
_LOCK = threading.Lock()


def _path(root):
    return Path(root) / "planner-maintenance.json"


def status(root):
    """Operational metadata only; this read never opens or modifies SQLite."""
    try:
        value = json.loads(_path(root).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {"state": "not_run"}
    except OSError, ValueError:
        return {"state": "not_run"}


def run(store, force=False):
    """Use an independent connection; busy/error cannot undo original evidence."""
    if not _LOCK.acquire(blocking=False):
        return {"state": "busy", "reason": "Planner maintenance already running"}
    try:
        previous = status(store.root)
        current = time.time()
        try:
            last_attempt = float(previous.get("attempt_epoch", 0))
        except TypeError, ValueError:
            last_attempt = 0
        if not force and current - last_attempt < _MIN_INTERVAL:
            return {**previous, "deferred": True}
        result = {
            "state": "complete",
            "attempt_epoch": current,
            "attempted_at": datetime.now(timezone.utc).isoformat(),
            "policy": "Bounded PRAGMA optimize after schema change or material writes",
            "analysis_limit": 1000,
        }
        started = time.monotonic()
        try:
            with closing(sqlite3.connect(store.db, timeout=0.25)) as db:
                db.execute("PRAGMA busy_timeout=250")
                db.execute("PRAGMA analysis_limit=1000")
                db.set_progress_handler(lambda: int(time.monotonic() - started > 1.0), 1000)
                db.execute("PRAGMA optimize=0x10002").fetchall()
                db.commit()
                db.set_progress_handler(None, 0)
                exists = db.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='sqlite_stat1'"
                ).fetchone()
                result["stat_rows"] = (
                    db.execute("SELECT count(*) FROM sqlite_stat1").fetchone()[0] if exists else 0
                )
                result["completed_at"] = result["attempted_at"]
        except sqlite3.Error as error:
            result.update(state="deferred", reason=str(error))
        result["elapsed_ms"] = round((time.monotonic() - started) * 1000, 2)
        try:
            destination = _path(store.root)
            temporary = destination.with_suffix(f".{os.getpid()}.tmp")
            temporary.write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
            temporary.replace(destination)
        except OSError:
            pass
        return result
    finally:
        _LOCK.release()


def after_commit(store, changes):
    """Called outside the caller's transaction and application writer lock."""
    store._planner_changes = getattr(store, "_planner_changes", 0) + changes
    if store._planner_changes >= _MIN_CHANGES:
        result = run(store, force=not getattr(store, "_planner_material_maintained", False))
        if result.get("state") == "complete" and not result.get("deferred"):
            store._planner_changes = 0
            store._planner_material_maintained = True
