"""Read queries shared by case and entity views."""

from __future__ import annotations

from datetime import date
from fastapi import HTTPException
from ..cases import STAGES
from ..repositories.cases import CaseRepository
from modules.library.components.intelligence_index import decorate_rows


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
