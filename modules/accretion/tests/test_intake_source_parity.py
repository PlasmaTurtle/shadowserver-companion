"""Deliver the same fictional observations through each production acquisition channel."""

from datetime import datetime, timezone
import hashlib
import io
import json

from openpyxl import Workbook
import pytest

from modules.accretion.components.api_import import enqueue_download
from modules.accretion.components.scheduling import AcquisitionSchedule, DEFAULTS
from modules.accretion.components.shadowserver_reports import ReportDownloader
from modules.accretion.components.shadowserver_reports.demo import _Opener, _Response
from modules.accretion.tests.support.api_acquisition import acquisition, catalog, finished
from modules.accretion.tests.support.intake_acquisition import receipt
from modules.accretion.tests.support.intake_profiles import csv_bytes, row
from modules.library.components.cve_catalog.storage import CatalogStorage
from tests.support.qualification import registry_factory
from tests.support.workbench import FakeRegistry


def observations():
    accepted = row(timestamp="2026-11-06 04:00:00", protocol="tcp", port="443")
    return [accepted, {**accepted, "hostname": "bad.example.com", "region": "Virginia"}]


def workbook_bytes(rows):
    source = io.BytesIO()
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Observations"
    sheet.append(list(rows[0]))
    for record in rows:
        sheet.append(list(record.values()))
    workbook.save(source)
    workbook.close()
    return source.getvalue()


@pytest.mark.parametrize("channel", ["workbook", "manual_api", "scheduled_api"])
def test_channel_reaches_same_qualified_lead(acquisition, channel):
    service, remote, store = acquisition
    registry = FakeRegistry()
    service.intake.attribution_factory = registry_factory(lambda: registry)
    rows = observations()
    if channel == "workbook":
        result = service.intake.enqueue("scan_http_vulnerable.xlsx", workbook_bytes(rows))
        import_id = result["id"]
    else:
        content = csv_bytes(rows)
        service.downloader_factory = lambda root: ReportDownloader(
            root, opener=_Opener(lambda request, timeout: _Response(content, "text/csv"))
        )
        if channel == "manual_api":
            ids = catalog(service, remote)
            run = finished(service, service.start("import", report_ids=ids))
            assert run["status"] == "completed", run
            import_id = run["results"][0]["import_id"]
        else:
            service.configure(remote.credentials.api_key, remote.credentials.secret)
            schedule = AcquisitionSchedule(
                store,
                service,
                CatalogStorage(store.root),
                clock=lambda: datetime(2026, 11, 6, 7, tzinfo=timezone.utc),
            )
            schedule.configure(
                {
                    **DEFAULTS,
                    "enabled": True,
                    "reference": False,
                    "subscription": "synthetic-example",
                    "report_types": ["scan_http_vulnerable"],
                }
            )
            schedule.tick()
            [import_id] = schedule.status()["run"]["imports"]
    service.intake.process(import_id)
    if channel == "scheduled_api":
        schedule.tick()
        assert schedule.status()["run"]["status"] == "complete"
        schedule.close()
    saved = store.one("SELECT * FROM imports WHERE id=?", (import_id,))
    assert saved["status"] == "done", saved["error"]
    assert (saved["rows_read"], saved["valid_rows"], saved["groups_total"], saved["qualified"]) == (
        2,
        1,
        1,
        1,
    )
    assert json.loads(saved["rejected"]) == {"outside_jurisdiction": 1}
    assert store.all("SELECT root_domain FROM domain_groups") == [{"root_domain": "example.com"}]
    assert store.one("SELECT count(*) AS n FROM lead_queue WHERE status='pending'")["n"] == 1
    assert registry.calls == ["8.8.8.8"]
    assert store.one("SELECT count(*) AS n FROM awareness_findings")["n"] == 1


def test_duplicate_receipt_arriving_during_filter_is_retained(acquisition, monkeypatch, tmp_path):
    from modules.accretion.components import intake_service

    service, _, store = acquisition
    registry = FakeRegistry()
    service.intake.attribution_factory = registry_factory(lambda: registry)
    content = csv_bytes(observations())
    name = "scan_http_vulnerable.csv"
    path = tmp_path / name
    path.write_bytes(content)
    first = service.intake.enqueue(name, content)
    original_filter = intake_service.filter_report
    proof = receipt(content, name=name)

    def also_deliver_receipt(*args, **kwargs):
        result = enqueue_download(service.intake, path, proof)
        assert result["duplicate"] and result["id"] == first["id"]
        return original_filter(*args, **kwargs)

    monkeypatch.setattr(intake_service, "filter_report", also_deliver_receipt)
    service.intake.process(first["id"])
    saved = store.one("SELECT * FROM imports WHERE id=?", (first["id"],))
    assert saved["status"] == "done", saved["error"]
    assert saved["qualified"] == 1
    config = json.loads(saved["config"])
    assert config["acquisition"]["kind"] == "manual_file"
    assert [r["receipt"]["logical_id"] for r in config["acquisition_receipts"]] == [
        proof["logical_id"]
    ]
    assert store.one("SELECT count(*) n FROM imports")["n"] == 1
    assert store.one("SELECT count(*) n FROM lead_queue")["n"] == 1
    assert store.one("SELECT count(*) n FROM domain_groups")["n"] == 1
    assert registry.calls == ["8.8.8.8"]


def test_csv_and_workbook_preserve_both_sources_and_one_review(acquisition):
    service, _, store = acquisition
    service.intake.attribution_factory = registry_factory(FakeRegistry)
    rows = observations()
    for name, content in [
        ("scan_http_vulnerable.csv", csv_bytes(rows)),
        ("scan_http_vulnerable.xlsx", workbook_bytes(rows)),
    ]:
        source = service.intake.enqueue(name, content)
        assert not source["duplicate"]
        service.intake.process(source["id"])
        imported = store.one("SELECT status,path FROM imports WHERE id=?", (source["id"],))
        assert imported["status"] == "done"
        assert store.path(imported["path"]).read_bytes() == content
    assert store.one("SELECT count(*) n FROM domain_groups")["n"] == 1
    assert (
        store.one("SELECT count(*) n FROM lead_queue WHERE status='pending' AND superseded_by=''")[
            "n"
        ]
        == 1
    )
    assert store.one("SELECT count(*) n FROM awareness_findings")["n"] == 1


@pytest.mark.parametrize("legacy_kind", ["manual_file", "shadowserver_api_receipt"])
def test_version_14_source_identity_survives_upgrade(acquisition, legacy_kind, tmp_path):
    from modules.accretion.components.report_profiles import PROFILE_VERSION
    from modules.workspace.components.primitives import dump

    service, _, store = acquisition
    content = csv_bytes(observations())
    name = "scan_http_vulnerable.csv"
    if legacy_kind == "manual_file":
        added = service.intake.enqueue(name, content)
    else:
        path = tmp_path / name
        path.write_bytes(content)
        added = enqueue_download(service.intake, path, receipt(content, name=name))
    config = json.loads(
        store.one("SELECT config FROM imports WHERE id=?", (added["id"],))["config"]
    )
    if legacy_kind == "shadowserver_api_receipt":
        config["report_type"] = config["acquisition"]["receipt"]["report_type"]
    previous_policy = {
        "regions": sorted(config["regions"]),
        "sheet": config["sheet"],
        "version": 14,
        "accretion_policy": config["accretion_policy"],
        "critical_only": config["critical_only"],
        "outreach_mode": config["outreach_mode"],
        "targeted_reason": config["targeted_reason"],
        "report_type": config["report_type"],
        "profile_version": PROFILE_VERSION,
        "catalog_revision": {
            k: config["catalog_at_import"].get(k)
            for k in ("total", "bootstrap_complete", "last_success_at")
        },
        "filename_profile": "scan_http_vulnerable",
        "acquisition_kind": legacy_kind,
    }
    previous = hashlib.sha256(
        (hashlib.sha256(content).hexdigest() + dump(previous_policy)).encode()
    ).hexdigest()
    with store.transaction() as db:
        db.execute(
            "UPDATE imports SET fingerprint=?,config=? WHERE id=?",
            (previous, dump(config), added["id"]),
        )
    repeated = service.intake.enqueue(name, content)
    assert repeated["id"] == added["id"] and repeated["duplicate"]
    replay = service.intake.reevaluate(added["id"])
    assert replay["id"] != added["id"] and not replay["duplicate"]
    assert service.intake.enqueue(name, content)["id"] == replay["id"]
