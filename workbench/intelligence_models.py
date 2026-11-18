"""Internal JSON contracts for normalized vulnerability intelligence.

These annotations document the adapter boundary without coercing, dropping, or
rewriting captured provider fields. Optional keys support older saved revisions.
Raw source bodies stay JSON objects and are never reconstructed from these types.
Request validation remains in api_models; provider validation remains in adapters.
"""

from typing import Literal, Required, TypedDict

type JSONValue = None | bool | int | float | str | list[JSONValue] | dict[str, JSONValue]
type RawRecord = dict[str, JSONValue]


class SourceReference(TypedDict, total=False):
    publisher: str
    url: str
    public_url: str
    retrieved_at: str | None
    revision_id: str
    record_path: str
    original_record_path: str
    body_sha256: str
    sha256: str
    http_status: int


class RansomwareSignal(TypedDict):
    status: str
    raw: JSONValue
    label: str
    availability: str
    source_revision_id: str | None


class SSVCAssessment(TypedDict, total=False):
    id: Required[str]
    publisher: str
    provider_role: str
    role: JSONValue
    scheme_version: JSONValue
    assessed_at: str | None
    assessment_date_valid: bool
    exploitation: Literal["active", "poc", "none"] | None
    raw_exploitation: JSONValue
    label: str
    availability: str
    source_revision_id: str | None
    source_path: str
    raw_options: JSONValue
    raw: RawRecord


class CVERecord(TypedDict, total=False):
    id: Required[str]
    verification_status: str
    state: str
    source: str
    description: str
    cvss: float | None
    severity: str | None
    cvss_assessments: list[RawRecord]
    epss: float | None
    epss_percentile: float | None
    epss_date: str | None
    epss_availability: str
    kev: bool | None
    kev_details: RawRecord | None
    kev_availability: str
    kev_catalog_complete: bool
    ransomware: RansomwareSignal
    ssvc_assessments: list[SSVCAssessment]
    selected_ssvc_assessment_id: str | None
    ssvc_availability: str
    impacts: list[RawRecord]
    sources: list[SourceReference]
    record: RawRecord
    record_path: str
    body_sha256: str
    references: list[str]
    affected: list[RawRecord]
    retrieved_at: str | None
    checked_at: str
    revision_id: str
    intelligence_revision_id: str
    acquisition: list[RawRecord]
    errors: list[str]
    from_cache: bool
    stale: bool


class IntelligenceFlags(TypedDict):
    kev: Literal[True] | None
    ransomware_known: Literal[True] | None
    intelligence_basis: str
