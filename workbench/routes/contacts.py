"""Authenticated contact discovery, review and source-evidence routes."""

from typing import Literal
from fastapi import HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.background import BackgroundTask

from ..contact_records import ContactConflict


class ContactDiscoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    root_domain: str | None = Field(default=None, min_length=1, max_length=253)
    include_www: bool = True
    refresh: bool = False
    source_url: str | None = Field(default=None, min_length=1, max_length=2048)


class ContactBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_ids: list[str] = Field(min_length=1, max_length=25)
    include_www: bool = True


class ContactReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["confirm", "ignore", "pending"]
    expected_revision: int = Field(ge=1)


class ContactUseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    expected_revision: int = Field(ge=1)


class ContactRouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: Literal["prefer", "unusable", "restore"]
    reason: str = Field(min_length=1, max_length=2000)
    expected_revision: int = Field(ge=1)


class VerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str = Field(max_length=1000)
    expected_value: str = Field(default="", max_length=1000)


class PreparationVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    expected_context: str = Field(pattern="^[a-f0-9]{64}$")


class PreparationReset(PreparationVersion):
    reviewed_context: bool = False


class PreparationValues(PreparationReset):
    subject: str = Field(max_length=1000)
    message: str = Field(max_length=20000)
    call_outline: str = Field(max_length=10000)


def register(app, *, store, jobs, cases):
    def conflict(call, *args, **kwargs):
        try:
            return call(*args, **kwargs)
        except ContactConflict as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post("/api/contact-discovery/find-all")
    def find_all():
        return conflict(jobs.queue_directory)

    @app.get("/api/contact-discovery/directory-status")
    def directory_status():
        return jobs.directory_status()

    @app.post("/api/entities/{entity_id}/contacts/refresh")
    def refresh_directory(entity_id: str):
        return conflict(jobs.queue_directory, entity_id)

    @app.get("/api/contact-discovery/overviews")
    def directory_contacts(entity_ids: list[str] = Query(min_length=1, max_length=100)):
        from ..contact_outcomes import directory_contact

        result = {}
        with store.read_snapshot() as db:
            for entity_id in dict.fromkeys(entity_ids):
                if db.execute(
                    "SELECT 1 FROM leads WHERE id=? AND merged_into IS NULL", (entity_id,)
                ).fetchone():
                    result[entity_id] = directory_contact(store, entity_id, db)
        return result

    @app.get("/api/entities/{entity_id}/contacts")
    def contact_state(entity_id: str):
        return jobs.state(entity_id)

    @app.post("/api/entities/{entity_id}/contacts/discover")
    def discover(entity_id: str, body: ContactDiscoveryRequest):
        return conflict(jobs.start, entity_id, **body.model_dump())

    @app.post("/api/contact-discovery/batch")
    def batch(body: ContactBatchRequest):
        return conflict(jobs.batch, **body.model_dump())

    @app.get("/api/contact-discovery/jobs/{job_id}")
    def job(job_id: str):
        return jobs.get(job_id)

    @app.post("/api/contact-discovery/jobs/{job_id}/cancel")
    def cancel(job_id: str):
        return jobs.cancel(job_id)

    @app.post("/api/entities/{entity_id}/contacts/{candidate_id}/review")
    def review(entity_id: str, candidate_id: str, body: ContactReviewRequest):
        return conflict(jobs.records.review, entity_id, candidate_id, **body.model_dump())

    @app.post("/api/cases/{case_id}/contacts/{candidate_id}/use")
    def use(case_id: str, candidate_id: str, body: ContactUseRequest):
        return conflict(jobs.records.use, cases, case_id, candidate_id, **body.model_dump())

    @app.post("/api/entities/{entity_id}/contacts/{candidate_id}/route")
    def route_decision(entity_id: str, candidate_id: str, body: ContactRouteRequest):
        return conflict(jobs.records.route_decision, entity_id, candidate_id, **body.model_dump())

    @app.get("/api/cases/{case_id}/outreach-handoff")
    def handoff(case_id: str):
        from ..outreach_preparation import preparation

        return preparation(store, jobs.records, case_id)

    @app.put("/api/cases/{case_id}/outreach-preparation")
    def save_preparation(case_id: str, body: PreparationValues):
        from ..outreach_preparation import save_preparation

        return conflict(save_preparation, store, jobs.records, case_id, **body.model_dump())

    @app.post("/api/cases/{case_id}/outreach-preparation/reset")
    def reset_preparation(case_id: str, body: PreparationReset):
        from ..outreach_preparation import save_preparation

        return conflict(
            save_preparation, store, jobs.records, case_id, reset=True, **body.model_dump()
        )

    @app.post("/api/cases/{case_id}/outreach-preparation/copy")
    def copy_preparation(case_id: str, body: PreparationVersion):
        from ..outreach_preparation import copy_preparation

        return conflict(copy_preparation, store, jobs.records, case_id, **body.model_dump())

    @app.put("/api/contact-discovery/verification-route")
    def verification(body: VerificationRequest):
        return conflict(jobs.records.configure_verification, **body.model_dump())

    @app.get("/api/entities/{entity_id}/contacts/evidence.zip")
    def evidence(entity_id: str, run_id: str | None = None):
        path = jobs.records.export(entity_id, run_id)
        return FileResponse(
            path,
            filename="contact-discovery-evidence.zip",
            background=BackgroundTask(path.unlink, missing_ok=True),
        )
