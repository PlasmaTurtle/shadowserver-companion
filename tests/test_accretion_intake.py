"""Accretion filters before local enrichment and preserves source/decision evidence."""

import csv
import io
import json

from workbench.accretion import vet_cves
from workbench.cve_catalog.storage import CatalogStorage
from workbench.intake import EntryValidator, UnvalidatedEntry
from workbench.intake_service import IntakeService
from workbench.report_profiles import notification_eligibility, resolve_profile
from workbench.store import Store


class Registry:
    def __init__(self):
        self.calls = []

    def lookup(self, ip):
        self.calls.append(ip)
        return None

    def close(self):
        pass


def row(**changes):
    return {
        "hostname": "mail.example.com",
        "ip": "8.8.8.8",
        "tag": "CVE-2026-12345",
        "version": "Acme/1.2",
        "region": "North Carolina",
        "city": "Burnsville",
        "severity": "high",
        "timestamp": "2026-11-11 10:00:00",
        **changes,
    }


def report(rows):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def seed(root, identifier="CVE-2026-12345", *, score=9.8, rejected=False):
    catalog = CatalogStorage(root)
    raw = {
        "id": identifier,
        "published": "2026-11-01T10:00:00Z",
        "lastModified": "2026-11-10T10:00:00Z",
        "vulnStatus": "Rejected" if rejected else "Analyzed",
        "descriptions": [{"lang": "en", "value": "Synthetic CVE for intake validation"}],
        "metrics": {
            "cvssMetricV31": [
                {
                    "type": "Primary",
                    "cvssData": {
                        "version": "3.1",
                        "baseScore": score,
                        "baseSeverity": "CRITICAL" if score >= 9 else "HIGH",
                    },
                }
            ]
        },
    }
    with catalog.connection() as db:
        catalog.upsert(
            db,
            raw,
            {
                "url": "https://nvd.nist.gov/feeds/json/cve/2.0/nvdcve-2.0-2026.json.gz",
                "retrieved_at": "2026-11-11T10:00:00Z",
            },
        )
    return catalog


def run_import(store, rows):
    registry = Registry()
    intake = IntakeService(store, lookup_factory=lambda: registry)
    original = report(rows)
    import_id = intake.enqueue("scan-http_vulnerable.csv", original)["id"]
    intake.process(import_id)
    result = store.one("SELECT * FROM imports WHERE id=?", (import_id,))
    assert result["status"] == "done", result["error"]
    return intake, registry, result, original


def test_local_catalog_opens_admission_without_rewriting_source(tmp_path):
    store = Store(tmp_path / "workspace")
    seed(store.root)
    _, registry, result, original = run_import(store, [row(), row(severity="low", tag="eol-acme")])
    assert result["groups_total"] == 1 and result["valid_rows"] == 2
    assert registry.calls == ["8.8.8.8"]
    assert store.path(result["path"]).read_bytes() == original
    entries = json.loads(
        store.one("SELECT payload FROM jobs WHERE import_id=?", (result["id"],))["payload"]
    )
    admission = entries[0]["normalized"]["eligibility"]
    assert admission["severity"] == "high" and admission["raw_severity"] == "high"
    assert admission["admission_severity"] == "critical"
    assert admission["admission_basis"] == "local_catalog_cvss"
    assert admission["admission_cves"] == ["CVE-2026-12345"]
    assert entries[0]["source"]["fields"]["severity"] == "high"
    assert entries[0]["normalized"]["accretion_cves"]["CVE-2026-12345"]["source"]["record_sha256"]
    assert entries[1]["normalized"]["eligibility"]["included_as_context"]
    stats = json.loads(result["config"])["intake_stats"]["accretion"]
    assert stats["admitted_rows"] == 2 and stats["context_rows"] == 1
    assert stats["catalog_critical_rows"] == 1 and stats["cves_checked"] == 1
    queued = store.one("SELECT intake_score FROM lead_queue WHERE import_id=?", (result["id"],))
    assert json.loads(queued["intake_score"])["quality"] > 0


def test_filter_precedes_one_deduplicated_local_batch(tmp_path, monkeypatch):
    store = Store(tmp_path / "workspace")
    seed(store.root)
    batches = []

    def vetted(root, ids, **kwargs):
        batches.append(list(ids))
        return vet_cves(root, ids, **kwargs)

    monkeypatch.setattr("workbench.intake_service.vet_cves", vetted)
    _, registry, result, _ = run_import(
        store,
        [
            row(),
            row(hostname="other.example.com"),
            row(hostname="outside.com", region="Virginia", tag="CVE-2026-99991"),
            row(hostname="broken hostname", tag="CVE-2026-99992"),
            row(tag="   "),
        ],
    )
    assert batches == [["CVE-2026-12345"]]
    assert result["valid_rows"] == 2 and len(registry.calls) == 1
    assert json.loads(result["rejected"]) == {
        "outside_jurisdiction": 1,
        "invalid_hostname": 1,
        "missing_required_value": 1,
    }


def test_missing_catalog_never_manufactures_critical_or_drops_reported_critical(tmp_path):
    store = Store(tmp_path / "workspace")
    _, registry, result, _ = run_import(
        store,
        [
            row(hostname="high.com"),
            row(hostname="critical.com", severity="critical"),
        ],
    )
    assert result["groups_total"] == 1 and len(registry.calls) == 1
    assert json.loads(result["rejected"]) == {"below_critical": 1}
    entries = json.loads(
        store.one("SELECT payload FROM jobs WHERE import_id=?", (result["id"],))["payload"]
    )
    assert entries[0]["normalized"]["eligibility"]["admission_basis"] == "reported"
    assert entries[0]["normalized"]["accretion_cves"]["CVE-2026-12345"]["status"] == "unavailable"


def test_withdrawn_only_cves_rejected_but_independent_eol_survives(tmp_path):
    store = Store(tmp_path / "workspace")
    seed(store.root, rejected=True)
    _, registry, result, _ = run_import(
        store,
        [
            row(hostname="withdrawn.com", severity="critical"),
            row(hostname="supported.com", severity="critical", tag="CVE-2026-12345;eol-acme"),
        ],
    )
    assert result["valid_rows"] == 1 and result["groups_total"] == 1
    assert json.loads(result["rejected"]) == {"withdrawn_cve_only": 1}
    assert len(registry.calls) == 1


def test_catalog_cannot_bypass_profile_or_targeted_gates():
    source = row()
    vetted = {"CVE-2026-12345": {"status": "available", "cvss": 10}}
    for profile, config, reason in [
        (resolve_profile(source, configured_type="scan_ftp"), {}, "unsupported_report_profile"),
        (
            resolve_profile(source, configured_type="scan_rdp"),
            {},
            "targeted_profile_review_required",
        ),
        (
            resolve_profile(source, configured_type="scan_http_vulnerable"),
            {"outreach_mode": "targeted"},
            "targeted_reason_required",
        ),
    ]:
        result = notification_eligibility(source, profile, config, catalog_records=vetted)
        assert not result["eligible"] and result["reason"] == reason


def test_policy_and_priority_change_replay_without_rewriting_prior(tmp_path, monkeypatch):
    store = Store(tmp_path / "workspace")
    intake = IntakeService(store)
    original = report([row()])
    first = intake.enqueue("scan-http_vulnerable.csv", original)
    assert intake.enqueue("scan-http_vulnerable.csv", original)["duplicate"]
    before = store.one("SELECT config,path FROM imports WHERE id=?", (first["id"],))
    settings = store.settings()
    settings["accretion_priority_cities"] = ["Burnsville"]
    monkeypatch.setattr(store, "settings", lambda: dict(settings))
    replay = intake.reevaluate(first["id"])
    assert replay["id"] != first["id"] and not replay["duplicate"]
    after = store.one("SELECT config,path FROM imports WHERE id=?", (replay["id"],))
    assert after["path"] == before["path"]
    assert json.loads(after["config"])["accretion_policy"]["priority_cities"] == ["burnsville"]
    assert store.one("SELECT config,path FROM imports WHERE id=?", (first["id"],)) == before


def test_whitespace_only_required_fields_and_eol_version_fail_filter():
    validator = EntryValidator({"North Carolina"})
    for field in ("tag", "hostname", "ip", "region"):
        source = UnvalidatedEntry("source.csv", "CSV", 2, row(**{field: " \t"}))
        assert validator.rejection_reason(source) == "missing_required_value"
    source = UnvalidatedEntry("source.csv", "CSV", 2, row(tag="eol-acme", version=" \t"))
    assert validator.rejection_reason(source) == "missing_version"


def test_legacy_queued_import_keeps_original_admission_policy(tmp_path, monkeypatch):
    store = Store(tmp_path / "workspace")
    seed(store.root)
    intake = IntakeService(store, lookup_factory=Registry)
    import_id = intake.enqueue("scan-http_vulnerable.csv", report([row()]))["id"]
    original = store.one("SELECT config FROM imports WHERE id=?", (import_id,))
    legacy_config = json.loads(original["config"])
    legacy_config.pop("accretion_policy")
    with store.transaction() as db:
        db.execute("UPDATE imports SET config=? WHERE id=?", (json.dumps(legacy_config), import_id))

    def forbidden(*args, **kwargs):
        raise AssertionError("A saved legacy policy must not silently gain local-CVE admission")

    monkeypatch.setattr("workbench.intake_service.vet_cves", forbidden)
    intake.process(import_id)
    result = store.one("SELECT * FROM imports WHERE id=?", (import_id,))
    assert result["status"] == "done", result["error"]
    assert result["groups_total"] == 0
    assert json.loads(result["rejected"]) == {"below_critical": 1}


def test_retry_preserves_entry_scores_when_catalog_and_priorities_change(tmp_path, monkeypatch):
    from workbench.intake import WhoisLookupError

    class DeferredRegistry(Registry):
        def lookup(self, ip):
            raise WhoisLookupError("Synthetic temporary registry outage")

    store = Store(tmp_path / "workspace")
    seed(store.root)
    intake = IntakeService(store, lookup_factory=DeferredRegistry)
    import_id = intake.enqueue("scan-http_vulnerable.csv", report([row()]))["id"]
    intake.process(import_id)
    first = store.one("SELECT * FROM imports WHERE id=?", (import_id,))
    assert first["status"] == "needs_retry", first["error"]
    original_score = store.one(
        "SELECT intake_score FROM lead_queue WHERE import_id=?", (import_id,)
    )
    original_payload = store.one("SELECT payload FROM jobs WHERE import_id=?", (import_id,))
    seed(store.root, score=4.0)
    settings = store.settings()
    settings["accretion_priority_cities"] = ["Burnsville"]
    monkeypatch.setattr(store, "settings", lambda: dict(settings))

    def forbidden(*args, **kwargs):
        raise AssertionError("Attribution retry must reuse captured CVE snapshots")

    monkeypatch.setattr("workbench.intake_service.vet_cves", forbidden)
    intake.lookup_factory = Registry
    intake.retry(import_id)
    intake.process(import_id)
    retried = store.one("SELECT * FROM imports WHERE id=?", (import_id,))
    assert retried["status"] == "done", retried["error"]
    assert (
        json.loads(retried["config"])["accretion_policy"]
        == json.loads(first["config"])["accretion_policy"]
    )
    assert (
        store.one("SELECT intake_score FROM lead_queue WHERE import_id=?", (import_id,))
        == original_score
    )
    assert store.one("SELECT payload FROM jobs WHERE import_id=?", (import_id,)) == original_payload


def test_complete_catalog_metrics_can_filter_reported_critical(tmp_path):
    store = Store(tmp_path / "workspace")
    seed(store.root, score=7.5)
    _, registry, result, original = run_import(store, [row(severity="critical")])
    assert result["groups_total"] == 0 and not registry.calls
    assert json.loads(result["rejected"]) == {"below_critical": 1}
    assert store.path(result["path"]).read_bytes() == original
    recorded = store.one(
        "SELECT disposition,reason FROM intake_observations WHERE import_id=?", (result["id"],)
    )
    assert recorded == {"disposition": "dark_matter", "reason": "below_critical"}


def test_partial_catalog_coverage_and_independent_eol_keep_reported_fallback():
    records = {"CVE-2026-12345": {"status": "available", "cvss": 7.5}}
    source = row(severity="critical")
    profile = resolve_profile(source, configured_type="scan_http_vulnerable")
    complete = notification_eligibility(source, profile, {}, catalog_records=records)
    assert not complete["eligible"] and complete["severity"] == "critical"
    assert complete["admission_severity"] == "high"
    assert (
        complete["admission_basis"] == "local_catalog_cvss"
        and complete["admission_catalog_complete"]
    )
    for tag in ("CVE-2026-12345;CVE-2026-99999", "CVE-2026-12345;eol-acme"):
        result = notification_eligibility(
            {**source, "tag": tag}, profile, {}, catalog_records=records
        )
        assert result["eligible"] and result["admission_basis"] == "reported"
    targeted = notification_eligibility(
        source,
        profile,
        {"outreach_mode": "targeted", "targeted_reason": "This month's selected product"},
        catalog_records=records,
    )
    assert targeted["eligible"] and targeted["admission_severity"] == "high"


def test_catalog_uses_highest_resolved_cve_and_ignores_withdrawn_metric():
    source = row(severity="critical", tag="CVE-2026-12345;CVE-2026-12346")
    profile = resolve_profile(source, configured_type="scan_http_vulnerable")
    records = {
        "CVE-2026-12345": {"status": "available", "cvss": 7.5},
        "CVE-2026-12346": {"status": "rejected", "cvss": 10},
    }
    result = notification_eligibility(source, profile, {}, catalog_records=records)
    assert not result["eligible"] and result["admission_severity"] == "high"
    assert result["admission_cves"] == ["CVE-2026-12345"]
    records["CVE-2026-12346"] = {"status": "available", "cvss": 9.8}
    result = notification_eligibility(source, profile, {}, catalog_records=records)
    assert result["eligible"] and result["admission_severity"] == "critical"
    assert result["admission_cves"] == ["CVE-2026-12346"]


def test_verified_kev_rescues_high_but_not_withdrawn_or_nonkev_findings(tmp_path):
    import hashlib
    from workbench.cve_catalog.risk import RiskStore

    store = Store(tmp_path / "workspace")
    high, nonkev, withdrawn = "CVE-2026-12345", "CVE-2026-12346", "CVE-2026-12347"
    seed(store.root, high, score=7.5)
    seed(store.root, nonkev, score=7.5)
    seed(store.root, withdrawn, score=7.5, rejected=True)
    risk = RiskStore(store.root)
    with risk.connection(write=True) as db:
        risk.put_metadata("kev", {"last_success_at": "2026-11-11T10:00:00Z", "count": 2}, db=db)
        for identifier in (high, withdrawn):
            raw = json.dumps({"cveID": identifier, "knownRansomwareCampaignUse": "Unknown"})
            db.execute(
                "INSERT INTO kev VALUES (?,?,?)",
                (identifier, raw, hashlib.sha256(raw.encode()).hexdigest()),
            )
    _, registry, result, _ = run_import(
        store,
        [
            row(hostname="exploited.com", tag=high),
            row(hostname="nonexploited.com", tag=nonkev),
            row(hostname="withdrawn.com", tag=withdrawn),
        ],
    )
    assert result["valid_rows"] == 1 and result["groups_total"] == 1
    assert len(registry.calls) == 1
    assert json.loads(result["rejected"]) == {"below_critical": 1, "withdrawn_cve_only": 1}
    entries = json.loads(
        store.one("SELECT payload FROM jobs WHERE import_id=?", (result["id"],))["payload"]
    )
    admission = entries[0]["normalized"]["eligibility"]
    assert admission["severity"] == "high" and admission["admission_severity"] == "high"
    assert admission["admission_basis"] == "local_kev"
    assert admission["admission_signal"] == "known_exploitation"
    assert admission["admission_cves"] == [high]
    assert json.loads(result["config"])["intake_stats"]["accretion"]["kev_admitted_rows"] == 1


def test_kev_cannot_bypass_incident_or_targeted_only_gates():
    source = row()
    records = {"CVE-2026-12345": {"status": "available", "cvss": 7.5, "kev": {"listed": True}}}
    for report_type, config, reason in [
        ("compromised_website", {}, "incident_review_required"),
        ("scan_rdp", {}, "targeted_profile_review_required"),
        ("scan_ftp", {}, "unsupported_report_profile"),
    ]:
        profile = resolve_profile(source, configured_type=report_type)
        result = notification_eligibility(source, profile, config, catalog_records=records)
        assert not result["eligible"] and result["reason"] == reason
    profile = resolve_profile(source, configured_type="scan_http_vulnerable")
    records["CVE-2026-12345"]["status"] = "invalid"
    assert not notification_eligibility(source, profile, {}, catalog_records=records)["eligible"]
    assert not notification_eligibility({**source, "kev": True}, profile, {})["eligible"]


def test_score_timestamp_is_local_vetting_time_not_queued_import_time(tmp_path, monkeypatch):
    store = Store(tmp_path / "workspace")
    seed(store.root)
    intake = IntakeService(store, lookup_factory=Registry)
    import_id = intake.enqueue("scan-http_vulnerable.csv", report([row()]))["id"]
    with store.transaction() as db:
        db.execute(
            "UPDATE imports SET created_at=? WHERE id=?", ("2026-01-01T00:00:00.000Z", import_id)
        )
    scored_at = "2026-11-12T12:34:56.000Z"
    monkeypatch.setattr("workbench.intake_service.now", lambda: scored_at)
    captured_times = []

    def checked(root, ids, *, as_of=None):
        captured_times.append(as_of)
        return vet_cves(root, ids, as_of=as_of)

    monkeypatch.setattr("workbench.intake_service.vet_cves", checked)
    intake.process(import_id)
    result = store.one("SELECT * FROM imports WHERE id=?", (import_id,))
    assert result["status"] == "done", result["error"]
    assert captured_times == [scored_at]
    assert json.loads(result["config"])["accretion_scored_at"] == scored_at
    score = json.loads(
        store.one("SELECT intake_score FROM lead_queue WHERE import_id=?", (import_id,))[
            "intake_score"
        ]
    )
    assert score["scored_at"] == scored_at
    assert score["scored_at"] != result["created_at"]
