"""The report explains only the association supported by saved case evidence."""

from copy import deepcopy

import pytest

from modules.investigations.components.attribution_model import REVISION
from modules.investigations.components.approved_template import ATTRIBUTION

from modules.investigations.tests.support.attribution_exhibit import (
    build,
    google_dns_inputs,
    inputs,
)


def test_exact_record_keeps_provenance_counts_and_approved_language_without_mutation():
    parts = inputs(count=70)
    parts[0]["qualified_lead"]["validated_leads"][0]["entries"].append(
        deepcopy(parts[0]["qualified_lead"]["validated_leads"][0]["entries"][0])
    )
    before = deepcopy(parts)
    model = build(parts)
    item = model["items"][0]
    assert model["layout_revision"] == REVISION and model["narrative"] == ATTRIBUTION
    assert item["supported"] and not item["review_required"]
    assert item["reported_ip"] == "192.0.2.14"
    assert item["corroborated_value"] == "192.0.2.0 – 192.0.2.255"
    assert item["reported_asset_count"] == 70 and item["supporting_attribution_count"] == 1
    assert item["validated_at"] == "2026-11-07T14:00:00Z"
    assert item["retrieved_at"] == "2026-11-01T09:00:00Z" and item["from_cache"]
    assert item["validated_by"] == "Attribution Module"
    assert item["appendix_entry_ids"] == ["B-1", "A-1"] and item["citations"] == [4]
    assert (
        model["business_registration_reviewed"]
        and "Business-registration" in model["business_registration_note"]
    )
    assert parts == before


def test_dns_reads_actual_answer_and_keeps_resolution_time_separate():
    parts = inputs("dns")
    item = build(parts)["items"][0]
    assert item["supported"] and item["corroborated_label"] == "DNS answer"
    assert item["corroborated_value"] == "192.0.2.14"
    assert item["method_label"] == "Forward DNS match"
    parts[2][0]["source"]["evidence"]["details"]["basis"] = "forward_confirmed_reverse"
    assert build(parts)["items"][0]["method_label"] == "Forward-confirmed reverse DNS"


@pytest.mark.parametrize(
    "change",
    ["different_answer", "missing_forward", "different_hostname", "different_query", "ptr_only"],
)
def test_dns_does_not_promote_insufficient_saved_evidence(change):
    parts = inputs("dns")
    proof = parts[2][0]["source"]
    if change == "different_answer":
        proof["record"]["answers"] = ["192.0.2.200"]
    if change == "missing_forward":
        proof["evidence"]["details"].pop("dns_forward_match")
    if change == "different_hostname":
        proof["evidence"]["details"]["resolved_hostname"] = "unrelated.example"
    if change == "different_query":
        proof["record"]["query"] = "other.example.com"
    if change == "ptr_only":
        proof["record"]["type"] = "PTR"
    item = build(parts)["items"][0]
    assert not item["supported"] and item["review_required"]
    assert item["supporting_attribution_count"] == 0


def test_unaccepted_keyword_stays_review_only_and_acceptance_has_its_own_author_time():
    parts = inputs("rdap_keyword")
    item = build(parts)["items"][0]
    assert not item["supported"] and "pending review" in item["method_label"]
    parts[2][0]["source"]["review"] = {
        "decision": "accept",
        "reviewer": "Example Analyst",
        "reviewed_at": "2026-11-07T17:00:00Z",
        "note": "Reviewed organization name.",
    }
    item = build(parts)["items"][0]
    assert item["supported"] and not item["review_required"]
    assert item["validated_by"] == "Example Analyst"
    assert item["validated_at"] == "2026-11-07T17:00:00Z"
    assert item["retrieved_at"] == "2026-11-01T09:00:00Z"
    parts[2][0]["source"]["review"]["decision"] = "reject"
    assert not build(parts)["items"][0]["supported"]


def test_missing_validation_time_never_uses_retrieval_time():
    parts = inputs()
    parts[2][0]["source"].pop("evaluated_at")
    item = build(parts)["items"][0]
    assert item["supported"] and item["review_required"]
    assert item["validated_at"] is None and item["validated_by"] is None
    assert item["timestamp_note"] == "Validation time was not recorded."


@pytest.mark.parametrize(
    "change",
    ["no_entries", "wrong_hostname", "proof_mismatch", "evidence_mismatch"],
)
def test_reported_ip_comes_from_selected_observation_not_the_evidence(change):
    parts = inputs()
    entries = parts[0]["qualified_lead"]["validated_leads"][0]["entries"]
    proof = parts[2][0]["source"]
    if change == "no_entries":
        entries.clear()
    if change == "wrong_hostname":
        entries[0]["source"]["fields"]["hostname"] = "other.example"
    if change == "proof_mismatch":
        proof["ip"] = "192.0.2.250"
    if change == "evidence_mismatch":
        proof["evidence"]["ip"] = "192.0.2.250"
    item = build(parts)["items"][0]
    assert not item["supported"]
    if change == "no_entries":
        assert item["reported_ip"] == "Not recorded"


def test_source_order_does_not_change_the_original_supporting_association():
    parts = inputs()
    entries = parts[0]["qualified_lead"]["validated_leads"][0]["entries"]
    entries.reverse()
    before = deepcopy(entries)
    item = build(parts)["items"][0]
    assert item["supported"] and item["reported_ip"] == "192.0.2.14"
    assert entries == before


@pytest.mark.parametrize("method", ["rdap", "dns"])
def test_historical_proof_covers_current_rows_without_changing_evidence_ip(method):
    from modules.accretion.components.intake.records import (
        SourceObservation,
        CandidateObservation,
        CandidateGroup,
    )
    from modules.attribution.components.attribution_bridge import group_coverage

    parts = inputs(method, count=1)
    entries = parts[0]["qualified_lead"]["validated_leads"][0]["entries"]
    entry = entries[0]
    entry["ip"] = "198.51.100.20"
    entry["source"]["fields"]["ip"] = entry["ip"]
    entry["source"].update(workbook="current.csv", sheet="Report", row=2)
    proof = parts[2][0]["source"]
    proof.update(
        result_id="original-result",
        attribution={"root_domain": "example.com", "matched_domain": "remote.example.com"},
    )
    group = CandidateGroup(
        "example.com",
        [CandidateObservation(SourceObservation(**entry["source"]), entry["ip"], False)],
    )
    proof["coverage"] = group_coverage(group, proof)
    before = deepcopy(parts)
    item = build(parts)["items"][0]
    assert item["supported"] and not item["review_required"]
    assert item["reported_ip"] == "198.51.100.20"
    assert item["evidence_ip"] == "192.0.2.14"
    assert "evidence IP 192.0.2.14" in item["explanation"]
    assert parts == before
    entry["source"]["row"] = 3
    assert not build(parts)["items"][0]["supported"]


@pytest.mark.parametrize(
    "change",
    ["outside_range", "inconsistent_range", "wrong_domain", "wrong_value", "missing_record"],
)
def test_registration_match_requires_the_saved_field_and_covering_network(change):
    parts = inputs()
    proof = parts[2][0]["source"]
    if change == "outside_range":
        proof["evidence"]["details"].update(
            network_start="198.51.100.0", network_end="198.51.100.255"
        )
        proof["record"].update(startAddress="198.51.100.0", endAddress="198.51.100.255")
    if change == "inconsistent_range":
        proof["evidence"]["details"]["cidr"] = "198.51.100.0/24"
    if change == "wrong_domain":
        proof["evidence"]["match"]["matched_domain"] = "example.com.unrelated.example"
    if change == "wrong_value":
        proof["record"]["email"] = "security@unrelated.example"
    if change == "missing_record":
        proof["record"] = {}
    item = build(parts)["items"][0]
    assert not item["supported"] and item["review_required"]


def test_ipv6_numeric_containment_and_mapped_address_equivalence():
    parts = inputs()
    entry = parts[0]["qualified_lead"]["validated_leads"][0]["entries"][0]
    proof = parts[2][0]["source"]
    entry["ip"] = "::ffff:192.0.2.14"
    assert build(parts)["items"][0]["supported"]
    entry["ip"] = "2001:db8::a"
    proof["ip"] = "2001:0db8:0:0:0:0:0:a"
    proof["evidence"]["ip"] = "2001:db8::a"
    proof["evidence"]["details"].update(network_start="2001:db8::", network_end="2001:db8::ffff")
    proof["record"].update(startAddress="2001:db8::", endAddress="2001:db8::ffff")
    assert build(parts)["items"][0]["supported"]


def test_entity_record_can_reference_network_bounds_preserved_in_evidence_details():
    parts = inputs()
    proof = parts[2][0]["source"]
    proof["record"].pop("startAddress")
    proof["record"].pop("endAddress")
    assert build(parts)["items"][0]["supported"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("registry", "Different source"),
        ("source_url", "https://different.example/record"),
        ("retrieved_at", "2026-11-02T09:00:00Z"),
    ],
)
def test_citation_metadata_must_correspond_to_the_displayed_saved_evidence(field, value):
    parts = inputs()
    parts[2][0]["source"][field] = value
    item = build(parts)["items"][0]
    assert not item["supported"] and item["review_required"]
    assert "citation metadata disagrees" in item["explanation"]


def test_equivalent_timestamp_spellings_are_not_a_source_conflict():
    parts = inputs()
    parts[2][0]["source"]["retrieved_at"] = "2026-11-01T09:00:00+00:00"
    assert build(parts)["items"][0]["supported"]


def test_missing_citation_cannot_support_a_positive_exhibit_claim():
    parts = inputs()
    parts[2][0]["citation"] = None
    item = build(parts)["items"][0]
    assert not item["supported"] and item["review_required"]


def test_google_dns_exact_response_and_citation_metadata_are_rendered_without_mutation():
    parts = google_dns_inputs()
    before = deepcopy(parts)
    item = build(parts)["items"][0]
    proof = parts[2][0]["source"]
    assert item["supported"] and not item["review_required"]
    assert item["source_name"] == "Google Public DNS"
    assert item["source_url"] == proof["source_url"]
    assert item["retrieved_at"] == "2026-11-01T09:00:00Z" and item["from_cache"]
    assert item["validated_at"] == "2026-11-07T14:00:00Z"
    assert item["matched_field"] == "/Answer/2/data"
    assert item["corroborated_value"] == "192.0.2.14" and item["citations"] == [4]
    assert parts == before


@pytest.mark.parametrize(
    "change",
    [
        "unrelated_owner",
        "wrong_question",
        "wrong_pointer",
        "wrong_source_query",
        "wrong_type",
        "missing_alias",
        "source_metadata_conflict",
        "dns_failure",
        "wrong_value",
    ],
)
def test_google_report_does_not_promote_unrelated_or_conflicting_saved_answers(change):
    parts = google_dns_inputs()
    proof = parts[2][0]["source"]
    if change == "unrelated_owner":
        proof["record"]["Answer"][2]["name"] = "other.test."
    elif change == "wrong_question":
        proof["record"]["Question"][0]["name"] = "other.example.com."
    elif change == "wrong_pointer":
        proof["evidence"]["match"]["field_path"] = "/Answer/1/data"
    elif change == "wrong_source_query":
        proof["source_url"] = proof["evidence"]["source_url"] = (
            "https://dns.google/resolve?name=other.example.com&type=A"
        )
    elif change == "wrong_type":
        proof["evidence"]["details"]["record_type"] = "AAAA"
    elif change == "missing_alias":
        proof["record"]["Answer"][0]["name"] = "other.example.com."
    elif change == "source_metadata_conflict":
        proof["registry"] = "Workstation DNS resolver"
    elif change == "dns_failure":
        proof["record"]["Status"] = 2
    elif change == "wrong_value":
        proof["evidence"]["match"]["value"] = "192.0.2.200"
    item = build(parts)["items"][0]
    assert not item["supported"] and item["review_required"]
    assert item["supporting_attribution_count"] == 0


def test_historical_workstation_evidence_keeps_original_identity_and_query():
    parts = inputs("dns")
    proof = parts[2][0]["source"]
    proof["registry"] = proof["evidence"]["source_name"] = "Workstation DNS resolver"
    before = deepcopy(parts)
    item = build(parts)["items"][0]
    assert item["supported"]
    assert item["source_name"] == "Workstation DNS resolver"
    assert item["source_url"] == "dns://system/remote.example.com/A"
    assert item["retrieved_at"] == "2026-11-01T09:00:00Z"
    assert parts == before


def test_historical_google_normalized_evidence_retains_supported_association_and_provenance():
    parts = inputs("dns")
    proof = parts[2][0]["source"]
    proof["registry"] = proof["evidence"]["source_name"] = "Google Public DNS"
    proof["source_url"] = proof["evidence"]["source_url"] = (
        "https://dns.google/resolve?name=remote.example.com&type=A"
    )
    proof["evidence"]["match"]["field_path"] = "/answers/0"
    proof.update(
        body_sha256="1" * 64,
        raw_response_sha256="2" * 64,
        raw_response_path="dns-google-response.json",
        hash_scope="body_sha256 covers canonical normalized record; raw_response_sha256 covers saved HTTP response bytes.",
    )
    before = deepcopy(parts)
    item = build(parts)["items"][0]
    assert item["supported"] and not item["review_required"]
    assert item["supporting_attribution_count"] == 1
    assert item["corroborated_value"] == "192.0.2.14"
    assert item["matched_field"] == "/answers/0"
    assert item["source_name"] == "Google Public DNS"
    assert item["source_url"] == proof["source_url"]
    assert item["retrieved_at"] == "2026-11-01T09:00:00Z"
    assert item["citations"] == [4]
    assert parts == before


@pytest.mark.parametrize(
    "marker", ["Status", "TC", "RD", "RA", "AD", "CD", "Question", "Answer", "pointer"]
)
def test_damaged_raw_google_evidence_cannot_fall_back_to_normalized_answers(marker):
    parts = google_dns_inputs()
    proof = parts[2][0]["source"]
    raw = proof["record"]
    proof["record"] = {"query": "remote.example.com", "type": "A", "answers": ["192.0.2.14"]}
    if marker != "pointer":
        proof["record"][marker] = raw[marker]
        proof["evidence"]["match"]["field_path"] = "/answers/0"
    item = build(parts)["items"][0]
    assert not item["supported"] and item["review_required"]
    assert item["supporting_attribution_count"] == 0


def test_incomplete_normalized_google_evidence_does_not_qualify():
    parts = inputs("dns")
    proof = parts[2][0]["source"]
    proof["registry"] = proof["evidence"]["source_name"] = "Google Public DNS"
    del proof["record"]["query"]
    assert not build(parts)["items"][0]["supported"]
