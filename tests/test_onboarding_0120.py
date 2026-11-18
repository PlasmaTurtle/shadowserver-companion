"""First-run setup is resumable, scoped, authenticated and never stores secrets."""

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from workbench.onboarding import AGENCIES, KEY, SetupService
from workbench.routes.onboarding import ProfileValues, ProgressValues
from workbench.store import Store
from test_api_acquisition_routes_098 import api_app


def identity(**changes):
    return dict(
        analyst_name="Synthetic Analyst",
        analyst_title="",
        agency=AGENCIES[0]["name"],
        department=AGENCIES[0]["department"],
        office="Charlotte field office",
        email="",
        regions=["North Carolina"],
        display_timezone="America/New_York",
        **changes,
    )


def save_existing(store, values):
    with store.transaction() as db:
        db.execute(
            "UPDATE settings SET value=? WHERE key='profile'",
            (json.dumps({**store.settings(db), **values}),),
        )


def test_fresh_manual_setup_resumes_and_completion_survives_restart(tmp_path):
    store = Store(tmp_path)
    setup = SetupService(store)
    assert setup.status()["required"]
    with pytest.raises(ValueError, match="identity"):
        setup.complete()
    setup.progress("connections", "manual")
    assert SetupService(store).status()["step"] == "profile"
    setup.save_profile(identity())
    with pytest.raises(ValueError, match="all three"):
        setup.complete()
    setup.progress("automation", "manual")
    setup.complete()
    status = SetupService(Store(tmp_path)).status()
    assert status["completed"] and not status["required"]
    assert status["profile"]["analyst_title"] == ""
    assert status["steps"]["automation"]["mode"] == "manual"


def test_existing_complete_profile_is_not_forced_through_first_run(tmp_path):
    store = Store(tmp_path)
    save_existing(store, identity())
    setup = SetupService(store)
    assert setup.status()["established_profile"]
    assert not setup.status()["required"]
    # Explicitly entering guided setup makes unfinished progress resumable.
    setup.progress("connections", "manual")
    assert setup.status()["required"]


def test_profile_preserves_preferences_and_scope_invalidation_sees_committed_regions(tmp_path):
    store = Store(tmp_path)
    save_existing(
        store, {"appearance": "dark", "watch_inbox": True, "accretion_priority_cities": ["Durham"]}
    )
    seen = []
    acquisition = SimpleNamespace(
        status=lambda: {}, scope_changed=lambda: seen.append(store.settings()["regions"])
    )
    setup = SetupService(store, acquisition)
    values = identity()
    values.update(agency=AGENCIES[1]["name"], department=AGENCIES[1]["department"])
    result = setup.save_profile(values)
    assert result["settings"]["regions"] == ["North Carolina"]
    assert not seen
    values["regions"] = ["  Virginia  ", "Virginia"]
    result = setup.save_profile(values)
    assert seen == [["Virginia"]]
    assert result["settings"]["appearance"] == "dark"
    assert result["settings"]["watch_inbox"] is True
    assert result["settings"]["accretion_priority_cities"] == ["Durham"]
    assert "regions" not in AGENCIES[1]


def test_invalid_profile_has_no_partial_identity_or_progress_write(tmp_path):
    store = Store(tmp_path)
    setup = SetupService(store)
    before = store.settings()
    for field, value in [
        ("analyst_name", "  "),
        ("agency", ""),
        ("office", ""),
        ("regions", []),
        ("display_timezone", "Invalid/Place"),
    ]:
        payload = identity()
        payload[field] = value
        with pytest.raises(ValueError):
            setup.save_profile(payload)
        assert store.settings() == before
        assert store.one("SELECT value FROM settings WHERE key=?", (KEY,)) is None


def test_api_key_fields_are_rejected_and_only_progress_metadata_is_persisted(tmp_path):
    with pytest.raises(ValidationError):
        ProfileValues(**identity(), api_key="never-store-this")
    with pytest.raises(ValidationError):
        ProgressValues(step="connections", mode="manual", secret="never-store-this")
    store = Store(tmp_path)
    setup = SetupService(store)
    setup.progress("connections", "manual")
    record = json.loads(store.one("SELECT value FROM settings WHERE key=?", (KEY,))["value"])
    assert set(record) == {"version", "completed", "steps", "started_at"}
    assert set(record["steps"]["connections"]) == {"mode", "reviewed_at"}
    assert setup.status()["connections"].get("configured") is None


def test_automation_review_matches_saved_scheduler_state(tmp_path):
    store = Store(tmp_path)
    config = {"enabled": False}
    setup = SetupService(store, schedule=SimpleNamespace(status=lambda: {"config": config}))
    with pytest.raises(ValueError, match="enabled schedule"):
        setup.progress("automation", "configured")
    setup.progress("automation", "manual")
    config["enabled"] = True
    with pytest.raises(ValueError, match="Turn off"):
        setup.progress("automation", "manual")
    setup.progress("automation", "configured")


def test_configured_automation_cannot_be_reviewed_or_completed_with_stale_scope(tmp_path):
    store = Store(tmp_path)
    status = {
        "config": {"enabled": True},
        "scope_error": "Subscription is outside your jurisdiction",
    }
    setup = SetupService(store, schedule=SimpleNamespace(status=lambda: status))
    setup.save_profile(identity())
    setup.progress("connections", "manual")
    with pytest.raises(ValueError, match="outside your jurisdiction"):
        setup.progress("automation", "configured")
    with pytest.raises(ValueError, match="outside your jurisdiction"):
        setup.complete()


def test_malformed_progress_requires_review_instead_of_hiding_setup(tmp_path):
    store = Store(tmp_path)
    save_existing(store, identity())
    with store.transaction() as db:
        db.execute("INSERT INTO settings VALUES(?, ?)", (KEY, "not-json"))
    assert SetupService(store).status()["required"]


def test_setup_routes_require_session_and_mutation_token(api_app):
    app, client, remote = api_app
    assert client.get("/api/setup").json()["required"]
    token = client.headers.pop("X-Workbench-Token")
    assert client.put("/api/setup/profile", json=identity()).status_code == 403
    client.headers["X-Workbench-Token"] = token
    assert (
        client.put(
            "/api/setup/progress", json={"step": "connections", "mode": "manual"}
        ).status_code
        == 200
    )
    assert client.put("/api/setup/profile", json=identity()).status_code == 200
    assert (
        client.put("/api/setup/progress", json={"step": "automation", "mode": "manual"}).status_code
        == 200
    )
    assert client.post("/api/setup/complete").json()["completed"]
    client.cookies.clear()
    assert client.get("/api/setup").status_code == 401
    assert remote.api_calls == remote.download_calls == 0
