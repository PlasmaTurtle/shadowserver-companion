"""Exercise real local-session boundaries without an implicit test login."""

import json
import os
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from modules.workspace.components.api import create_app
from modules.workspace.components.local_session import (
    LocalSessions,
    origin_tuple,
    read_instance,
    write_instance,
)


@pytest.fixture
def application(tmp_path):
    return create_app(tmp_path / "data", worker=False)


def client_for(app):
    return TestClient(app, base_url="http://127.0.0.1")


def test_native_unauthenticated_client_cannot_read_or_write(application):
    with client_for(application) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/").status_code == 200
        for path in ("/api/bootstrap", "/api/dashboard", "/api/leads", "/api/reports/any/pdf"):
            response = client.get(path)
            assert response.status_code == 401
            assert "token" not in response.json()
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["x-content-type-options"] == "nosniff"
            assert response.headers["referrer-policy"] == "no-referrer"
            assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
        assert client.post("/api/backup").status_code == 401
        assert client.put("/api/settings", json={}).status_code == 401
        assert client.post("/api/session/launch").status_code == 401
        assert (
            client.post(
                "/api/session/exchange", headers={"X-Workbench-Launch": "x" * 43}
            ).status_code
            == 401
        )
        assert client.get("/api/health", headers={"Host": "testserver"}).status_code == 400


def test_one_time_exchange_cookie_and_restart_boundary(application, tmp_path):
    with client_for(application) as client:
        token = application.state.sessions.issue_launch()
        response = client.post("/api/session/exchange", headers={"X-Workbench-Launch": token})
        assert response.status_code == 200
        cookie = response.headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/api" in cookie
        assert (
            client.post("/api/session/exchange", headers={"X-Workbench-Launch": token}).status_code
            == 401
        )
        assert client.get("/api/bootstrap").status_code == 200
        csrf = client.get("/api/bootstrap").json()["token"]
        assert client.post("/api/backup").status_code == 403
        client.headers["X-Workbench-Token"] = csrf
        assert client.post("/api/backup").status_code == 200
        # Another process has no browser cookie and cannot bootstrap itself.
        with client_for(application) as stranger:
            assert stranger.get("/api/bootstrap").status_code == 401
        restarted = create_app(tmp_path / "other", worker=False)
        with client_for(restarted) as other:
            other.cookies.update(client.cookies)
            assert other.get("/api/bootstrap").status_code == 401


@pytest.mark.parametrize(
    "origin", ["null", "http://evil.example", "https://127.0.0.1", "http://127.0.0.1:9999"]
)
def test_full_origin_checked_even_with_valid_credentials(application, origin):
    with client_for(application) as client:
        launch = application.state.sessions.issue_launch()
        headers = {"X-Workbench-Launch": launch, "Origin": origin}
        assert client.post("/api/session/exchange", headers=headers).status_code == 403
        headers["Origin"] = "http://127.0.0.1"
        assert client.post("/api/session/exchange", headers=headers).status_code == 200
        csrf = client.get("/api/bootstrap").json()["token"]
        assert (
            client.put(
                "/api/settings", headers={"X-Workbench-Token": csrf, "Origin": origin}, json={}
            ).status_code
            == 403
        )
        assert client.get("/api/bootstrap", headers={"Origin": origin}).status_code == 403


def test_launcher_endpoint_requires_user_credential(application):
    with client_for(application) as client:
        for key in ("", "wrong"):
            assert (
                client.post(
                    "/api/session/launch", headers={"X-Workbench-Launcher": key}
                ).status_code
                == 401
            )
        result = client.post(
            "/api/session/launch",
            headers={"X-Workbench-Launcher": application.state.sessions.launcher_key},
        )
        assert result.status_code == 200
        assert (
            client.post(
                "/api/session/exchange", headers={"X-Workbench-Launch": result.json()["launch"]}
            ).status_code
            == 200
        )


def test_launch_and_session_expire(monkeypatch):
    import modules.workspace.components.local_session as module

    clock = [100.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    sessions = LocalSessions()
    expired = sessions.issue_launch()
    clock[0] += module.LAUNCH_SECONDS + 1
    assert sessions.exchange(expired) is None
    session = sessions.exchange(sessions.issue_launch())
    request = type("Request", (), {"cookies": {sessions.cookie_name: session}})()
    assert sessions.authorized(request)
    clock[0] += module.SESSION_SECONDS + 1
    assert not sessions.authorized(request)


def test_private_instance_roundtrip(tmp_path):
    sessions = LocalSessions()
    path = write_instance(tmp_path, 8877, False, sessions)
    assert read_instance(tmp_path, 8877, False) == sessions.launcher_key
    with pytest.raises(ValueError):
        read_instance(tmp_path, 8878, False)
    if os.name != "nt":
        assert path.stat().st_mode & 0o077 == 0
        path.chmod(0o644)
        with pytest.raises(ValueError, match="private"):
            read_instance(tmp_path, 8877, False)


@pytest.mark.parametrize("failure", ["fsync", "replace"])
def test_failed_instance_publication_retains_previous_private_credential(
    tmp_path, monkeypatch, failure
):
    from modules.tools.components import filesystem

    original = LocalSessions()
    path = write_instance(tmp_path, 8877, False, original)
    saved = path.read_bytes()

    def fail(*args):
        raise OSError("Synthetic publication failure")

    monkeypatch.setattr(filesystem.os, failure, fail)
    with pytest.raises(OSError, match="Synthetic publication failure"):
        write_instance(tmp_path, 8877, False, LocalSessions())

    assert path.read_bytes() == saved
    assert read_instance(tmp_path, 8877, False) == original.launcher_key
    assert list(tmp_path.iterdir()) == [path]
    if os.name != "nt":
        assert path.stat().st_mode & 0o077 == 0
