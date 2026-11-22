"""Associate commits each qualified group once while retaining its ownership guard."""

from tests.support.qualification import registry_factory, capture_website

import json

import pytest

from modules.accretion.components import accretion
from tests.support.qualification import WhoisRecord
from modules.accretion.components.intake_service import IntakeService
from modules.accretion.tests.support.intake import report, row, seed
from modules.leads.components import lead_queue
from modules.leads.helpers.queue_identity import queue_id
from modules.workspace.components.primitives import now
from modules.workspace.components.store import Store


class Registry:
    def lookup(self, ip):
        return WhoisRecord(
            ip,
            "Fixture registry",
            "https://rdap.arin.net/registry/ip/" + ip,
            now(),
            {"contact": "it@example.com"},
        )

    def close(self):
        pass


@pytest.fixture
def pipeline(tmp_path):
    store = Store(tmp_path / "workspace")
    seed(store.root)
    return store, IntakeService(
        store, attribution_factory=registry_factory(Registry), capture=capture_website
    )


def test_associate_registers_once_and_preserves_initial_score(pipeline, monkeypatch):
    store, intake = pipeline
    registrations, scores = [], []
    original_register, original_score = lead_queue.register_group, accretion.score_lead

    def register(*args, **kwargs):
        registrations.append(kwargs)
        return original_register(*args, **kwargs)

    def score(*args, **kwargs):
        result = original_score(*args, **kwargs)
        scores.append(result)
        return result

    monkeypatch.setattr(lead_queue, "register_group", register)
    monkeypatch.setattr(accretion, "score_lead", score)
    imported = intake.enqueue("scan_http_vulnerable.csv", report([row()]))
    intake.process(imported["id"])
    saved = store.one("SELECT * FROM imports WHERE id=?", (imported["id"],))
    assert saved["status"] == "done", saved["error"]
    assert len(registrations) == 1
    assert registrations[0]["qualified"] is True
    assert len(scores) == 1
    queued = store.one("SELECT * FROM lead_queue")
    assert queued["id"] == queue_id(imported["id"], "example.com")
    assert queued["qualified"] == 1 and queued["association_state"] == "new"
    assert json.loads(queued["intake_score"]) == scores[0]
    admitted = store.all(
        "SELECT evidence_ref FROM awareness_admission_events WHERE state='admitted'"
    )
    assert admitted
    assert all(
        json.loads(event["evidence_ref"])["qualified_queue_id"] == queued["id"]
        for event in admitted
    )


def test_context_finding_is_retained_without_qualification_admission(pipeline):
    store, intake = pipeline
    context_cve = "CVE-2026-23456"
    seed(store.root, context_cve, score=2)
    source = report([row(), row(hostname="web.example.com", tag=context_cve, severity="low")])
    imported = intake.enqueue("scan_http_vulnerable.csv", source)
    intake.process(imported["id"])
    saved = store.one("SELECT * FROM imports WHERE id=?", (imported["id"],))
    assert saved["status"] == "done", saved["error"]
    assert store.path(saved["path"]).read_bytes() == source
    queued = json.loads(store.one("SELECT payload FROM lead_queue")["payload"])
    assert [entry["normalized"]["active_conditions"] for entry in queued] == [["CVE-2026-12345"]]
    retained = [json.loads(entry["payload"]) for entry in store.all("SELECT payload FROM entries")]
    context = next(entry for entry in retained if entry["source"]["fields"]["tag"] == context_cve)
    assert context["normalized"]["eligibility"]["eligible"] is False
    assert context["normalized"]["eligibility"]["reason"] == "below_critical"
    assert {
        item["condition"]: item["admitted"]
        for item in store.all("SELECT condition,admitted FROM awareness_findings")
    } == {"CVE-2026-12345": 1, context_cve: 0}
    assert {
        item["condition"]: item["state"]
        for item in store.all(
            "SELECT f.condition,e.state FROM awareness_admission_events e "
            "JOIN awareness_findings f ON f.id=e.finding_id"
        )
    } == {"CVE-2026-12345": "admitted", context_cve: "observed"}
    from modules.accretion.components.dark_matter import DarkMatterStore, drain

    drain(store.root)
    archive = DarkMatterStore(store.root).query(include_promoted=True)
    assert all(item["outcome"] != "pending" for item in archive["items"])
    context = next(item for item in archive["items"] if item["raw_fields"]["tag"] == context_cve)
    assert (context["outcome"], context["reason"], context["promoted"]) == (
        "rejected",
        "below_critical",
        False,
    )


def test_group_admission_provenance_remains_complete_and_valid(pipeline):
    store, intake = pipeline
    source = report([row(hostname=f"host{index}.example.com") for index in range(12)])
    imported = intake.enqueue("scan_http_vulnerable.csv", source)
    intake.process(imported["id"])
    saved = store.one("SELECT * FROM imports WHERE id=?", (imported["id"],))
    assert saved["status"] == "done", saved["error"]
    qualification = json.loads(store.one("SELECT qualification FROM jobs")["qualification"])
    assert len(qualification["findings"]) == len(qualification["coverage"]) == 12
    assert store.path(saved["path"]).read_bytes() == source
    queued = store.one("SELECT id FROM lead_queue")
    events = store.all("SELECT evidence_ref FROM awareness_admission_events WHERE state='admitted'")
    assert len(events) == 12
    for event in events:
        reference = json.loads(event["evidence_ref"])
        assert reference["qualified_queue_id"] == queued["id"]
        assert reference["attribution_result_id"] == qualification["attribution"]["result_id"]
        assert len(event["evidence_ref"]) <= 4000


def test_settled_condition_in_mixed_row_keeps_history_without_new_admission(pipeline):
    from modules.accretion.components.awareness import ignore_findings

    store, intake = pipeline
    first = intake.enqueue("scan_http_vulnerable.csv", report([row()]))
    intake.process(first["id"])
    original = store.one("SELECT * FROM awareness_findings WHERE condition='CVE-2026-12345'")
    with store.transaction() as db:
        ignore_findings(db, [original["id"]])
    ignored = store.one("SELECT * FROM awareness_findings WHERE id=?", (original["id"],))
    active_cve = "CVE-2026-23456"
    seed(store.root, active_cve)
    tag = "CVE-2026-12345;" + active_cve
    source = report([row(tag=tag, timestamp="2026-11-12 10:00:00")])
    second = intake.enqueue("scan_http_vulnerable.csv", source)
    intake.process(second["id"])
    saved = store.one("SELECT * FROM imports WHERE id=?", (second["id"],))
    assert saved["status"] == "done", saved["error"]
    queued = store.one("SELECT payload FROM lead_queue WHERE import_id=?", (second["id"],))
    entry = json.loads(queued["payload"])[0]
    assert entry["source"]["fields"]["tag"] == tag
    assert entry["normalized"]["active_conditions"] == [active_cve]
    assert store.path(saved["path"]).read_bytes() == source
    events = store.all(
        "SELECT f.condition,e.state FROM awareness_admission_events e "
        "JOIN awareness_findings f ON f.id=e.finding_id WHERE e.import_id=?",
        (second["id"],),
    )
    assert {item["condition"]: item["state"] for item in events} == {
        "CVE-2026-12345": "observed",
        active_cve: "admitted",
    }
    current = store.one("SELECT * FROM awareness_findings WHERE id=?", (original["id"],))
    assert current == ignored
    assert (
        store.one(
            "SELECT count(*) n FROM awareness_admission_events WHERE finding_id=? AND state='admitted'",
            (original["id"],),
        )["n"]
        == 1
    )
