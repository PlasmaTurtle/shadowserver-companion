"""Per-notification condition scope without changing original observations."""

import json
from .primitives import dump
from .cve_state import excluded_cves


def notified_cve_exclusions(db, entity_id):
    """Read each sent case's saved decision once; historical delivery stays intact."""
    return {
        row["case_id"]: excluded_cves({"cve_dispositions": json.loads(row["dispositions"] or "{}")})
        for row in db.execute(
            """SELECT DISTINCT r.case_id,json_extract(c.draft,'$.cve_dispositions') dispositions
            FROM reports r JOIN cases c ON c.id=r.case_id
            WHERE r.entity_id=? AND r.sent_at IS NOT NULL""",
            (entity_id,),
        )
    }


def project(entry, conditions):
    return {
        **entry,
        "normalized": {
            **entry.get("normalized", {}),
            "case_condition_scope": True,
            "active_conditions": conditions,
            "active_cves": [value for value in conditions if value.startswith("CVE-")],
        },
    }


def pin(db, case_id, intake_lead_id=None, *, entry_ids=None):
    """Pin selected conditions; supporting attribution rows add no new findings."""
    from .awareness import mark_handled, source_key

    queued = {}
    if intake_lead_id:
        lead = db.execute(
            "SELECT q.payload,i.sha256 FROM lead_queue q JOIN imports i ON i.id=q.import_id WHERE q.id=?",
            (intake_lead_id,),
        ).fetchone()
        if lead:
            payload = json.loads(lead["payload"])
            queued = {source_key(entry, lead["sha256"]): entry for entry in payload}
    selected = set(entry_ids) if entry_ids is not None else None
    rows = db.execute(
        "SELECT e.id,e.payload FROM entries e JOIN case_entries ce ON ce.entry_id=e.id WHERE ce.case_id=?",
        (case_id,),
    ).fetchall()
    for row in rows:
        if selected is not None and row["id"] not in selected:
            continue
        entry = {"id": row["id"], **json.loads(row["payload"])}
        if intake_lead_id:
            normalized = queued.get(row["id"], {}).get("normalized", {})
            conditions = normalized.get("active_conditions")
            if row["id"] not in queued:
                conditions = []
            if conditions is not None:
                db.execute(
                    "INSERT OR IGNORE INTO case_entry_conditions VALUES(?,?,?)",
                    (case_id, row["id"], dump(conditions)),
                )
                saved = db.execute(
                    "SELECT conditions FROM case_entry_conditions WHERE case_id=? AND entry_id=?",
                    (case_id, row["id"]),
                ).fetchone()
                entry = project(entry, json.loads(saved["conditions"]))
        mark_handled(db, entry, case_id)


def overlay(db, case_id, entries):
    scopes = {
        row["entry_id"]: json.loads(row["conditions"])
        for row in db.execute("SELECT * FROM case_entry_conditions WHERE case_id=?", (case_id,))
    }
    return [
        project(entry, scopes[entry["id"]]) if entry["id"] in scopes else entry for entry in entries
    ]
