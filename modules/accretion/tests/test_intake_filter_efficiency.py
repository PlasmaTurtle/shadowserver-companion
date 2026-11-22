"""Filter decisions stay bounded without changing admission policy."""

from tests.support.qualification import registry_factory, capture_website

from collections import Counter
import json

from modules.accretion.components import intake_service
from modules.accretion.components import report_profiles
from modules.accretion.components import intake_filter as filtering
from modules.accretion.components.intake import EntryValidator
from modules.accretion.components.intake_service import IntakeService
from modules.accretion.tests.support.intake import Registry, report, row
from modules.workspace.components.store import Store


def critical_row(**changes):
    return row(tag="eol-php", version="PHP/7.3.25", severity="critical", **changes)


def saved_import(store, identifier):
    saved = store.one("SELECT * FROM imports WHERE id=?", (identifier,))
    assert saved["status"] == "done", saved["error"]
    return saved


def test_filter_evaluates_each_supported_row_once_and_preserves_reasons(tmp_path, monkeypatch):
    store = Store(tmp_path / "workspace")
    registry = Registry()
    intake = IntakeService(
        store, attribution_factory=registry_factory(lambda: registry), capture=capture_website
    )
    decisions = Counter()
    original = EntryValidator.rejection_reason

    def decide(self, entry, **kwargs):
        decisions[entry.row] += 1
        return original(self, entry, **kwargs)

    monkeypatch.setattr(EntryValidator, "rejection_reason", decide)
    rows = [
        critical_row(),
        critical_row(region="Virginia"),
        {**critical_row(), "version": ""},
        critical_row(ip="invalid"),
    ]
    source = report(rows)
    identifier = intake.enqueue("scan_http_vulnerable.csv", source)["id"]
    intake.process(identifier)
    saved = saved_import(store, identifier)
    assert decisions == {2: 1, 3: 1, 4: 1, 5: 1}
    assert json.loads(saved["rejected"]) == {
        "outside_jurisdiction": 1,
        "missing_version": 1,
        "invalid_ip": 1,
    }
    assert saved["valid_rows"] == 1
    assert registry.calls == ["8.8.8.8"]
    assert store.path(saved["path"]).read_bytes() == source
    assert store.dark_matter.query(include_promoted=True)["total"] == 4
    assert json.loads(saved["config"])["intake_stats"]["accretion"]["discarded_rows"] == 0
    assert not store.all("SELECT * FROM lead_queue")


def test_filename_identity_is_reused_without_caching_row_schema_or_explicit_choice(monkeypatch):
    report_profiles._filename_profile.cache_clear()
    original = report_profiles.re.search
    searches = []

    def search(pattern, *args, **kwargs):
        searches.append(pattern)
        return original(pattern, *args, **kwargs)

    monkeypatch.setattr(report_profiles.re, "search", search)
    first = report_profiles.resolve_profile(critical_row(), "scan_http_vulnerable.csv")
    first_searches = len(searches)
    assert first_searches > 0
    for _ in range(20):
        changed = report_profiles.resolve_profile(
            {"hostname": "mail.example.com", "extra_column": "untouched"},
            "SCAN_HTTP_VULNERABLE.CSV",
        )
        assert changed["id"] == first["id"]
        assert changed["schema_observation"]["missing_notification_columns"] == [
            "ip",
            "region",
            "tag",
        ]
        assert "extra_column" in changed["schema_observation"]["unknown_columns"]
    assert len(searches) == first_searches
    assert first["schema_observation"]["missing_notification_columns"] == []
    explicit = report_profiles.resolve_profile(
        critical_row(report_type="scan_rdp"), "scan_http_vulnerable.csv"
    )
    configured = report_profiles.resolve_profile(
        critical_row(report_type="scan_rdp"), "scan_http_vulnerable.csv", "scan_mongodb"
    )
    assert (explicit["id"], explicit["selection_basis"]) == ("scan_rdp", "reported")
    assert (configured["id"], configured["selection_basis"]) == ("scan_mongodb", "configured")


def test_retry_empty_funnel_skips_completed_filter(tmp_path, monkeypatch):
    store = Store(tmp_path / "workspace")
    intake = IntakeService(
        store, attribution_factory=registry_factory(Registry), capture=capture_website
    )
    source = report([{**critical_row(), "severity": "high"}])
    identifier = intake.enqueue("scan_http_vulnerable.csv", source)["id"]
    reads = []
    original = filtering.read_entries

    def read(*args, **kwargs):
        reads.append(args[0])
        return original(*args, **kwargs)

    monkeypatch.setattr(filtering, "read_entries", read)
    intake.process(identifier)
    first = saved_import(store, identifier)
    retained = store.dark_matter.query(include_promoted=True)
    intake.retry(identifier)
    intake.process(identifier)
    second = saved_import(store, identifier)
    assert len(reads) == 1
    assert second["valid_rows"] == 0 and second["rejected"] == first["rejected"]
    assert store.dark_matter.query(include_promoted=True) == retained
    assert store.path(second["path"]).read_bytes() == source
    assert not store.all("SELECT * FROM jobs")


def test_failed_filter_commit_is_retried_instead_of_treated_as_complete(tmp_path, monkeypatch):
    store = Store(tmp_path / "workspace")
    intake = IntakeService(
        store, attribution_factory=registry_factory(Registry), capture=capture_website
    )
    identifier = intake.enqueue(
        "scan_http_vulnerable.csv", report([{**critical_row(), "severity": "high"}])
    )["id"]

    def fail(*args, **kwargs):
        raise RuntimeError("Synthetic interruption during raw observation retention")

    with monkeypatch.context() as patch:
        patch.setattr(intake_service, "enqueue_prepared", fail)
        intake.process(identifier)
    failed = store.one("SELECT * FROM imports WHERE id=?", (identifier,))
    assert failed["status"] == "error"
    assert not json.loads(failed["config"])["intake_progress"].get("filter_complete")
    assert store.dark_matter.query(include_promoted=True)["total"] == 0
    intake.retry(identifier)
    intake.process(identifier)
    saved_import(store, identifier)
    assert store.dark_matter.query(include_promoted=True)["total"] == 1
