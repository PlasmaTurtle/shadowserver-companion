"""Append-only section records. Mutation methods use the caller's connection.

No method opens or commits a write transaction. Services can atomically update
reviews, case revisions and event history using the same SQLite connection.
"""

from modules.workspace.components.primitives import now, uid
import modules.workspace.components.compact_json as compact_json


class SectionReviewRepository:
    def __init__(self, store):
        self.store = store

    def active(self, case_id, db=None):
        sql = """SELECT v.* FROM section_validations v WHERE v.id=(
          SELECT e.validation_id FROM section_events e WHERE e.case_id=v.case_id
          AND e.section_key=v.section_key AND e.action IN ('validated','reopened')
          ORDER BY e.id DESC LIMIT 1) AND v.case_id=?"""
        rows = db.execute(sql, (case_id,)).fetchall() if db else self.store.all(sql, (case_id,))
        return {r["section_key"]: dict(r) for r in rows}

    def history(self, case_id):
        return self.store.all(
            """SELECT e.*,v.content_hash,
            CASE WHEN e.action='stale' THEN 'system' ELSE 'analyst' END AS actor_kind
            FROM section_events e LEFT JOIN section_validations v ON v.id=e.validation_id
            WHERE e.case_id=? ORDER BY e.id""",
            (case_id,),
        )

    def snapshots(self, case_id):
        rows = self.store.all(
            "SELECT * FROM section_validations WHERE case_id=? ORDER BY validated_at,rowid",
            (case_id,),
        )
        resources = {}
        for row in rows:
            row["snapshot"] = compact_json.loads(row.pop("snapshot_json"), resource_pool=resources)
        return rows

    def last_revision(self, case_id, key, db=None):
        sql = "SELECT COALESCE(MAX(revision),0) AS n FROM section_validations WHERE case_id=? AND section_key=?"
        row = (
            db.execute(sql, (case_id, key)).fetchone()
            if db
            else self.store.one(sql, (case_id, key))
        )
        return row["n"]

    def event(
        self,
        db,
        case_id,
        key,
        action,
        actor,
        reason,
        revision,
        validation_id=None,
        dependency_hash="",
    ):
        stamp = now()
        db.execute(
            """INSERT INTO section_events(case_id,section_key,action,actor,created_at,reason,revision,validation_id,dependency_hash)
          VALUES(?,?,?,?,?,?,?,?,?)""",
            (case_id, key, action, actor, stamp, reason, revision, validation_id, dependency_hash),
        )
        return stamp

    def save_validation(self, db, case_id, key, actor, frozen):
        revision = self.last_revision(case_id, key, db) + 1
        validation_id, stamp = uid(), now()
        db.execute(
            "INSERT INTO section_validations VALUES(?,?,?,?,?,?,?,?)",
            (
                validation_id,
                case_id,
                key,
                revision,
                stamp,
                actor,
                frozen["content_hash"],
                compact_json.dumps(frozen),
            ),
        )
        db.execute(
            """INSERT INTO section_events(case_id,section_key,action,actor,created_at,revision,validation_id)
            VALUES(?,?,?,?,?,?,?)""",
            (case_id, key, "validated", actor, stamp, revision, validation_id),
        )
        return stamp
