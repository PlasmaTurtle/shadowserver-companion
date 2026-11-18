"""Drafts HTTP adapters."""

from __future__ import annotations

from fastapi import HTTPException
from fastapi.responses import Response
from .. import approved_template as approved
from ..outreach_template import apply_outreach_template
from ..services.drafts import DraftRevisionConflict
from ..api_models import DraftValues, DraftUpdate, PresentationAdoption
from ..report_layouts import CURRENT_LAYOUTS
from ..report_drafts import narrative_groups


def register(app, *, store, get_lead, drafts):
    @app.post("/api/leads/{lead_id}/narrative")
    def narrative(lead_id: str, body: DraftValues, case_id: str | None = None):
        lead = get_lead(lead_id, case_id)
        fields = body.model_dump()
        fields["narrative_revision"] = lead["draft"]["narrative_revision"]
        from ..sender_identity import effective_settings, pin_submitted

        pin_submitted(fields, lead["draft"])
        data = approved.apply_template(lead, fields, effective_settings(store.settings(), fields))
        apply_outreach_template(lead, data)
        return {
            "narrative": data["narrative"],
            "groups": narrative_groups(lead, data),
        }

    @app.put("/api/leads/{lead_id}/draft")
    def save_draft(lead_id: str, body: DraftUpdate, case_id: str | None = None):
        lead = get_lead(lead_id, case_id)
        try:
            fields = body.fields.model_dump()
            from ..observation_scope import SCOPE_FIELDS

            for key in SCOPE_FIELDS:
                if key not in body.fields.model_fields_set:
                    fields.pop(key, None)
            for key in CURRENT_LAYOUTS:
                if key not in body.fields.model_fields_set:
                    fields.pop(key, None)
            drafts.save(lead, fields, body.expected_revision)
        except DraftRevisionConflict as error:
            raise HTTPException(409, str(error)) from error
        return get_lead(lead_id, lead["case_id"])

    @app.get("/api/leads/{lead_id}/previous-template.json")
    def prior_template(lead_id: str, case_id: str | None = None):
        lead = get_lead(lead_id, case_id)
        row = store.one(
            "SELECT payload FROM cache WHERE key=?", ("pre-approved-template:" + lead["case_id"],)
        )
        if not row:
            raise HTTPException(404, "No previous template draft is archived for this case")
        return Response(row["payload"], media_type="application/json")

    @app.post("/api/cases/{case_id}/presentation/adopt")
    def adopt_presentation(case_id: str, body: PresentationAdoption):
        entity_id = drafts.adopt_presentation(case_id, body.expected_revision, body.reason)
        return get_lead(entity_id, case_id)
