"""Case capture scope, immutable evidence attachment and freeze races."""

import hashlib
import json
from pathlib import Path
import threading

from fastapi.testclient import TestClient as RawClient
from PIL import Image
import pytest

from tests.session_helpers import TestClient
from modules.entities.tests.support.contacts import attributed_entity
from modules.workspace.components.api import create_app
from modules.investigations.components.cases import Cases
from modules.investigations.components.image_evidence import metadata_path
from modules.investigations.components.report_snapshot import snapshot
from modules.investigations.components.reviews.queries import SectionReviewQueries

from modules.investigations.tests.support.website_capture import (
    captured,
    done,
)


@pytest.fixture
def fixture(tmp_path):
    app = create_app(tmp_path / "data", worker=False, website_capture=lambda *a, **k: captured())
    entity = attributed_entity(app.state.store)
    case = Cases(app.state.store).create(entity["id"])
    with TestClient(app) as client:
        yield app, client, entity, case["case_id"]


def test_capture_authentication_and_reported_scope(fixture):
    app, client, entity, case = fixture
    base = f"/api/cases/{case}/website-capture"
    raw = RawClient(app, base_url="http://127.0.0.1")
    assert raw.get(base).status_code == 401
    assert client.post(base, json={"hostname": "unrelated.example.com"}).status_code == 422
    assert (
        client.post(
            base, json={"hostname": "mail.example.com", "url": "http://127.0.0.1/"}
        ).status_code
        == 422
    )
    token = client.headers.pop("X-Workbench-Token")
    assert client.post(base, json={"hostname": "mail.example.com"}).status_code == 403
    client.headers["X-Workbench-Token"] = token


def test_capture_retains_exact_original_provenance_and_preview_hash(fixture):
    app, client, entity, case = fixture
    base = f"/api/cases/{case}/website-capture"
    assert client.get(base).json()["hostnames"] == ["mail.example.com"]
    response = client.post(base, json={"hostname": "mail.example.com"})
    assert response.status_code == 200, response.text
    result = done(app.state.website_jobs, response.json()["id"])
    assert result["state"] == "completed", result
    row = app.state.store.one("SELECT * FROM evidence WHERE id=?", (result["evidence_id"],))
    assert row["included"] == 1
    assert app.state.store.path(row["path"]).read_bytes() == captured()[0]
    meta = json.loads(app.state.store.path(metadata_path(row["id"])).read_text(encoding="utf-8"))
    assert meta["website_capture"]["final_url"] == "https://www.example.com/"
    assert (
        meta["preview_sha256"]
        == hashlib.sha256(app.state.store.path(row["preview_path"]).read_bytes()).hexdigest()
    )
    data = snapshot(app.state.store, entity["id"], case, include_reviews=False, capture_sections=())
    assert data["evidence"][0]["source_metadata"]["website_capture"]["title"] == "Example business"
    response = client.put(
        "/api/evidence/" + row["id"],
        json={
            "included": False,
            "caption": "Website",
            "source_url": "https://spoof.example/",
            "captured_at": row["captured_at"],
        },
    )
    assert response.status_code == 409
    Image.new("RGB", (1440, 900), "red").save(app.state.store.path(row["preview_path"]), "PNG")
    data = snapshot(app.state.store, entity["id"], case, include_reviews=False, capture_sections=())
    assert not next(item for item in data["readiness"] if item["key"] == "evidence_integrity")["ok"]


def test_partial_capture_is_saved_but_not_automatically_included(fixture):
    app, client, _, case = fixture
    app.state.website_jobs.capture = lambda *a, **k: captured("challenge")
    result = done(
        app.state.website_jobs,
        client.post(
            f"/api/cases/{case}/website-capture", json={"hostname": "mail.example.com"}
        ).json()["id"],
    )
    assert result["state"] == "completed"
    assert (
        app.state.store.one("SELECT included FROM evidence WHERE id=?", (result["evidence_id"],))[
            "included"
        ]
        == 0
    )


def test_capture_completion_cannot_change_a_now_frozen_section(fixture, monkeypatch):
    app, client, _, case = fixture
    gate, started = threading.Event(), threading.Event()

    def delayed(*args, **kwargs):
        started.set()
        gate.wait(3)
        return captured()

    app.state.website_jobs.capture = delayed
    result = client.post(
        f"/api/cases/{case}/website-capture", json={"hostname": "mail.example.com"}
    ).json()
    assert started.wait(2)
    original = app.state.store.one("SELECT * FROM cases WHERE id=?", (case,))

    def frozen(*args, **kwargs):
        raise ValueError("Section frozen while capture was running")

    monkeypatch.setattr(SectionReviewQueries, "assert_editable", frozen)
    gate.set()
    assert done(app.state.website_jobs, result["id"])["state"] == "failed"
    assert not app.state.store.all("SELECT * FROM evidence")
    assert not list((app.state.store.root / "evidence").glob("*"))
    current = app.state.store.one("SELECT * FROM cases WHERE id=?", (case,))
    assert (original["draft"], original["version"]) == (current["draft"], current["version"])


@pytest.mark.parametrize("terminal_state", ["failed", "cancelled"])
def test_terminal_capture_status_waits_for_temporary_file_cleanup(
    fixture, monkeypatch, terminal_state
):
    app, client, _, case = fixture
    store, jobs = app.state.store, app.state.website_jobs
    captured_ready, release_capture = threading.Event(), threading.Event()
    cleaning, release_cleanup = threading.Event(), threading.Event()
    original_unlink = Path.unlink

    def delayed_capture(*args, **kwargs):
        captured_ready.set()
        assert release_capture.wait(5)
        return captured()

    def delayed_unlink(path, *args, **kwargs):
        if path.parent == store.root / "evidence" and not cleaning.is_set():
            cleaning.set()
            assert release_cleanup.wait(5)
        return original_unlink(path, *args, **kwargs)

    jobs.capture = delayed_capture
    result = client.post(
        f"/api/cases/{case}/website-capture", json={"hostname": "mail.example.com"}
    ).json()
    assert captured_ready.wait(2)

    def stop_attachment(*args, **kwargs):
        if terminal_state == "cancelled":
            jobs.cancel(result["id"])
        raise ValueError("Section froze before capture attachment")

    monkeypatch.setattr(SectionReviewQueries, "assert_editable", stop_attachment)
    monkeypatch.setattr(Path, "unlink", delayed_unlink)
    release_capture.set()
    try:
        assert cleaning.wait(3)
        pending = jobs.get(result["id"])
        assert pending["state"] == "running"
        assert "finished_at" not in pending
        assert jobs.busy()
        assert list((store.root / "evidence").glob("*"))
        with pytest.raises(ValueError, match="active reports and lookups"):
            with app.state.workspace_data.operation():
                pytest.fail("Workspace maintenance overlapped unfinished capture cleanup")
    finally:
        release_cleanup.set()
    finished = done(jobs, result["id"])
    assert finished["state"] == terminal_state
    assert finished["finished_at"]
    assert not jobs.busy()
    assert not store.all("SELECT * FROM evidence")
    assert not list((store.root / "evidence").glob("*"))


def test_cancel_and_duplicate_jobs_do_not_attach(fixture):
    app, client, _, case = fixture
    started = threading.Event()

    def wait_cancel(*args, cancel_event, **kwargs):
        started.set()
        cancel_event.wait(3)
        return captured()

    jobs = app.state.website_jobs
    jobs.capture = wait_cancel
    base = f"/api/cases/{case}/website-capture"
    one = client.post(base, json={"hostname": "mail.example.com"}).json()
    assert started.wait(2)
    two = client.post(base, json={"hostname": "mail.example.com"}).json()
    assert one["id"] == two["id"]
    assert jobs.busy()
    client.post("/api/website-captures/" + one["id"] + "/cancel", json={})
    assert done(jobs, one["id"])["state"] == "cancelled"
    assert not app.state.store.all("SELECT * FROM evidence")


def test_http_observation_selects_http_without_silent_tls_downgrade(fixture):
    app, client, _, case = fixture
    store = app.state.store
    with store.transaction() as db:
        db.execute("UPDATE entries SET payload=json_set(payload,'$.source.fields.port',80)")
    requested = []

    def response(url, **kwargs):
        requested.append(url)
        png, metadata = captured()
        metadata["requested_url"] = url
        return png, metadata

    app.state.website_jobs.capture = response
    started = client.post(
        f"/api/cases/{case}/website-capture", json={"hostname": "mail.example.com"}
    )
    assert started.status_code == 200, started.text
    assert done(app.state.website_jobs, started.json()["id"])["state"] == "completed"
    assert requested == ["http://mail.example.com/"]
