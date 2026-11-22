"""Local, analyst-maintained deconfliction entries for Associate."""


def schema(db):
    db.execute(
        """CREATE TABLE intake_deconfliction(
          id TEXT PRIMARY KEY, scope TEXT NOT NULL CHECK(scope IN ('domain','host')),
          identifier TEXT NOT NULL, external_reference TEXT NOT NULL, reason TEXT NOT NULL,
          updated_at TEXT NOT NULL, UNIQUE(scope,identifier))"""
    )
    # Re-rank active government work under its own saved evidence and weights.
    # Historical reports, dismissed rows and review decisions stay immutable.
    candidates = db.execute(
        """SELECT q.id FROM lead_queue q WHERE q.qualified=1
        AND q.status IN ('pending','deferred') AND q.superseded_by='' AND q.suppression_reason=''
        AND EXISTS (SELECT 1 FROM json_each(q.payload) e
            WHERE lower(rtrim(json_extract(e.value,'$.source.fields.hostname'),'.')) LIKE '%.gov')"""
    ).fetchall()
    if candidates:
        import json
        import sqlite3
        from modules.accretion.components.evaluation import evaluate_scope
        from modules.accretion.components.evaluated_lead import EvaluationScope
        from modules.leads.components.lead_frontier import preview_current

        previous_factory = db.row_factory
        db.row_factory = sqlite3.Row
        try:
            for (identity,) in candidates:
                scope = preview_current(db, identity)
                if scope and scope["entries"]:
                    score = evaluate_scope(EvaluationScope(scope)).payload()
                    db.execute(
                        "UPDATE lead_queue SET intake_score=? WHERE id=?",
                        (json.dumps(score), scope["winner"]["id"]),
                    )
        finally:
            db.row_factory = previous_factory
