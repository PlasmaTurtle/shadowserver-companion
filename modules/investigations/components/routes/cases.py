"""Cases HTTP adapters."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


import shutil
import tempfile
from datetime import date
from pathlib import Path
from fastapi import HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from ..services.reviews import SectionReviewService
from ..report_operations import register_operations
from ..report_execution import prepare_closing
from modules.investigations.components.api_models import (
    CaseCreate,
    CaseRevision,
    SectionVersion,
    SectionReopen,
    CasePlan,
    ContactAttempt,
    ClosingValues,
)
from ..services.case_queries import list_cases
from ..outreach_policy import OutreachPolicyValues
from ..services.outreach import save_policy


class ObservationScopeChange(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_version: int = Field(ge=0)
    expected_revision: int = Field(ge=0)
    entry_ids: list[str] = Field(min_length=1, max_length=1000)
    decision: Literal["include", "exclude"]
    reason: str = Field(min_length=1, max_length=5000)
    reopen_affected: bool = False


def register(app, *, store, cases, get_lead):
    operations = register_operations(app)

    @app.get("/api/cases")
    def case_list(
        stage: str = "", entity_id: str = "", q: str = "", due_before: date | None = None
    ):
        return list_cases(store, stage, entity_id, q, due_before)

    @app.put("/api/cases/{case_id}/outreach-policy")
    def outreach_policy(case_id: str, body: OutreachPolicyValues):
        lead = save_policy(store, case_id, body.model_dump(mode="json"))
        return get_lead(lead["id"], case_id)

    @app.post("/api/cases")
    def new_case(body: CaseCreate):
        lead = cases.create(body.entity_id, body.title)
        return get_lead(lead["id"], lead["case_id"])

    @app.get("/api/cases/{case_id}")
    def case_detail(case_id: str):
        lead = cases.view(case_id)
        return get_lead(lead["id"], case_id)

    @app.post("/api/cases/{case_id}/observation-scope")
    def observation_scope(case_id: str, body: ObservationScopeChange):
        from ..services.observation_scope import ObservationScopeService

        with operations.run(case_id, "observation scope review"):
            reopened = ObservationScopeService(store).update(case_id, body.model_dump())
            lead = cases.view(case_id)
            result = get_lead(lead["id"], case_id)
            result["scope_reopened_sections"] = reopened
            return result

    @app.put("/api/cases/{case_id}/plan")
    def case_plan(case_id: str, body: CasePlan):
        lead = cases.plan(case_id, body.model_dump(mode="json"))
        return get_lead(lead["id"], case_id)

    @app.post("/api/cases/{case_id}/attempts")
    def case_attempt(case_id: str, body: ContactAttempt):
        lead = cases.attempt(case_id, body.model_dump(mode="json"))
        return get_lead(lead["id"], case_id)

    @app.post("/api/cases/{case_id}/revise")
    def revise_case(case_id: str, body: CaseRevision):
        lead = cases.revise(case_id, body.expected_version, body.reason)
        return get_lead(lead["id"], case_id)

    @app.post("/api/cases/{case_id}/sections/{section_key}/validate")
    def validate_section(case_id: str, section_key: str, body: SectionVersion):
        with operations.run(case_id, "section validation"):
            SectionReviewService(store).validate(case_id, section_key, body.expected_revision)
            lead = cases.view(case_id)
            return get_lead(lead["id"], case_id)

    @app.post("/api/cases/{case_id}/sections/{section_key}/reopen")
    def reopen_section(case_id: str, section_key: str, body: SectionReopen):
        SectionReviewService(store).reopen(
            case_id, section_key, body.expected_revision, body.reason
        )
        lead = cases.view(case_id)
        return get_lead(lead["id"], case_id)

    @app.post("/api/cases/{case_id}/closing-preview")
    def closing_preview(case_id: str, body: ClosingValues):
        with operations.run(case_id, "closing preview"):
            from ..closing import closing_data, render_closing

            directory = Path(tempfile.mkdtemp())
            try:
                preview_data = closing_data(store, case_id, body.model_dump())
                preview_data["preview"] = True
                prepare_closing(
                    preview_data,
                    directory,
                    fallback=render_closing,
                )
            except Exception:
                shutil.rmtree(directory, ignore_errors=True)
                raise
            return FileResponse(
                directory / "closing-report.pdf",
                media_type="application/pdf",
                background=BackgroundTask(shutil.rmtree, directory, ignore_errors=True),
            )

    @app.post("/api/cases/{case_id}/close")
    def close_notification(case_id: str, body: ClosingValues):
        from ..closing import close_case

        with operations.run(case_id, "closing publication"):
            return close_case(store, case_id, body.model_dump())

    @app.get("/api/cases/{case_id}/closing/{format}")
    def closing_file(case_id: str, format: str):
        record = store.one("SELECT * FROM case_closures WHERE case_id=?", (case_id,))
        if not record or format not in ("pdf", "docx", "json"):
            raise HTTPException(404, "Closing report not found")
        if not store.closure_available(record):
            raise HTTPException(
                409, "Closing report package is missing or changed. Restore it from backup."
            )
        name = "snapshot.json" if format == "json" else "closing-report." + format
        return FileResponse(
            store.path(record["path"]) / name, filename=f"closing-{case_id[:8]}.{format}"
        )
