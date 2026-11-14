"""Report identity stays coherent, deliberate, and independent of current settings."""

from copy import deepcopy
import hashlib
import json

import pytest

from test_workbench import (
    app,
    client,
    import_rows,
    observations,
    ready,
    reopen_sections,
    validate_sections,
)
from test_notification_narrative import inputs
from workbench import approved_template as approved
from workbench.outreach_template import apply_outreach_template
from workbench.introduction_model import INTRO as CURRENT_INTRO
from workbench.report_snapshot import snapshot
from workbench.sender_identity import (
    capture_profile,
    effective_settings,
    identity_copy,
    profile_issue,
    responsibility,
    security_intro,
    update_available,
)
from workbench.workspace_defaults import DEFAULT_SETTINGS


CUSTOM = {
    "analyst_name": "Alex Example",
    "analyst_title": "",
    "agency": "Regional Cyber Outreach Office",
    "department": "Regional Services",
    "office": "Asheville Office",
    "email": "analyst@example.invalid",
}


def settings(client, **changes):
    value = client.get("/api/bootstrap").json()["settings"]
    value.update(changes)
    result = client.put("/api/settings", json=value)
    assert result.status_code == 200, result.text
    return result.json()


def opened(client, app):
    # Sender tests use public synthetic endpoints; scope anomalies have their
    # own explicit disposition and certification tests.
    import_rows(client, app, rows=[r for r in observations() if r["ip"] != "10.1.2.3"])
    entity = client.get("/api/leads").json()[0]["id"]
    return client.get("/api/leads/" + entity).json()


def adopt(client, lead):
    return client.post(
        f"/api/cases/{lead['case_id']}/presentation/adopt",
        json={"expected_revision": lead["draft_revision"], "reason": "Review sender identity"},
    )


def test_current_usss_profile_retains_established_sender_copy():
    profile = capture_profile({**DEFAULT_SETTINGS, "analyst_name": "Alex", "analyst_title": ""})
    draft = {"sender_profile": profile}
    for text in (
        CURRENT_INTRO,
        approved.INTRO,
        "The United States Secret Service Charlotte Cyber Fraud Task Force (CFTF) is reaching out",
        "On November 13, 2026, the United States Secret Service, Charlotte Cyber Fraud Task Force, began reviewing",
    ):
        assert identity_copy(text, draft) == text
    assert responsibility(approved.RESPONSIBILITY, draft) == approved.RESPONSIBILITY
    assert security_intro(approved.SECURITY_INTRO, draft) == approved.SECURITY_INTRO
    assert profile_issue(draft) is None


@pytest.mark.parametrize("text", [CURRENT_INTRO, approved.INTRO])
def test_custom_profile_explains_notice_purpose_without_asserting_agency_mission(text):
    result = identity_copy(text, {"sender_profile": capture_profile(CUSTOM)})
    assert "help your organization review reported exposures and protect its systems" in result
    assert "ongoing effort" not in result and "financial crime" not in result


@pytest.mark.parametrize("office", ["Asheville Office", "", "Regional Cyber Outreach Office"])
def test_custom_profile_uses_configured_identity_without_invented_task_force(office):
    lead, draft = inputs()
    draft.update(
        sender_profile=capture_profile({**CUSTOM, "office": office}),
        narrative_revision="report-start-2026-11-12-v5",
    )
    apply_outreach_template(lead, draft)
    assert CUSTOM["agency"] in draft["narrative"]
    assert "Secret Service" not in draft["narrative"]
    assert "Charlotte" not in draft["narrative"]
    assert "Cyber Fraud Task Force" not in draft["narrative"]
    assert "Secret Service" not in responsibility(approved.RESPONSIBILITY, draft)
    assert "Secret Service" not in security_intro(approved.SECURITY_INTRO, draft)
    if office == CUSTOM["agency"]:
        assert CUSTOM["agency"] + ", " + CUSTOM["agency"] not in draft["narrative"]


def test_another_usss_office_does_not_claim_charlotte_task_force_or_carolinas_mission():
    lead, draft = inputs()
    draft.update(
        sender_profile=capture_profile(
            {**DEFAULT_SETTINGS, "analyst_name": "Alex", "office": "Atlanta Field Office"}
        ),
        narrative_revision="report-start-2026-11-12-v5",
    )
    apply_outreach_template(lead, draft)
    assert "United States Secret Service, Atlanta Field Office" in draft["narrative"]
    assert (
        "Charlotte" not in draft["narrative"] and "Cyber Fraud Task Force" not in draft["narrative"]
    )
    assert "Carolinas" not in security_intro(approved.SECURITY_INTRO, draft)


@pytest.mark.parametrize("field", ["agency", "analyst_name"])
def test_missing_sender_setup_blocks_introduction_with_an_adoption_action(client, app, field):
    settings(client, **{field: ""})
    lead = opened(client, app)
    check = next(row for row in lead["readiness"] if row["key"] == "sender_profile")
    assert not check["ok"] and "adopt" in check["label"]
    result = client.post(
        f"/api/cases/{lead['case_id']}/sections/introduction/validate",
        json={"expected_revision": lead["draft_revision"]},
    )
    assert result.status_code == 422 and "Settings" in result.text


@pytest.mark.parametrize("value", [None, {}])
def test_legacy_identity_is_not_inferred_or_rewritten(value):
    draft = {"sender_profile": value}
    assert identity_copy(approved.INTRO, draft) == approved.INTRO
    assert effective_settings(CUSTOM, draft) == CUSTOM
    assert update_available(CUSTOM, draft)
    assert profile_issue(draft) is None


@pytest.mark.parametrize("value", [[], "broken", 7, {"revision": "future"}, {"agency": []}])
def test_malformed_profile_can_be_described_and_repaired_without_crashing(value):
    draft = {"sender_profile": value}
    assert profile_issue(draft)
    assert effective_settings(CUSTOM, draft)["agency"] == CUSTOM["agency"]
    identity_copy(approved.INTRO, draft)
    security_intro(approved.SECURITY_INTRO, draft)
    responsibility(approved.RESPONSIBILITY, draft)


@pytest.mark.parametrize(
    "field,value", [("agency", ""), ("analyst_name", ""), ("office", "Bad\x00office")]
)
def test_incomplete_profile_is_not_ready(field, value):
    profile = capture_profile(CUSTOM)
    profile[field] = value
    assert profile_issue({"sender_profile": profile})


@pytest.mark.parametrize(
    "field", ["agency", "department", "office", "analyst_name", "analyst_title", "email"]
)
def test_settings_reject_multiline_or_control_identity(client, field):
    value = client.get("/api/bootstrap").json()["settings"]
    value[field] = "First\nSecond"
    assert client.put("/api/settings", json=value).status_code == 422


def test_custom_profile_is_consistent_across_live_report_model_and_sender_name_without_title(
    client, app
):
    settings(client, **CUSTOM)
    lead = opened(client, app)
    draft = lead["draft"]
    assert draft["sender_name"] == CUSTOM["analyst_name"] and draft["sender_title"] == ""
    assert draft["sender_profile"] == capture_profile(CUSTOM)
    assert CUSTOM["agency"] in draft["intro"] and CUSTOM["agency"] in draft["narrative"]
    assert "Secret Service" not in draft["intro"] + draft["narrative"]
    data = snapshot(app.state.store, lead["id"], lead["case_id"], capture_sections=())
    assert data["profile"]["agency"] == CUSTOM["agency"]
    introduction = data["composition"]["sections"][0]["model"]
    assert CUSTOM["agency"].upper() in introduction["agency"]
    assert CUSTOM["agency"] in introduction["sender"]
    closing = next(e for e in data["composition"]["exhibits"] if e.get("type") == "closing")
    assert "Secret Service" not in closing["responsibility"]
    info = next(e for e in data["composition"]["exhibits"] if e.get("type") == "information")
    assert "the Secret Service provides" not in json.dumps(info)


def test_settings_changes_preserve_frozen_sender_until_reasoned_adoption(client, app):
    lead = opened(client, app)
    lead = ready(client, lead["id"])
    original = {r["key"]: r["validation_id"] for r in lead["section_reviews"]}
    old_profile = deepcopy(lead["draft"]["sender_profile"])
    settings(client, **CUSTOM)
    lead = client.get(f"/api/cases/{lead['case_id']}").json()
    assert lead["draft"]["sender_profile"] == old_profile
    assert lead["draft"]["sender_name"] == "Test Analyst"
    assert lead["sender_profile_update_available"]
    assert all(r["status"] == "validated" for r in lead["section_reviews"])
    assert {r["key"]: r["validation_id"] for r in lead["section_reviews"]} == original
    blocked = adopt(client, lead)
    assert blocked.status_code == 422 and "Reopen" in blocked.text
    lead = reopen_sections(
        client,
        lead,
        "Review new sender organization",
        ["introduction", "vulnerabilities", "information", "closing"],
    )
    changed = adopt(client, lead)
    assert changed.status_code == 200, changed.text
    lead = changed.json()
    assert lead["draft"]["sender_profile"] == capture_profile(CUSTOM)
    assert not lead["sender_profile_update_available"]
    assert (
        next(r for r in lead["section_reviews"] if r["key"] == "attribution")["validation_id"]
        == original["attribution"]
    )
    assert "Secret Service" not in lead["draft"]["intro"] + lead["draft"]["narrative"]
    assert all(r["status"] == "draft" for r in lead["section_reviews"] if r["key"] != "attribution")


def test_client_cannot_rewrite_sender_or_preview_identity_and_old_client_omission_keeps_pin(
    client, app
):
    lead = opened(client, app)
    fields = deepcopy(lead["draft"])
    fields["sender_profile"]["agency"] = "Forged agency"
    url = f"/api/leads/{lead['id']}"
    for path, body in [
        (url + "/draft", {"expected_revision": lead["draft_revision"], "fields": fields}),
        (url + "/narrative", fields),
    ]:
        result = (
            client.put(path, json=body) if path.endswith("draft") else client.post(path, json=body)
        )
        assert result.status_code == 422 and "Sender identity is read-only" in result.text
    fields = deepcopy(lead["draft"])
    fields.pop("sender_profile")
    fields["sender_name"] = "Forged name"
    result = client.put(
        url + "/draft", json={"expected_revision": lead["draft_revision"], "fields": fields}
    )
    assert result.status_code == 200, result.text
    assert result.json()["draft"]["sender_profile"] == lead["draft"]["sender_profile"]
    assert result.json()["draft"]["sender_name"] == "Test Analyst"


def test_legacy_saved_draft_requires_explicit_adoption_for_custom_identity(client, app):
    lead = opened(client, app)
    with app.state.store.transaction() as db:
        draft = json.loads(
            db.execute("SELECT draft FROM cases WHERE id=?", (lead["case_id"],)).fetchone()[0]
        )
        draft.pop("sender_profile")
        db.execute("UPDATE cases SET draft=? WHERE id=?", (json.dumps(draft), lead["case_id"]))
    settings(client, **CUSTOM)
    lead = client.get(f"/api/cases/{lead['case_id']}").json()
    assert "sender_profile" not in lead["draft"]
    assert "United States Secret Service" in lead["draft"]["intro"]
    assert lead["sender_profile_update_available"]
    assert not next(row for row in lead["readiness"] if row["key"] == "sender_profile")["ok"]
    introduction = next(row for row in lead["section_reviews"] if row["key"] == "introduction")
    assert not introduction["can_validate"]
    result = adopt(client, lead)
    assert result.status_code == 200, result.text
    assert CUSTOM["agency"] in result.json()["draft"]["intro"]


def test_certified_bytes_and_sender_survive_settings_changes(client, app):
    lead = opened(client, app)
    lead = ready(client, lead["id"])
    certified = client.post(f"/api/leads/{lead['id']}/finalize")
    assert certified.status_code == 200, certified.text
    report_id = certified.json()["id"]
    path = f"/api/reports/{report_id}/pdf"
    before = hashlib.sha256(client.get(path).content).hexdigest()
    settings(client, **CUSTOM)
    historical = client.get(f"/api/cases/{lead['case_id']}").json()
    assert historical["draft"]["sender_name"] == "Test Analyst"
    assert historical["draft"]["sender_profile"]["agency"] == DEFAULT_SETTINGS["agency"]
    assert not historical["sender_profile_update_available"]
    assert hashlib.sha256(client.get(path).content).hexdigest() == before
    assert adopt(client, historical).status_code == 422
