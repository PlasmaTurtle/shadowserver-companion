"""Public data contracts for validated responses and explicit capture receipts."""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

VERSION = "0.2.8"
SCHEMA_VERSION = 2
Status = Literal["matched", "review", "no_match", "incomplete", "deferred", "no_eligible_ip"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")


def parse_json(body: bytes) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON member")
            result[key] = value
        return result

    def reject(value):
        raise ValueError("Non-finite JSON number")

    try:
        value = json.loads(body, object_pairs_hook=pairs, parse_constant=reject)
    except (UnicodeError, RecursionError, json.JSONDecodeError) as error:
        raise ValueError("Response is not valid JSON") from error
    if not isinstance(value, dict):
        raise ValueError("Response must be a JSON object")
    return value


@dataclass(frozen=True)
class Settings:
    timeout: float = 10.0
    operation_budget: float = 45.0
    retries: int = 1
    interval: float = 0.5
    max_response_bytes: int = 2 * 1024 * 1024
    max_redirects: int = 5
    max_entity_requests: int = 8
    max_entity_depth: int = 3
    cache_ttl: float = 86400.0
    negative_ttl: float = 600.0
    bootstrap_ttl: float = 86400.0
    enable_dns: bool = True

    def __post_init__(self):
        if type(self.enable_dns) is not bool:
            raise ValueError("enable_dns must be a boolean")
        for name in ("timeout", "operation_budget", "cache_ttl", "negative_ttl", "bootstrap_ttl"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be positive and finite")
        if not math.isfinite(self.interval) or self.interval < 0:
            raise ValueError("interval must be nonnegative and finite")
        for name, low, high in (("retries", 0, 3), ("max_redirects", 0, 10),
                               ("max_entity_requests", 0, 50), ("max_entity_depth", 0, 10),
                               ("max_response_bytes", 1024, 20 * 1024 * 1024)):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{name} must be an integer between {low} and {high}")


@dataclass(frozen=True)
class CandidateIP:
    entry_id: str
    ip: str
    hostname: str | None = None


@dataclass(frozen=True)
class DomainMatch:
    target_domain: str
    matched_domain: str
    field_path: str  # RFC 6901 JSON Pointer, relative to the saved response
    value: str
    entity_handle: str | None = None
    entity_roles: tuple[str, ...] = ()
    field_type: str = "text"


@dataclass(frozen=True)
class ResponseSnapshot:
    snapshot_id: str
    requested_url: str
    source_url: str
    retrieved_at: str
    status_code: int
    headers: dict[str, str]
    body: bytes = field(repr=False)
    body_sha256: str = ""
    body_retention: str = "original"
    received_body_sha256: str = ""
    received_body_size: int | None = None

    @classmethod
    def create(cls, requested_url, source_url, status_code, headers, body):
        return cls(uuid4().hex, requested_url, source_url, utc_now(), status_code,
                   headers, body, hashlib.sha256(body).hexdigest())

    def metadata(self) -> dict:
        result = asdict(self)
        del result["body"]
        result["body_size"] = len(self.body)
        # Existing source metadata participates in pinned attribution/contact
        # fingerprints. Default fields must not change their historical shape.
        if self.body_retention == "original" and not self.received_body_sha256 and self.received_body_size is None:
            for key in ("body_retention", "received_body_sha256", "received_body_size"):
                result.pop(key)
        return result

    def record(self) -> dict:
        return parse_json(self.body)

    def without_body(self, reason: str) -> ResponseSnapshot:
        """An explicit receipt, with separate received and stored-byte hashes."""
        if self.body_retention != "original":
            return self
        return replace(self, body=b"", body_sha256=hashlib.sha256(b"").hexdigest(),
                       body_retention=reason, received_body_sha256=self.body_sha256,
                       received_body_size=len(self.body))


@dataclass(frozen=True)
class AttributionEvidence:
    method: str
    ip: str
    source_name: str
    source_url: str
    retrieved_at: str
    snapshot_id: str
    supporting_snapshot_ids: tuple[str, ...]
    match: DomainMatch
    details: dict = field(default_factory=dict)
    from_cache: bool = False


@dataclass(frozen=True)
class ProviderResult:
    status: str
    evidence: AttributionEvidence | None = None
    reason: str = ""
    message: str = ""
    snapshot_ids: tuple[str, ...] = ()
    retry_at: float | None = None
    warnings: tuple[str, ...] = ()
    network_requests: int = 0
    cache_hits: int = 0
    partial_evidence: tuple[AttributionEvidence, ...] = ()


@dataclass(frozen=True)
class Attempt:
    entry_id: str
    ip: str
    method: str
    status: str
    reason: str
    message: str = ""
    snapshot_ids: tuple[str, ...] = ()
    retry_at: float | None = None
    warnings: tuple[str, ...] = ()
    network_requests: int = 0
    cache_hits: int = 0


@dataclass(frozen=True)
class AttributionResult:
    result_id: str
    root_domain: str
    status: Status
    evaluated_at: str
    candidates: tuple[CandidateIP, ...]
    matched_entry_id: str | None
    matched_ip: str | None
    evidence: tuple[AttributionEvidence, ...]
    attempts: tuple[Attempt, ...]
    policy: dict
    settings: dict
    schema_version: int = SCHEMA_VERSION
    module_version: str = VERSION
    partial_evidence: tuple[AttributionEvidence, ...] = ()

    def to_dict(self) -> dict:
        return asdict(self)


class LookupFailure(Exception):
    def __init__(self, reason, message, *, status="deferred", retry_at=None, snapshot_ids=()):
        super().__init__(message)
        self.reason, self.status = reason, status
        self.retry_at, self.snapshot_ids = retry_at, tuple(snapshot_ids)

