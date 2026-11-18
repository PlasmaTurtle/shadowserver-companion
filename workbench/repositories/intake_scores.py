"""Persist immutable intake decisions at the case scope boundary.

Caller-owned transactions keep priority changes atomic with scope edits.
This repository performs no scoring, catalog reads, or workflow transitions.
"""

import json

from ..primitives import dump
from ..intake.identity import signature


def mark_handled(db, case_id, ids):
    for oid in ids:
        row = db.execute("SELECT payload,lead_id FROM entries WHERE id=?", (oid,)).fetchone()
        if row:
            db.execute(
                "UPDATE intake_observations SET handled_case_id=? WHERE entity_id=? AND signal_key=?",
                (case_id, row["lead_id"], signature(json.loads(row["payload"]))),
            )


def pin_case_score(db, case_id, *, entry_ids=(), source_case_id=None, lead_id=None):
    """Pin decisions for newly selected scope, retaining earlier source snapshots.

    Supporting attribution rows may come from another notification and must
    not silently contribute that notification's outreach priority.
    """
    mark_handled(db, case_id, entry_ids)
    prior = db.execute("SELECT intake_score FROM cases WHERE id=?", (case_id,)).fetchone()
    snapshot = json.loads(prior["intake_score"]) if prior else {}
    sources = {s["lead_id"]: s for s in snapshot.get("source_scores", [])}
    if source_case_id:
        source = db.execute(
            "SELECT intake_score FROM cases WHERE id=?", (source_case_id,)
        ).fetchone()
        if source:
            for item in json.loads(source["intake_score"]).get("source_scores", []):
                sources.setdefault(item["lead_id"], item)
    if lead_id:
        # Re-evaluation keeps original entry IDs/import provenance. Pin the
        # analyst-selected queue decision, not an older evaluation of those IDs.
        row = db.execute(
            "SELECT id,import_id,root_domain,intake_score FROM lead_queue WHERE id=?",
            (lead_id,),
        ).fetchone()
        if row:
            sources.setdefault(
                row["id"],
                {
                    "lead_id": row["id"],
                    "import_id": row["import_id"],
                    "root_domain": row["root_domain"],
                    "intake_score": json.loads(row["intake_score"]) or None,
                },
            )
    ids = [] if lead_id else list(dict.fromkeys(entry_ids))
    for start in range(0, len(ids), 500):
        batch = ids[start : start + 500]
        rows = db.execute(
            """SELECT DISTINCT q.id,q.import_id,q.root_domain,q.intake_score
            FROM entries e JOIN lead_queue q
            ON q.import_id=e.import_id AND q.root_domain=e.root_domain
            WHERE e.id IN ("""
            + ",".join("?" for _ in batch)
            + ") ORDER BY q.id",
            batch,
        )
        for row in rows:
            sources.setdefault(
                row["id"],
                {
                    "lead_id": row["id"],
                    "import_id": row["import_id"],
                    "root_domain": row["root_domain"],
                    "intake_score": json.loads(row["intake_score"]) or None,
                },
            )
    scored = [source for source in sources.values() if source["intake_score"]]
    if not scored:
        return
    strongest = max(scored, key=lambda source: source["intake_score"]["aggregate"])
    snapshot = {
        **strongest["intake_score"],
        "source_lead_id": strongest["lead_id"],
        "source_scores": [sources[key] for key in sorted(sources)],
        "unscored_sources": len(sources) - len(scored),
    }
    db.execute("UPDATE cases SET intake_score=? WHERE id=?", (dump(snapshot), case_id))
