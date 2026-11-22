"""Read queries shared by case and entity views."""

from __future__ import annotations

from datetime import date
import json
from fastapi import HTTPException
from ..cases import STAGES
from ..repositories.cases import CaseRepository
from modules.library.components.intelligence_index import decorate_rows


def completed_notifications(db, entity_id, *, include_cases=False):
    """Count a case once at its first recorded delivery, across stages and revisions."""
    return notification_histories(db, [entity_id], include_cases=include_cases)[entity_id]


def notification_histories(db, entity_ids, *, include_cases=False):
    """Read one summary per requested entity or merged alias in one snapshot."""
    result = {
        identity: {"count": 0, "last_notified_at": None, "last_case_id": None}
        for identity in entity_ids
    }
    if include_cases:
        for item in result.values():
            item["cases"] = []
    if not result:
        return result
    rows = db.execute(
        """WITH owners AS (
            SELECT id AS requested, COALESCE(merged_into,id) AS canonical FROM leads
            WHERE id IN (SELECT value FROM json_each(?))
        ), entity_cases AS (
            SELECT id,entity_id,title,delivered_at FROM cases
            WHERE entity_id IN (SELECT canonical FROM owners)
        ), receipts AS (
            SELECT id, delivered_at AS notified_at FROM entity_cases WHERE delivered_at > ''
            UNION ALL
            SELECT c.id, r.sent_at FROM entity_cases c
            JOIN reports r ON r.case_id=c.id WHERE r.sent_at > ''
        ), deliveries AS (
            SELECT id, MIN(notified_at) AS notified_at FROM receipts GROUP BY id
        ), ranked AS (
            SELECT d.id,c.entity_id,c.title,d.notified_at,
              COUNT(*) OVER (PARTITION BY c.entity_id) AS total,
              ROW_NUMBER() OVER (PARTITION BY c.entity_id ORDER BY d.notified_at DESC,d.id) AS position
            FROM deliveries d JOIN entity_cases c ON c.id=d.id
        )
        SELECT o.requested,r.* FROM owners o JOIN ranked r ON r.entity_id=o.canonical"""
        + ("" if include_cases else " WHERE r.position=1")
        + " ORDER BY o.requested, r.position",
        (json.dumps(list(result)),),
    )
    for row in rows:
        summary = result[row["requested"]]
        if row["position"] == 1:
            summary.update(
                count=row["total"], last_notified_at=row["notified_at"], last_case_id=row["id"]
            )
        if include_cases:
            summary["cases"].append({key: row[key] for key in ("id", "title", "notified_at")})
    return result


def list_cases(
    store,
    stage: str = "",
    entity_id: str = "",
    q: str = "",
    due_before: date | None = None,
    *,
    db=None,
    case_ids=None,
):
    if stage and stage not in STAGES:
        raise HTTPException(400, "Unknown case stage")
    if db is None:
        with store.read_snapshot() as snapshot:
            return list_cases(
                store, stage, entity_id, q, due_before, db=snapshot, case_ids=case_ids
            )
    rows = CaseRepository(store).list(stage, entity_id, q, due_before, db=db, case_ids=case_ids)
    return decorate_rows(store, rows, kind="cases", db=db)
