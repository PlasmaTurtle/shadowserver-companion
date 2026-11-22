"""Read-only, paged membership of CVEs in retained case source selections."""

import json
from contextlib import contextmanager
from urllib.parse import quote


class ReferenceUsage:
    def __init__(self, store):
        self.store = store

    @contextmanager
    def open_kev_selections(self):
        """Stream compact selections in one snapshot, with one row per case and CVE."""
        scope = "c.stage IN ('in_progress','pending_notification')"
        readable = """CASE WHEN json_valid(c.draft) THEN
            json_type(c.draft)='object' AND
            coalesce(json_type(c.draft,'$.cve_records'),'null') IN ('array','null')
            ELSE 0 END"""
        with self.store.read_snapshot() as db:
            unreadable = db.execute(
                f"SELECT count(*) FROM cases c WHERE {scope} AND NOT ({readable})"
            ).fetchone()[0]
            rows = db.execute(f"""
                WITH pins AS (
                    SELECT c.id,c.title,
                           CASE WHEN p.type='object' THEN p.value ELSE '{{}}' END AS pin
                    FROM cases c, json_each(
                        CASE WHEN {readable} THEN c.draft ELSE '{{}}' END, '$.cve_records'
                    ) p WHERE {scope}
                ), proof AS (
                    SELECT id,title,upper(json_extract(pin,'$.id')) AS cve_id,
                           json_extract(pin,'$.kev_retrieved_at') AS retrieved_at,
                           json_extract(pin,'$.kev_date') AS released_at,
                           CASE WHEN json_type(pin,'$.kev')='true' THEN 1
                                WHEN json_type(pin,'$.kev')='false'
                                 AND json_type(pin,'$.kev_catalog_complete')='true' THEN 0 END AS listed
                    FROM pins
                )
                SELECT id,title,cve_id,max(retrieved_at) AS retrieved_at,max(released_at) AS released_at,
                       CASE WHEN min(listed)=max(listed) AND count(*)=count(listed)
                            THEN max(listed) END AS listed
                FROM proof WHERE cve_id IS NOT NULL GROUP BY id,cve_id ORDER BY id,cve_id
            """)
            yield rows, unreadable

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
