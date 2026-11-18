"""A configured sender name is sufficient; titles are explicit and optional."""

from copy import deepcopy

import pytest

from test_workbench import app, client
from test_section_validation_050 import prepared, status
from workbench.api_models import SettingsUpdate
from workbench.report_composition import compose
from workbench.reporting import snapshot
from workbench.store import Store


def update_profile(client, **changes):
    profile = client.get("/api/bootstrap").json()["settings"]
    result = client.put("/api/settings", json={**profile, **changes})
    assert result.status_code == 200, result.text
    return result.json()


def test_new_workspace_does_not_assume_a_title(app):
    assert app.state.store.settings()["analyst_title"] == ""
    assert SettingsUpdate(regions=["North Carolina"]).analyst_title == ""


@pytest.mark.parametrize("title", ["", " \t \n"])
def test_name_only_profile_survives_save_restart_and_report_review(client, app, title):
    update_profile(client, analyst_title="Special Agent")
    assert update_profile(client, analyst_title=title)["analyst_title"] == ""
    assert Store(app.state.store.root).settings()["analyst_title"] == ""

    lead = prepared(client, app)
    assert lead["draft"]["sender_name"] == "Test Analyst"
    assert lead["draft"]["sender_title"] == ""
    assert status(lead, "introduction")["status"] == "validated"
    assert status(lead, "introduction")["validated_by"] == "Test Analyst"
    assert status(lead, "introduction")["frozen_fields"]["sender_title"] == ""

    data = snapshot(app.state.store, lead["id"])
    expected = ["Test Analyst", data["profile"]["agency"], data["profile"]["office"]]
    current = compose(data)
    intro = next(n["model"] for n in current["sections"] if n["kind"] == "introduction")
    closing = next(e for e in current["exhibits"] if e["type"] == "closing")
    assert intro["sender"].splitlines() == expected
    assert closing["sender_lines"] == expected

    # Both historical native layouts and current exhibit layouts omit the line.
    historical = deepcopy(data)
    historical["draft"].update(introduction_revision="legacy", closing_revision="legacy")
    native = compose(historical)
    sender = next(n["text"] for n in native["sections"] if n.get("label") == "From")
    signature = next(n["text"] for n in native["sections"] if n.get("style") == "signature")
    assert sender.splitlines() == expected
    assert signature.splitlines() == expected
    handoff = client.get(f"/api/cases/{lead['case_id']}/outreach-handoff")
    assert handoff.status_code == 200, handoff.text
    assert f"My name is Test Analyst, {data['profile']['agency']}." in handoff.json()["message"]
    assert ", ," not in handoff.json()["message"]


def test_existing_explicit_title_is_preserved_when_other_settings_change(client, app):
    update_profile(client, analyst_title="Cybersecurity Analyst")
    result = client.put("/api/settings", json={"regions": ["North Carolina"], "sheet": "Reports"})
    assert result.status_code == 200, result.text
    assert result.json()["analyst_title"] == "Cybersecurity Analyst"
    assert Store(app.state.store.root).settings()["analyst_title"] == "Cybersecurity Analyst"
    lead = prepared(client, app)
    assert lead["draft"]["sender_title"] == "Cybersecurity Analyst"
    assert status(lead, "introduction")["frozen_fields"]["sender_title"] == "Cybersecurity Analyst"
