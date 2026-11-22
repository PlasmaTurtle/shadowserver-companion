"""Read-only, paged membership of CVEs in retained case source selections."""

import json
from urllib.parse import quote


class ReferenceUsage:
    def __init__(self, store):
        self.store = store

    def cases(self, cve_id, *, limit=25, offset=0, include_completed=False):
        if not 1 <= limit <= 100 or not 0 <= offset <= 500000:
            raise ValueError("Invalid case reference page")
        scope = "1=1" if include_completed else "c.stage IN ('in_progress','pending_notification')"
        # SQLite selects only matching source objects for the requested page.
        # It does not load every complete case draft into application memory.
        records = (
            "json_each(CASE WHEN json_valid(c.draft) THEN c.draft ELSE '{}' END,'$.cve_records')"
        )
        membership = (
            "UPPER(json_extract(CASE WHEN p.type='object' THEN p.value ELSE '{}' END,'$.id'))=?"
        )
        selected = f"{scope} AND EXISTS(SELECT 1 FROM {records} p WHERE {membership})"
        with self.store.read_snapshot() as db:
            total = db.execute(
                "SELECT count(*) FROM cases c WHERE " + selected, (cve_id,)
            ).fetchone()[0]
            unreadable = db.execute(
                f"SELECT count(*) FROM cases c WHERE {scope} AND NOT json_valid(c.draft)"
            ).fetchone()[0]
            rows = db.execute(
                "SELECT c.id,c.title,c.stage,c.certified_report_id,"
                f"(SELECT p.value FROM {records} p WHERE {membership} LIMIT 1) AS pinned "
                f"FROM cases c WHERE {selected} "
                "ORDER BY c.updated_at DESC,c.id LIMIT ? OFFSET ?",
                (cve_id, cve_id, limit, offset),
            ).fetchall()
        return {
            "items": [
                {
                    "id": row["id"],
                    "title": row["title"],
                    "stage": row["stage"],
                    "url": "#workspace/notifications/" + quote(row["id"], safe=""),
                    "certified": bool(row["certified_report_id"]),
                    "certified_report_id": row["certified_report_id"],
                    "pinned": json.loads(row["pinned"]),
                }
                for row in rows
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
            "include_completed": include_completed,
            "coverage_complete": unreadable == 0,
            "unreadable_cases": unreadable,
            "basis": (
                "Retained source selections in all notification cases, including completed and closed work."
                if include_completed
                else "Retained source selections in work in progress and pending notifications."
            )
            + " Observations without a selected source are available through observed connections.",
        }
