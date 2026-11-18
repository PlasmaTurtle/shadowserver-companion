"""Exercise real signing/download/intake with a synthetic service and no account."""

from hashlib import sha256
from dataclasses import replace
import difflib
import json
from pathlib import Path
from types import SimpleNamespace
import threading
import time

import pytest

from workbench.api_acquisition import APIAcquisition
from workbench.intake_service import IntakeService
from workbench.store import Store
from workbench.shadowserver_reports import ReportDownloader, SignedTransport
from workbench.shadowserver_reports.demo import _Opener, _SyntheticService, _Response
from workbench.shadowserver_reports.errors import ConfigurationError, DownloadError


def finished(service, job):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = service.get(job["id"])
        if result["status"] not in {"queued", "running"}:
            return result
        time.sleep(0.01)
    raise AssertionError("Synthetic operation did not finish")


@pytest.fixture
def acquisition(tmp_path):
    store = Store(tmp_path / "workspace")
    intake = IntakeService(store)
    remote = _SyntheticService()
    service = APIAcquisition(
        store,
        intake,
        transport_factory=lambda provider: SignedTransport(
            provider, backend=_Opener(remote.api_open)
        ),
        downloader_factory=lambda root: ReportDownloader(
            root, opener=_Opener(remote.download_open)
        ),
    )
    yield service, remote, store
    service.close()
    intake.close()


def connected(service, remote):
    service.configure(remote.credentials.api_key, remote.credentials.secret)
    result = finished(service, service.start("connection"))
    assert result["status"] == "completed"


def catalog(service, remote):
    connected(service, remote)
    result = finished(
        service,
        service.start(
            "catalog",
            selection={
                "start": "2026-11-06",
                "end": "2026-11-06",
                "subscription": "synthetic-example",
                "report_type": "scan_http_vulnerable",
            },
        ),
    )
    assert result["status"] == "completed"
    return [r["id"] for r in service.status()["reports"]]


def test_unconfigured_is_explicit_and_never_calls_service(acquisition):
    service, remote, _ = acquisition
    assert service.status()["configured"] is False
    with pytest.raises(ConfigurationError):
        service.start("connection")
    assert remote.api_calls == 0


def test_original_report_import_is_idempotent_and_receipted(acquisition):
    service, remote, store = acquisition
    ids = catalog(service, remote)
    first = finished(service, service.start("import", report_ids=ids))
    assert first["status"] == "completed"
    row = store.one("SELECT * FROM imports")
    raw = store.path(row["path"]).read_bytes()
    assert sha256(raw).hexdigest() == first["results"][0]["sha256"]
    config = json.loads(row["config"])
    assert "narrative_date_basis" not in config["acquisition"]
    assert config["acquisition"]["receipt"]["report_date"] == "2026-11-06"
    assert "path" not in config["acquisition"]["receipt"]
    assert store.one("SELECT COUNT(*) n FROM cases")["n"] == 0
    second = finished(service, service.start("import", report_ids=ids))
    assert second["results"][0]["duplicate"]
    assert store.one("SELECT COUNT(*) n FROM imports")["n"] == 1
    assert (
        len(json.loads(store.one("SELECT config FROM imports")["config"])["acquisition_receipts"])
        == 2
    )


def test_public_state_has_no_credentials_or_download_capability(acquisition):
    service, remote, store = acquisition
    ids = catalog(service, remote)
    finished(service, service.start("import", report_ids=ids))
    public = json.dumps(service.status()) + json.dumps(store.all("SELECT * FROM imports"))
    for secret in [
        remote.credentials.api_key,
        remote.credentials.secret,
        "SYNTHETIC-NONFUNCTIONAL-",
        "demo-only",
    ]:
        assert secret not in public
        assert secret.encode() not in (store.root / "workbench.sqlite3").read_bytes()


def test_reconfiguration_invalidates_old_selection(acquisition):
    service, remote, _ = acquisition
    ids = catalog(service, remote)
    service.configure("new-synthetic-key", "new-synthetic-secret")
    assert not service.status()["connected"]
    assert not service.status()["reports"]
    with pytest.raises(ValueError, match="expired"):
        service.start("import", report_ids=ids)
    service.forget()
    assert not service.status()["configured"]


def test_bad_csv_is_not_imported(acquisition):
    service, remote, store = acquisition
    ids = catalog(service, remote)
    service.downloader_factory = lambda root: ReportDownloader(
        root, opener=_Opener(lambda *_args, **_kw: _Response(b"<html>error</html>", "text/html"))
    )
    job = finished(service, service.start("import", report_ids=ids))
    assert job["status"] == "failed"
    assert job["error_code"] == "download_error"
    assert store.one("SELECT COUNT(*) n FROM imports")["n"] == 0


def test_csv_attachment_labeled_html_reaches_intake_unchanged(acquisition):
    service, remote, store = acquisition
    ids = catalog(service, remote)
    downloaded = []

    def mislabeled_response(request, timeout):
        response = remote.download_open(request, timeout)
        response.headers["Content-Type"] = "text/html; charset=UTF-8"
        response.headers["Content-Disposition"] = 'attachment; filename="report.csv"'
        downloaded.append(response.getvalue())
        return response

    service.downloader_factory = lambda root: ReportDownloader(
        root, opener=_Opener(mislabeled_response)
    )
    job = finished(service, service.start("import", report_ids=ids))
    assert job["status"] == "completed"
    row = store.one("SELECT * FROM imports")
    assert store.path(row["path"]).read_bytes() == downloaded[0]
    assert job["results"][0]["sha256"] == sha256(downloaded[0]).hexdigest()
    assert store.one("SELECT COUNT(*) n FROM imports")["n"] == 1
    assert store.one("SELECT COUNT(*) n FROM cases")["n"] == 0


def test_cancellation_keeps_completed_imports_and_allows_retry(acquisition):
    service, remote, store = acquisition
    ids = catalog(service, remote)
    started = threading.Event()

    class WaitingDownloader:
        def download_report(self, report, *, operation):
            started.set()
            operation.wait(5)
            raise AssertionError("Expected cancellation")

    service.downloader_factory = lambda _root: WaitingDownloader()
    job = service.start("import", report_ids=ids)
    assert started.wait(2)
    with pytest.raises(ValueError, match="current API"):
        service.forget()
    service.cancel(job["id"])
    result = finished(service, job)
    assert result["status"] == "cancelled"
    assert store.one("SELECT COUNT(*) n FROM imports")["n"] == 0
    service.downloader_factory = lambda root: ReportDownloader(
        root, opener=_Opener(remote.download_open)
    )
    assert finished(service, service.start("import", report_ids=ids))["status"] == "completed"


def test_legacy_next_day_parameter_does_not_enter_intake(acquisition):
    service, remote, store = acquisition
    ids = catalog(service, remote)
    result = finished(
        service,
        service.start("import", report_ids=ids, narrative_date_basis="emailed_row_plus_one"),
    )
    assert result["status"] == "completed"
    assert (
        "narrative_date_basis"
        not in json.loads(store.one("SELECT config FROM imports")["config"])["acquisition"]
    )


def test_unexpected_exception_does_not_leak_secret(acquisition):
    service, remote, _ = acquisition
    ids = catalog(service, remote)

    class BrokenDownloader:
        def download_report(self, report, *, operation):
            raise RuntimeError(remote.credentials.secret)

    service.downloader_factory = lambda _root: BrokenDownloader()
    job = finished(service, service.start("import", report_ids=ids))
    assert job["status"] == "failed"
    assert remote.credentials.secret not in json.dumps(job)


def test_selection_bounds_and_maintenance_gate(acquisition):
    service, remote, store = acquisition
    connected(service, remote)
    with pytest.raises(ValueError, match="31 days"):
        service.start(
            "catalog",
            selection={
                "start": "2026-01-01",
                "end": "2026-03-01",
                "subscription": "synthetic-example",
                "report_type": "scan_http_vulnerable",
            },
        )
    store.maintenance = threading.Event()
    store.maintenance.set()
    with pytest.raises(ValueError, match="workspace data"):
        service.start("connection")


def test_vendored_module_matches_local_manifest_and_preserved_baseline():
    root = Path(__file__).resolve().parents[1]
    folder = root / "components/shadowserver_api"
    manifest = json.loads((folder / "source-manifest.json").read_text())
    for name, digest in manifest["files"].items():
        assert sha256((root / manifest["location"] / name).read_bytes()).hexdigest() == digest
    baseline_bytes = (folder / manifest["baseline"]["manifest"]).read_bytes()
    assert sha256(baseline_bytes).hexdigest() == manifest["baseline"]["manifest_sha256"]
    baseline = json.loads(baseline_bytes)
    assert baseline["source_version"] == manifest["baseline"]["version"] == "0.1.1"
    assert manifest["source_version"] == "0.1.2" and manifest["base_source_version"] == "0.1.0"
    patched = set()
    for patch in manifest["local_patches"]:
        name = patch["file"]
        assert name not in patched
        patched.add(name)
        before = (folder / patch["baseline_file"]).read_bytes()
        after = (root / manifest["location"] / name).read_bytes()
        assert sha256(before).hexdigest() == patch["baseline_sha256"] == baseline["files"][name]
        assert sha256(after).hexdigest() == patch["patched_sha256"] == manifest["files"][name]
        recorded = (folder / patch["patch_file"]).read_bytes()
        assert sha256(recorded).hexdigest() == patch["patch_sha256"]
        expected = "".join(
            difflib.unified_diff(
                before.decode().splitlines(keepends=True),
                after.decode().splitlines(keepends=True),
                fromfile="baseline-0.1.1/" + name,
                tofile=manifest["location"] + "/" + name,
            )
        ).encode()
        assert recorded == expected
    assert {
        name for name, digest in manifest["files"].items() if digest != baseline["files"][name]
    } == patched


def test_failed_catalog_refresh_discards_previous_report_selection(acquisition):
    service, remote, _ = acquisition
    old_ids = catalog(service, remote)
    service.transport_factory = lambda provider: SignedTransport(
        provider, backend=_Opener(lambda *_a, **_kw: _Response(b"{}", "application/json"))
    )
    job = finished(
        service,
        service.start(
            "catalog",
            selection={
                "start": "2026-11-05",
                "end": "2026-11-05",
                "subscription": "synthetic-example",
                "report_type": "scan_http_vulnerable",
            },
        ),
    )
    assert job["status"] == "failed"
    assert service.status()["reports"] == []
    assert service.status()["completeness"] is None
    with pytest.raises(ValueError, match="expired"):
        service.start("import", report_ids=old_ids)


@pytest.mark.parametrize("cancel_second", [False, True])
def test_partial_batch_preserves_completed_receipts(acquisition, cancel_second):
    service, remote, store = acquisition
    ids = catalog(service, remote)
    first = service.catalog[ids[0]]
    second = replace(first, filename="2026-11-06-second-example.csv")
    service.catalog["second-report"] = second
    reached_second = threading.Event()

    class PartialDownloader:
        def __init__(self, root):
            self.real = ReportDownloader(root, opener=_Opener(remote.download_open))

        def download_report(self, report, *, operation):
            if report == second:
                reached_second.set()
                if cancel_second:
                    operation.wait(5)
                raise DownloadError("Synthetic second-report failure.")
            return self.real.download_report(report, operation=operation)

    service.downloader_factory = PartialDownloader
    pending = service.start("import", report_ids=[*ids, "second-report"])
    assert reached_second.wait(2)
    if cancel_second:
        service.cancel(pending["id"])
    job = finished(service, pending)
    assert job["status"] == ("cancelled" if cancel_second else "partial")
    assert job["completed"] == 1 and job["total"] == 2
    assert len(job["results"]) == 1
    assert store.one("SELECT COUNT(*) n FROM imports")["n"] == 1
    saved = store.one("SELECT * FROM imports WHERE id=?", (job["results"][0]["import_id"],))
    assert sha256(store.path(saved["path"]).read_bytes()).hexdigest() == job["results"][0]["sha256"]


def test_close_drains_cancelled_producer_and_clears_session_state(acquisition):
    service, remote, store = acquisition
    ids = catalog(service, remote)
    started = threading.Event()

    class WaitingDownloader:
        def download_report(self, report, *, operation):
            started.set()
            operation.wait(5)
            raise AssertionError("Shutdown must cancel the download")

    service.downloader_factory = lambda _root: WaitingDownloader()
    job = service.start("import", report_ids=ids)
    assert started.wait(2)
    service.close()
    assert service.get(job["id"])["status"] == "cancelled"
    assert not service.busy()
    assert not service.status()["configured"]
    assert not service.status()["connected"]
    assert service.status()["reports"] == []
    assert store.one("SELECT COUNT(*) n FROM imports")["n"] == 0
    with pytest.raises(ValueError, match="closing"):
        service.start("connection")


def test_native_storage_is_explicit_and_session_replacement_removes_old_account(
    acquisition, monkeypatch
):
    import workbench.api_acquisition as module

    service, remote, store = acquisition

    class NativeStore:
        value = None

        def store(self, credentials):
            self.value = credentials

        def delete(self):
            self.value = None

        def __call__(self):
            if self.value is None:
                raise ConfigurationError("No saved account.")
            return self.value

    native = NativeStore()
    service.windows = native
    monkeypatch.setattr(module, "os", SimpleNamespace(name="nt"))
    saved = service.configure(remote.credentials.api_key, remote.credentials.secret, remember=True)
    assert saved["storage"] == "windows" and native.value is not None
    assert service.session_credentials is None
    session = service.configure("session-key", "session-secret", remember=False)
    assert session["storage"] == "session" and native.value is None
    service.forget()
    assert not service.status()["configured"]
    raw = (store.root / "workbench.sqlite3").read_bytes()
    assert b"session-secret" not in raw and remote.credentials.secret.encode() not in raw


def test_catalog_limit_remains_explicitly_partial(acquisition, monkeypatch):
    from workbench.shadowserver_reports.models import CatalogResult

    service, remote, _ = acquisition
    ids = catalog(service, remote)
    report = service.catalog[ids[0]]
    monkeypatch.setattr(
        "workbench.api_acquisition.ReportsClient.list_reports",
        lambda *_a, **_kw: CatalogResult((report,), "partial", ("catalog_response_at_limit",)),
    )
    result = finished(
        service,
        service.start(
            "catalog",
            selection={
                "start": "2026-11-06",
                "end": "2026-11-06",
                "subscription": "synthetic-example",
                "report_type": "scan_http_vulnerable",
            },
        ),
    )
    assert "incomplete" in result["message"]
    assert service.status()["completeness"] == "partial"
    assert service.status()["reasons"] == ["catalog_response_at_limit"]
    assert len(service.status()["reports"]) == 1
