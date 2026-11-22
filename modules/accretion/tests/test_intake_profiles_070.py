"""Profile boundaries and critical outreach preserve the full source inventory."""

from tests.support.qualification import registry_factory, capture_website

import json

from openpyxl import Workbook

from modules.accretion.components.intake import SourceObservation, read_entries
from modules.accretion.components.intake_service import IntakeService
from modules.accretion.components.report_profiles import (
    inventory_metadata,
    notification_eligibility,
    observation_envelope,
    products_from_version,
    resolve_profile,
)
from modules.workspace.components.store import Store

from modules.accretion.tests.support.intake_profiles import (
    Registry,
    csv_bytes,
    row,
)


def test_inventory_is_pinned_and_capability_is_not_inferred_from_177_definitions():
    meta = inventory_metadata()
    assert meta["inventory_count"] == 177 and meta["distinct_field_count"] == 746
    assert len(meta["commit"]) == 40 and len(meta["sha256"]) == 64
    profile = resolve_profile(row(), "2026-11-05-scan-http_vulnerable-13941.csv")
    assert profile["id"] == "scan_http_vulnerable" and profile["capability"] == "eligible"
    assert "component_version" in profile["declared_fields"]
    unknown = resolve_profile({"ip": "8.8.8.8", "future_field": False}, "future.csv")
    assert unknown["id"] == "unclassified" and unknown["capability"] == "retained"
    ftp = resolve_profile(row(), "scan-ftp.csv")
    assert ftp["id"] == "scan_ftp" and ftp["capability"] == "retained"


def test_severity_requires_reported_critical_not_kev_eol_or_high_cvss():
    profile = resolve_profile(row(), configured_type="scan_http_vulnerable")
    for value, reason in [
        (None, "unknown_severity"),
        ("", "unknown_severity"),
        ("high", "below_critical"),
        (False, "unknown_severity"),
        (0, "unknown_severity"),
    ]:
        result = notification_eligibility(row(severity=value, kev=True, cvss=10), profile, {})
        assert result["eligible"] is False and result["reason"] == reason
        assert result["raw_severity"] == value
    assert notification_eligibility(row(severity="CRITICAL"), profile, {})["eligible"]
    assert not notification_eligibility(row(severity="high"), profile, {"critical_only": False})[
        "eligible"
    ]
    targeted = notification_eligibility(
        row(severity="high"),
        profile,
        {"outreach_mode": "targeted", "targeted_reason": "Specific follow-up"},
    )
    assert targeted["eligible"] and targeted["severity"] == "high" and targeted["override_reason"]


def test_unknown_fields_zero_false_null_formula_and_all_unknown_schema_are_preserved(tmp_path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["future", "zero", "false", "empty", "formula"])
    sheet.append(["原始情報", 0, False, None, "=1+1"])
    path = tmp_path / "unknown.xlsx"
    workbook.save(path)
    before = path.read_bytes()
    rows = list(read_entries(path, ""))
    assert rows[0].fields == {
        "future": "原始情報",
        "zero": 0,
        "false": False,
        "empty": None,
        "formula": "=1+1",
    }
    assert path.read_bytes() == before
    store = Store(tmp_path / "store")
    registry = Registry()
    intake = IntakeService(
        store, attribution_factory=registry_factory(lambda: registry), capture=capture_website
    )
    iid = intake.enqueue(path.name, before)["id"]
    intake.process(iid)
    result = store.one("SELECT * FROM imports WHERE id=?", (iid,))
    assert result["status"] == "done" and result["rows_read"] == 1 and result["groups_total"] == 0
    assert json.loads(result["rejected"]) == {"unsupported_report_profile": 1}
    assert not registry.calls
    assert store.path(result["path"]).read_bytes() == before


def test_prelookup_gates_and_critical_group_context_without_losing_rows(tmp_path):
    store = Store(tmp_path / "store")
    registry = Registry()
    intake = IntakeService(
        store, attribution_factory=registry_factory(lambda: registry), capture=capture_website
    )
    rows = [
        row(),
        row(ip="10.1.2.3", severity="low"),
        row(hostname="another.com", ip="9.9.9.9", severity="high"),
        row(hostname="unknown.com", severity=""),
        row(hostname="outside.com", region="Virginia"),
    ]
    source = csv_bytes(rows)
    iid = intake.enqueue("scan-http_vulnerable.csv", source)["id"]
    intake.process(iid)
    result = store.one("SELECT * FROM imports WHERE id=?", (iid,))
    assert result["status"] == "done", result["error"]
    assert result["rows_read"] == 5 and result["valid_rows"] == 2 and result["groups_total"] == 1
    assert registry.calls == ["8.8.8.8"]
    assert json.loads(result["rejected"]) == {
        "below_critical": 1,
        "unknown_severity": 1,
        "outside_jurisdiction": 1,
    }
    entries = json.loads(store.one("SELECT payload FROM jobs WHERE import_id=?", (iid,))["payload"])
    assert (
        entries[1]["private_ip"] and entries[1]["normalized"]["eligibility"]["included_as_context"]
    )
    assert entries[1]["normalized"]["eligibility"]["severity"] == "low"
    assert store.path(result["path"]).read_bytes() == source
    assert (
        json.loads(result["config"])["profile_inventory"]["sha256"]
        == inventory_metadata()["sha256"]
    )


def test_product_associations_retain_fragments_and_original_observation():
    raw = "Apache/2.4.6 PHP/7.3.25 custom build note"
    products = products_from_version(raw, "service-one")
    assert products["raw_version"] == raw
    assert [(x["product"], x["version"]) for x in products["products"]] == [
        ("Apache", "2.4.6"),
        ("PHP", "7.3.25"),
    ]
    assert products["unresolved_fragments"] == ["custom build note"]
    assert all(x["service_ref"] == "service-one" for x in products["products"])
    assert products_from_version("7.3.25", "another")["unresolved_fragments"] == ["7.3.25"]
    source = SourceObservation("original.xlsx", "Sheet1", 8, row(tag="cve-2026-12345;eol-php"))
    normalized = observation_envelope(
        source,
        resolve_profile(source.fields, configured_type="scan_http_vulnerable"),
        notification_eligibility(
            source.fields,
            resolve_profile(source.fields, configured_type="scan_http_vulnerable"),
            {},
        ),
    )
    assert normalized["findings"][0]["id"] == "CVE-2026-12345"
    assert normalized["findings"][0]["service_ref"] == normalized["service"]["id"]
    assert source.fields["tag"] == "cve-2026-12345;eol-php"
