"""Retained report identity and its candidate handoff; no persistence or I/O."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import re
from typing import Any

from .intake.files import restore_observation
from .intake.records import CandidateGroup, observation_payload


@dataclass(frozen=True, slots=True)
class Report:
    """The retained source descriptor, independent of report size and workflow."""

    id: str
    name: str
    sha256: str
    path: str

    def __post_init__(self) -> None:
        for field in ("id", "name", "path"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Report {field} must be a nonempty string")
        if not isinstance(self.sha256, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", self.sha256):
            raise ValueError("Report requires a SHA-256 digest")
        object.__setattr__(self, "sha256", self.sha256.lower())

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> Report:
        """Read only the stable source fields from an import record."""
        return cls(record["id"], record["name"], record["sha256"], record["path"])


@dataclass(frozen=True, slots=True)
class ReportCandidate:
    """One filtered domain group bound to the report that supplied its rows."""

    report: Report
    group: CandidateGroup

    def __post_init__(self) -> None:
        if not isinstance(self.report, Report):
            raise TypeError("ReportCandidate requires a Report")
        if not isinstance(self.group, CandidateGroup):
            raise TypeError("ReportCandidate requires a CandidateGroup")
        for observation in self.group.observations:
            if observation.source.workbook != self.report.name:
                raise ValueError("Candidate workbook does not belong to its report")
            digest = observation.normalized.get("source_sha256")
            if digest is not None and (
                not isinstance(digest, str) or digest.lower() != self.report.sha256
            ):
                raise ValueError("Candidate source digest does not belong to its report")

    @classmethod
    def restore(
        cls, report: Report, domain: str, payload: Iterable[Mapping[str, Any]]
    ) -> ReportCandidate:
        """Restore a saved job through the same validated source handoff."""
        observations = tuple(restore_observation(item) for item in payload)
        return cls(report, CandidateGroup(domain, observations))

    def payload(self) -> list[dict[str, object]]:
        """Keep the established job JSON shape at the persistence boundary."""
        return [observation_payload(observation) for observation in self.group.observations]
