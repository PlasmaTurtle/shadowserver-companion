"""Read-only, bounded decision chronology; historical actors stay unknown."""

import json

from fastapi import Query


def register(app, *, store):
    @app.get("/api/activity")
    def activity(
        q: str = Query(default="", max_length=200),
        action: str = Query(default="", max_length=100),
        actor: str = Query(default="", max_length=200),
        entity_id: str = Query(default="", max_length=100),
        case_id: str = Query(default="", max_length=100),
        before: int | None = Query(default=None, ge=1),
        limit: int = Query(default=50, ge=1, le=200),
    ):
        clauses, args = [], []
        for column, value in (
            ("action", action),
            ("actor", actor),
            ("lead_id", entity_id),
            ("case_id", case_id),
        ):
            if value:
                clauses.append(f"{column}=?")
                args.append(value)
        if q:
            escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            clauses.append(
                "(detail LIKE ? ESCAPE '\\' OR action LIKE ? ESCAPE '\\' OR actor LIKE ? ESCAPE '\\')"
            )
            args.extend(["%" + escaped + "%"] * 3)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        page_clauses, page_args = list(clauses), list(args)
        if before is not None:
            page_clauses.append("id<?")
            page_args.append(before)
        page_where = " WHERE " + " AND ".join(page_clauses) if page_clauses else ""
        with store.read_snapshot() as db:
            total = db.execute("SELECT count(*) FROM events" + where, args).fetchone()[0]
            rows = [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM events" + page_where + " ORDER BY id DESC LIMIT ?",
                    (*page_args, limit + 1),
                )
            ]
        more = len(rows) > limit
        rows = rows[:limit]
        for row in rows:
            row["metadata"] = json.loads(row["metadata"])
            row["actor_recorded"] = bool(row["actor"])
        return {
            "items": rows,
            "total": total,
            "unit": "recorded events",
            "next_before": rows[-1]["id"] if more else None,
        }
