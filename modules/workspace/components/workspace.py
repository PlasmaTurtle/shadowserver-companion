"""SQLite connection, workspace paths and caller-owned transactions.

Opening a Workspace initializes its schema and defaults. Report recovery and
entity/workflow operations belong to services composed by the Store facade.
"""

from __future__ import annotations
import json
import sqlite3
import threading
from pathlib import Path
from contextlib import contextmanager, closing
from .primitives import dump, now
from ..databases.workspace_defaults import DEFAULT_SETTINGS
from modules.library.components.content_bank import seed_defaults


class Workspace:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        for folder in (
            "inbox",
            "originals",
            "evidence",
            "reports",
            "exports",
            "backups",
            "closures",
        ):
            (self.root / folder).mkdir(exist_ok=True)
        self.db = self.root / "workbench.sqlite3"
        self.lock = threading.RLock()
        self.after_commit = []
        self.migrate()
        with self.transaction() as db:
            db.execute(
                "INSERT OR IGNORE INTO settings VALUES (?,?)", ("profile", dump(DEFAULT_SETTINGS))
            )
            seed_defaults(db)
            db.execute("UPDATE imports SET status='queued',stage='Resuming' WHERE status='running'")

    def migrate(self):
        from ..databases.migrations import migrate

        with closing(self.connect()) as db:
            before = db.execute("PRAGMA user_version").fetchone()[0]
            migrate(db, self.root / "backups")
            changed = before != db.execute("PRAGMA user_version").fetchone()[0]
            db.execute("PRAGMA journal_mode=WAL")
        if changed:
            from .planner_maintenance import run

            run(self, force=True)

    def connect(self):
        # Pin the existing explicit BEGIN/commit contract rather than relying
        # on Python's default transaction mode remaining unchanged.
        db = sqlite3.connect(self.db, timeout=15, autocommit=sqlite3.LEGACY_TRANSACTION_CONTROL)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=15000")
        return db

    @contextmanager
    def read_snapshot(self):
        """Related SELECTs see one committed state without reserving a writer."""
        with closing(self.connect()) as db:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            try:
                yield db
            finally:
                db.rollback()

    @contextmanager
    def transaction(self):
        with self.lock:
            db = self.connect()
            try:
                db.execute("BEGIN IMMEDIATE")
                yield db
                db.commit()
                changes = db.total_changes
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()
        from .planner_maintenance import after_commit

        after_commit(self, changes)
        for callback in self.after_commit:
            callback()

    def all(self, sql, args=()):
        with closing(self.connect()) as db:
            return [dict(row) for row in db.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        result = self.all(sql, args)
        return result[0] if result else None

    def settings(self, db=None):
        row = (
            db.execute("SELECT value FROM settings WHERE key=?", ("profile",)).fetchone()
            if db is not None
            else self.one("SELECT value FROM settings WHERE key=?", ("profile",))
        )
        values = {
            **DEFAULT_SETTINGS,
            **json.loads(row["value"]),
        }
        # Old workspaces may retain these historical preferences on disk.
        # Do not advertise or carry them into a new intake policy.
        values.pop("com_only", None)
        values.pop("exclude_numeric_roots", None)
        return values

    def log(self, db, action, detail, lead_id=None, case_id=None, *, metadata=None):
        profile = db.execute("SELECT value FROM settings WHERE key='profile'").fetchone()
        actor = str(json.loads(profile[0]).get("analyst_name") or "").strip() if profile else ""
        context = dict(metadata or {})
        if actor:
            context.setdefault("actor_basis", "configured_operator_profile")
        if case_id:
            revision = db.execute(
                "SELECT version,draft_revision FROM cases WHERE id=?", (case_id,)
            ).fetchone()
            if revision:
                context.setdefault("case_version", revision["version"])
                context.setdefault("draft_revision", revision["draft_revision"])
        db.execute(
            "INSERT INTO events(lead_id,action,detail,created_at,case_id,actor,metadata) VALUES(?,?,?,?,?,?,?)",
            (lead_id, action, detail, now(), case_id, actor, dump(context)),
        )

    def path(self, relative):
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Invalid workspace path")
        return path
