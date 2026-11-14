"""Reviewed report families preserve source identity and deliberate outreach scope."""

import gzip
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from test_intake_acquisition_095 import receipt
from test_intake_profiles_070 import Registry, csv_bytes
from workbench.api_import import enqueue_download
from workbench.eclipse import Eclipse
from workbench.intake.records import UnvalidatedEntry
from workbench.intake.validation import EntryValidator
from workbench.intake_service import IntakeService
from workbench.report_profiles import (
    notification_eligibility,
    observation_envelope,
    resolve_profile,
    supported_profiles,
)
from workbench.routes.intake import register
from workbench.store import Store


SELECTED = [
    "scan_http_vulnerable",
    "scan6_http_vulnerable",
    "scan_smtp_vulnerable",
    "scan6_smtp_vulnerable",
    "scan_exchange",
    "scan6_exchange",
    "scan_badsecrets",
    "scan6_badsecrets",
    "scan_isakmp",
    "scan6_isakmp",
    "scan_rdp",
    "scan6_rdp",
    "scan_mongodb",
    "scan6_mongodb",
    "scan_msrpc",
    "scan6_msrpc",
    "compromised_website",
    "compromised_website6",
    "compromised_iot",
    "compromised_iot6",
]
EXPOSURES = [
    "scan_http",
    "scan6_http",
    "population_isakmp",
    "population6_isakmp",
    "scan_gtp",
    "population_ntrip",
]
TARGETED = {"outreach_mode": "targeted", "targeted_reason": "Operator-selected review"}


def fields(**changes):
    return {
        "timestamp": "2026-11-01 03:00:00",
        "ip": "8.8.8.8",
        "hostname": "service.example.com",
        "region": "North Carolina",
        "protocol": "tcp",
        "port": "443",
        "severity": "critical",
        "tag": "CVE-2099-12345",
        "opaque_extension": "retained unchanged",
        **changes,
    }


def setup_intake(tmp_path, **policy):
    store = Store(tmp_path / "workspace")
    if policy:
        config = store.settings()
        config.update(policy)
        with store.transaction() as db:
            db.execute("UPDATE settings SET value=? WHERE key='profile'", (json.dumps(config),))
    registry = Registry()
    return store, IntakeService(store, lookup_factory=lambda: registry), registry


@pytest.mark.parametrize("source_id", SELECTED)
def test_selected_adapter_ids_and_targeted_policy(source_id):
    source = fields(severity="high")
    profile = resolve_profile(source, f"2026-11-01-{source_id}.csv")
    assert profile["id"] == source_id and profile["capability"] == "eligible"
    assert profile["adapter_version"] == "0.9.92-1"
    assert not notification_eligibility(source, profile, {})["eligible"]
    result = notification_eligibility(source, profile, TARGETED)
    assert result["eligible"] and result["severity"] == "high"
    assert result["severity_basis"] == "reported"


@pytest.mark.parametrize("source_id", EXPOSURES)
def test_exposure_ids_require_explicit_targeted_outreach(source_id):
    profile = resolve_profile(fields(http_code=200), f"{source_id}.csv")
    assert profile["id"] == source_id and profile["capability"] == "eligible"
    assert (
        notification_eligibility(fields(), profile, {})["reason"]
        == "targeted_profile_review_required"
    )


def test_http_headers_and_tags_do_not_establish_report_provenance():
    profile = resolve_profile(fields(http_code=200, version="PHP/5.6.29"), "renamed.csv")
    assert profile["id"] == "unclassified" and profile["capability"] == "retained"
    explicit = resolve_profile(fields(http_code=200), "renamed.csv", "Vulnerable HTTP")
    assert explicit["id"] == "scan_http_vulnerable" and explicit["selection_basis"] == "configured"
    reported = resolve_profile(fields(report_type="IPv6 Vulnerable Exchange Server"), "renamed.csv")
    assert reported["id"] == "scan6_exchange" and reported["selection_basis"] == "reported"


@pytest.mark.parametrize(
    "filename",
    ["scan_http_vulnerabletypo.csv", "prefixscan_http_vulnerable.csv", "scan6_exchange_bad.csv"],
)
def test_filename_prefixes_do_not_fall_back_to_a_different_report(filename):
    assert resolve_profile(fields(http_code=200), filename)["id"] == "unclassified"


@pytest.mark.parametrize(
    ("source_id", "reason"),
    [
        ("compromised_website", "incident_review_required"),
        ("compromised_iot6", "incident_review_required"),
        ("scan_rdp", "targeted_profile_review_required"),
        ("scan6_msrpc", "targeted_profile_review_required"),
    ],
)
def test_incidents_and_remote_services_require_deliberate_targeted_review(source_id, reason):
    profile = resolve_profile(fields(), configured_type=source_id)
    assert notification_eligibility(fields(), profile, {})["reason"] == reason
    assert (
        notification_eligibility(fields(), profile, {"outreach_mode": "targeted"})["reason"]
        == "targeted_reason_required"
    )
    assert notification_eligibility(fields(), profile, TARGETED)["eligible"]


@pytest.mark.parametrize(
    "source_id",
    [
        "scan_smtp_vulnerable",
        "scan_exchange",
        "scan_badsecrets",
        "scan_isakmp",
        "scan_rdp",
        "scan_mongodb",
        "scan_msrpc",
        "compromised_website",
        "compromised_iot",
    ],
)
def test_non_cve_service_or_indicator_rows_do_not_need_fabricated_versions(source_id):
    source_fields = fields(tag="source-reported-condition")
    profile = resolve_profile(source_fields, configured_type=source_id)
    source = UnvalidatedEntry(f"{source_id}.csv", "CSV", 2, source_fields)
    validator = EntryValidator({"North Carolina"})
    assert validator.validate_entry(source, profile=profile)
    assert "version" not in source.fields
    http = resolve_profile(source_fields, configured_type="scan_http_vulnerable")
    assert validator.rejection_reason(source, profile=http) == "missing_version"


def test_eol_requires_software_version_and_protocol_revisions_remain_raw_evidence():
    validator = EntryValidator({"North Carolina"})
    for source_id in ("scan_isakmp", "scan_msrpc", "scan_rdp"):
        source_fields = fields(tag="service", version="IKE/10")
        profile = resolve_profile(source_fields, configured_type=source_id)
        source = UnvalidatedEntry("source.csv", "CSV", 2, source_fields)
        envelope = observation_envelope(source, profile, {})
        assert envelope["profile"]["version_semantics"] == "protocol"
        assert envelope["products"] == []
        assert envelope["raw_version"] == "IKE/10"
        assert source.fields["version"] == "IKE/10"
        eol = UnvalidatedEntry("source.csv", "CSV", 2, {**source_fields, "tag": "eol-device"})
        assert validator.rejection_reason(eol, profile=profile) == "missing_version"
    exchange = resolve_profile(fields(), configured_type="scan_exchange")
    source = UnvalidatedEntry("source.csv", "CSV", 2, fields(tag="eol"))
    assert validator.rejection_reason(source, profile=exchange) == "missing_version"


@pytest.mark.parametrize("source_id", SELECTED)
def test_manual_import_retains_exact_supported_type_and_original_fields(tmp_path, source_id):
    store, intake, _ = setup_intake(tmp_path, **TARGETED)
    source_fields = fields(
        ip="2001:4860:4860::8888"
        if ("scan6_" in source_id or source_id.endswith("6"))
        else "8.8.8.8"
    )
    body = csv_bytes([source_fields])
    result = intake.enqueue(f"{source_id}.csv", body)
    intake.process(result["id"])
    saved = store.one("SELECT * FROM imports WHERE id=?", (result["id"],))
    assert saved["status"] == "done", saved["error"]
    assert saved["valid_rows"] == 1 and saved["groups_total"] == 1
    entry = json.loads(
        store.one("SELECT payload FROM jobs WHERE import_id=?", (result["id"],))["payload"]
    )[0]
    assert entry["source"]["fields"] == source_fields
    assert entry["normalized"]["profile"]["id"] == source_id
    assert entry["normalized"]["acquisition"]["kind"] == "manual_file"
    assert store.path(saved["path"]).read_bytes() == body


@pytest.mark.parametrize(
    "source_id", ["scan_smtp_vulnerable", "scan6_exchange", "scan_badsecrets", "compromised_iot"]
)
def test_api_receipt_selects_profile_without_filename_or_header_guessing(tmp_path, source_id):
    store, intake, _ = setup_intake(tmp_path, **TARGETED)
    source_fields = fields(tag="source-reported-condition")
    body = gzip.compress(csv_bytes([source_fields]))
    path = tmp_path / "opaque-download.csv.gz"
    path.write_bytes(body)
    proof = receipt(body, name=path.name, report_type=source_id)
    result = enqueue_download(intake, path, proof, narrative_date_basis="emailed_row_plus_one")
    intake.process(result["id"])
    saved = store.one("SELECT * FROM imports WHERE id=?", (result["id"],))
    assert saved["status"] == "done", saved["error"]
    entry = json.loads(
        store.one("SELECT payload FROM jobs WHERE import_id=?", (result["id"],))["payload"]
    )[0]
    assert entry["normalized"]["profile"]["id"] == source_id
    assert entry["source"]["fields"] == source_fields
    assert entry["normalized"]["acquisition"]["report_date"] == "2026-11-01"


def test_exposure_default_disposition_matches_saved_profile_policy(tmp_path):
    store, intake, registry = setup_intake(tmp_path)
    result = intake.enqueue("scan_rdp.csv", csv_bytes([fields(tag="rdp", severity="high")]))
    intake.process(result["id"])
    saved = store.one("SELECT * FROM imports WHERE id=?", (result["id"],))
    assert json.loads(saved["rejected"]) == {"targeted_profile_review_required": 1}
    assert not registry.calls
    observation = Eclipse(store).snapshot()["observations"][0]
    assert observation["intake_reason"] == "targeted_profile_review_required"
    assert observation["disposition_reason"] == "Outside the selected outreach mode"
    assert "version" not in observation["disposition_reason"].lower()


def test_capabilities_publish_only_reviewed_notification_adapters(tmp_path):
    store, intake, _ = setup_intake(tmp_path)
    app = FastAPI()
    register(app, store=store, intake=intake)
    with TestClient(app) as client:
        payload = client.get("/api/intake/capabilities").json()
    assert payload["notification_profiles"] == sorted(SELECTED + EXPOSURES) == supported_profiles()
    assert payload["api_live_selection"] is False
