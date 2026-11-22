"""Settings profile choices follow the pinned adapter inventory."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
from threading import Event

import pytest

from tests.support.workbench import app, client
from modules.accretion.components.report_profiles import inventory, supported_profiles


def test_settings_catalog_uses_supported_source_ids_and_readable_names(client):
    profiles = client.get("/api/bootstrap").json()["notification_profiles"]
    assert {p["id"] for p in profiles} == set(supported_profiles())
    assert [p["name"] for p in profiles] == sorted((p["name"] for p in profiles), key=str.casefold)
    for profile in profiles:
        assert profile["name"] == inventory()[profile["id"]]["name"].replace("-", " ")
        assert profile["notification_mode"] in {"critical_or_targeted", "targeted"}
    assert next(p for p in profiles if p["id"] == "scan_rdp")["notification_mode"] == "targeted"
    assert (
        next(p for p in profiles if p["id"] == "compromised_website")["notification_mode"]
        == "targeted"
    )


def test_accretion_focus_is_bounded_normalized_and_preserved(client):
    response = client.put(
        "/api/settings",
        json={
            "regions": ["North Carolina"],
            "accretion_priority_cities": [" Burnsville ", "burnsville", ""],
            "accretion_priority_products": ["Exchange"],
        },
    )
    assert response.status_code == 200
    assert response.json()["accretion_priority_cities"] == ["Burnsville"]
    response = client.put("/api/settings", json={"regions": ["North Carolina"], "sheet": ""})
    assert response.json()["accretion_priority_products"] == ["Exchange"]
    for values in (["x" * 81], ["bad\nname"], [str(i) for i in range(21)]):
        assert (
            client.put(
                "/api/settings",
                json={"regions": ["North Carolina"], "accretion_priority_cities": values},
            ).status_code
            == 422
        )


def test_appearance_only_save_preserves_current_profile_and_jurisdiction(app, client, monkeypatch):
    response = client.put(
        "/api/settings",
        json={"regions": ["Virginia"], "office": "Updated Example Office", "watch_inbox": False},
    )
    assert response.status_code == 200, response.text
    before = app.state.store.settings()
    scope_changes = []
    monkeypatch.setattr(app.state.api_acquisition, "scope_changed", lambda: scope_changes.append(1))

    response = client.put("/api/settings", json={"appearance": "dark"})

    assert response.status_code == 200, response.text
    expected = {**before, "appearance": "dark"}
    assert response.json() == expected
    assert app.state.store.settings() == expected
    assert not scope_changes


@pytest.mark.parametrize("regions", [[], None, [" ", "\t"]])
def test_explicit_invalid_regions_do_not_save_other_preferences(app, client, regions):
    before = app.state.store.settings()
    response = client.put("/api/settings", json={"regions": regions, "appearance": "dark"})
    assert response.status_code == 422, response.text
    assert app.state.store.settings() == before


def test_partial_outreach_mode_change_can_return_to_critical_without_a_reason(client):
    response = client.put(
        "/api/settings",
        json={
            "regions": ["North Carolina"],
            "outreach_mode": "targeted",
            "targeted_reason": "Review the synthetic report",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["critical_only"] is False

    response = client.put(
        "/api/settings",
        json={"regions": ["North Carolina"], "outreach_mode": "critical", "targeted_reason": ""},
    )
    assert response.status_code == 200, response.text
    assert response.json()["outreach_mode"] == "critical"
    assert response.json()["critical_only"] is True
    assert response.json()["targeted_reason"] == ""


def test_legacy_outreach_flag_requires_a_reason_and_selects_the_matching_mode(app, client):
    before = app.state.store.settings()
    payload = {"regions": ["North Carolina"], "critical_only": False}
    response = client.put("/api/settings", json=payload)
    assert response.status_code == 422 and "recorded reason" in response.text
    assert app.state.store.settings() == before

    response = client.put(
        "/api/settings", json={**payload, "targeted_reason": "Review the synthetic report"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["outreach_mode"] == "targeted"
    assert response.json()["critical_only"] is False

    response = client.put(
        "/api/settings", json={"regions": ["North Carolina"], "critical_only": True}
    )
    assert response.status_code == 200, response.text
    assert response.json()["outreach_mode"] == "critical"
    assert response.json()["critical_only"] is True


def test_explicit_outreach_mode_is_authoritative_over_the_legacy_flag(app, client):
    response = client.put(
        "/api/settings",
        json={"regions": ["North Carolina"], "outreach_mode": "critical", "critical_only": False},
    )
    assert response.status_code == 200, response.text
    assert response.json()["outreach_mode"] == "critical"
    assert response.json()["critical_only"] is True
    before = app.state.store.settings()
    response = client.put(
        "/api/settings",
        json={"regions": ["North Carolina"], "outreach_mode": "targeted", "critical_only": True},
    )
    assert response.status_code == 422 and "recorded reason" in response.text
    assert app.state.store.settings() == before


@pytest.mark.parametrize(
    "endpoint,changes",
    [
        ("/api/settings", {"sheet": "Reports"}),
        (
            "/api/setup/profile",
            {
                "analyst_name": "Synthetic Analyst",
                "agency": "Example Agency",
                "office": "Example Office",
            },
        ),
    ],
)
def test_profile_save_preserves_concurrent_unrelated_updates(
    app, client, monkeypatch, endpoint, changes
):
    store = app.state.store
    transaction = store.transaction
    saving = Event()

    @contextmanager
    def observed_transaction():
        saving.set()
        with transaction() as db:
            yield db

    monkeypatch.setattr(store, "transaction", observed_transaction)
    verification_route = "https://example.invalid/verify"
    with ThreadPoolExecutor(max_workers=1) as pool:
        # Hold a writer while the request begins. WAL readers can still see the
        # old profile, but its replacement must merge after this writer commits.
        with transaction() as db:
            future = pool.submit(
                client.put,
                endpoint,
                json={"regions": ["North Carolina"], **changes},
            )
            assert saving.wait(10), "Settings save did not reach its transaction"
            current = store.settings(db)
            current.update(outreach_verification_route=verification_route, appearance="dark")
            db.execute("UPDATE settings SET value=? WHERE key='profile'", (json.dumps(current),))
        response = future.result(timeout=10)

    assert response.status_code == 200, response.text
    saved = store.settings()
    assert saved.get("outreach_verification_route") == verification_route
    assert saved["appearance"] == "dark"
    assert all(saved[key] == value for key, value in changes.items())
    if endpoint == "/api/setup/profile":
        assert response.json()["setup"]["steps"]["profile"]["mode"] == "configured"
