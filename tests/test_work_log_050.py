"""Historical decisions remain distinct from retrieval and present-day settings."""

import copy
import shutil
import socket
import subprocess

from workbench.work_log import build_chronology, render_work_log


def proof(**overrides):
    return {
        "ip": "192.0.2.40",
        "registry": "ARIN",
        "protocol": "RDAP",
        "source_url": "https://rdap.arin.net/registry/ip/192.0.2.40",
        "retrieved_at": "2026-11-05T13:00:00Z",
        "evaluated_at": "2026-11-06T14:00:00Z",
        "result_id": "result-1",
        "snapshot_id": "snapshot-1",
        "attribution": {
            "matched_domain": "example.com",
            "field": "vcard.email",
            "value": "admin@example.com",
        },
        **overrides,
    }


def test_sources_evaluation_review_and_certification_are_distinct_and_preserved():
    saved = proof(
        review={
            "id": "review-1",
            "reviewer": "Historical Analyst",
            "reviewed_at": "2026-11-06T15:00:00Z",
            "decision": "accept",
            "note": "Confirmed the saved registration name.",
        }
    )
    lead = {
        "case_id": "case-1",
        "domain": "example.com",
        "domain_groups": [{"root_domain": "example.com", "attribution": saved}],
        "history": [
            {
                "id": 10,
                "action": "case_created",
                "detail": "Created notification",
                "created_at": "2026-11-06T15:01:00Z",
            }
        ],
    }
    section_history = [
        {
            "id": "section-1",
            "section_key": "attribution",
            "action": "validated",
            "actor": "Section Analyst",
            "created_at": "2026-11-06T15:02:00Z",
            "reason": "",
            "revision": 2,
            "snapshot_hash": "a" * 64,
            "validation_id": "validation-2",
            "dependency_hash": "b" * 64,
            "content_hash": "c" * 64,
        }
    ]
    original = copy.deepcopy((lead, section_history))
    events = build_chronology(
        lead,
        section_history,
        {
            "certified_at": "2026-11-06T15:03:00Z",
            "certified_by": "Certifying Analyst",
            "revision": 3,
        },
    )
    assert (lead, section_history) == original
    assert [event["action"] for event in events] == [
        "source_retrieved",
        "attribution_evaluated",
        "attribution_review",
        "case_created",
        "validated",
        "report_certified",
    ]
    assert [event["actor"] for event in events] == [
        None,
        "Attribution Module",
        "Historical Analyst",
        None,
        "Section Analyst",
        "Certifying Analyst",
    ]
    assert events[0]["created_at"] != events[1]["created_at"] != events[2]["created_at"]
    assert events[2]["reason"] == saved["review"]["note"]
    assert events[-2]["context"]["snapshot_hash"] == "a" * 64
    assert events[-2]["context"]["validation_id"] == "validation-2"
    assert events[-2]["context"]["dependency_hash"] == "b" * 64
    assert events[-2]["context"]["content_hash"] == "c" * 64
    assert events[-1]["revision"] == 3


def test_legacy_missing_decision_time_never_becomes_retrieval_time():
    events = build_chronology({"attribution": proof(evaluated_at=None)}, [])
    retrieval, decision = events
    assert retrieval["timestamp_status"] == "recorded"
    assert decision["action"] == "attribution_validated"
    assert decision["created_at"] is decision["timestamp_utc"] is decision["actor"] is None
    assert decision["timestamp_status"] == "not_recorded"
    # A display-level validated_at derived from review is not automatic evidence.
    reviewed = proof(
        evaluated_at=None,
        validated_at="2026-11-06T15:00:00Z",
        review={"reviewer": "Reviewer", "reviewed_at": "2026-11-06T15:00:00Z"},
    )
    events = build_chronology({"attribution": reviewed}, [])
    assert next(e for e in events if e["action"] == "attribution_evaluated")["created_at"] is None


def test_legacy_evaluation_can_use_only_its_original_immutable_result_summary():
    lead = {
        "domain": "example.com",
        "attribution": proof(evaluated_at=None),
        "attribution_summaries": [
            {
                "root_domain": "example.com",
                "details": {
                    "result_id": "result-1",
                    "snapshot_id": "snapshot-1",
                    "evaluated_at": "2026-11-06T14:00:00Z",
                },
            }
        ],
    }
    assert build_chronology(lead, [])[-1]["created_at"] == "2026-11-06T14:00:00Z"
    lead["attribution_summaries"][0]["details"]["result_id"] = "another-result"
    assert build_chronology(lead, [])[-1]["created_at"] is None


def test_deduplication_retains_domains_and_revisions_and_has_stable_order():
    saved = proof()
    lead = {
        "domain_groups": [
            {"root_domain": domain, "attribution": saved}
            for domain in ("example.com", "example.com", "example.org")
        ]
    }
    history = [
        {
            "id": str(revision),
            "action": "validated",
            "section_key": "introduction",
            "created_at": "2026-11-06T14:00:00Z",
            "revision": revision,
            "actor": "Analyst",
        }
        for revision in (1, 2)
    ]
    events = build_chronology(lead, history + history)
    assert len(events) == 4
    assert events[0]["context"]["root_domains"] == ["example.com", "example.org"]
    assert {e["revision"] for e in events if e["source_kind"] == "section_history"} == {1, 2}
    assert events == build_chronology(
        {"domain_groups": list(reversed(lead["domain_groups"]))}, list(reversed(history))
    )


def test_offset_fractional_missing_and_unzoned_clocks_sort_without_fabrication():
    history = [
        {"id": str(index), "action": "saved", "created_at": clock}
        for index, clock in enumerate(
            (
                "2026-11-06T14:00:00.1Z",
                "2026-11-06T09:00:00-05:00",
                None,
                "2026-11-06T13:59:00",
                "bad-clock",
            )
        )
    ]
    events = build_chronology({"history": history}, [])
    assert events[0]["created_at"] == "2026-11-06T09:00:00-05:00"
    assert events[0]["timestamp_utc"] == "2026-11-06T14:00:00Z"
    assert events[1]["created_at"] == "2026-11-06T14:00:00.1Z"
    assert {e["timestamp_status"] for e in events[2:]} == {
        "not_recorded",
        "timezone_not_recorded",
        "invalid",
    }
    assert all(e["timestamp_utc"] is None for e in events[2:])


def test_work_log_renders_offline_wraps_literal_content_and_spans_pages(tmp_path, monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("A package work log must render offline")

    monkeypatch.setattr(socket, "create_connection", no_network)
    long_reason = (
        "Reviewed <script>literal</script> & source attribution; retain the original record. " * 35
        + "\nhttps://example.com/"
        + "longsourcepath" * 25
    )
    sections = [
        {
            "id": str(index),
            "section_key": "attribution",
            "action": "reopened",
            "actor": "Analyst García",
            "created_at": f"2026-11-06T15:{index:02}:01.123456Z",
            "revision": index,
            "reason": long_reason,
        }
        for index in range(8)
    ]
    events = build_chronology(
        {
            "case_id": "case-1",
            "history": [
                {
                    "id": 1,
                    "action": "legacy_import",
                    "created_at": None,
                    "detail": "Historical author not recorded",
                }
            ],
        },
        sections,
    )
    destination = render_work_log(
        {
            "case_id": "case-1",
            "domain": "example.com",
            "report_revision": 2,
            "draft_revision": 12,
            "draft": {"company": "Example & Company"},
            "certification": {"certified_by": "Final Analyst"},
        },
        events,
        tmp_path / "work-log.pdf",
    )
    assert destination.read_bytes().startswith(b"%PDF-")
    if not shutil.which("pdftotext"):
        return
    text = subprocess.check_output(["pdftotext", "-layout", str(destination), "-"]).decode()
    assert text.count("INTERNAL WORK LOG") > 2
    assert "INTERNAL WORK LOG" in text and "Example & Company" in text
    assert "Report revision: 2" in text
    assert "2026-11-06 15:00:01.123456 UTC" in text
    assert "<script>literal</script>" in text
    assert "Analyst García" in text
    assert "Timestamp not recorded | Actor: Not recorded" in text
    assert "Historical author not recorded" in text
    assert text.count("Page ") == text.count("INTERNAL WORK LOG")
