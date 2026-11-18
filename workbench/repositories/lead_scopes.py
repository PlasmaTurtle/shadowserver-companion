"""Read the current qualified queue, excluding retired attribution support rows."""


def pending_counts(db, entity_id=None):
    scope = " AND q.entity_id=?" if entity_id is not None else ""
    return {
        row["entity_id"]: row["total"]
        for row in db.execute(
            """SELECT q.entity_id,count(DISTINCT e.id) total
            FROM lead_queue q JOIN json_each(q.payload) item
            JOIN entries e ON e.id=json_extract(item.value,'$.normalized.observation_ref')
            WHERE q.qualified=1 AND q.status IN ('pending','deferred')
              AND q.superseded_by='' AND q.suppression_reason=''
              AND q.association_state<>'review'
              AND NOT EXISTS(SELECT 1 FROM case_entries ce WHERE ce.entry_id=e.id)
            """
            + scope
            + " GROUP BY q.entity_id",
            (entity_id,) if entity_id is not None else (),
        )
    }
