"""Operational overview from saved records, without opening or hashing report files."""

from datetime import date
import json


def workspace_brief(store, as_of=None):
    with store.read_snapshot() as db:
        stages = {
            r["stage"]: r["n"]
            for r in db.execute("SELECT stage,count(*) n FROM cases GROUP BY stage")
        }
        # Lead frontier stores canonical source IDs. Check unassigned membership
        # directly instead of rebuilding every lead, hashing rows or reading
        # artifacts just to draw the four work counters.
        leads = [
            dict(row)
            for row in db.execute(
                "SELECT q.id,q.root_domain domain,COALESCE(NULLIF(l.company,''),l.domain) entity_name,"
                "q.intake_score,q.observation_day observed_to,count(*) OVER() total "
                "FROM lead_queue q JOIN leads l ON l.id=q.entity_id "
                "WHERE q.qualified=1 AND q.status='pending' AND q.association_state<>'review' "
                "AND q.superseded_by='' AND q.suppression_reason='' AND q.payload<>'[]' "
                "AND l.merged_into IS NULL AND EXISTS(SELECT 1 FROM json_each(q.payload) item "
                "JOIN entries e ON e.id=json_extract(item.value,'$.normalized.observation_ref') "
                "WHERE NOT EXISTS(SELECT 1 FROM case_entries ce WHERE ce.entry_id=e.id)) "
                "ORDER BY CAST(json_extract(q.intake_score,'$.aggregate') AS REAL) DESC,"
                "q.observation_day DESC,q.created_at DESC,q.id LIMIT 4"
            )
        ]
        totals = {"leads": leads[0]["total"] if leads else 0}
        for lead in leads:
            lead.pop("total")
            lead["intake_score"] = json.loads(lead["intake_score"]) or None
        totals["entities"] = db.execute(
            "SELECT count(*) FROM leads WHERE merged_into IS NULL"
        ).fetchone()[0]
        totals["review"] = db.execute("SELECT count(*) FROM jobs WHERE status='review'").fetchone()[
            0
        ]
        workflow = {
            key: stages.get(key, 0)
            for key in ("in_progress", "pending_notification", "notification_completed", "closed")
        }
        workflow.update(
            scan_validation=db.execute(
                "SELECT count(*) FROM jobs WHERE status IN ('pending','review','deferred')"
            ).fetchone()[0],
            due=db.execute(
                "SELECT count(*) FROM cases WHERE stage!='closed' AND follow_up_date!='' AND follow_up_date<=?",
                ((as_of or date.today()).isoformat(),),
            ).fetchone()[0],
            delivered_total=db.execute(
                "SELECT count(*) FROM cases WHERE delivered_at IS NOT NULL"
            ).fetchone()[0],
            closed_without_delivery=db.execute(
                "SELECT count(*) FROM cases WHERE stage='closed' AND delivered_at IS NULL"
            ).fetchone()[0],
        )
        imports = [
            dict(r)
            for r in db.execute(
                "SELECT id,name,status,stage,error,created_at,rows_read,valid_rows,groups_total,groups_done,qualified,"
                "coalesce(json_extract(config,'$.intake_stats.ignored_empty_rows'),0) ignored_empty_rows "
                "FROM imports ORDER BY created_at DESC LIMIT 3"
            )
        ]
        events = [
            dict(r)
            for r in db.execute(
                "SELECT id,lead_id,case_id,action,detail,created_at FROM events ORDER BY id DESC LIMIT 5"
            )
        ]
    return {
        "counts": totals,
        "workflow": workflow,
        "leads": leads,
        "imports": imports,
        "events": events,
        "basis": "Saved workflow records. Package integrity is checked when opening or exporting report files.",
    }
