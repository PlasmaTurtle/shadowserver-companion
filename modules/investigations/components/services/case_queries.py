"""Read queries shared by case and entity views."""

from __future__ import annotations

from datetime import date
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
    rows = CaseRepository.notification_history_rows(db, result.keys(), include_cases=include_cases)
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
