"""Settings profile choices follow the pinned adapter inventory."""

from test_workbench import app, client
from workbench.report_profiles import inventory, supported_profiles


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
