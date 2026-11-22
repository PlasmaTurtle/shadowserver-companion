"""Internal scope ledger is readable, escaped and separate from recipient copy."""

from copy import deepcopy
import json

from modules.investigations.components.evidence_reader import write_evidence_reader
from modules.investigations.components.observation_scope import apply_scope
from modules.activity.components.work_log import build_chronology


def source_data():
    decision = {
        "decision": "exclude",
        "reason": "Private <address> is not evidence of public exposure.",
        "actor": "Synthetic Analyst",
        "decided_at": "2026-11-13T15:00:00Z",
    }
    lead = apply_scope(
        {
            "case_id": "case",
            "draft": {"observation_scope": {"private": decision}},
            "entries": [
                {
                    "id": "private",
                    "ip": "10.1.2.3",
                    "source": {
                        "workbook": "evidence.csv",
                        "sheet": "CSV",
                        "row": 3,
                        "fields": {"hostname": "private.example.com", "tag": "eol-php"},
                    },
                },
                {
                    "id": "public",
                    "ip": "8.8.8.8",
                    "source": {"fields": {"hostname": "public.example.com"}},
                },
            ],
        }
    )
    return {
        **lead,
        "entity_name": "Synthetic organization",
        "domain": "example.com",
        "composition": {"appendix": {"entries": []}},
    }, decision


def test_internal_reader_explains_excluded_source_and_keeps_recipient_model_unchanged(tmp_path):
    data, decision = source_data()
    before = deepcopy(data)
    (tmp_path / "snapshot.json").write_text(json.dumps(data))
    (tmp_path / "notification.pdf").write_bytes(b"Unchanged synthetic recipient artifact")
    write_evidence_reader(data, tmp_path)
    html = (tmp_path / "Evidence_Record.html").read_text(encoding="utf-8")
    assert 'id="observation-scope"' in html
    assert "<strong>1</strong> included in this report" in html
    assert (
        "<strong>1</strong> excluded" in html
        and "<strong>2</strong> original observations retained" in html
    )
    assert "private.example.com" in html and "10.1.2.3" in html
    assert "evidence.csv" in html and "row 3" in html
    assert "Private &lt;address&gt; is not evidence" in html and "Private <address>" not in html
    assert "Synthetic Analyst" in html and "13 Nov 2026" in html
    assert 'data-group="observation-scope"' in html
    assert data == before
    assert (tmp_path / "notification.pdf").read_bytes() == b"Unchanged synthetic recipient artifact"


def test_scope_chronology_records_readable_reason_actor_and_full_original_decision():
    data, decision = source_data()
    saved = {**decision, "entry_ids": ["private"], "reopened_sections": ["vulnerabilities"]}
    data["history"] = [
        {
            "id": 1,
            "action": "observation_scope_changed",
            "detail": json.dumps(saved),
            "created_at": decision["decided_at"],
        }
    ]
    before = deepcopy(data)
    event = build_chronology(data, [])[0]
    assert event["actor"] == decision["actor"] and event["actor_kind"] == "analyst"
    assert event["reason"] == decision["reason"]
    assert "Excluded from the recipient report: 1 observation(s)" in event["detail"]
    assert "Reopened sections: vulnerabilities" in event["detail"]
    assert event["context"]["scope_decision"] == saved
    assert event["timestamp_utc"] == decision["decided_at"]
    assert data == before
