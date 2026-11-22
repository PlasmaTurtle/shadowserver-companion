"""Reviewed HTTP surface and service transaction compatibility."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from modules.investigations.components.api_models import DraftValues
from modules.investigations.components.cases import Cases
from modules.investigations.components.services import drafts as draft_operations
from tests.support.workbench import app as app, client as client, import_rows, observations


def open_case(client, app):
    import_rows(client, app, observations())
    entity = client.get("/api/leads").json()[0]["id"]
    return client.get("/api/leads/" + entity).json()


def test_http_contract_matches_reviewed_application_contract(app):
    """Every route, request constraint and response schema needs deliberate review."""
    contract = json.loads(
        (Path(__file__).parent / "fixtures/http-contract.json").read_text(encoding="utf-8")
    )
    schema = app.openapi()
    assert {key: schema[key] for key in ("paths", "components")} == contract


def test_draft_and_legacy_projection_rollback_together(client, app, monkeypatch):
    lead = open_case(client, app)
    store = app.state.store
    fields = DraftValues.model_validate(lead["draft"]).model_dump()
    fields["notes"] = "This edit must roll back with the failed projection."
    original_fields = deepcopy(fields)
    original_case = store.one("SELECT * FROM cases WHERE id=?", (lead["case_id"],))
    original_entity = store.one("SELECT * FROM leads WHERE id=?", (lead["id"],))
    original_events = store.all("SELECT * FROM events ORDER BY id")
    original_projection = draft_operations.project_legacy_draft

    def fail_after_projection(db, entity_id, draft):
        original_projection(db, entity_id, draft)
        raise RuntimeError("Synthetic projection failure")

    monkeypatch.setattr(draft_operations, "project_legacy_draft", fail_after_projection)
    service = draft_operations.DraftService(store, Cases(store))
    with pytest.raises(RuntimeError, match="Synthetic projection failure"):
        service.save(lead, fields, lead["draft_revision"])
    assert store.one("SELECT * FROM cases WHERE id=?", (lead["case_id"],)) == original_case
    assert store.one("SELECT * FROM leads WHERE id=?", (lead["id"],)) == original_entity
    assert store.all("SELECT * FROM events ORDER BY id") == original_events
    assert fields == original_fields


def test_draft_service_owns_input_copy_and_rejects_stale_revision(client, app):
    lead = open_case(client, app)
    store = app.state.store
    fields = DraftValues.model_validate(lead["draft"]).model_dump()
    fields["notes"] = "Service edit retained in case and compatibility projection."
    original_fields = deepcopy(fields)
    service = draft_operations.DraftService(store, Cases(store))
    service.save(lead, fields, lead["draft_revision"])
    case = store.one("SELECT * FROM cases WHERE id=?", (lead["case_id"],))
    entity = store.one("SELECT * FROM leads WHERE id=?", (lead["id"],))
    assert json.loads(case["draft"])["notes"] == fields["notes"]
    assert json.loads(entity["draft"])["notes"] == fields["notes"]
    assert case["draft_revision"] == lead["draft_revision"] + 1
    assert fields == original_fields
    with pytest.raises(draft_operations.DraftRevisionConflict):
        service.save(lead, fields, lead["draft_revision"])
    assert store.one("SELECT * FROM cases WHERE id=?", (lead["case_id"],)) == case
