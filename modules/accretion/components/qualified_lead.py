"""Qualify's validated product: source scope, attribution and a related screenshot.

Constructors check evidence relationships without database or network work.
The owning services retain/check the referenced bytes and recheck live ownership.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import json
import re

from modules.attribution.components.attribution_bridge import coverage_covers, same_domain
from modules.investigations.components import website_evidence

from .awareness import conditions
from .intake.records import CandidateGroup, observation_payload
from .intake.versions import project_conditions
from .report import Report, ReportCandidate


def _check_findings(candidate, findings, *, demonstration):
    observations = candidate.group.observations
    if not findings:
        raise ValueError("A qualified lead requires actionable source findings")
    seen, expected = set(), {}
    for finding in findings:
        index = finding.get("entry_index")
        if type(index) is not int or not 0 <= index < len(observations):
            raise ValueError("Qualified finding does not reference a candidate observation")
        if index not in expected:
            observation = observations[index]
            entry = observation_payload(observation)
            profile = observation.normalized.get("profile") or {}
            if not demonstration:
                if any(
                    not isinstance(profile.get(key), str) or not profile[key].strip()
                    for key in ("id", "observation_kind")
                ):
                    raise ValueError("Qualified finding requires its report schema from Filter")
                if observation.normalized.get("eligibility", {}).get("eligible") is not True:
                    raise ValueError("Qualified finding was not admitted by Filter")
            source = entry["source"]
            report_type = source["fields"].get("report_type") if demonstration else profile["id"]
            expected[index] = (
                set(conditions(entry)),
                {key: source[key] for key in ("workbook", "sheet", "row")},
                report_type,
                profile.get("observation_kind"),
            )
        supported, source_reference, report_type, observation_kind = expected[index]
        if (
            (finding.get("condition"), finding.get("kind")) not in supported
            or finding.get("source") != source_reference
            or finding.get("report_type") != report_type
            or finding.get("observation_kind") != observation_kind
            or finding.get("basis")
            != ("synthetic_demonstration" if demonstration else "shadowserver_report")
        ):
            raise ValueError("Qualified finding does not match its source evidence")
        key = (index, finding["condition"])
        if key in seen:
            raise ValueError("Qualified finding scope contains a duplicate condition")
        seen.add(key)


def _check_evidence(candidate, evidence, *, demonstration):
    if not isinstance(candidate, ReportCandidate):
        raise TypeError("Qualify requires a report-bound candidate group")
    # Recheck source identity as well as finding coverage at downstream handoffs.
    candidate.group.validate()
    ReportCandidate(candidate.report, candidate.group)
    attribution, website = evidence["attribution"], evidence["website"]
    root = candidate.group.root_domain
    entries = [observation_payload(value) for value in candidate.group.observations]
    if not same_domain(
        attribution.get("attribution", {}).get("root_domain"), root
    ) or not coverage_covers(entries, {**attribution, "coverage": evidence["coverage"]}):
        raise ValueError("Attribution does not cover the qualified source observations")
    if not attribution.get("snapshot_id") or not re.fullmatch(
        r"[0-9a-f]{64}", str(attribution.get("body_sha256", ""))
    ):
        raise ValueError("Qualified attribution requires retained source evidence")
    capture = website.get("capture") or {}
    if (
        not same_domain(website.get("root_domain"), root)
        or not website_evidence.is_usable_capture(capture)
        or not website_evidence.related_capture(capture, root)
        or not website.get("id")
        or any(not website.get(key) for key in ("path", "preview_path", "metadata_path"))
        or any(
            not re.fullmatch(r"[0-9a-f]{64}", str(website.get(key, "")))
            for key in ("sha256", "preview_sha256", "metadata_sha256")
        )
        or any(
            website.get(key) != capture.get(key)
            for key in ("requested_url", "final_url", "captured_at", "capture_status")
        )
    ):
        raise ValueError("A qualified lead requires a retained functioning related screenshot")
    if demonstration:
        if (
            not root.endswith(".example")
            or attribution.get("synthetic") is not True
            or capture.get("synthetic") is not True
            or any(
                not str(entry["source"]["fields"].get("source_note", "")).startswith(
                    "SYNTHETIC DEMONSTRATION"
                )
                for entry in entries
            )
        ):
            raise ValueError("Demonstration qualification requires explicitly synthetic evidence")
    elif (
        attribution.get("synthetic")
        or capture.get("synthetic")
        or not attribution.get("evaluated_at")
    ):
        raise ValueError("Qualified attribution requires a completed real decision")
    if not isinstance(evidence["ownership_token"], str) or not evidence["ownership_token"]:
        raise ValueError("A qualified lead requires its ownership context")
    _check_findings(candidate, evidence["findings"], demonstration=demonstration)


@dataclass(frozen=True, slots=True, init=False)
class QualifiedLead:
    """Completed qualification; callers cannot replace its evidence with a dictionary."""

    candidate: ReportCandidate
    _evidence_json: str = field(repr=False)
    is_demonstration: bool = False

    def __init__(
        self,
        candidate: ReportCandidate,
        attribution: dict,
        coverage: tuple[dict, ...],
        website: dict,
        findings: tuple[dict, ...],
        ownership_token: str,
    ) -> None:
        self._initialize(
            candidate, attribution, coverage, website, findings, ownership_token, False
        )

    def _initialize(
        self, candidate, attribution, coverage, website, findings, token, demonstration
    ):
        if not isinstance(candidate, ReportCandidate):
            raise TypeError("Qualify requires a report-bound candidate group")
        evidence = {
            "version": 1,
            "root_domain": candidate.group.root_domain,
            "attribution": attribution,
            "coverage": list(coverage),
            "website": website,
            "findings": list(findings),
            "ownership_token": token,
        }
        # JSON is already the evidence owners' interchange format. Retain one
        # detached snapshot, exporting fresh values instead of mutable aliases.
        encoded = json.dumps(evidence, ensure_ascii=False, allow_nan=False)
        _check_evidence(candidate, json.loads(encoded), demonstration=demonstration)
        object.__setattr__(self, "candidate", deepcopy(candidate))
        object.__setattr__(self, "_evidence_json", encoded)
        object.__setattr__(self, "is_demonstration", demonstration)

    @classmethod
    def demonstration(
        cls,
        candidate: ReportCandidate,
        attribution: dict,
        coverage: tuple[dict, ...],
        website: dict,
        ownership_token: str,
    ) -> QualifiedLead:
        """Build labelled demo evidence with exact row/condition scope, never real attribution."""
        findings = []
        for index, observation in enumerate(candidate.group.observations):
            entry = observation_payload(observation)
            source = entry["source"]
            for condition, kind in conditions(entry):
                findings.append(
                    {
                        "entry_index": index,
                        "finding_id": None,
                        "condition": condition,
                        "kind": kind,
                        "report_type": source["fields"].get("report_type"),
                        "observation_kind": observation.normalized.get("profile", {}).get(
                            "observation_kind"
                        ),
                        "basis": "synthetic_demonstration",
                        "source": {key: source[key] for key in ("workbook", "sheet", "row")},
                    }
                )
        lead = object.__new__(cls)
        lead._initialize(candidate, attribution, coverage, website, findings, ownership_token, True)
        return lead

    @property
    def group(self) -> CandidateGroup:
        return self.candidate.group

    @property
    def report(self) -> Report:
        return self.candidate.report

    @property
    def attribution(self) -> dict:
        return self.evidence()["attribution"]

    @property
    def coverage(self) -> tuple[dict, ...]:
        return tuple(self.evidence()["coverage"])

    @property
    def website(self) -> dict:
        return self.evidence()["website"]

    @property
    def findings(self) -> tuple[dict, ...]:
        return tuple(self.evidence()["findings"])

    @property
    def ownership_token(self) -> str:
        return self.evidence()["ownership_token"]

    def condition_scopes(self) -> dict[int, list[str]]:
        scopes = {}
        for finding in self.findings:
            scopes.setdefault(finding["entry_index"], []).append(finding["condition"])
        return scopes

    def actionable_entries(self) -> list[dict]:
        """Project precisely the approved conditions, retaining original source fields."""
        scopes = self.condition_scopes()
        return [
            project_conditions(observation_payload(observation), scopes[index])
            for index, observation in enumerate(self.group.observations)
            if index in scopes
        ]

    def evidence(self) -> dict:
        return json.loads(self._evidence_json)

    def validate(self) -> None:
        """Reject accidental source mutation before another stage consumes this product."""
        _check_evidence(self.candidate, self.evidence(), demonstration=self.is_demonstration)
