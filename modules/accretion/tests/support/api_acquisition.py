"""Reusable synthetic api acquisition fixtures and builders."""

from tests.support.qualification import capture_website

import time

import pytest

from modules.accretion.components.api_acquisition import APIAcquisition
from modules.accretion.components.intake_service import IntakeService
from modules.accretion.components.shadowserver_reports import ReportDownloader, SignedTransport
from modules.accretion.components.shadowserver_reports.demo import _Opener, _SyntheticService
from modules.workspace.components.api import create_app
from modules.workspace.components.store import Store
from tests.session_helpers import TestClient


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
    intake = IntakeService(store, capture=capture_website)
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


@pytest.fixture
def api_app(tmp_path):
    remote = _SyntheticService()
    app = create_app(
        tmp_path / "workspace",
        worker=False,
        api_transport_factory=lambda provider: SignedTransport(
            provider, backend=_Opener(remote.api_open)
        ),
        api_downloader_factory=lambda root: ReportDownloader(
            root, opener=_Opener(remote.download_open)
        ),
    )
    with TestClient(app) as client:
        yield app, client, remote
