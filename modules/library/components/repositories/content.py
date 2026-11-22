"""Explainer current pointers and immutable revisions; transactions belong to callers."""

import json

from modules.workspace.components.primitives import dump
from ...resources.defaults import EXPLAINERS

DEFAULT_IDS = {item[0] for item in EXPLAINERS}


def metadata_key(block_id, revision):
    return f"block-sources:{block_id}:{revision}"


def blocks(db, *, include_archived=False, block_id=None):
    where, args = [], []
    if not include_archived:
        where.append("COALESCE(s.archived_at,'')=''")
    if block_id is not None:
        where.append("e.id=?")
        args.append(block_id)
    rows = db.execute(
        "SELECT e.*,COALESCE(s.archived_at,'') AS archived_at,"
        "COALESCE(r.source_metadata,c.payload) AS citations,"
        "EXISTS(SELECT 1 FROM explainer_revisions h WHERE h.block_id=e.id AND "
        "(h.action IN ('updated','restored') OR (h.action='legacy_current' AND h.revision>1))) AS locally_edited "
        "FROM explainers e LEFT JOIN explainer_state s ON s.block_id=e.id "
        "LEFT JOIN explainer_revisions r ON r.block_id=e.id AND r.revision=e.revision "
        "LEFT JOIN cache c ON c.key='block-sources:' || e.id || ':' || e.revision"
        + (" WHERE " + " AND ".join(where) if where else "")
        + " ORDER BY e.rowid",
        args,
    )
    result = []
    for row in rows:
        item = dict(row)
        citations = item.pop("citations")
        edited = item.pop("locally_edited")
        item["origin"] = (
            ("bundled_edited" if edited else "bundled") if item["id"] in DEFAULT_IDS else "analyst"
        )
        # Immutable history is authoritative; cache is only a legacy fallback.
        if citations is not None:
            item["source_metadata"] = json.loads(citations)
        result.append(item)
    return result


def current(db, block_id):
    rows = blocks(db, include_archived=True, block_id=block_id)
    if not rows:
        raise LookupError("Explainer not found")
    return rows[0]


def retain(db, block, *, actor="", action, restored_from=None):
    db.execute(
        """INSERT INTO explainer_revisions
        (block_id,revision,title,body,sources,source_metadata,updated_at,actor,action,restored_from,archived_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (
            block["id"],
            block["revision"],
            block["title"],
            block["body"],
            block["sources"],
            dump(block.get("source_metadata", [])),
            block["updated_at"],
            actor,
            action,
            restored_from,
            block.get("archived_at", ""),
        ),
    )


def revision(db, block_id, number):
    row = db.execute(
        "SELECT * FROM explainer_revisions WHERE block_id=? AND revision=?", (block_id, number)
    ).fetchone()
    if row is None:
        raise LookupError("Explainer revision not found")
    value = dict(row)
    value["id"] = value.pop("block_id")
    value["source_metadata"] = json.loads(value["source_metadata"])
    return value


def publish(db, block, *, actor, action, restored_from=None):
    db.execute(
        "UPDATE explainers SET title=?,body=?,sources=?,revision=?,updated_at=? WHERE id=?",
        tuple(block[key] for key in ("title", "body", "sources", "revision", "updated_at", "id")),
    )
    db.execute(
        "INSERT INTO explainer_state(block_id,archived_at) VALUES(?,?) "
        "ON CONFLICT(block_id) DO UPDATE SET archived_at=excluded.archived_at",
        (block["id"], block["archived_at"]),
    )
    db.execute(
        "INSERT INTO cache(key,payload,retrieved_at) VALUES(?,?,?)",
        (
            metadata_key(block["id"], block["revision"]),
            dump(block.get("source_metadata", [])),
            block["updated_at"],
        ),
    )
    retain(db, block, actor=actor, action=action, restored_from=restored_from)
