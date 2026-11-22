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


def test_group_reuse_keeps_original_ip_proof_and_verified_recent_host_capture(pipeline):
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
    assert registry.calls == ["8.8.8.8"] and not calls
    original = json.loads(first["qualification"])["website"]
    assert proof["website"]["id"] == original["id"]
    assert proof["website"]["sha256"] == original["sha256"]
    assert json.loads(second["attempts"])[0]["status"] == "reused"
    assert store.one("SELECT count(*) n FROM website_captures")["n"] == 1


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
    assert fresh["status"] == "qualified" and not calls
    assert json.loads(fresh["attempts"])[0]["status"] == "reused"


@pytest.mark.parametrize(
    ("title", "status", "reason"),
    [
        ("Sign in", "login_required", "website_unidentified"),
        ("Please authenticate to continue", "captured", "website_unidentified"),
        ("Welcome to your new hosting account", "captured", "website_unidentified"),
        ("Buy this domain", "captured", "website_parked"),
    ],
)
def test_unidentified_200_government_site_cannot_enter_leads(pipeline, title, status, reason):
    store, intake, registry = pipeline

    def capture(url, **kwargs):
        data, metadata = capture_website(url, **kwargs)
        return data, {
            **metadata,
            "title": title,
            "site_name": "",
            "heading": title,
            "capture_status": status,
        }

    intake.capture = capture
    _, job = run(pipeline, [row(hostname="portal.example.gov")])
    assert (job["status"], job["error"]) == ("dismissed", reason)
    assert json.loads(job["attempts"])[0]["final_url"] == "https://portal.example.gov/"
    assert not registry.calls
    assert not store.all("SELECT id FROM lead_queue")


def test_scoped_external_deconfliction_crud_explains_and_preserves_sibling(pipeline):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from modules.accretion.components.routes.intake import register

    store, intake, _ = pipeline
    app = FastAPI()
    register(app, store=store, intake=intake)
    with TestClient(app) as client:
        url = "/api/intake/deconfliction"
        entry = {
            "scope": "host",
            "identifier": "Mail.Example.Com.",
            "external_reference": "NC-17",
            "reason": "Partner is handling this hostname",
        }
        response = client.post(url, json=entry)
        assert response.status_code == 200, response.text
        identity = response.json()["id"]
        assert client.post(url, json=entry).status_code == 409
        assert client.post(url, json={**entry, "scope": "domain"}).status_code == 400
        _, mixed = run(pipeline, [row(), row(hostname="other.example.com")])
        assert mixed["status"] == "qualified"
        matches = [a for a in json.loads(mixed["attempts"]) if a["method"] == "associate"]
        assert [
            (a["entry_id"], a["scope"], a["identifier"], a["reference"], a["reason"])
            for a in matches
        ] == [(identity, "host", "mail.example.com", "NC-17", entry["reason"])]
        queue = store.one("SELECT payload FROM lead_queue WHERE status='pending'")
        assert [e["source"]["fields"]["hostname"] for e in json.loads(queue["payload"])] == [
            "other.example.com"
        ]
        assert [e["hostname"] for e in store.all("SELECT hostname FROM entries")] == [
            "other.example.com"
        ]

        response = client.put(
            url + "/" + identity,
            json={
                **entry,
                "scope": "domain",
                "identifier": "example.com",
                "external_reference": "NC-23",
            },
        )
        assert response.status_code == 200
        _, excluded = run(pipeline, [row(hostname="new.example.com")])
        assert (excluded["status"], excluded["error"]) == ("dismissed", "association_deconflicted")
        totals = {"qualified": 1, "evaluated": 1, "published": 0, "excluded_by_associate": 1}
        assert client.get("/api/intake/progress").json()["current"]["stage_totals"] == totals
        detail = client.get("/api/imports/" + excluded["import_id"]).json()
        assert detail["stage_totals"] == totals
        assert detail["groups"][0]["error"] == "association_deconflicted"
        history = json.loads(excluded["attempts"])
        assert any(a.get("reference") == "NC-23" and a["scope"] == "domain" for a in history)
        assert len(store.all("SELECT id FROM lead_queue")) == 1
        assert client.delete(url + "/" + identity).status_code == 200
        assert client.get(url).json() == []
        assert any(
            a.get("reference") == "NC-17"
            for a in json.loads(
                store.one("SELECT attempts FROM jobs WHERE id=?", (mixed["id"],))["attempts"]
            )
        )


def test_generic_login_site_name_cannot_supply_business_identity(pipeline):
    store, intake, registry = pipeline

    def capture(url, **options):
        pixels, page = capture_website(url, **options)
        return pixels, dict(
            page,
            site_name="Login Center",
            heading="Sign in",
            title="Sign in to your account",
            capture_status="login_required",
        )

    intake.capture = capture
    _, job = run(pipeline)
    assert (job["status"], job["error"]) == ("dismissed", "website_unidentified")
    assert not registry.calls
    assert not store.all("SELECT id FROM lead_queue")


@pytest.mark.parametrize("during_evaluation", [False, True])
def test_case_adopts_only_surviving_host_and_registration_evidence(pipeline, during_evaluation):
    from modules.investigations.components.cases import Cases

    store, intake, registry = pipeline
    originally_evaluate = intake.evaluate_lead

    def refer_first_host():
        with store.transaction() as db:
            db.execute(
                "INSERT INTO intake_deconfliction VALUES(?,?,?,?,?,?)",
                ("mail-ref", "host", "mail.example.com", "NC-22", "Referred to partner", now()),
            )

    def evaluate(*args, **kwargs):
        evaluated = originally_evaluate(*args, **kwargs)
        refer_first_host()
        return evaluated

    if during_evaluation:
        intake.evaluate_lead = evaluate
    else:
        refer_first_host()
    imported, job = run(pipeline, [row(), row(hostname="other.example.com", ip="9.9.9.9")])
    if during_evaluation:
        assert (job["status"], job["error"]) == ("deferred", "association_evidence_changed")
        assert "NC-22" in job["attempts"]
        from modules.accretion.components.intake_progress import overview

        assert overview(store)["current"]["stage_totals"] == {
            "qualified": 1,
            "evaluated": 1,
            "published": 0,
            "excluded_by_associate": 0,
        }
        assert not store.all("SELECT id FROM lead_queue")
        assert not store.all("SELECT * FROM website_capture_entities")
        intake.evaluate_lead = originally_evaluate
        intake.retry(imported["id"])
        intake.process(imported["id"])
        job = store.one("SELECT * FROM jobs WHERE id=?", (job["id"],))
    assert job["status"] == "qualified"
    evidence = json.loads(job["qualification"])
    assert (
        evidence["website"]["requested_url"]
        == evidence["website"]["final_url"]
        == "https://other.example.com/"
    )
    assert evidence["attribution"]["ip"] == "9.9.9.9"
    assert registry.calls == (["8.8.8.8", "9.9.9.9"] if during_evaluation else ["9.9.9.9"])
    assert [entry["source"]["fields"]["hostname"] for entry in json.loads(job["payload"])] == [
        "mail.example.com",
        "other.example.com",
    ]
    entity = store.one("SELECT id, attribution FROM leads")
    coverage = json.loads(entity["attribution"])["coverage"]
    assert [(c["entry_id"], c["hostname"], c["relationship"]) for c in coverage] == [
        ("1", "other.example.com", "matched_address")
    ]
    case_id = Cases(store).create(entity["id"])["case_id"]
    adopted = store.one("SELECT * FROM evidence WHERE case_id=?", (case_id,))
    assert adopted["path"] == evidence["website"]["path"]
    assert adopted["sha256"] == evidence["website"]["sha256"]
    assert (
        store.one("SELECT capture_id FROM website_capture_cases WHERE case_id=?", (case_id,))[
            "capture_id"
        ]
        == evidence["website"]["id"]
    )


def test_referred_redirect_does_not_supply_proof_for_a_clean_host(pipeline):
    store, intake, registry = pipeline
    with store.transaction() as db:
        db.execute(
            "INSERT INTO intake_deconfliction VALUES(?,?,?,?,?,?)",
            ("host", "host", "auth.example.com", "NC-23", "External investigation", now()),
        )

    def capture(url, **options):
        pixels, page = capture_website(url, **options)
        return pixels, dict(
            page,
            final_url="https://auth.example.com/",
            redirects=[url, "https://auth.example.com/"],
        )

    intake.capture = capture
    _, job = run(pipeline)
    assert (job["status"], job["error"]) == ("deferred", "website_deconflicted_destination")
    assert not registry.calls
    assert not store.all("SELECT id FROM website_captures")
    assert not store.all("SELECT id FROM lead_queue")


def test_government_domain_uses_existing_agency_priority_weight():
    base = {"source": {"fields": row()}, "normalized": {}}
    commercial = accretion.score_lead([base], root_domain="example.com")
    government = accretion.score_lead(
        [{**base, "source": {"fields": row(hostname="mail.example.gov")}}],
        root_domain="example.gov",
    )
    assert government["aggregate"] > commercial["aggregate"]
    assert "Government domain (.gov)" in json.dumps(government)


def test_full_exclusion_keeps_unmatched_context_rows_original_reason(pipeline):
    store, _, _ = pipeline
    with store.transaction() as db:
        db.execute(
            "INSERT INTO intake_deconfliction VALUES(?,?,?,?,?,?)",
            ("external", "host", "mail.example.com", "NC-1", "Coordinated elsewhere", now()),
        )
    _, job = run(
        pipeline, [row(), row(hostname="other.example.com", tag="CVE-2026-99999", severity="low")]
    )
    assert job["error"] == "association_deconflicted"
    assert {
        item["raw_fields"]["hostname"]: item["reason"]
        for item in store.dark_matter.query()["items"]
    } == {"mail.example.com": "association_deconflicted", "other.example.com": "below_critical"}


def test_associate_reports_previous_delivery_and_enforces_current_hold(pipeline):
    from modules.investigations.components.cases import Cases

    store, _, _ = pipeline
    run(pipeline)
    entity = store.one("SELECT id FROM leads")["id"]
    case_id = Cases(store).create(entity)["case_id"]
    with store.transaction() as db:
        db.execute("UPDATE cases SET delivered_at=? WHERE id=?", (now(), case_id))
        db.execute(
            "INSERT INTO case_outreach_policy VALUES(?,?,?,?,?,?)",
            (
                case_id,
                "do_not_contact",
                "Handled by the coordinating agency",
                None,
                "Operator",
                now(),
            ),
        )
    _, held = run(
        pipeline,
        [
            row(
                hostname="another.example.com",
                tag="eol-php",
                severity="critical",
                version="PHP/7.3.25",
            )
        ],
    )
    assert (held["status"], held["error"]) == ("dismissed", "association_deconflicted")
    decisions = [a for a in json.loads(held["attempts"]) if a["method"] == "associate"]
    assert [(a["kind"], a["identifier"], a["reference"], a["action"]) for a in decisions] == [
        ("notification_history", entity, case_id, "inform"),
        ("outreach_do_not_contact", entity, case_id, "exclude"),
    ]
    assert decisions[0]["count"] == 1
    assert decisions[1]["reason"] == "Handled by the coordinating agency"


def test_identity_evidence_can_name_a_business_different_from_its_domain():
    from modules.accretion.components.website_identity import rejection_reason

    page = {
        "final_url": "https://portal.example.com/",
        "capture_status": "captured",
        "title": "Oak Cedar Foundation | Home",
        "heading": "Oak Cedar Foundation",
    }
    assert rejection_reason(page, "example.com") is None
    assert (
        rejection_reason({**page, "final_url": "https://unrelated.org/"}, "example.com")
        == "website_identity_review"
    )


def test_certificate_patterns_cannot_substitute_for_a_reported_hostname(pipeline):
    store, intake, registry = pipeline
    report_id = intake.enqueue("scan_http_vulnerable.csv", report([row(hostname="*.example.com")]))[
        "id"
    ]
    intake.process(report_id)
    item = store.one("SELECT * FROM imports WHERE id=?", (report_id,))
    assert json.loads(item["rejected"]) == {"unusable_certificate_hostname": 1}
    assert item["groups_total"] == 0 and not registry.calls


def test_budget_resume_starts_at_first_unchecked_hostname(pipeline, monkeypatch):
    from modules.accretion.components import qualification
    from modules.tools.components.website_capture import WebsiteLoadError

    store, intake, registry = pipeline
    clock = [100.0]
    calls = []
    monkeypatch.setattr(qualification, "monotonic", lambda: clock[0])

    def capture(url, **options):
        calls.append(url)
        if len(calls) == 1:
            clock[0] = options["deadline"]
            raise WebsiteLoadError("Synthetic timeout", {"attempted_urls": [url]})
        return capture_website(url, **options)

    intake.capture = capture
    original, job = run(
        pipeline, [row(hostname="first.example.com"), row(hostname="second.example.com")]
    )
    assert (original["status"], job["error"]) == ("needs_retry", "website_budget_exhausted")
    intake.retry(original["id"])
    intake.process(original["id"])
    assert store.one("SELECT status FROM jobs WHERE id=?", (job["id"],))["status"] == "qualified"
    assert calls == ["https://first.example.com/", "https://second.example.com/"]
    assert registry.calls == ["8.8.8.8"]


def test_existing_qualified_government_lead_gets_its_weight_on_upgrade(pipeline):
    store, intake, registry = pipeline

    class StateRegistry(Registry):
        def lookup(self, address):
            from dataclasses import replace

            return replace(super().lookup(address), record={"contact": "security@example.gov"})

    intake.attribution_factory = registry_factory(StateRegistry)
    _, job = run(pipeline, [row(hostname="portal.example.gov")])
    assert job["status"] == "qualified"
    lead = store.one("SELECT * FROM lead_queue")
    expected = json.loads(lead["intake_score"])
    old = {
        **expected,
        "aggregate": 0,
        "evaluation_scope": {**expected["evaluation_scope"], "version": 2},
    }
    with store.transaction() as db:
        db.execute("UPDATE lead_queue SET intake_score=?", (json.dumps(old),))
        db.execute("DROP TABLE intake_deconfliction")
        db.execute("PRAGMA user_version=23")
    store.migrate()
    restored = store.one("SELECT * FROM lead_queue")
    assert restored["id"] == lead["id"] and restored["payload"] == lead["payload"]
    assert json.loads(restored["intake_score"])["aggregate"] == expected["aggregate"]
    assert "Government domain (.gov)" in restored["intake_score"]


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
