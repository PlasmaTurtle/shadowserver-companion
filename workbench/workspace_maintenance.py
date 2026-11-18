"""Conservative cleanup: expire reuse pointers, never their retained evidence."""

from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import time

from .workspace_read import readonly


def _eligible(db, cutoff):
    if db.execute("PRAGMA user_version").fetchone()[0] != 2:
        raise ValueError("Attribution schema must be compatible before cleanup")
    return [
        tuple(row)
        for row in db.execute(
            "SELECT key,snapshot_ids,expires FROM cache WHERE expires<=? ORDER BY key", (cutoff,)
        )
    ]


def _summary(rows, cutoff):
    encoded = json.dumps(rows, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return {
        "available": True,
        "cutoff": cutoff,
        "token": hashlib.sha256(encoded.encode()).hexdigest(),
        "lookup_pointers": len(rows),
        "estimated_payload_bytes": sum(
            len(key.encode()) + len(ids.encode()) + 8 for key, ids, _ in rows
        ),
        "files_removed": 0,
        "policy": "Only expired attribution lookup pointers are disposable. Captures, results, revisions, reports and original files are retained.",
        "disk_space_note": "Deleting pointers makes database pages reusable. File size may not shrink; offline compaction is a separate action.",
    }


def plan(root, *, cutoff=None):
    cutoff = time.time() if cutoff is None else cutoff
    if (
        not isinstance(cutoff, (float, int))
        or not math.isfinite(cutoff)
        or cutoff <= 0
        or cutoff > time.time()
    ):
        raise ValueError("Cleanup review time is invalid")
    path = Path(root) / "attribution.sqlite3"
    if not path.exists():
        return _summary([], cutoff)
    if path.is_symlink():
        raise ValueError("Cleanup cannot follow a database link")
    with readonly(path) as db:
        return _summary(_eligible(db, cutoff), cutoff)


def cleanup(root, *, cutoff, token):
    """Caller owns the workspace operation gate; recheck under the SQLite lock."""
    expected = plan(root, cutoff=cutoff)
    if expected["token"] != token:
        raise ValueError("Cleanup candidates changed. Review a fresh cleanup estimate.")
    path = Path(root) / "attribution.sqlite3"
    if not path.exists():
        return {**expected, "removed": 0}
    with closing(sqlite3.connect(path, timeout=2)) as db:
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE")
            reviewed = _summary(_eligible(db, cutoff), cutoff)
            if reviewed["token"] != token:
                raise ValueError("Cleanup candidates changed. Review a fresh cleanup estimate.")
            if (
                db.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
                or db.execute("PRAGMA foreign_key_check").fetchone()
            ):
                raise ValueError("Repair database integrity before cleanup")
            # Do not delete snapshots or results, even if no current lookup points
            # to them: case/report/contact history can still pin those captures.
            removed = db.execute("DELETE FROM cache WHERE expires<=?", (cutoff,)).rowcount
            if removed != reviewed["lookup_pointers"]:
                raise ValueError("Cleanup changed during application; nothing was removed")
            db.commit()
            return {**reviewed, "removed": removed}
        except BaseException:
            db.rollback()
            raise
