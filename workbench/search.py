"""Small read-only projections for the command palette; never open report snapshots."""

from __future__ import annotations

from urllib.parse import quote


def search_records(store, query="", limit=6):
    query = " ".join(str(query).split())[:120]
    limit = max(1, min(int(limit), 10))
    if query and len(query) < 2:
        return {"query": query, "groups": [], "total": 0, "minimum_length": 2}
    term = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    groups = []
    with store.read_snapshot() as db:
        # All expressions are fixed; the user's text is bound and LIKE wildcards are literal.
        specifications = [
            (
                "entity",
                "Entities",
                "SELECT l.id,coalesce(nullif(l.company,''),l.domain) title,l.domain detail,l.updated_at updated "
                "FROM leads l WHERE l.merged_into IS NULL",
                "(l.company LIKE ? ESCAPE '\\' OR l.domain LIKE ? ESCAPE '\\' OR EXISTS "
                "(SELECT 1 FROM entries e WHERE e.lead_id=l.id AND "
                "(e.hostname LIKE ? ESCAPE '\\' OR e.ip LIKE ? ESCAPE '\\' OR e.tag LIKE ? ESCAPE '\\')))",
                5,
                "#entity/",
            ),
            (
                "notification",
                "Notifications",
                "SELECT c.id,coalesce(nullif(json_extract(c.entity_snapshot,'$.company'),''),nullif(l.company,''),l.domain) title,"
                "c.stage || ' · ' || c.title detail,c.updated_at updated "
                "FROM cases c JOIN leads l ON l.id=c.entity_id WHERE 1=1",
                "(c.title LIKE ? ESCAPE '\\' OR l.company LIKE ? ESCAPE '\\' OR l.domain LIKE ? ESCAPE '\\' "
                "OR json_extract(c.entity_snapshot,'$.company') LIKE ? ESCAPE '\\' OR EXISTS "
                "(SELECT 1 FROM case_entries ce JOIN entries e ON e.id=ce.entry_id WHERE ce.case_id=c.id "
                "AND (e.hostname LIKE ? ESCAPE '\\' OR e.ip LIKE ? ESCAPE '\\' OR e.tag LIKE ? ESCAPE '\\')))",
                7,
                "#workspace/notifications/",
            ),
            (
                "lead",
                "Incoming leads",
                "SELECT id,root_domain title,status || ' · ' || "
                "CASE WHEN qualified=1 THEN 'Attribution recorded' ELSE 'Attribution pending' END detail,"
                "updated_at updated FROM lead_queue WHERE status IN ('pending','deferred','dismissed')",
                "(root_domain LIKE ? ESCAPE '\\' OR EXISTS (SELECT 1 FROM json_each(payload) item WHERE "
                "json_extract(item.value,'$.ip') LIKE ? ESCAPE '\\' OR "
                "json_extract(item.value,'$.source.fields.hostname') LIKE ? ESCAPE '\\' OR "
                "json_extract(item.value,'$.source.fields.tag') LIKE ? ESCAPE '\\'))",
                4,
                "#leads/",
            ),
            (
                "import",
                "Source files",
                "SELECT id,name title,status || ' · ' || rows_read || ' observations' detail,created_at updated "
                "FROM imports WHERE 1=1",
                "name LIKE ? ESCAPE '\\'",
                1,
                "",
            ),
            (
                "explainer",
                "Library",
                "SELECT id,title,'Revision ' || revision detail,updated_at updated FROM explainers WHERE 1=1",
                "(title LIKE ? ESCAPE '\\' OR body LIKE ? ESCAPE '\\')",
                2,
                "#library?item=",
            ),
        ]
        for kind, label, base, where, parameters, prefix in specifications:
            # Recent work is deliberately small; source/library suggestions need search text.
            if not query and kind in {"import", "explainer"}:
                continue
            sql = base + (" AND " + where if query else "") + " ORDER BY updated DESC,1 LIMIT ?"
            values = [term] * parameters if query else []
            rows = db.execute(sql, (*values, limit + 1)).fetchall()
            if not rows:
                continue
            items = [
                {
                    "id": row["id"],
                    "kind": kind,
                    "title": row["title"][:250],
                    "detail": row["detail"][:300],
                    "updated_at": row["updated"],
                    "href": prefix + quote(row["id"], safe="") if prefix else "",
                }
                for row in rows[:limit]
            ]
            groups.append(
                {"kind": kind, "label": label, "items": items, "has_more": len(rows) > limit}
            )
    return {"query": query, "groups": groups, "total": sum(len(g["items"]) for g in groups)}
