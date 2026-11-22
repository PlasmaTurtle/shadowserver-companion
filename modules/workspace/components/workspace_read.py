"""Bounded SQLite read snapshots shared by diagnostics and cleanup review."""

from contextlib import contextmanager
from pathlib import Path
import sqlite3
import time


@contextmanager
def readonly(path):
    """Include committed WAL pages; immutable=1 would silently omit them."""
    db = sqlite3.connect(Path(path).absolute().as_uri() + "?mode=ro", uri=True, timeout=2)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA query_only=ON")
        deadline = time.monotonic() + 60
        db.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
        db.execute("BEGIN")
        yield db
    finally:
        db.close()
