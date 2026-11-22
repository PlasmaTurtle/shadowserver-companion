"""Explicit Red Hat acquisition and local-only vendor statement reads."""

from typing import Annotated, Literal

from fastapi import Query
from pydantic import BaseModel, Field

from ..intelligence.redhat import ScopeText
from ..vendor_statements import read_redhat, refresh_redhat


CaptureTime = Annotated[str, Field(json_schema_extra={"format": "date-time"})]
SourceURL = Annotated[str, Field(json_schema_extra={"format": "uri"})]


class VendorAcquisitionAttempt(BaseModel, strict=True, extra="forbid"):
    outcome: Literal["success", "rate_limited", "not_found", "unavailable", "invalid_response"]
    attempted_at: CaptureTime
    completed_at: CaptureTime
    error: str | None
    http_status: int | None
    retry_after: Annotated[str, Field(max_length=128)] | None


class VendorProductStatement(BaseModel, strict=True, extra="forbid"):
    product: ScopeText
    package: ScopeText | None
    cpe: ScopeText | None
    status: ScopeText = Field(description="Publisher fix state, or Fixed for a released erratum.")
    advisory: ScopeText | None
    release_date: ScopeText | None
    source_pointer: str = Field(pattern=r"^/(package_state|affected_release)/[0-9]+$")


class VendorStatementResponse(BaseModel, strict=True, extra="forbid"):
    cve_id: str = Field(pattern=r"^CVE-[0-9]{4}-[0-9]{4,}$", max_length=80)
    publisher: Literal["Red Hat Product Security"]
    source_url: SourceURL
    public_url: SourceURL
    status: Literal["available", "not_retrieved", "unavailable"]
    retrieved_at: CaptureTime | None
    revision_id: Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")] | None = Field(
        description="Local immutable capture identifier."
    )
    sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")] | None
    published_at: ScopeText | None = Field(description="Red Hat public_date for the vulnerability.")
    stale: bool | None = Field(description="Null when there is no verified response.")
    last_attempt: VendorAcquisitionAttempt | None
    publisher_statement: Annotated[str, Field(max_length=65536)] | None = Field(
        description="Exact Red Hat statement text when supplied."
    )
    statements: list[VendorProductStatement] = Field(max_length=100)
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0, le=500000)
    error: str | None


def register(app, *, store):
    @app.get(
        "/api/library/vendor-statements/redhat/{cve_id}", response_model=VendorStatementResponse
    )
    def vendor_statement(
        cve_id: str, offset: int = Query(0, ge=0, le=500000), limit: int = Query(25, ge=1, le=100)
    ):
        return read_redhat(store, cve_id, offset=offset, limit=limit)

    @app.post(
        "/api/library/vendor-statements/redhat/{cve_id}/refresh",
        response_model=VendorStatementResponse,
    )
    def refresh(cve_id: str):
        return refresh_redhat(store, cve_id)
