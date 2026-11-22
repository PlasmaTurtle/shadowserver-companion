"""Current pages are defaults; saved layouts require explicit guarded adoption."""

from copy import deepcopy
import json

from tests.support.workbench import app, client, import_rows, reopen_sections
from modules.investigations.components.report_drafts import default_draft, hydrated_draft
from modules.investigations.components.report_layouts import (
    CURRENT_LAYOUTS,
    CURRENT_REVISIONS,
    NARRATIVE_REVISION,
)
from modules.investigations.components.introduction_model import INTRO, SUBJECT
from modules.workspace.databases.workspace_defaults import DEFAULT_SETTINGS


def minimal_lead():
    return {"company": "Example", "domain": "example.com", "entries": [], "draft": {}}


def test_current_pages_are_selected_without_a_preview_fixture():
    draft = default_draft(minimal_lead(), DEFAULT_SETTINGS)
    assert {key: draft[key] for key in CURRENT_LAYOUTS} == CURRENT_LAYOUTS
    assert draft["narrative_revision"] == NARRATIVE_REVISION
    assert draft["intro"] == INTRO and draft["subject"] == SUBJECT


def test_saved_legacy_and_historical_drafts_do_not_inherit_new_page_defaults():
    lead = minimal_lead()
    lead["draft"] = {
        "subject": "Saved subject",
        "intro": "Saved introduction",
        "narrative": "Saved narrative",
    }
    lead["case"] = {"stage": "pending_notification", "draft_revision": 4}
    original = deepcopy(lead)
    draft = hydrated_draft(lead, DEFAULT_SETTINGS)
    assert all(draft[key] == "legacy" for key in CURRENT_LAYOUTS)
    assert draft["narrative_revision"] == "legacy"
    assert draft["subject"] == "Saved subject" and draft["narrative"] == "Saved narrative"
    assert lead == original
    lead["case"]["stage"] = "in_progress"
    draft = hydrated_draft(lead, DEFAULT_SETTINGS)
    assert all(draft[key] == "legacy" for key in CURRENT_LAYOUTS)
    lead["draft"]["narrative_revision"] = ""
    assert hydrated_draft(lead, DEFAULT_SETTINGS)["narrative_revision"] == "legacy"


def test_new_case_pins_revisions_and_old_client_save_cannot_downgrade(client, app):
    import_rows(client, app)
    lead = client.get("/api/leads/" + client.get("/api/leads").json()[0]["id"]).json()
    saved = json.loads(
        app.state.store.one("SELECT draft FROM cases WHERE id=?", (lead["case_id"],))["draft"]
    )
    assert {key: saved[key] for key in CURRENT_REVISIONS} == CURRENT_REVISIONS
    fields = deepcopy(lead["draft"])
    for key in CURRENT_LAYOUTS:
        fields.pop(key)
    fields["notes"] = "Administrative note from an older client"
    fields["narrative_revision"] = "legacy"
    response = client.put(
        "/api/leads/" + lead["id"] + "/draft",
        json={"expected_revision": lead["draft_revision"], "fields": fields},
    )
    assert response.status_code == 200, response.text
    assert {key: response.json()["draft"][key] for key in CURRENT_LAYOUTS} == CURRENT_LAYOUTS
    assert response.json()["draft"]["intro"] == INTRO
    assert response.json()["draft"]["narrative_revision"] == NARRATIVE_REVISION
    preview = client.post("/api/leads/" + lead["id"] + "/narrative", json=fields)
    assert preview.status_code == 200, preview.text
    assert preview.json()["narrative"] == response.json()["draft"]["narrative"]


def test_legacy_layout_adoption_obeys_section_freezes_and_logs_reason(client, app):
    import_rows(client, app)
    lead = client.get("/api/leads/" + client.get("/api/leads").json()[0]["id"]).json()
    old = deepcopy(lead["draft"])
    old.update({key: "legacy" for key in CURRENT_LAYOUTS})
    response = client.put(
        "/api/leads/" + lead["id"] + "/draft",
        json={"expected_revision": lead["draft_revision"], "fields": old},
    )
    assert response.status_code == 200, response.text
    lead = response.json()
    assert lead["presentation_update_available"] is True
    # Closing can be reviewed independently of incomplete attribution work.
    response = client.post(
        f"/api/cases/{lead['case_id']}/sections/closing/validate",
        json={"expected_revision": lead["draft_revision"]},
    )
    assert response.status_code == 200, response.text
    lead = response.json()
    frozen = next(r for r in lead["section_reviews"] if r["key"] == "closing")
    url = f"/api/cases/{lead['case_id']}/presentation/adopt"
    response = client.post(
        url,
        json={
            "expected_revision": lead["draft_revision"],
            "reason": "Use the finalized notification layout",
        },
    )
    assert response.status_code == 422 and "Closing" in response.text
    refreshed = client.get(f"/api/cases/{lead['case_id']}").json()
    assert all(refreshed["draft"][key] == "legacy" for key in CURRENT_LAYOUTS)
    assert (
        next(r for r in refreshed["section_reviews"] if r["key"] == "closing")["snapshot"]
        == frozen["snapshot"]
    )
    reopened = reopen_sections(client, refreshed, "Review the finalized page layout", ["closing"])
    response = client.post(
        url,
        json={
            "expected_revision": reopened["draft_revision"],
            "reason": "Use the finalized notification layout",
        },
    )
    assert response.status_code == 200, response.text
    updated = response.json()
    assert {key: updated["draft"][key] for key in CURRENT_LAYOUTS} == CURRENT_LAYOUTS
    assert updated["presentation_update_available"] is False
    history = app.state.store.all(
        "SELECT * FROM events WHERE case_id=? AND action='document_presentation_adopted'",
        (lead["case_id"],),
    )
    assert len(history) == 1 and "finalized" in history[0]["detail"]
