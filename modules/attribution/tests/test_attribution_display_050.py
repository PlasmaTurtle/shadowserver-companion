"""Attribution cards preserve what was actually validated and when."""

from copy import deepcopy
from types import SimpleNamespace

from modules.attribution.components.attribution_display import attribution_summaries

from modules.attribution.tests.support.attribution_display import (
    EVALUATED,
    RETRIEVED,
    case_lead,
    entry,
    saved_record,
)


REVIEWED = "2026-11-06T16:45:00Z"


def test_bridge_preserves_actual_evaluation_time_and_cache_provenance(tmp_path):
    _, record = saved_record(tmp_path)
    assert record["evaluated_at"] == EVALUATED
    assert record["retrieved_at"] == RETRIEVED
    assert record["from_cache"] is True
    assert record["record"]["unknown_extension"] == {"preserved": True}


def test_cached_automatic_result_has_distinct_validation_and_retrieval_time(tmp_path):
    store, record = saved_record(tmp_path)
    observations = [entry("support", "8.8.8.8")] + [
        entry(str(i), f"10.1.0.{i}") for i in range(1, 70)
    ]
    # Repeated scan observations do not inflate the unique reported-IP count.
    observations += [entry("repeat", "8.8.8.8")]
    (summary,) = attribution_summaries(store, case_lead(record, observations))
    assert summary["reported_ip"] == summary["validated_ip"] == "8.8.8.8"
    assert summary["validated_at"] == EVALUATED
    assert summary["retrieved_at"] == RETRIEVED
    assert summary["validated_by"] == "Attribution Module"
    assert summary["validation_kind"] == "automatic"
    assert summary["from_cache"] is True
    assert summary["supporting_ip_count"] == 1
    assert summary["reported_ip_count"] == 70
    assert summary["supported"] is True
    assert "example.com in /contact" in summary["match_summary"]
    assert summary["details"]["matched_value"] == "security@example.com"
    assert summary["details"]["raw_record"] == record["record"]
    assert summary["source_name"] == "ARIN"


def test_older_record_recovers_evaluation_from_its_original_result(tmp_path):
    store, record = saved_record(tmp_path)
    del record["evaluated_at"]
    (summary,) = attribution_summaries(store, case_lead(record))
    assert summary["validated_at"] == EVALUATED
    assert summary["details"]["evaluated_at"] == EVALUATED
    assert summary["validated_by"] == "Attribution Module"
    assert "evaluated_at" not in record  # Presentation does not mutate saved evidence.


def test_legacy_record_has_explicitly_unknown_validation_time(tmp_path):
    record = {
        "ip": "8.8.8.8",
        "registry": "Historical registry",
        "retrieved_at": RETRIEVED,
        "attribution": {
            "root_domain": "example.com",
            "matched_domain": "example.com",
            "field": "record.email",
            "value": "abuse@example.com",
        },
        "record": {"email": "abuse@example.com"},
    }
    (summary,) = attribution_summaries(SimpleNamespace(root=tmp_path), case_lead(record))
    assert summary["validated_at"] is None
    assert summary["validated_by"] is None
    assert summary["validation_kind"] == "unknown"
    assert summary["retrieved_at"] == RETRIEVED
    assert summary["details"]["timestamp_note"] == "Validation time was not recorded."
    assert not (tmp_path / "attribution.sqlite3").exists()


def test_analyst_partial_uses_recorded_reviewer_and_review_time(tmp_path):
    review = {
        "decision": "accept",
        "reviewer": "Recorded Analyst",
        "reviewed_at": REVIEWED,
        "note": "Confirmed organization-name association in the saved registration.",
    }
    store, record = saved_record(tmp_path, method="rdap_keyword", review=review)
    (summary,) = attribution_summaries(store, case_lead(record))
    assert summary["method"] == "analyst_review"
    assert summary["validation_kind"] == "analyst"
    assert summary["validated_by"] == "Recorded Analyst"
    assert summary["validated_at"] == REVIEWED
    assert summary["details"]["evaluated_at"] == EVALUATED
    assert summary["retrieved_at"] == RETRIEVED
    assert summary["details"]["review_note"] == review["note"]
    assert summary["supported"] is True
    assert "matching words: example" in summary["match_summary"]


def test_partial_without_acceptance_is_never_presented_as_validated(tmp_path):
    store, record = saved_record(tmp_path, method="rdap_keyword")
    (summary,) = attribution_summaries(store, case_lead(record))
    assert summary["supported"] is False
    assert summary["supporting_ip_count"] == 0
    assert summary["validated_at"] is None
    assert summary["validation_kind"] == "unknown"
    assert "no recorded analyst acceptance" in summary["details"]["integrity_warning"]


def test_dns_description_distinguishes_forward_confirmed_reverse(tmp_path):
    store, record = saved_record(tmp_path, method="dns", basis="forward_confirmed_reverse")
    (summary,) = attribution_summaries(store, case_lead(record))
    assert summary["method"] == "dns"
    assert summary["source_url"] == "dns://system/mail.example.com/A"
    assert "Reverse DNS identified mail.example.com" in summary["match_summary"]
    assert "saved forward lookup returned the reported IP" in summary["match_summary"]
    assert summary["details"]["dns_basis"] == "forward_confirmed_reverse"
    record["evidence"]["details"]["basis"] = "forward"
    (summary,) = attribution_summaries(store, case_lead(record))
    assert (
        summary["match_summary"]
        == "A saved forward lookup of mail.example.com returned the reported IP."
    )


def test_dns_without_recorded_forward_match_requires_review(tmp_path):
    store, record = saved_record(tmp_path, method="dns")
    record["evidence"]["details"].pop("dns_forward_match")
    (summary,) = attribution_summaries(store, case_lead(record))
    assert summary["supported"] is False
    assert "does not record a forward IP match" in summary["details"]["integrity_warning"]


def test_selected_original_row_must_match_evidence_not_just_first_row(tmp_path):
    store, record = saved_record(tmp_path)
    lead = case_lead(record, [entry("other", "1.1.1.1"), entry("support", "8.8.8.8")])
    (summary,) = attribution_summaries(store, lead)
    assert summary["reported_ip"] == "8.8.8.8"
    lead["domain_groups"][0]["attribution_entry_id"] = "other"
    (summary,) = attribution_summaries(store, lead)
    assert summary["reported_ip"] == "1.1.1.1"
    assert summary["validated_ip"] == "8.8.8.8"
    assert summary["supported"] is False
    assert summary["supporting_ip_count"] == 0
    assert "does not match" in summary["details"]["integrity_warning"]


def test_missing_original_observation_does_not_synthesize_reported_ip(tmp_path):
    store, record = saved_record(tmp_path)
    lead = case_lead(record, [entry("other", "1.1.1.1")])
    (summary,) = attribution_summaries(store, lead)
    assert summary["reported_ip"] is None
    assert summary["supported"] is False
    assert summary["validated_ip"] == "8.8.8.8"


def test_cards_use_only_case_groups_and_count_each_group_separately(tmp_path):
    store, record = saved_record(tmp_path)
    second = deepcopy(record)
    second["ip"] = second["evidence"]["ip"] = "9.9.9.9"
    second["registry"] = second["evidence"]["source_name"] = "Second saved source"
    second["attribution"].update(root_domain="second.com", matched_domain="second.com")
    second["evidence"]["match"].update(target_domain="second.com", matched_domain="second.com")
    lead = case_lead(record)
    lead["entries"] += [
        entry("second", "9.9.9.9", "www.second.com"),
        entry("outside", "4.4.4.4", "notexample.com"),
    ]
    lead["domain_groups"].append(
        {"root_domain": "second.com", "attribution_entry_id": "second", "attribution": second}
    )
    first, other = attribution_summaries(store, lead)
    assert first["source_name"] == "ARIN"
    assert first["reported_ip_count"] == 2
    assert other["source_name"] == "Second saved source"
    assert other["reported_ip_count"] == 1
    assert other["reported_ip"] == "9.9.9.9"
    assert first["details"]["raw_record"] == record["record"]


def test_result_from_another_domain_cannot_supply_a_validation_time(tmp_path):
    store, record = saved_record(tmp_path)
    del record["evaluated_at"]
    record["attribution"].update(root_domain="unrelated.com", matched_domain="unrelated.com")
    record["evidence"]["match"].update(
        target_domain="unrelated.com", matched_domain="unrelated.com"
    )
    lead = case_lead(record, [entry("support", "8.8.8.8", "unrelated.com")])
    lead["domain_groups"][0]["root_domain"] = "unrelated.com"
    (summary,) = attribution_summaries(store, lead)
    assert summary["validated_at"] is None
    assert summary["supported"] is False
    assert "does not belong" in summary["details"]["integrity_warning"]
