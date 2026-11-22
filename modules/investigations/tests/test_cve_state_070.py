"""Authoritative state reversals require a later captured published source."""

from copy import deepcopy

import pytest

from modules.investigations.components.cve_state import guard_cve_states, state_events

ID = "CVE-2025-12345"


def record(state, hour, revision=None):
    revision = revision or f"{state}-{hour}"
    stamp = f"2026-11-07T{hour:02d}:00:00Z" if hour is not None else None
    return {
        "id": ID,
        "state": state.upper(),
        "verification_status": state,
        "revision_id": revision,
        "retrieved_at": stamp,
        "source": "CVE Program",
        "sources": [{"publisher": "CVE Program", "revision_id": revision, "retrieved_at": stamp}],
    }


def test_prior_rejection_survives_two_step_omission():
    rejected = record("rejected", 10)
    history = guard_cve_states([], [rejected], [], [], {})
    assert history[0]["state"] == "rejected"
    with pytest.raises(ValueError, match="Reserved or rejected"):
        guard_cve_states([], [], history, [], {ID: {"action": "fallback"}})


@pytest.mark.parametrize("hour", [8, 9, 10, None])
def test_older_equal_or_undated_published_snapshot_cannot_reverse_rejection(hour):
    with pytest.raises(ValueError, match="captured after"):
        guard_cve_states([record("published", hour)], [record("rejected", 10)], [], [], {})


def test_later_authoritative_published_snapshot_can_reverse_rejection():
    history = guard_cve_states([record("published", 11)], [record("rejected", 10)], [], [], {})
    assert [item["state"] for item in history] == ["rejected", "published"]
    assert history[0]["retrieved_at"] < history[1]["retrieved_at"]


def test_later_selected_published_record_allows_documented_fallback():
    history = guard_cve_states(
        [record("published", 11)], [record("reserved", 10)], [], [], {ID: {"action": "fallback"}}
    )
    assert len(history) == 2


def test_undated_restriction_is_not_assumed_old():
    with pytest.raises(ValueError, match="missing timestamp"):
        guard_cve_states([record("published", 11)], [record("reserved", None)], [], [], {})


def test_unchanged_pinned_record_not_silently_invalidated_by_bank_refresh():
    selected = record("published", 9)
    history = guard_cve_states([deepcopy(selected)], [selected], [], [record("rejected", 10)], {})
    assert any(item["state"] == "rejected" for item in history)
    assert selected["state"] == "PUBLISHED"
    # Deliberately adding a manual fallback is a new decision, not an unchanged view.
    with pytest.raises(ValueError, match="captured after"):
        guard_cve_states([selected], [selected], history, [], {ID: {"action": "fallback"}})


def test_rejection_from_supplement_uses_its_capture_timestamp():
    selected = record("rejected", 9, "nvd-old")
    selected.update(
        source="NVD",
        state_conflict={
            "primary_state": "PUBLISHED",
            "supplementary_state": "REJECTED",
            "source_revision_id": "program-new",
        },
    )
    supplement = {
        "publisher": "CVE Program",
        "revision_id": "program-new",
        "retrieved_at": "2026-11-07T11:00:00Z",
    }
    selected["sources"].append(supplement)
    selected["supplementary_records"] = [
        {"source": supplement, "record": {"cveMetadata": {"cveId": ID, "state": "REJECTED"}}}
    ]
    events = state_events(selected)
    assert events[0]["retrieved_at"] == "2026-11-07T11:00:00Z"
    assert events[0]["revision_id"] == "program-new"
    with pytest.raises(ValueError, match="captured after"):
        guard_cve_states([record("published", 10)], [], [], [selected], {})


def test_missing_supplement_capture_cannot_borrow_primary_date():
    selected = record("rejected", 9, "nvd-old")
    selected["state_conflict"] = {
        "supplementary_state": "REJECTED",
        "source_revision_id": "missing",
    }
    event = state_events(selected)[0]
    assert event["retrieved_at"] is None and event["revision_id"] == "missing"


def test_assessment_date_does_not_substitute_for_capture_date():
    selected = record("published", None)
    selected["date_updated"] = "2026-11-07T12:00:00Z"
    selected["ssvc_assessments"] = [{"assessed_at": "2026-11-07T12:00:00Z"}]
    with pytest.raises(ValueError, match="captured after"):
        guard_cve_states([selected], [record("reserved", 10)], [], [], {})


def test_offset_comparison_is_chronological_not_lexicographic():
    selected = record("published", 11)
    selected["retrieved_at"] = selected["sources"][0]["retrieved_at"] = "2026-11-07T07:00:00-05:00"
    assert (
        guard_cve_states([selected], [record("reserved", 11)], [], [], {})[-1]["state"]
        == "published"
    )


def test_naive_timestamps_do_not_establish_subsequent_capture():
    selected = record("published", 11)
    selected["retrieved_at"] = selected["sources"][0]["retrieved_at"] = "2026-11-07T12:00:00"
    with pytest.raises(ValueError):
        guard_cve_states([selected], [record("reserved", 10)], [], [], {})


def test_case_history_retains_distinct_source_revisions_without_duplicates():
    selected = record("rejected", 10)
    first = guard_cve_states([selected], [], [], [selected], {})
    assert len(first) == 1
    original = deepcopy(first)
    later = guard_cve_states([record("published", 11)], [selected], first, [selected], {})
    assert first == original and len(later) == 2


def test_manual_fallback_is_not_an_authoritative_published_capture():
    selected = record("published", 11)
    selected["manual_fallback"] = True
    with pytest.raises(ValueError):
        guard_cve_states([selected], [record("reserved", 10)], [], [], {ID: {"action": "fallback"}})


def test_unrelated_bank_rejection_does_not_enter_case_history():
    unrelated = record("rejected", 10)
    unrelated["id"] = "CVE-2026-98765"
    history = guard_cve_states([record("published", 9)], [], [], [unrelated], {})
    assert len(history) == 1 and history[0]["id"] == ID


def test_exclusion_retains_rejected_record_without_promoting_it():
    rejected = record("rejected", 10)
    history = guard_cve_states(
        [],
        [rejected],
        [],
        [],
        {ID: {"action": "exclude", "reason": "Retained as rejected identifier"}},
    )
    assert history[0]["state"] == "rejected"
