"""Evaluate's immutable scope, assessment and qualified-lead handoff."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math

from modules.attribution.components.attribution_bridge import same_domain
from modules.workspace.components.primitives import dump

from .qualified_lead import QualifiedLead


@dataclass(frozen=True, slots=True, init=False)
class EvaluationScope:
    """Snapshot selected by Leads; it may combine several qualified reports."""

    root_domain: str
    fingerprint: str
    _snapshot: str

    def __init__(self, frontier: dict):
        root = frontier["winner"]["root_domain"]
        fingerprint = frontier["fingerprint"]
        if not isinstance(root, str) or not root:
            raise ValueError("Evaluate requires a domain scope")
        if not isinstance(fingerprint, str) or len(fingerprint) != 64:
            raise ValueError("Evaluate requires a scope fingerprint")
        if not frontier["entries"]:
            raise ValueError("Evaluate requires actionable findings")
        snapshot = {
            key: frontier[key] for key in ("winner", "entries", "policy", "as_of", "rows", "parsed")
        }
        object.__setattr__(self, "root_domain", root)
        object.__setattr__(self, "fingerprint", fingerprint)
        object.__setattr__(self, "_snapshot", dump(snapshot))

    def inputs(self) -> dict:
        """Return detached scorer inputs; queue ownership stays with Leads."""
        return json.loads(self._snapshot)

    def require_lead(self, lead: QualifiedLead) -> None:
        """Check the actual qualified projection, including its report identity."""
        from .awareness_identity import source_key

        inputs = self.inputs()
        row = next(
            (
                row
                for row in inputs["rows"]
                if row["import_id"] == lead.report.id
                and same_domain(row["root_domain"], lead.group.root_domain)
            ),
            None,
        )
        if row is None:
            raise ValueError("Evaluation does not include this report's qualified lead")
        expected = json.loads(dump(lead.actionable_entries()))
        for entry in expected:
            normalized = entry.setdefault("normalized", {})
            normalized.setdefault("source_sha256", lead.report.sha256)
            normalized.setdefault("observation_ref", source_key(entry, normalized["source_sha256"]))
        if expected != inputs["parsed"][row["id"]]:
            raise ValueError("Evaluation does not describe these qualified findings")


@dataclass(frozen=True, slots=True, init=False)
class UrgencyAssessment:
    """A score bound to the exact scope that Evaluate ranked."""

    scope: EvaluationScope
    _score: str

    def __init__(self, scope: EvaluationScope, score: dict):
        if not isinstance(scope, EvaluationScope):
            raise TypeError("An urgency assessment requires an EvaluationScope")
        value = score.get("aggregate")
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 100:
            raise ValueError("An urgency assessment requires an aggregate from 0 to 100")
        if score.get("evaluation_scope", {}).get("fingerprint") != scope.fingerprint:
            raise ValueError("Urgency assessment does not match its evaluation scope")
        object.__setattr__(self, "scope", scope)
        object.__setattr__(self, "_score", dump(score))

    def payload(self) -> dict:
        return json.loads(self._score)


@dataclass(frozen=True, slots=True, init=False)
class EvaluatedLead:
    """The only Associate input: qualified evidence plus its completed assessment."""

    lead: QualifiedLead
    assessment: UrgencyAssessment
    _references: str

    def __init__(self, lead: QualifiedLead, assessment: UrgencyAssessment, cve_records=()):
        if not isinstance(lead, QualifiedLead):
            raise TypeError("Evaluate requires a QualifiedLead")
        if not isinstance(assessment, UrgencyAssessment):
            raise TypeError("Associate requires an UrgencyAssessment")
        lead.validate()
        assessment.scope.require_lead(lead)
        object.__setattr__(self, "lead", lead)
        object.__setattr__(self, "assessment", assessment)
        object.__setattr__(self, "_references", dump(list(cve_records)))

    @property
    def cve_records(self) -> list[dict]:
        return json.loads(self._references)

    def validate(self) -> None:
        self.lead.validate()
        self.assessment.scope.require_lead(self.lead)
