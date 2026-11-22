"""Sequential intake reuses one authoritative proof for a related source group."""

from tests.support.qualification import registry_factory, capture_website

from datetime import datetime, timedelta, timezone
import json

import pytest

from modules.accretion.tests.support.intake import report, row, seed
from modules.accretion.components.intake import CandidateGroup, restore_observation
from tests.support.qualification import WhoisRecord
from modules.accretion.components.qualification_context import recognize_group
from modules.accretion.components.intake_service import IntakeService
from modules.accretion.components.report import Report, ReportCandidate
from modules.leads.components.lead_queue import LeadQueue
from modules.workspace.components.primitives import now
from modules.leads.components.provider_policy import is_provider
from modules.workspace.components.store import Store


class Registry:
    def __init__(self):
        self.calls = []

    def lookup(self, ip):
        self.calls.append(ip)
        return WhoisRecord(
            ip,
            "Fixture registry",
            "https://rdap.arin.net/registry/ip/" + ip,
            now(),
            {"contact": "it@example.com" if ip == "8.8.8.8" else "it@other.org"},
        )

    def close(self):
        pass


@pytest.fixture
def pipeline(tmp_path):
    store = Store(tmp_path / "workspace")
    registry = Registry()
    return (
        store,
        registry,
        IntakeService(
            store, attribution_factory=registry_factory(lambda: registry), capture=capture_website
        ),
    )


def source(day, **changes):
    return row(
        **{
            "tag": "eol-php",
            "version": "PHP/7.3.25",
            "severity": "critical",
            "timestamp": f"2026-11-{day:02d} 10:00:00",
            "protocol": "tcp",
            "port": "443",
            **changes,
        }
    )


def ingest(pipeline, rows, name="scan_http_vulnerable.csv"):
    store, _, intake = pipeline
    queued = intake.enqueue(name, report(rows))
    intake.process(queued["id"])
    saved = store.one("SELECT * FROM imports WHERE id=?", (queued["id"],))
    assert saved["status"] == "done", saved["error"]
    return saved


def test_repeat_next_day_reuses_proof_and_retains_its_original_date(pipeline):
    store, registry, _ = pipeline
    ingest(pipeline, [source(10)])
    original = json.loads(store.one("SELECT attribution FROM domain_groups")["attribution"])
    registry.calls.clear()
    saved = ingest(pipeline, [source(11)])
    assert registry.calls == []
    proof = json.loads(store.one("SELECT attribution FROM domain_groups")["attribution"])
    assert proof["retrieved_at"] == original["retrieved_at"]
    assert proof["reuse"]["fresh_lookup"] is False
    job = store.one("SELECT * FROM jobs WHERE import_id=?", (saved["id"],))
    assert any(
        attempt.get("reason") == "established_group_reused"
        for attempt in json.loads(job["attempts"])
    )
    assert len(LeadQueue(store).list()) == 1
    assert store.one("SELECT count(*) n FROM awareness_findings")["n"] == 1
    assert store.one("SELECT count(*) n FROM awareness_observations")["n"] == 2
    progress = json.loads(saved["config"])["intake_progress"]
    assert progress["associated_groups"] == 1 and progress["reused_groups"] == 1


def test_new_cve_uses_local_vetting_without_repeating_endpoint_lookup(pipeline, monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("Intake CVE vetting must remain local")

    monkeypatch.setattr("requests.get", no_network)
    store, registry, _ = pipeline
    seed(store.root)
    ingest(pipeline, [source(10)])
    registry.calls.clear()
    changed = source(11)
    changed.update(tag="eol-php;CVE-2026-12345", version="PHP/7.3.26")
    ingest(pipeline, [changed])
    assert registry.calls == []
    conditions = {r["condition"] for r in store.all("SELECT condition FROM awareness_findings")}
    assert conditions == {"eol-php:7.3", "CVE-2026-12345"}
    leads = LeadQueue(store).list()
    assert len(leads) == 1
    assert leads[0]["finding_count"] == 2
    assert leads[0]["observations"] == 2, "One event supporting two CVEs is counted once"
    assert leads[0]["observation_days"] == 2


def test_associate_commits_entity_findings_and_job_completion_together(pipeline, monkeypatch):
    store, _, intake = pipeline
    queued = intake.enqueue("scan_http_vulnerable.csv", report([source(10)]))
    original = intake.associate_lead

    def interrupted(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("Simulated interruption before job completion")

    with monkeypatch.context() as patch:
        patch.setattr(intake, "associate_lead", interrupted)
        intake.process(queued["id"])
    assert store.one("SELECT status FROM imports")["status"] == "error"
    assert store.one("SELECT status FROM jobs")["status"] == "pending"
    assert store.all("SELECT * FROM leads") == []
    assert store.one("SELECT count(*) n FROM awareness_observations")["n"] == 0
    assert store.one("SELECT count(*) n FROM lead_queue")["n"] == 0
    intake.retry(queued["id"])
    intake.process(queued["id"])
    assert store.one("SELECT status FROM imports")["status"] == "done"
    assert store.one("SELECT status FROM jobs")["status"] == "qualified"
    assert store.one("SELECT count(*) n FROM leads")["n"] == 1
    assert store.one("SELECT sum(admitted) n FROM awareness_observations")["n"] == 1


def test_reordered_export_reuses_proof_without_adding_event_density(pipeline):
    store, registry, _ = pipeline
    rows = [source(10), source(10, port="8443")]
    ingest(pipeline, rows)
    before = store.one("SELECT count(*) n FROM awareness_observations")["n"]
    registry.calls.clear()
    ingest(pipeline, rows[::-1], "reexport_http_vulnerable.csv")
    assert registry.calls == []
    assert store.one("SELECT count(*) n FROM awareness_observations")["n"] == before
    assert store.one("SELECT count(*) n FROM imports")["n"] == 2


def test_production_candidate_subset_retains_original_review_indexes():
    from types import SimpleNamespace
    from modules.attribution.components.attribution_bridge import RegistrationAttribution
    from modules.accretion.components.intake import EntryValidator, SourceObservation

    validator = EntryValidator({"North Carolina"})
    entries = [
        validator.validate_entry(SourceObservation("test.csv", "CSV", i + 1, fields))
        for i, fields in enumerate([source(10), source(11, ip="8.8.4.4")])
    ]
    group = CandidateGroup("example.com", entries)
    captured = []

    def attribute(root, candidates, **kwargs):
        captured.extend(candidates)
        return SimpleNamespace(result_id="result", status="no_match", attempts=[])

    adapter = object.__new__(RegistrationAttribution)
    adapter.module = SimpleNamespace(
        attribute=attribute,
        store=SimpleNamespace(
            result=lambda _: {"result_id": "result", "root_domain": "example.com"}
        ),
    )
    decision = adapter.qualify(group, candidate_indices=[1])
    assert decision.status == "no_match" and decision.proof is None
    assert decision.result_id == "result"
    assert [(c.entry_id, c.ip) for c in captured] == [("1", "8.8.4.4")]
    assert group.observations == tuple(entries)


def test_new_address_in_same_group_reuses_original_proof_with_explicit_coverage(pipeline):
    store, registry, _ = pipeline
    ingest(pipeline, [source(10)])
    original = json.loads(store.one("SELECT attribution FROM domain_groups")["attribution"])
    registry.calls.clear()
    saved = ingest(pipeline, [source(11), source(11, ip="8.8.4.4")])
    assert registry.calls == []
    job = store.one("SELECT * FROM jobs WHERE import_id=?", (saved["id"],))
    assert job["status"] == "qualified"
    qualified = json.loads(job["qualification"])
    assert qualified["attribution"]["ip"] == original["ip"]
    assert qualified["attribution"]["result_id"] == original["result_id"]
    assert [row["ip"] for row in qualified["coverage"]] == ["8.8.8.8", "8.8.4.4"]
    assert qualified["coverage"][1]["relationship"] == "shared_root_domain"
    assert (
        store.one("SELECT admitted FROM awareness_observations WHERE ip='8.8.4.4'")["admitted"] == 1
    )
    assert store.one("SELECT id FROM lead_queue WHERE import_id=?", (saved["id"],))


@pytest.mark.parametrize("change", ["hostname", "ip", "port"])
def test_changed_related_endpoint_reuses_group_proof(pipeline, change):
    _, registry, _ = pipeline
    ingest(pipeline, [source(10)])
    registry.calls.clear()
    changes = {"hostname": "other.example.com", "ip": "8.8.4.4", "port": "8443"}
    ingest(pipeline, [source(11, **{change: changes[change]})])
    assert registry.calls == []


def test_stale_proof_and_explicit_refresh_prevent_reuse(pipeline):
    from attribution import EvidenceStore
    from modules.attribution.components.attribution_reuse import reuse_attribution
    from modules.accretion.components.qualification import Qualifier
    from threading import Event

    store, registry, intake = pipeline
    ingest(pipeline, [source(10)])
    queued = store.one("SELECT * FROM lead_queue")
    payload = json.loads(queued["payload"])
    group = CandidateGroup("example.com", [restore_observation(entry) for entry in payload])
    imported = store.one("SELECT * FROM imports WHERE id=?", (queued["import_id"],))
    candidate = ReportCandidate(Report.from_record(imported), group)
    local = recognize_group(store, group)
    original = local["saved_proof"]
    with EvidenceStore(store.root / "attribution.sqlite3") as evidence:
        options = {"entity_id": local["entity_id"], "saved_proof": original}
        assert reuse_attribution(store, group, evidence, **options)
        assert reuse_attribution(store, group, evidence, refresh=True, **options) is None
        assert (
            reuse_attribution(
                store,
                group,
                evidence,
                clock=datetime.now(timezone.utc) + timedelta(days=8),
                **options,
            )
            is None
        )
    registry.calls.clear()
    qualifier = Qualifier(
        store,
        store.settings(),
        Event(),
        attribution_factory=intake.attribution_factory,
        capture=capture_website,
    )
    try:
        fresh = qualifier.qualify(candidate, refresh=True)
        assert fresh.status == "qualified"
        assert fresh.result_id != original["result_id"]
        assert registry.calls == ["8.8.8.8"]
    finally:
        qualifier.close()
    assert original == recognize_group(store, group)["saved_proof"], (
        "Refreshing evidence alone does not publish a new lead"
    )


@pytest.mark.parametrize(
    "host",
    [
        "1-2-3-4.googlefiber.net",
        "gfiber.com",
        "webpass.net",
        "fiber.google.com",
        "cox.net",
        "tmodns.net",
    ],
)
def test_major_provider_roots_receive_penalty(host):
    assert is_provider(host)


@pytest.mark.parametrize(
    "host",
    [
        "example.com",
        "local-isp.example.org",
        "google.com",
        "spectrum.com.example.com",
        "fiber.google.com.example.net",
    ],
)
def test_customers_local_providers_and_lookalikes_are_not_penalized(host):
    assert not is_provider(host)
