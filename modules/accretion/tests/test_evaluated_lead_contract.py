"""Evaluate and Associate accept only their completed, matching stage products."""

from copy import deepcopy

import pytest

from modules.accretion.components.association import associate_lead
from modules.accretion.components.awareness_identity import source_key
from modules.accretion.components.evaluated_lead import (
    EvaluatedLead,
    EvaluationScope,
    UrgencyAssessment,
)
from modules.accretion.components.evaluation import evaluate_lead, evaluate_scope
from modules.accretion.components.qualified_lead import QualifiedLead
from modules.accretion.tests.support.products import qualification_values


@pytest.fixture
def qualified():
    return QualifiedLead(**qualification_values())


def frontier_for(lead):
    entries = lead.actionable_entries()
    for entry in entries:
        entry["normalized"]["observation_ref"] = source_key(entry, lead.report.sha256)
    queued = {
        "id": "candidate-queue",
        "import_id": lead.report.id,
        "root_domain": lead.group.root_domain,
        "entity_id": None,
        "intake_score": "{}",
    }
    return {
        "winner": queued,
        "rows": [queued],
        "parsed": {queued["id"]: deepcopy(entries)},
        "entries": entries,
        "policy": None,
        "as_of": "2026-11-21T10:00:00Z",
        "fingerprint": "f" * 64,
    }


def assessment_for(frontier):
    scope = EvaluationScope(frontier)
    score = {
        "aggregate": 42,
        "evaluation_scope": {"version": 2, "fingerprint": scope.fingerprint},
    }
    return UrgencyAssessment(scope, score)


def test_incomplete_stage_products_stop_before_provider_or_storage_work(qualified):
    with pytest.raises(TypeError, match="QualifiedLead"):
        evaluate_lead(None, qualified.candidate, checkpoint=lambda: None)
    with pytest.raises(TypeError, match="EvaluationScope"):
        evaluate_scope(frontier_for(qualified))
    with pytest.raises(TypeError, match="EvaluatedLead"):
        associate_lead(None, qualified)
    with pytest.raises(TypeError, match="UrgencyAssessment"):
        EvaluatedLead(qualified, {"aggregate": 42})


@pytest.mark.parametrize("mismatch", ["report", "domain", "findings"])
def test_evaluated_lead_rejects_assessment_for_different_qualified_work(qualified, mismatch):
    frontier = frontier_for(qualified)
    if mismatch == "report":
        frontier["winner"]["import_id"] = "another-report"
    elif mismatch == "domain":
        frontier["winner"]["root_domain"] = "another.example"
    else:
        frontier["parsed"]["candidate-queue"][0]["normalized"]["active_conditions"] = []
    with pytest.raises(ValueError, match="report|domain|findings"):
        EvaluatedLead(qualified, assessment_for(frontier))


@pytest.mark.parametrize("current_root", ["example.com", "EXAMPLE.COM"])
def test_entity_scope_accepts_current_lead_when_another_domain_wins(qualified, current_root):
    frontier = frontier_for(qualified)
    current = frontier["rows"][0]
    current.update(root_domain=current_root, entity_id="same-entity")
    winner = {
        **current,
        "id": "other-queue",
        "import_id": "other-report",
        "root_domain": "example.net",
    }
    other_entries = deepcopy(frontier["entries"])
    for entry in other_entries:
        entry["source"]["workbook"] = "other-report.csv"
        entry["source"]["fields"]["hostname"] = "example.net"
        entry["normalized"]["source_sha256"] = "b" * 64
        entry["normalized"]["observation_ref"] = source_key(entry, "b" * 64)
    frontier["winner"] = winner
    frontier["rows"].append(winner)
    frontier["parsed"][winner["id"]] = other_entries
    frontier["entries"].extend(other_entries)

    evaluated = EvaluatedLead(qualified, assessment_for(frontier))

    assert evaluated.lead.report.id == current["import_id"]
    assert evaluated.assessment.scope.root_domain == winner["root_domain"]
    assert len(evaluated.assessment.scope.inputs()["rows"]) == 2
    evaluated.validate()


def test_empty_actionable_scope_cannot_become_an_assessment(qualified):
    frontier = frontier_for(qualified)
    frontier["entries"] = []
    with pytest.raises(ValueError, match="actionable"):
        EvaluationScope(frontier)


def test_score_cannot_be_attached_to_a_different_scope(qualified):
    scope = EvaluationScope(frontier_for(qualified))
    with pytest.raises(ValueError, match="scope"):
        UrgencyAssessment(scope, {"aggregate": 42, "evaluation_scope": {"fingerprint": "e" * 64}})


@pytest.mark.parametrize("aggregate", [float("nan"), float("inf"), -1, 101, True])
def test_assessment_rejects_unusable_ranking_values(qualified, aggregate):
    scope = EvaluationScope(frontier_for(qualified))
    with pytest.raises(ValueError, match="aggregate"):
        UrgencyAssessment(
            scope, {"aggregate": aggregate, "evaluation_scope": {"fingerprint": scope.fingerprint}}
        )


def test_evaluated_product_detaches_score_scope_and_references(qualified):
    frontier = frontier_for(qualified)
    original_frontier = deepcopy(frontier)
    scope = EvaluationScope(frontier)
    score = {"aggregate": 42, "evaluation_scope": {"fingerprint": scope.fingerprint}}
    references = [{"cve_id": "CVE-2026-12345", "references": ["retained-reference"]}]
    assessment = UrgencyAssessment(scope, score)
    evaluated = EvaluatedLead(qualified, assessment, references)
    frontier["parsed"]["candidate-queue"].clear()
    score["aggregate"] = 99
    references[0]["references"].clear()
    assessment.payload()["evaluation_scope"]["fingerprint"] = "changed"
    evaluated.cve_records[0]["references"].clear()
    assert assessment.payload()["aggregate"] == 42
    assert assessment.payload()["evaluation_scope"]["fingerprint"] == scope.fingerprint
    assert scope.inputs()["parsed"] == original_frontier["parsed"]
    assert evaluated.cve_records[0]["references"] == ["retained-reference"]
    evaluated.validate()


def test_evaluate_rejects_changed_raw_ip_before_accessing_retained_evidence(qualified):
    qualified.group.observations[0].source.fields["ip"] = "1.1.1.1"
    with pytest.raises(ValueError, match="match the source address"):
        evaluate_lead(None, qualified, checkpoint=lambda: None)


@pytest.mark.parametrize("mutation", ["report_digest", "raw_ip"])
def test_associate_rechecks_a_product_changed_after_evaluation(qualified, mutation):
    evaluated = EvaluatedLead(qualified, assessment_for(frontier_for(qualified)))
    observation = evaluated.lead.group.observations[0]
    if mutation == "report_digest":
        observation.normalized["source_sha256"] = "b" * 64
        expected = "digest"
    else:
        observation.source.fields["ip"] = "1.1.1.1"
        expected = "match the source address"
    with pytest.raises(ValueError, match=expected):
        associate_lead(None, evaluated)
