"""Internal report contracts; these annotations do not transform persisted JSON.

Source dictionaries deliberately remain open-ended: the complete imported row and
captured provider response must survive future schema additions unchanged.
"""

from typing import Any, NotRequired, TypedDict


class HandlingPolicy(TypedDict):
    label: str
    standard_version: str
    policy_version: str
    foreground: str
    background: str
    minimum_font_pt: int
    source_restrictions: list
    guidance_url: str
    sharing: str


class DocumentPolicy(TypedDict):
    brand_profile: dict[str, Any]
    print_policy_version: str
    renderer_version: str
    handling: HandlingPolicy
    paragraph_alignment: NotRequired[str]


class ReadinessItem(TypedDict):
    key: str
    label: str
    ok: bool


class Certification(TypedDict):
    certified_by: str
    certified_at: str
    revision: NotRequired[int]
    report_id: NotRequired[str]


class ReportSnapshot(TypedDict):
    schema_version: int
    app_version: str
    notification_id: str
    case_id: str
    entity_id: str
    domain: str
    entity_name: str
    hostnames: list
    draft_revision: int
    report_revision: int
    created_at: str
    demo: bool
    profile: dict[str, Any]
    entity_profile: dict[str, Any]
    draft: dict[str, Any]
    assets: list[dict[str, Any]]
    cves: list[str]
    explainers: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    references: list[str]
    qualified_lead: dict[str, Any]
    readiness: list[ReadinessItem]
    document_policy: DocumentPolicy
    handling: HandlingPolicy
    source_snapshots: list[dict[str, Any]]
    source_integrity_issues: list
    attribution_history: list[dict[str, Any]]
    composition: dict[str, Any]
    section_reviews: NotRequired[list[dict[str, Any]]]
    section_history: NotRequired[list[dict[str, Any]]]
    section_validations: NotRequired[list[dict[str, Any]]]
    certification: NotRequired[Certification]
    chronology: NotRequired[list[dict[str, Any]]]
    contact_research: NotRequired[dict[str, Any]]
    exhibit_artifacts: NotRequired[list[dict[str, Any]]]
    package_format: NotRequired[str]
    intake_score: NotRequired[dict[str, Any]]
