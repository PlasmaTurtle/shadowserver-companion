"""A completed qualification cannot contain unrelated or incomplete evidence."""

from copy import deepcopy

import pytest

from modules.accretion.components.qualified_lead import QualifiedLead
from modules.accretion.tests.support.products import qualification_values


def test_qualified_product_detaches_source_and_evidence_from_its_caller():
    values = qualification_values()
    lead = QualifiedLead(**values)
    values["candidate"].group.observations[0].source.fields["tag"] = "unrelated"
    values["attribution"]["attribution"]["root_domain"] = "unrelated.example"
    values["website"]["capture"]["http_status"] = 500
    values["findings"][0]["condition"] = "unrelated"
    exported = lead.evidence()
    exported["findings"].clear()
    lead.website["capture"]["http_status"] = 500
    lead.validate()
    assert lead.group.observations[0].source.fields["tag"] == "eol-php"
    assert lead.condition_scopes() == {0: ["eol-php:7.3"]}
    assert lead.website["capture"]["http_status"] == 200


@pytest.mark.parametrize("field", ["findings", "coverage"])
def test_empty_evidence_cannot_be_a_qualified_lead(field):
    values = qualification_values()
    values[field] = ()
    with pytest.raises(ValueError):
        QualifiedLead(**values)


@pytest.mark.parametrize("index", [-1, 1, True, "0"])
def test_findings_must_reference_an_actual_source_observation(index):
    values = qualification_values()
    values["findings"][0]["entry_index"] = index
    with pytest.raises(ValueError, match="reference a candidate observation"):
        QualifiedLead(**values)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("condition", "CVE-2026-99999"),
        ("kind", "cve"),
        ("report_type", "compromised_website"),
        ("source", {"workbook": "other.csv", "sheet": "CSV", "row": 2}),
        ("basis", "synthetic_demonstration"),
    ],
)
def test_finding_scope_must_match_original_source_evidence(field, value):
    values = qualification_values()
    values["findings"][0][field] = value
    with pytest.raises(ValueError, match="match its source evidence"):
        QualifiedLead(**values)


@pytest.mark.parametrize("field", ["id", "observation_kind"])
@pytest.mark.parametrize("missing", [None, "", " "])
def test_qualified_findings_require_the_report_schema_from_filter(field, missing):
    values = qualification_values()
    values["candidate"].group.observations[0].normalized["profile"][field] = missing
    finding_field = "report_type" if field == "id" else field
    values["findings"][0][finding_field] = missing
    with pytest.raises(ValueError, match="report schema"):
        QualifiedLead(**values)


def test_filtered_out_observation_cannot_be_a_qualified_finding():
    values = qualification_values()
    values["candidate"].group.observations[0].normalized["eligibility"]["eligible"] = False
    with pytest.raises(ValueError, match="not admitted by Filter"):
        QualifiedLead(**values)


def test_coverage_of_another_report_row_cannot_qualify_the_candidate():
    values = qualification_values()
    values["coverage"][0]["source"]["row"] = 3
    with pytest.raises(ValueError, match="does not cover"):
        QualifiedLead(**values)


@pytest.mark.parametrize("failure", ["unrelated", "unavailable", "no_screenshot"])
def test_website_requires_retained_functioning_related_screenshot(failure):
    values = qualification_values()
    website = values["website"]
    if failure == "unrelated":
        website["capture"]["final_url"] = website["final_url"] = "https://unrelated.example/"
    elif failure == "unavailable":
        website["capture"]["http_status"] = 500
    else:
        website.pop("sha256")
    with pytest.raises(ValueError, match="retained functioning related screenshot"):
        QualifiedLead(**values)


def test_direct_source_mutation_is_rejected_at_next_handoff():
    lead = QualifiedLead(**qualification_values())
    lead.group.observations[0].source.fields["tag"] = "unrelated"
    with pytest.raises(ValueError, match="match its source evidence"):
        lead.validate()


def test_actionable_projection_preserves_source_but_admits_only_qualified_conditions():
    values = qualification_values()
    values["candidate"].group.observations[0].source.fields["tag"] += ";CVE-2026-12345"
    lead = QualifiedLead(**values)
    projected = lead.actionable_entries()
    assert projected[0]["normalized"]["active_conditions"] == ["eol-php:7.3"]
    assert projected[0]["source"]["fields"]["tag"] == "eol-php;CVE-2026-12345"
    assert "active_conditions" not in lead.group.observations[0].normalized


def test_explicit_demonstration_has_exact_source_scope_even_without_decision_time():
    values = qualification_values(demonstration=True)
    values.pop("findings")
    lead = QualifiedLead.demonstration(**values)
    assert lead.is_demonstration
    assert lead.condition_scopes() == {0: ["eol-php:7.3"]}
    assert lead.findings[0]["source"]["row"] == 2
    assert lead.findings[0]["basis"] == "synthetic_demonstration"
    assert lead.actionable_entries()[0]["normalized"]["active_conditions"] == ["eol-php:7.3"]
    lead.validate()


def test_demonstration_path_cannot_be_used_for_ordinary_evidence():
    values = qualification_values()
    values.pop("findings")
    with pytest.raises(ValueError, match="explicitly synthetic"):
        QualifiedLead.demonstration(**values)


def test_normal_constructor_rejects_synthetic_evidence_and_incomplete_decision():
    with pytest.raises(ValueError, match="completed real decision"):
        QualifiedLead(**qualification_values(demonstration=True))
    values = qualification_values()
    values["attribution"].pop("evaluated_at")
    with pytest.raises(ValueError, match="completed real decision"):
        QualifiedLead(**values)


def test_qualified_product_requires_the_typed_previous_stage():
    values = qualification_values()
    values["candidate"] = deepcopy(values["candidate"].payload())
    with pytest.raises(TypeError, match="report-bound candidate"):
        QualifiedLead(**values)
