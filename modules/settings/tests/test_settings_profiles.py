"""Settings profile choices follow the pinned adapter inventory."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
from threading import Event

import pytest

from tests.support.workbench import app, client
from modules.accretion.components.report_profiles import inventory, supported_profiles
from modules.settings.components.api_models import SettingsUpdate
from modules.settings.components.profile_catalog import AGENCIES, REGIONS, TIMEZONES
from pydantic import ValidationError


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
                "agency": "Federal Bureau of Investigation",
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


@pytest.mark.parametrize(
    "changes",
    [
        {"regions": ["North Carolina", "Atlantis"]},
        {"regions": ["North\x00Carolina"]},
        {"agency": "Other organization"},
        {"department": "Other department"},
        {"analyst_name": " "},
        {"office": " "},
        {"email": "not-an-address"},
        {"email": "Person <person@example.invalid>"},
        {"email": "person@example.invalid,other@example.invalid"},
        {"email": "person(comment)@example.invalid"},
        {"email": "person@-example.invalid"},
        {"display_timezone": "Europe/London"},
        {"timeout": True},
        {"timeout": "10"},
        {"interval": False},
        {"retries": 1.5},
        {"retries": True},
        {"watch_inbox": "true"},
        {"report_type": "made_up_report"},
        {"sheet": "Bad\nSheet"},
        {"targeted_reason": "reason\x00text"},
        {"accretion_priority_cities": ["Bad\x7fcity"]},
    ],
)
def test_invalid_settings_input_is_atomic(app, client, changes):
    before = app.state.store.settings()
    response = client.put("/api/settings", json={"appearance": "dark", **changes})
    assert response.status_code == 422, response.text
    assert app.state.store.settings() == before


@pytest.mark.parametrize("field", ["timeout", "interval"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_numeric_preferences_are_rejected(field, value):
    with pytest.raises(ValidationError):
        SettingsUpdate.model_validate({field: value})


def test_catalog_and_canonical_writes_share_the_supported_choices(client):
    catalog = client.get("/api/setup").json()
    assert {agency["id"] for agency in catalog["agencies"]} == {"cisa", "fbi", "usss"}
    assert len(set(catalog["regions"])) == 56
    assert catalog["regions"] == list(REGIONS)
    assert catalog["timezones"] == list(TIMEZONES)
    for agency in AGENCIES:
        response = client.put(
            "/api/settings",
            json={
                "agency": " " + agency["name"].lower() + " ",
                "regions": [" nc ", "North Carolina", "PR", "District of Columbia"],
                "email": "analyst+review@example.invalid",
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["agency"] == agency["name"]
        assert response.json()["department"] == agency["department"]
        assert response.json()["regions"] == [
            "North Carolina",
            "Puerto Rico",
            "District of Columbia",
        ]
    for zone in TIMEZONES:
        assert SettingsUpdate(display_timezone=zone).display_timezone == zone
    for report in ["auto", *supported_profiles()]:
        assert client.put("/api/settings", json={"report_type": report}).status_code == 200


def test_targeted_authority_is_derived_and_agency_change_requires_new_review(app, client):
    cisa = next(agency for agency in AGENCIES if agency["id"] == "cisa")
    fbi = next(agency for agency in AGENCIES if agency["id"] == "fbi")
    response = client.put(
        "/api/settings",
        json={
            "agency": cisa["name"],
            "outreach_mode": "targeted",
            "targeted_reason": "Review the synthetic exposed service for requested assistance.",
            "targeted_authority": {"agency_id": "forged", "authorities": []},
        },
    )
    assert response.status_code == 200, response.text
    authority = response.json()["targeted_authority"]
    assert authority["agency_id"] == "cisa"
    assert authority["revision"] == cisa["authority"]["revision"]
    assert authority["authorities"][0]["citation"] == "6 U.S.C. § 659(c)(6), (7), (9), (n)"
    before = app.state.store.settings()
    response = client.put("/api/settings", json={"agency": fbi["name"]})
    assert response.status_code == 422 and "reason" in response.text
    assert app.state.store.settings() == before
    response = client.put(
        "/api/settings",
        json={
            "agency": fbi["name"],
            "targeted_reason": "Review the synthetic federal investigation nexus.",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["targeted_authority"]["agency_id"] == "fbi"
    assert response.json()["department"] == "U.S. Department of Justice"
    assert authority["agency_id"] == "cisa"
    response = client.put("/api/settings", json={"outreach_mode": "critical"})
    assert response.status_code == 200 and "targeted_authority" not in response.json()


def test_legacy_profile_is_not_rewritten_by_unrelated_preference_save(app, client):
    store = app.state.store
    with store.transaction() as db:
        before = {
            **store.settings(db),
            "agency": "Historical Regional Office",
            "department": "Historical department",
            "regions": ["Historical jurisdiction"],
            "display_timezone": "Europe/London",
            "email": "historical value",
            "report_type": "historical report",
            "outreach_mode": "targeted",
            "targeted_reason": "",
            "critical_only": False,
            "targeted_authority": {"revision": "historical"},
        }
        db.execute("UPDATE settings SET value=? WHERE key='profile'", (json.dumps(before),))
    assert client.get("/api/bootstrap").json()["settings"] == before
    response = client.put(
        "/api/settings", json={"appearance": "dark", "targeted_authority": {"revision": "forged"}}
    )
    assert response.status_code == 200, response.text
    assert response.json() == {**before, "appearance": "dark"}
    assert store.settings() == response.json()


def test_critical_agency_change_cannot_reactivate_a_reason_reviewed_for_another_agency(app, client):
    assert (
        client.put(
            "/api/settings",
            json={
                "outreach_mode": "targeted",
                "targeted_reason": "Synthetic USSS investigation nexus.",
            },
        ).status_code
        == 200
    )
    assert client.put("/api/settings", json={"outreach_mode": "critical"}).status_code == 200
    response = client.put("/api/settings", json={"agency": "Federal Bureau of Investigation"})
    assert response.status_code == 200, response.text
    assert response.json()["targeted_reason"] == ""
    assert "targeted_authority" not in response.json()
    before = app.state.store.settings()
    response = client.put("/api/settings", json={"outreach_mode": "targeted"})
    assert response.status_code == 422 and "recorded reason" in response.text
    assert app.state.store.settings() == before
    response = client.put(
        "/api/settings",
        json={"outreach_mode": "targeted", "targeted_reason": "Synthetic FBI investigation nexus."},
    )
    assert response.status_code == 200, response.text
    assert response.json()["targeted_authority"]["agency_id"] == "fbi"


def test_worksheet_title_keeps_significant_spaces(client):
    from openpyxl import Workbook

    workbook = Workbook()
    workbook.active.title = " Synthetic report "
    response = client.put("/api/settings", json={"sheet": workbook.active.title})
    assert response.status_code == 200, response.text
    assert response.json()["sheet"] in workbook.sheetnames
    assert response.json()["sheet"] == " Synthetic report "
    workbook.close()
