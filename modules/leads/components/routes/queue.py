"""Qualified lead queue HTTP adapters."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PendingLeadStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    case_id: str | None = None
    expected_case_version: int | None = Field(default=None, ge=0)


class PendingLeadDisposition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    status: Literal["pending", "deferred", "dismissed"]


class PendingLeadAssociation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    entity_id: str = Field(min_length=1, max_length=100)


def register(app, *, queue):
    @app.get("/api/pending-leads")
    def pending_leads(status: str = "pending", q: str = ""):
        return queue.list(status, q)

    @app.get("/api/pending-leads/{pending_id}")
    def pending_lead(pending_id: str):
        return queue.detail(pending_id)

    @app.post("/api/pending-leads/{pending_id}/start")
    def start_pending(pending_id: str, body: PendingLeadStart):
        return queue.start(
            pending_id,
            body.expected_revision,
            case_id=body.case_id,
            expected_case_version=body.expected_case_version,
        )

    @app.post("/api/pending-leads/{pending_id}/disposition")
    def disposition(pending_id: str, body: PendingLeadDisposition):
        return queue.disposition(pending_id, body.expected_revision, body.status)

    @app.post("/api/pending-leads/{pending_id}/associate")
    def associate(pending_id: str, body: PendingLeadAssociation):
        return queue.associate(pending_id, body.expected_revision, body.entity_id)
