"""Authenticated local API acquisition through the production app boundaries."""

import json
import threading

import pytest

from session_helpers import TestClient
from test_api_acquisition_098 import finished, catalog
from workbench.api import create_app
from workbench.shadowserver_reports import ReportDownloader, SignedTransport
from workbench.shadowserver_reports.demo import _Opener, _SyntheticService


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


def test_every_acquisition_route_requires_launcher_session(api_app):
    app, client, remote = api_app
    client.cookies.clear()
    for method, path, body in [
        ("GET", "status", None),
        ("PUT", "credentials", {}),
        ("DELETE", "credentials", None),
        ("POST", "connection", None),
        ("POST", "catalog", {}),
        ("POST", "import", {}),
        ("GET", "jobs/unknown", None),
        ("POST", "jobs/unknown/cancel", None),
    ]:
        response = client.request(method, "/api/shadowserver/" + path, json=body)
        assert response.status_code == 401, (path, response.text)
    assert remote.api_calls == remote.download_calls == 0
    assert app.state.api_acquisition.status()["configured"] is False


def test_credential_validation_never_echoes_rejected_inputs(api_app):
    app, client, remote = api_app
    private = "PRIVATE-CREDENTIAL-MARKER"
    for body in [
        {"api_key": private * 100, "secret": private},
        {"api_key": private, "secret": [private]},
        {"api_key": private, "secret": private, "unexpected": private},
        {"api_key": private},
    ]:
        response = client.put("/api/shadowserver/credentials", json=body)
        assert response.status_code == 422
        assert private not in response.text
    assert not app.state.api_acquisition.status()["configured"]
    assert remote.api_calls == 0


def test_mutations_require_csrf_and_same_origin(api_app):
    app, client, remote = api_app
    body = {"api_key": remote.credentials.api_key, "secret": remote.credentials.secret}
    token = client.headers.pop("X-Workbench-Token")
    assert client.put("/api/shadowserver/credentials", json=body).status_code == 403
    client.headers["X-Workbench-Token"] = token
    assert (
        client.put(
            "/api/shadowserver/credentials",
            json=body,
            headers={"Origin": "https://outside.example"},
        ).status_code
        == 403
    )
    assert not app.state.api_acquisition.status()["configured"]
    assert remote.api_calls == 0


def test_routes_connect_list_import_and_remove_credentials_without_exposing_secrets(api_app):
    app, client, remote = api_app
    acquisition = app.state.api_acquisition
    response = client.put(
        "/api/shadowserver/credentials",
        json={
            "api_key": remote.credentials.api_key,
            "secret": remote.credentials.secret,
        },
    )
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json()["configured"]
    job = client.post("/api/shadowserver/connection").json()
    assert finished(acquisition, job)["status"] == "completed"
    job = client.post(
        "/api/shadowserver/catalog",
        json={
            "start": "2026-11-06",
            "end": "2026-11-06",
            "subscription": "synthetic-example",
            "report_type": "scan_http_vulnerable",
        },
    ).json()
    assert finished(acquisition, job)["status"] == "completed"
    status = client.get("/api/shadowserver/status").json()
    assert status["reports"]
    assert (
        client.post("/api/shadowserver/import", json={"report_ids": ["wrong-id"]}).status_code
        == 422
    )
    response = client.post(
        "/api/shadowserver/import",
        json={
            "report_ids": [status["reports"][0]["id"]],
            "narrative_date_basis": "unconfirmed",
        },
    )
    assert response.status_code == 200, response.text
    result = finished(acquisition, response.json())
    assert result["status"] == "completed"
    public = json.dumps(status) + client.get("/api/shadowserver/jobs/" + result["id"]).text
    for secret in (
        remote.credentials.api_key,
        remote.credentials.secret,
        "SYNTHETIC-NONFUNCTIONAL-",
    ):
        assert secret not in public
    assert app.state.store.one("SELECT COUNT(*) n FROM imports")["n"] == 1
    assert client.delete("/api/shadowserver/credentials").json()["configured"] is False
    assert client.post("/api/shadowserver/connection").status_code == 400


def test_active_retrieval_blocks_workspace_replacement_and_cancels_through_route(api_app):
    app, client, remote = api_app
    acquisition = app.state.api_acquisition
    ids = catalog(acquisition, remote)
    started = threading.Event()

    class WaitingDownloader:
        def download_report(self, report, *, operation):
            started.set()
            operation.wait(5)
            raise AssertionError("Expected cancellation")

    acquisition.downloader_factory = lambda _root: WaitingDownloader()
    response = client.post("/api/shadowserver/import", json={"report_ids": ids})
    assert response.status_code == 200
    assert started.wait(2)
    job = response.json()
    assert client.post("/api/data/check").status_code == 422
    assert client.delete("/api/shadowserver/credentials").status_code == 422
    assert client.post("/api/shadowserver/jobs/" + job["id"] + "/cancel").status_code == 200
    assert finished(acquisition, job)["status"] == "cancelled"
    assert client.post("/api/data/check").status_code == 200
