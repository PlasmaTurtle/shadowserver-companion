"""The funnel's observable product and early-stop behavior through real owners."""

import json

import pytest

from modules.accretion.components import accretion
from modules.accretion.components.intake_service import IntakeService
from modules.accretion.tests.support.intake import report, row, seed
from modules.workspace.components.store import Store
from tests.support.qualification import capture_website, registry_factory, WhoisRecord
from modules.workspace.components.primitives import now


class Registry:
    def __init__(self):
        self.calls = []

    def lookup(self, address):
        self.calls.append(address)
        return WhoisRecord(
            address,
            "Fixture",
            "https://rdap.arin.net/registry/ip/" + address,
            now(),
            {"contact": "security@example.com"},
        )

    def close(self):
        pass


@pytest.fixture
def pipeline(tmp_path):
    store = Store(tmp_path / "workspace")
    seed(store.root)
    registry = Registry()
    intake = IntakeService(
        store, attribution_factory=registry_factory(lambda: registry), capture=capture_website
    )
    return store, intake, registry


def run(pipeline, rows=None, *, name="scan_http_vulnerable.csv"):
    store, intake, _ = pipeline
    identity = intake.enqueue(name, report(rows or [row()]))["id"]
    intake.process(identity)
    imported = store.one("SELECT * FROM imports WHERE id=?", (identity,))
    assert imported["status"] != "error", imported["error"]
    return imported, store.one("SELECT * FROM jobs WHERE import_id=?", (identity,))


def test_complete_product_retains_original_capture_and_report_type(pipeline):
    store, _, registry = pipeline
    _, job = run(pipeline)
    assert job["status"] == "qualified"
    evidence = json.loads(job["qualification"])
    assert evidence["findings"][0]["report_type"] == "scan_http_vulnerable"
    assert evidence["findings"][0]["basis"] == "shadowserver_report"
    assert evidence["coverage"][0]["proof_ip"] == "8.8.8.8"
    assert evidence["website"]["final_url"] == "https://mail.example.com/"
    assert registry.calls == ["8.8.8.8"]
    from modules.investigations.components.cases import Cases

    lead = store.one("SELECT id FROM leads")
    case_id = Cases(store).create(lead["id"])["case_id"]
    adopted = store.one("SELECT * FROM evidence WHERE case_id=?", (case_id,))
    assert adopted["path"] == evidence["website"]["path"]
    assert adopted["sha256"] == evidence["website"]["sha256"]


@pytest.mark.parametrize("status", ["partial", "challenge", "load_failed"])
def test_unusable_site_stops_attribution_evaluation_and_association(pipeline, monkeypatch, status):
    store, intake, registry = pipeline

    def capture(url, **kwargs):
        png, metadata = capture_website(url, **kwargs)
        metadata["capture_status"] = status
        return png, metadata

    intake.capture = capture
    monkeypatch.setattr(
        accretion, "score_lead", lambda *a, **k: pytest.fail("Evaluate ran before Qualify")
    )
    imported, job = run(pipeline)
    assert imported["status"] == "needs_retry"
    assert job["status"] == "deferred" and job["error"] == "website_unavailable"
    assert registry.calls == []
    assert store.one("SELECT count(*) n FROM leads")["n"] == 0
    assert store.one("SELECT count(*) n FROM entity_contact_queue")["n"] == 0


def test_functioning_login_passes_and_first_failed_host_does_not_end_group(pipeline):
    _, intake, registry = pipeline
    calls = []

    def capture(url, **kwargs):
        calls.append(url)
        png, metadata = capture_website(url, **kwargs)
        metadata["capture_status"] = "partial" if len(calls) == 1 else "login_required"
        return png, metadata

    intake.capture = capture
    _, job = run(pipeline, [row(hostname="broken.example.com"), row(hostname="login.example.com")])
    assert job["status"] == "qualified" and len(calls) == 2
    assert json.loads(job["qualification"])["website"]["final_url"] == "https://login.example.com/"
    assert registry.calls == ["8.8.8.8"]


def test_unrelated_redirect_requires_review_without_fresh_attribution(pipeline):
    _, intake, registry = pipeline

    def capture(url, **kwargs):
        png, metadata = capture_website(url, **kwargs)
        metadata["final_url"] = "https://another-business.org/"
        return png, metadata

    intake.capture = capture
    _, job = run(pipeline)
    assert job["error"] == "website_identity_review" and registry.calls == []


def test_group_reuse_keeps_original_ip_proof_and_captures_current_site(pipeline):
    store, intake, registry = pipeline
    _, first = run(pipeline)
    calls = []

    def capture(url, **kwargs):
        calls.append(url)
        return capture_website(url, **kwargs)

    intake.capture = capture
    _, second = run(pipeline, [row(ip="9.9.9.9", timestamp="2026-11-12 10:00:00")])
    assert first["status"] == second["status"] == "qualified"
    proof = json.loads(second["qualification"])
    assert proof["attribution"]["ip"] == "8.8.8.8"
    assert proof["coverage"][0]["ip"] == "9.9.9.9"
    assert proof["coverage"][0]["relationship"] == "shared_root_domain"
    assert registry.calls == ["8.8.8.8"] and len(calls) == 1
    assert store.one("SELECT count(*) n FROM website_captures")["n"] == 2


def test_handled_scope_stops_early_but_new_condition_remains_actionable(pipeline):
    store, intake, _ = pipeline
    run(pipeline)
    with store.transaction() as db:
        db.execute("UPDATE awareness_findings SET workflow='handled'")
    calls = []

    def capture(url, **kwargs):
        calls.append(url)
        return capture_website(url, **kwargs)

    intake.capture = capture
    _, handled = run(pipeline, [row(timestamp="2026-11-12 10:00:00")])
    assert handled["status"] == "dismissed" and not calls
    _, fresh = run(
        pipeline, [row(tag="CVE-2026-99999", severity="critical", timestamp="2026-11-13 10:00:00")]
    )
    assert fresh["status"] == "qualified" and len(calls) == 1


def test_shutdown_during_capture_never_reaches_provider(pipeline):
    store, intake, registry = pipeline

    def capture(url, **kwargs):
        result = capture_website(url, **kwargs)
        intake.stop_event.set()
        return result

    intake.capture = capture
    _, job = run(pipeline)
    assert job["status"] == "pending" and not registry.calls
    assert store.one("SELECT count(*) n FROM leads")["n"] == 0


@pytest.mark.parametrize("profile", ["compromised_website", "compromised_iot6"])
def test_supported_incident_is_actionable_without_cve_version_or_severity(pipeline, profile):
    _, job = run(
        pipeline,
        [row(report_type=profile, tag="compromised", version="", severity="")],
        name=profile + ".csv",
    )
    assert job["status"] == "qualified"
    findings = json.loads(job["qualification"])["findings"]
    assert findings[0]["condition"] == "compromised"
    assert findings[0]["report_type"] == profile
    assert findings[0]["observation_kind"] == "compromise_indicator"
