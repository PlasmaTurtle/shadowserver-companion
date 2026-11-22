"""Reviewed Settings authority follows targeted intake without rewriting history."""

from copy import deepcopy
import json

from tests.support.workbench import app, client
from modules.accretion.tests.support.intake_profiles import csv_bytes, row
from modules.accretion.components.report_profiles import notification_eligibility, resolve_profile


def test_targeted_authority_is_pinned_to_import_and_eligibility(app, client):
    reason = "Synthetic review of reported exposures within the selected agency mission."
    response = client.put(
        "/api/settings",
        json={
            "agency": "Cybersecurity and Infrastructure Security Agency",
            "outreach_mode": "targeted",
            "targeted_reason": reason,
        },
    )
    assert response.status_code == 200, response.text
    first_authority = deepcopy(response.json()["targeted_authority"])
    content = csv_bytes([row(severity="high")])
    first = app.state.intake.enqueue("scan_http_vulnerable.csv", content)
    captured = json.loads(
        app.state.store.one("SELECT config FROM imports WHERE id=?", (first["id"],))["config"]
    )
    assert captured["targeted_reason"] == reason
    assert captured["targeted_authority"] == first_authority
    profile = resolve_profile(row(), configured_type="scan_http_vulnerable")
    decision = notification_eligibility(row(severity="high"), profile, captured)
    assert decision["eligible"]
    assert decision["override_reason"] == reason
    assert decision["override_authority"] == first_authority
    decision["override_authority"]["title"] = "Changed local display"
    assert captured["targeted_authority"] == first_authority

    response = client.put(
        "/api/settings",
        json={"agency": "Federal Bureau of Investigation", "targeted_reason": reason},
    )
    assert response.status_code == 200, response.text
    assert response.json()["targeted_authority"] != first_authority
    second = app.state.intake.enqueue("scan_http_vulnerable.csv", content)
    assert not second["duplicate"] and second["id"] != first["id"]
    assert app.state.intake.enqueue("scan_http_vulnerable.csv", content)["id"] == second["id"]
    original = json.loads(
        app.state.store.one("SELECT config FROM imports WHERE id=?", (first["id"],))["config"]
    )
    assert original["targeted_authority"] == first_authority


def test_critical_eligibility_does_not_claim_targeted_authority():
    profile = resolve_profile(row(), configured_type="scan_http_vulnerable")
    decision = notification_eligibility(
        row(), profile, {"outreach_mode": "critical", "targeted_authority": {"id": "old"}}
    )
    assert "override_authority" not in decision
