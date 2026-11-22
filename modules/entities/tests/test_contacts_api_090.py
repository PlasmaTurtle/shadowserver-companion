"""Authenticated end-to-end contact workflow and finite background jobs."""

import json
import threading

import pytest
from fastapi.testclient import TestClient as RawClient
from modules.entities.tests.support.contacts import attributed_entity, contact_result
from modules.entities.components.contact_discovery import DiscoveryLimits

from modules.entities.tests.support.contacts_api import finished, fixture


def test_api_discover_confirm_use_cache_and_evidence(fixture):
    app, client, entity, case, calls = fixture
    jobs = app.state.contact_discovery_jobs
    base = "/api/entities/" + entity["id"] + "/contacts"
    before = app.state.store.one("SELECT * FROM cases WHERE id=?", (case["case_id"],))
    assert client.get(base).json()["roots"][0]["eligible"]
    start = client.post(base + "/discover", json={"include_www": True})
    assert start.status_code == 200, start.text
    result = finished(jobs, start.json()["id"])
    assert result["state"] == "completed" and result["completed"] == 1
    assert calls == [("example.com", ("www.example.com",))]
    candidate = client.get(base).json()["candidates"][0]
    use = "/api/cases/" + case["case_id"] + "/contacts/" + candidate["id"] + "/use"
    first_use = client.post(
        use,
        json={
            "expected_version": before["version"],
            "expected_revision": candidate["revision"],
        },
    )
    assert first_use.status_code == 200
    assert first_use.json()["filled_fields"] == ["contact_email"]
    reviewed = client.post(
        base + "/" + candidate["id"] + "/review",
        json={"action": "confirm", "expected_revision": candidate["revision"]},
    )
    assert reviewed.status_code == 200, reviewed.text
    candidate = reviewed.json()["candidates"][0]
    stale = client.post(
        base + "/" + candidate["id"] + "/review",
        json={"action": "ignore", "expected_revision": candidate["revision"] - 1},
    )
    assert stale.status_code == 409
    adopted = client.post(
        use,
        json={
            "expected_version": first_use.json()["version"],
            "expected_revision": candidate["revision"],
        },
    )
    assert adopted.status_code == 200, adopted.text
    assert adopted.json()["filled_fields"] == []
    after = app.state.store.one("SELECT * FROM cases WHERE id=?", (case["case_id"],))
    assert after["draft"] == before["draft"] and after["draft_revision"] == before["draft_revision"]
    cached = client.post(base + "/discover", json={"include_www": True})
    assert finished(jobs, cached.json()["id"])["cached"] and len(calls) == 1
    assert client.get(base + "/evidence.zip").status_code == 200
    assert client.post(base + "/discover", json={"root_domain": "evil.example"}).status_code == 422


def test_auth_token_and_body_validation(fixture):
    app, client, entity, _, _ = fixture
    base = "/api/entities/" + entity["id"] + "/contacts"
    raw = RawClient(app, base_url="http://127.0.0.1")
    assert raw.get(base).status_code == 401
    token = client.headers.pop("X-Workbench-Token")
    assert client.post(base + "/discover", json={}).status_code == 403
    client.headers["X-Workbench-Token"] = token
    assert client.post(base + "/discover", json={"url": "https://evil.example"}).status_code == 422
    assert (
        client.post(
            "/api/contact-discovery/batch", json={"entity_ids": ["business"] * 26}
        ).status_code
        == 422
    )


def test_cancel_duplicate_job_and_transfer_quiescence(fixture):
    app, client, entity, _, _ = fixture
    started, gate = threading.Event(), threading.Event()

    class Stalled:
        def discover(self, *args, **kwargs):
            started.set()
            gate.wait(5)
            return contact_result()

    jobs = app.state.contact_discovery_jobs
    jobs.core_factory = Stalled
    base = "/api/entities/" + entity["id"] + "/contacts/discover"
    start = client.post(base, json={}).json()
    assert started.wait(2)
    try:
        assert client.post(base, json={}).status_code == 409
        assert (
            client.get("/api/entities/business/contacts").json()["active_job"]["id"] == start["id"]
        )
        with pytest.raises(ValueError, match="active"):
            with app.state.workspace_data.operation():
                pass
        attributed_entity(app.state.store, "other.example", "other")
        with pytest.raises(ValueError, match="contact discovery"):
            app.state.store.merge_entities("business", "other", 0, 0)
        assert (
            client.post("/api/contact-discovery/jobs/" + start["id"] + "/cancel").status_code == 200
        )
        assert finished(jobs, start["id"])["state"] == "cancelled"
        assert not jobs.busy() and not app.state.store.all("SELECT * FROM contact_discovery_locks")
        assert not app.state.store.all("SELECT * FROM contact_runs")
        audit = app.state.store.all("SELECT action,detail FROM events WHERE lead_id='business'")
        assert any(event["action"] == "contact_discovery_started" for event in audit)
        assert any(
            event["action"] == "contact_discovery_finished" and "cancelled" in event["detail"]
            for event in audit
        )
    finally:
        gate.set()


def test_batch_searches_selected_entities_even_with_known_general_contacts(fixture):
    app, client, entity, _, calls = fixture
    attributed_entity(app.state.store, "other.example", "other")
    attributed_entity(app.state.store, "unselected.example", "unselected")
    with app.state.store.transaction() as db:
        db.execute(
            "INSERT INTO entity_profiles VALUES(?,?)",
            ("other", json.dumps({"contact_email": "manual@other.example"})),
        )
    response = client.post(
        "/api/contact-discovery/batch", json={"entity_ids": ["business", "business", "other"]}
    )
    assert response.status_code == 200, response.text
    result = finished(app.state.contact_discovery_jobs, response.json()["id"])
    assert (
        result["total"] == 2
        and result["completed"] == 2
        and calls
        == [("example.com", ("www.example.com",)), ("other.example", ("www.other.example",))]
    )
    assert all(item["status"] != "skipped" for item in result["results"])


def test_stalled_core_timeout_always_settles(fixture):
    app, _, _, _, _ = fixture
    gate = threading.Event()

    class Stalled:
        def discover(self, *args, **kwargs):
            gate.wait(5)
            return contact_result()

    jobs = app.state.contact_discovery_jobs
    jobs.core_factory = Stalled
    jobs.limits = DiscoveryLimits(timeout=0.01)
    try:
        result = finished(jobs, jobs.start("business")["id"])
        assert result["state"] == "failed"
        assert "time budget" in result["error"]
        assert not jobs.busy()
    finally:
        gate.set()
