"""Finding evidence must survive Filter before enrichment or scoring."""

from tests.support.qualification import registry_factory, capture_website

import json

import pytest

from modules.accretion.tests.support.intake import Registry, report, row, seed
from modules.accretion.components import intake_filter
from modules.accretion.components.accretion import vet_cves
from modules.accretion.components.intake import EntryValidator, SourceObservation
from modules.accretion.components.intake import findings
from modules.accretion.components.intake_service import IntakeService
from modules.accretion.components.report_profiles import resolve_profile, supported_profiles
from modules.workspace.components.store import Store


def reason(*, profile="scan_http_vulnerable", **changes):
    fields = row(**changes)
    source = SourceObservation("source.csv", "CSV", 2, fields)
    return EntryValidator({"North Carolina"}).rejection_reason(
        source, profile=resolve_profile(fields, configured_type=profile)
    )


@pytest.mark.parametrize(
    "version",
    [
        "unknown",
        " UNKNOWN ",
        "N/A",
        "none",
        "null",
        "-",
        "?",
        "not disclosed",
        "not reported",
        "unspecified",
        "PHP/unknown",
        "PHP/N/A",
        "version=unavailable",
        False,
        float("nan"),
        {"version": "1.0"},
    ],
)
def test_placeholder_versions_cannot_establish_required_software_evidence(version):
    assert reason(tag="eol-php", version=version) == "placeholder_version"
    assert reason(tag="custom-vendor-condition", version=version) == "placeholder_version"


@pytest.mark.parametrize(
    "version",
    ["PHP/5.6.40", "10", "1.0-beta+build.7", "Exchange/2019-CU11", "bookworm", 1.2],
)
def test_version_formats_are_open_and_do_not_require_semver(version):
    assert reason(tag="eol-php", version=version) is None


@pytest.mark.parametrize(
    ("suffix", "expected"),
    [("bookworm", False), ("PHP/N/A", True), ("Release/2019-CU11", False), ("", True)],
)
def test_delimiter_heavy_versions_have_linear_normalization_work(monkeypatch, suffix, expected):
    value = "a/" * 25_000 + suffix
    original = findings._absent_text
    normalized_characters = 0

    def bounded_normalization(text):
        nonlocal normalized_characters
        normalized_characters += len(text)
        # A work budget catches repeated whole-suffix normalization without
        # relying on machine speed or waiting for a quadratic input to finish.
        assert normalized_characters <= 3 * len(value)
        return original(text)

    monkeypatch.setattr(findings, "_absent_text", bounded_normalization)
    assert findings.version_is_placeholder(value) is expected


@pytest.mark.parametrize(
    "tag",
    [
        "CVE-2026-",
        "CVE-2026-123",
        "CVE2026-12345",
        "CVE-2026-12345suffix",
        "prefixCVE-2026-12345",
        "prefix_CVE-2026-12345",
        "CVE-2026-12...",
        "CVE-26-12345",
        "CVE-202X-12345",
        "CVE-٢٠٢٦-١٢٣٤٥",
        "CVE-2026-12345;CVE-2026-12",
    ],
)
def test_banner_or_other_valid_cve_cannot_repair_malformed_identifier(tag):
    assert reason(tag=tag, version="ExampleServer/1.2.3") == "malformed_cve_identifier"


@pytest.mark.parametrize(
    "tag", ["unknown", "N/A", "null", "none", "-", "0", "lorem ipsum", "not a vulnerability", 0]
)
def test_severity_and_banner_do_not_rescue_nonfinding_tags(tag):
    assert reason(tag=tag, version="ExampleServer/1.2.3") == "unsupported_finding"


@pytest.mark.parametrize(
    "tag",
    [
        "never-seen-this-tag",
        "vendor_new_condition",
        "CVE-2099-12345",
        "CVE-2099-12345; cve-2026-1234567",
        "CVE-2099-12345 CVE-2026-1234567",
        "CVE-2099-12345 eol-php",
        "eol-php;vendor-condition",
    ],
)
def test_unknown_identifiers_and_valid_lists_remain_supported(tag):
    assert reason(tag=tag, version="PHP/5.6.40") is None


@pytest.mark.parametrize(
    "profile", [name for name in supported_profiles() if "http_vulnerable" not in name]
)
def test_reviewed_service_profiles_do_not_need_fabricated_versions(profile):
    assert reason(profile=profile, tag="source-reported-condition", version=None) is None
    assert reason(profile=profile, tag="source-reported-condition", version="unknown") is None


def test_cve_without_eol_can_qualify_without_optional_banner_evidence():
    assert reason(tag="CVE-2099-12345", version="unknown") is None
    assert reason(tag="CVE-2099-12345;eol-php", version="unknown") == "placeholder_version"


def bad_rows():
    return [
        row(tag="eol-php", version="not disclosed", severity="critical"),
        row(tag="CVE-2026-123", severity="critical"),
        row(tag="not a vulnerability", severity="critical"),
    ]


def test_junk_is_rejected_before_catalog_or_registry_lookup(tmp_path, monkeypatch):
    def unexpected_lookup(*args, **kwargs):
        raise AssertionError("Rejected rows must not reach local catalog vetting")

    def unexpected_registry():
        raise AssertionError("Rejected rows must not initialize registry qualification")

    monkeypatch.setattr(intake_filter, "vet_cves", unexpected_lookup)
    store = Store(tmp_path / "workspace")
    intake = IntakeService(
        store, attribution_factory=registry_factory(unexpected_registry), capture=capture_website
    )
    original = report(bad_rows())
    identifier = intake.enqueue("scan-http_vulnerable.csv", original)["id"]
    intake.process(identifier)
    result = store.one("SELECT * FROM imports WHERE id=?", (identifier,))
    assert result["status"] == "done", result["error"]
    assert result["valid_rows"] == 0 and result["groups_total"] == 0
    assert json.loads(result["rejected"]) == {
        "placeholder_version": 1,
        "malformed_cve_identifier": 1,
        "unsupported_finding": 1,
    }
    assert not store.all("SELECT * FROM jobs")
    assert store.path(result["path"]).read_bytes() == original


def test_qualified_same_host_cannot_rescue_junk_as_context(tmp_path, monkeypatch):
    store = Store(tmp_path / "workspace")
    seed(store.root)
    checked = []

    def capture(root, identifiers, **kwargs):
        checked.extend(identifiers)
        return vet_cves(root, identifiers, **kwargs)

    monkeypatch.setattr(intake_filter, "vet_cves", capture)
    intake = IntakeService(
        store, attribution_factory=registry_factory(Registry), capture=capture_website
    )
    identifier = intake.enqueue("scan-http_vulnerable.csv", report([row(), *bad_rows()]))["id"]
    intake.process(identifier)
    result = store.one("SELECT * FROM imports WHERE id=?", (identifier,))
    assert result["status"] == "done", result["error"]
    assert result["valid_rows"] == 1 and result["groups_total"] == 1
    assert checked == ["CVE-2026-12345"]
    payload = json.loads(
        store.one("SELECT payload FROM jobs WHERE import_id=?", (identifier,))["payload"]
    )
    assert len(payload) == 1
