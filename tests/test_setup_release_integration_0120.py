"""Cross-service setup acceptance through the real local application boundary."""

import json

from tests.session_helpers import TestClient
from modules.settings.tests.support.setup import SetupService as SyntheticReports
from modules.accretion.tests.support.api_acquisition import finished
from modules.workspace.components.api import create_app
from modules.accretion.components.shadowserver_reports import SignedTransport
from modules.accretion.components.shadowserver_reports.demo import _Opener


def make_app(workspace, remote):
    return create_app(
        workspace,
        worker=False,
        report_processes=False,
        api_transport_factory=lambda provider: SignedTransport(
            provider, backend=_Opener(remote.api_open)
        ),
    )


def test_setup_and_update_routes_keep_the_existing_local_session_boundary(tmp_path):
    remote = SyntheticReports()
    app = make_app(tmp_path / "data", remote)
    routes = [
        ("GET", "/api/setup", None),
        ("PUT", "/api/setup/profile", {}),
        ("PUT", "/api/setup/progress", {"step": "connections", "mode": "manual"}),
        ("POST", "/api/setup/complete", None),
        ("GET", "/api/software/status", None),
        ("POST", "/api/software/check", None),
        ("POST", "/api/software/download", None),
        ("POST", "/api/software/install", None),
        ("GET", "/api/software/whats-new", None),
        ("POST", "/api/software/whats-new/seen", {"version": "0.12.0"}),
    ]
    with TestClient(app) as client:
        csrf = client.headers.pop("X-Workbench-Token")
        for method, url, body in routes:
            if method != "GET":
                assert client.request(method, url, json=body).status_code == 403, url
        client.headers["X-Workbench-Token"] = csrf
        for method, url, body in routes:
            if method != "GET":
                assert (
                    client.request(
                        method, url, json=body, headers={"Origin": "https://outside.example"}
                    ).status_code
                    == 403
                ), url
        client.cookies.clear()
        for method, url, body in routes:
            assert client.request(method, url, json=body).status_code == 401, url
    assert remote.api_calls == 0


def test_manual_setup_to_scoped_automation_and_restart_preserves_only_safe_state(tmp_path):
    workspace = tmp_path / "data"
    remote = SyntheticReports()
    app = make_app(workspace, remote)
    with TestClient(app) as client:
        assert client.get("/api/setup").json()["required"] is True
        assert client.post("/api/setup/complete").status_code >= 400
        assert (
            client.put(
                "/api/settings", json={"regions": ["North Carolina"], "sheet": "Custom sheet"}
            ).status_code
            == 200
        )
        assert (
            client.put(
                "/api/setup/progress", json={"step": "connections", "mode": "manual"}
            ).status_code
            == 200
        )
        profile = {
            "analyst_name": "Synthetic Setup Analyst",
            "analyst_title": "",
            "agency": "United States Secret Service",
            "department": "U.S. Department of Homeland Security",
            "office": "Charlotte, North Carolina",
            "email": "",
            "display_timezone": "America/New_York",
            "regions": ["North Carolina"],
        }
        saved = client.put("/api/setup/profile", json=profile)
        assert saved.status_code == 200, saved.text
        assert saved.json()["settings"]["sheet"] == "Custom sheet"
        assert (
            client.put(
                "/api/setup/progress", json={"step": "automation", "mode": "manual"}
            ).status_code
            == 200
        )
        complete = client.post("/api/setup/complete").json()
        assert complete["completed"] is True and complete["required"] is False

        credentials = {
            "api_key": remote.credentials.api_key,
            "secret": remote.credentials.secret,
            "remember": False,
        }
        assert client.put("/api/shadowserver/credentials", json=credentials).status_code == 200
        job = client.post("/api/shadowserver/connection").json()
        assert finished(app.state.api_acquisition, job)["status"] == "completed"
        status = client.get("/api/shadowserver/status").json()
        assert set(status["subscriptions"]) == {"US-NC", "united-states", "agency-custom"}
        assert status["selection_defaults"]["subscription"] == "US-NC"
        config = {
            "enabled": True,
            "shadowserver": True,
            "reference": False,
            "subscription": "US-NC",
            "report_types": ["scan_http_vulnerable"],
            "hour": 6,
            "minute": 0,
            "interval_hours": 4,
            "lookback_days": 7,
        }
        response = client.put("/api/schedule", json=config)
        assert response.status_code == 200, response.text
        assert (
            client.put(
                "/api/setup/progress", json={"step": "connections", "mode": "configured"}
            ).status_code
            == 200
        )
        assert (
            client.put(
                "/api/setup/progress", json={"step": "automation", "mode": "configured"}
            ).status_code
            == 200
        )

        # Profile and schedule are different settings records. Changing the former
        # must invalidate old choices throughout all acquisition entry points.
        response = client.put("/api/setup/profile", json={**profile, "regions": ["South Carolina"]})
        assert response.status_code == 200, response.text
        status = client.get("/api/shadowserver/status").json()
        assert set(status["subscriptions"]) == {"US-SC", "united-states", "agency-custom"}
        assert status["selection_defaults"]["subscription"] == "US-SC"
        assert status["schedule"]["scope_error"]
        assert client.post("/api/schedule/run").status_code >= 400
        assert (
            client.post(
                "/api/shadowserver/catalog",
                json={
                    "start": "2026-11-06",
                    "end": "2026-11-06",
                    "subscription": "US-NC",
                    "report_type": "scan_http_vulnerable",
                },
            ).status_code
            >= 400
        )
        response = client.put("/api/schedule", json={**config, "subscription": "US-SC"})
        assert response.status_code == 200, response.text
        assert not response.json()["scope_error"]
        notes = client.get("/api/software/whats-new").json()
        assert (
            client.post(
                "/api/software/whats-new/seen", json={"version": notes["version"]}
            ).status_code
            == 200
        )
        public = (
            json.dumps(status) + client.get("/api/setup").text + client.get("/api/bootstrap").text
        )
        profile_rows = json.dumps(app.state.store.all("SELECT * FROM settings"))
        for secret in (remote.credentials.api_key, remote.credentials.secret):
            assert secret not in public and secret not in profile_rows

    # Fresh process services must not inherit session-only API keys. Durable
    # identity, schedule configuration and presented release notes must survive.
    restarted = make_app(workspace, remote)
    with TestClient(restarted) as client:
        setup = client.get("/api/setup").json()
        assert setup["completed"] and not setup["required"]
        assert setup["profile"]["regions"] == ["South Carolina"]
        assert setup["profile"]["analyst_title"] == ""
        assert not client.get("/api/shadowserver/status").json()["configured"]
        assert client.get("/api/schedule").json()["config"]["subscription"] == "US-SC"
        assert client.get("/api/software/whats-new").json()["should_show"] is False
