"""Investigations request contracts; validation stays with the owning domain."""

from __future__ import annotations
from datetime import date, datetime, timezone
from typing import Literal
from urllib.parse import urlsplit
from pydantic import BaseModel, Field, ConfigDict, field_validator


class CVEDisposition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["exclude", "fallback"]
    reason: str = Field(default="", max_length=5000)
    description: str = Field(default="", max_length=100000)
    publisher: str = Field(default="", max_length=500)
    source_url: str = Field(default="", max_length=2000)
    retrieved_at: str = Field(default="", max_length=100)
    evidence_text: str = Field(default="", max_length=200000)

    @field_validator("source_url")
    @classmethod
    def source_link(cls, value):
        if value and (
            urlsplit(value).scheme not in ("https", "http") or not urlsplit(value).netloc
        ):
            raise ValueError("Official source URL must be an HTTP or HTTPS URL")
        return value

    @field_validator("retrieved_at")
    @classmethod
    def capture_date(cls, value):
        if value:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError("Source retrieval time must include its timezone")
        return value


class ReportTemplateValues(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Literal["standard"] = "standard"
    version: Literal[1, 2] = 2
    marking: str = Field(default="For Informational Purposes Only", max_length=150)
    font_size: float = Field(default=9.5, ge=8, le=12)


class NarrativeValues(BaseModel):
    model_config = ConfigDict(extra="forbid")
    software: str = Field(default="", max_length=1000)
    affected_versions: str = Field(default="", max_length=12000)


class DraftValues(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template_revision: str = Field(default="", max_length=100)
    narrative_revision: str = Field(default="", max_length=100)
    addressee_revision: Literal["legacy", "addressee-2026-11-08-v2"] = "legacy"
    narrative_values: dict[str, NarrativeValues] = Field(default_factory=dict, max_length=1000)
    company: str = Field(default="", max_length=500)
    contact_name: str = Field(default="", max_length=300)
    contact_title: str = Field(default="", max_length=300)
    contact_email: str = Field(default="", max_length=500)
    address: str = Field(default="", max_length=2000)
    sender_name: str = Field(default="", max_length=300)
    sender_title: str = Field(default="", max_length=300)
    sender_profile: dict = Field(default_factory=dict, max_length=10)
    report_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    subject: str = Field(max_length=500)
    intro: str = Field(max_length=20000)
    narrative: str = Field(max_length=50000)
    severity: Literal["Not specified", "Informational", "Low", "Medium", "High", "Critical"] = (
        "Not specified"
    )
    selected_explainers: list[str] = Field(default_factory=list, max_length=100)
    cve_records: list[dict] = Field(default_factory=list, max_length=100)
    cve_dispositions: dict[str, CVEDisposition] = Field(default_factory=dict, max_length=100)
    observation_scope: dict[str, dict] = Field(default_factory=dict, max_length=10000)
    observation_scope_archive: dict = Field(default_factory=dict)
    explainer_snapshots: list[dict] = Field(default_factory=list, max_length=1000)
    report_explainer_snapshots: list[dict] = Field(default_factory=list, max_length=100)
    finding_explainer_snapshots: list[dict] = Field(default_factory=list, max_length=100)
    finding_explainer_revision: Literal[
        "legacy", "finding-explainers-2026-11-10-v1", "finding-explainers-2026-11-22-v1"
    ] = "legacy"
    explainer_overrides: dict[str, dict[str, str]] = Field(default_factory=dict, max_length=100)
    report_template: ReportTemplateValues = Field(default_factory=ReportTemplateValues)
    recommendations: str = Field(max_length=20000)
    limitations: str = Field(max_length=10000)
    resources: str = Field(max_length=20000)
    closing: str = Field(max_length=10000)
    include_appendix: bool = True
    recipient_edition: Literal["full-v1", "compact-v1"] = "full-v1"
    website_verified: bool = False
    sos_verified: bool = False
    reviewed: bool = False
    cve_reviewed: bool = False
    notes: str = Field(default="", max_length=50000)
    document_policy: dict = Field(default_factory=dict)
    selected_ssvc_assessments: dict[str, str] = Field(default_factory=dict, max_length=1000)
    outreach_template: Literal["critical", "targeted-v1"] = "critical"
    introduction_revision: Literal[
        "legacy",
        "introduction-2026-11-07-review-1",
        "introduction-2026-11-13-notification-1",
        "introduction-2026-11-13-notification-2",
    ] = "legacy"
    vulnerability_revision: Literal[
        "legacy",
        "vulnerabilities-2026-11-07-review-1",
        "vulnerabilities-2026-11-11-editorial-1",
        "vulnerabilities-2026-11-13-readability-1",
    ] = "legacy"
    attribution_revision: Literal["legacy", "attribution-2026-11-07-review-1"] = "legacy"
    information_revision: Literal[
        "legacy",
        "information-2026-11-07-review-1",
        "information-2026-11-07-review-2",
        "information-2026-11-10-v1",
    ] = "legacy"
    closing_revision: Literal[
        "legacy",
        "closing-2026-11-07-review-1",
        "closing-2026-11-07-review-2",
        "closing-2026-11-08-final-1",
    ] = "legacy"
    appendix_revision: Literal[
        "appendix-2026-11-13-compact-3",
        "appendix-2026-11-13-compact-2",
        "appendix-2026-11-10-compact-1",
        "legacy",
        "appendix-2026-11-07-review-1",
        "appendix-2026-11-08-final-1",
    ] = "legacy"
    source_restrictions: list = Field(default_factory=list, max_length=100)
    cve_state_history: list[dict] = Field(default_factory=list, max_length=20000)

    @field_validator("report_date")
    @classmethod
    def calendar_date(cls, value):
        date.fromisoformat(value)
        return value

    @field_validator("resources")
    @classmethod
    def links(cls, value):
        for line in value.splitlines():
            if line.strip() and urlsplit(line.strip()).scheme not in ("http", "https"):
                raise ValueError("Resources must be HTTP or HTTPS URLs, one per line")
        return value

    @field_validator("cve_records")
    @classmethod
    def scores(cls, records):
        for item in records:
            try:
                if item.get("cvss") is not None and not 0 <= float(item["cvss"]) <= 10:
                    raise ValueError("CVSS must be between 0 and 10")
                if item.get("epss") is not None and not 0 <= float(item["epss"]) <= 1:
                    raise ValueError("EPSS must be a probability between 0 and 1")
            except TypeError as error:
                raise ValueError("Source metrics must be numeric or unavailable") from error
            sources = item.get("sources", [])
            if not isinstance(sources, list):
                raise ValueError("CVE sources must be a list")
            for source in sources:
                if not isinstance(source, dict) or not isinstance(source.get("url"), str):
                    raise ValueError("Each CVE source must have a URL")
                if urlsplit(source["url"]).scheme not in ("http", "https"):
                    raise ValueError("CVE source must use HTTP or HTTPS")
        return records


class DraftUpdate(BaseModel):
    expected_revision: int = Field(ge=0)
    fields: DraftValues


class PresentationAdoption(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_revision: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=2000)


class WebsiteCaptureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hostname: str = Field(min_length=1, max_length=253)


class EvidenceUpdate(BaseModel):
    included: bool
    caption: str = Field(max_length=1000)
    source_url: str = Field(default="", max_length=2000)
    captured_at: str = Field(max_length=100)


class Delivery(BaseModel):
    sent_at: str = Field(min_length=1, max_length=100)
    note: str = Field(default="", max_length=5000)
    recipient: str = Field(default="", max_length=500)


class CaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_id: str
    title: str = Field(default="", max_length=500)


class CaseVersion(BaseModel):
    expected_version: int = Field(ge=0)


class CaseRevision(CaseVersion):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field(min_length=1, max_length=5000)


class SectionVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)


class SectionReopen(SectionVersion):
    reason: str = Field(min_length=1, max_length=5000)


class CasePlan(CaseVersion):
    model_config = ConfigDict(extra="forbid")
    next_action: str = Field(default="", max_length=2000)
    follow_up_date: date | None = None
    contact_name: str = Field(default="", max_length=300)
    contact_role: str = Field(default="", max_length=300)
    contact_email: str = Field(default="", max_length=500)
    contact_phone: str = Field(default="", max_length=100)


class ContactAttempt(CaseVersion):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    report_id: str | None = None
    occurred_at: datetime
    channel: Literal["phone", "email", "mail", "in_person", "other"]
    outcome: Literal[
        "contact_research",
        "no_answer",
        "voicemail",
        "callback_requested",
        "email_sent",
        "bounced",
        "delivered",
        "acknowledged",
        "recipient_update",
        "other",
    ]
    recipient: str = Field(default="", max_length=500)
    destination: str = Field(default="", max_length=1000)
    notes: str = Field(default="", max_length=10000)
    recorded_by: str = Field(min_length=1, max_length=300)
    information_source: Literal["administrative", "recipient_reported", "analyst_verified"] = (
        "administrative"
    )

    @field_validator("occurred_at")
    @classmethod
    def aware_timestamp(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Activity dates must include a timezone")
        return value.astimezone(timezone.utc)


class ClosingValues(CaseVersion):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    disposition: Literal["notified", "unable_to_contact", "out_of_scope", "duplicate", "other"]
    conclusion: str = Field(min_length=1, max_length=20000)
    closed_by: str = Field(min_length=1, max_length=300)
    reviewed: bool = False
