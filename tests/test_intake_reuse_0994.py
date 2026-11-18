"""Sequential intake reuses evidence only for established, unchanged endpoints."""

from datetime import datetime, timedelta, timezone
import json

import pytest

from test_accretion_intake import report, row, seed
from workbench.intake import WhoisRecord, ValidatedLeads, restore_entry
from workbench.intake_reuse import recognize_group
from workbench.intake_service import IntakeService
from workbench.lead_queue import LeadQueue
from workbench.primitives import now
from workbench.provider_policy import is_provider
from workbench.store import Store


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
    return store, registry, IntakeService(store, lookup_factory=lambda: registry)


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
    assert json.loads(job["attempts"])[0]["reason"] == "established_endpoint_reused"
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
    original = intake.accept_group

    def interrupted(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("Simulated interruption before job completion")

    with monkeypatch.context() as patch:
        patch.setattr(intake, "accept_group", interrupted)
        intake.process(queued["id"])
    assert store.one("SELECT status FROM imports")["status"] == "error"
    assert store.one("SELECT status FROM jobs")["status"] == "pending"
    assert store.all("SELECT * FROM leads") == []
    assert store.one("SELECT sum(admitted) n FROM awareness_observations")["n"] == 0
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
    from workbench.attribution_bridge import RegistrationAttribution
    from workbench.intake import EntryValidator, UnvalidatedEntry

    validator = EntryValidator({"North Carolina"})
    entries = [
        validator.validate_entry(UnvalidatedEntry("test.csv", "CSV", i + 1, fields))
        for i, fields in enumerate([source(10), source(11, ip="8.8.4.4")])
    ]
    group = ValidatedLeads("example.com", entries)
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
    assert adapter.qualify(group, candidate_indices=[1]) == ("no_match", None)
    assert [(c.entry_id, c.ip) for c in captured] == [("1", "8.8.4.4")]
    assert group.entries == entries


def test_reuse_requires_proof_to_belong_to_the_saved_result():
    from types import SimpleNamespace
    from workbench.intake_reuse import _proof_matches

    proof = {
        "result_id": "result",
        "snapshot_id": "snapshot",
        "body_sha256": "digest",
        "ip": "8.8.8.8",
        "attribution": {"root_domain": "example.com"},
        "evidence": {"ip": "8.8.8.8", "supporting_snapshot_ids": []},
    }
    result = {
        "result_id": "result",
        "root_domain": "example.com",
        "status": "matched",
        "evidence": [{"snapshot_id": "snapshot", "ip": "8.8.8.8"}],
    }
    evidence = SimpleNamespace(
        result=lambda _: result,
        snapshot=lambda _: SimpleNamespace(body_sha256="digest"),
    )
    assert _proof_matches(proof, "example.com", evidence)
    result["evidence"][0]["snapshot_id"] = "unrelated"
    assert not _proof_matches(proof, "example.com", evidence)


def test_new_endpoint_cannot_fall_back_to_old_successful_endpoint(pipeline):
    store, registry, _ = pipeline
    ingest(pipeline, [source(10)])
    registry.calls.clear()
    saved = ingest(pipeline, [source(11), source(11, ip="8.8.4.4")])
    assert registry.calls == ["8.8.4.4"]
    job = store.one("SELECT * FROM jobs WHERE import_id=?", (saved["id"],))
    assert job["status"] == "no_match"
    assert store.one("SELECT count(*) n FROM leads")["n"] == 1
    assert (
        store.one("SELECT admitted FROM awareness_observations WHERE ip='8.8.4.4'")["admitted"] == 0
    )
    assert (
        store.one("SELECT max(admitted) n FROM awareness_observations WHERE ip='8.8.8.8'")["n"] == 1
    )


@pytest.mark.parametrize("change", ["hostname", "ip", "port"])
def test_changed_endpoint_is_examined(pipeline, change):
    _, registry, _ = pipeline
    ingest(pipeline, [source(10)])
    registry.calls.clear()
    changes = {"hostname": "other.example.com", "ip": "8.8.4.4", "port": "8443"}
    ingest(pipeline, [source(11, **{change: changes[change]})])
    assert registry.calls


def test_stale_proof_and_explicit_refresh_prevent_reuse(pipeline):
    store, registry, _ = pipeline
    ingest(pipeline, [source(10)])
    payload = json.loads(store.one("SELECT payload FROM lead_queue")["payload"])
    group = ValidatedLeads("example.com", [restore_entry(e) for e in payload])
    before = store.all("SELECT * FROM awareness_observations ORDER BY id")
    assert recognize_group(store, group)["attribution"]
    assert recognize_group(store, group, refresh=True)["attribution"] is None
    assert (
        recognize_group(store, group, clock=datetime.now(timezone.utc) + timedelta(days=8))[
            "attribution"
        ]
        is None
    )
    assert store.all("SELECT * FROM awareness_observations ORDER BY id") == before
    proof = json.loads(store.one("SELECT attribution FROM domain_groups")["attribution"])
    proof["retrieved_at"] = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    with store.transaction() as db:
        db.execute("UPDATE domain_groups SET attribution=?", (json.dumps(proof),))
    registry.calls.clear()
    ingest(pipeline, [source(11)])
    assert registry.calls == ["8.8.8.8"]


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
