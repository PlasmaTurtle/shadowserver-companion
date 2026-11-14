"""Compatibility checks for the 0.7.1 API/service extraction."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from workbench.api_models import DraftValues
from workbench.cases import Cases
from workbench.services import drafts as draft_operations
from test_workbench import app as app, client as client, import_rows, observations


def open_case(client, app):
    import_rows(client, app, observations())
    entity = client.get("/api/leads").json()[0]["id"]
    return client.get("/api/leads/" + entity).json()


def test_http_contract_matches_released_070(app):
    """The 0.7.0 contract plus explicitly enumerated, optional additions."""
    contract = json.loads((Path(__file__).parent / "fixtures/http-contract-070.json").read_text())
    schema = app.openapi()
    # These spreadsheet-era filters are obsolete. Legacy payload keys are
    # accepted as ignored extras, but are no longer advertised API settings.
    for field in ("com_only", "exclude_numeric_roots"):
        contract["components"]["schemas"]["SettingsUpdate"]["properties"].pop(field)
    assert set(schema["paths"]) - set(contract["paths"]) == {
        "/api/setup",
        "/api/setup/profile",
        "/api/setup/progress",
        "/api/setup/complete",
        "/api/software/status",
        "/api/software/check",
        "/api/software/download",
        "/api/software/install",
        "/api/software/whats-new",
        "/api/software/whats-new/seen",
        "/api/entities/{entity_id}/assets",
        "/api/entity-locations",
        "/api/schedule",
        "/api/schedule/run",
        "/api/schedule/background",
        "/api/dark-matter",
        "/api/intake/progress",
        "/api/contact-discovery/find-all",
        "/api/contact-discovery/directory-status",
        "/api/contact-discovery/overviews",
        "/api/entities/{entity_id}/contacts/refresh",
        "/api/nvd/credentials",
        "/api/cases/{case_id}/website-capture",
        "/api/website-captures/{job_id}",
        "/api/website-captures/{job_id}/cancel",
        "/api/cve-catalog",
        "/api/cve-catalog/status",
        "/api/cve-catalog/search",
        "/api/cve-catalog/records/{cve_id}",
        "/api/cve-catalog/sync",
        "/api/cve-catalog/cancel",
        "/api/cve-catalog/settings",
        "/api/cve-catalog/products",
        "/api/cve-catalog/products/{product_id}",
        "/api/cve-catalog/products/{product_id}/observations",
        "/api/cve-catalog/records/{cve_id}/observations",
        "/api/cve-catalog/fields",
        "/api/cve-catalog/fields/records",
        "/api/cve-catalog/changes",
        "/api/cve-catalog/index",
        "/api/cve-catalog/risk/sync",
        "/api/cve-catalog/risk/cancel",
        "/api/entities/{entity_id}/connections/dns",
        "/api/search",
        "/api/workspace/brief",
        "/api/eclipse/intelligence",
        "/api/eclipse/view",
        "/api/session/exchange",
        "/api/session/launch",
        "/api/asset-attribution/jobs/{job_id}",
        "/api/asset-attribution/jobs/{job_id}/cancel",
        "/api/asset-attribution/results/{lookup_id}",
        "/api/asset-attribution/results/{lookup_id}/adopt",
        "/api/asset-attribution/results/{lookup_id}/evidence.zip",
        "/api/cases/{case_id}/assets/attribution",
        "/api/data/cancel",
        "/api/data/delete",
        "/api/data/export",
        "/api/data/import",
        "/api/data/status",
        "/api/entities/{entity_id}/field-review",
        "/api/entities/{entity_id}/contacts",
        "/api/entities/{entity_id}/contacts/discover",
        "/api/entities/{entity_id}/contacts/{candidate_id}/review",
        "/api/entities/{entity_id}/contacts/evidence.zip",
        "/api/cases/{case_id}/contacts/{candidate_id}/use",
        "/api/contact-discovery/batch",
        "/api/contact-discovery/jobs/{job_id}",
        "/api/contact-discovery/jobs/{job_id}/cancel",
        "/api/activity",
        "/api/workspace/queue",
        "/api/cases/{case_id}/outreach-handoff",
        "/api/cases/{case_id}/observation-scope",
        "/api/cases/{case_id}/outreach-preparation",
        "/api/cases/{case_id}/outreach-preparation/reset",
        "/api/cases/{case_id}/outreach-preparation/copy",
        "/api/cases/{case_id}/outreach-policy",
        "/api/contact-discovery/verification-route",
        "/api/entities/{entity_id}/contacts/{candidate_id}/route",
        "/api/data/check",
        "/api/data/diagnostics",
        "/api/data/health",
        "/api/data/maintenance",
        "/api/data/analytical-index/rebuild",
        "/api/entities/{entity_id}/ownership-transfer",
        "/api/entities/{entity_id}/findings/{finding_id}/reactivation",
        "/api/data/restore-points/{identifier}",
        "/api/imports/api-receipt",
        "/api/imports/{import_id}/reevaluate",
        "/api/intake/capabilities",
        "/api/report-operations",
        "/api/report-operations/{operation_id}",
        "/api/report-operations/{operation_id}/cancel",
        "/api/entities",
        "/api/entities/{entity_id}/ip-associations",
        "/api/cases/{case_id}/entity-details",
        "/api/navigation-counts",
        "/api/pending-leads",
        "/api/pending-leads/{pending_id}",
        "/api/pending-leads/{pending_id}/associate",
        "/api/pending-leads/{pending_id}/disposition",
        "/api/pending-leads/{pending_id}/start",
        "/api/shadowserver/status",
        "/api/shadowserver/credentials",
        "/api/shadowserver/connection",
        "/api/shadowserver/catalog",
        "/api/shadowserver/import",
        "/api/shadowserver/jobs/{identity}",
        "/api/shadowserver/jobs/{identity}/cancel",
    }
    schema["paths"] = {
        key: value for key, value in schema["paths"].items() if key in contract["paths"]
    }
    additions = {
        "ProfileValues",
        "ProgressValues",
        "SeenVersion",
        "BackgroundValues",
        "ScheduleValues",
        "EntityAssetAssociation",
        "NVDKeyUpdate",
        "WebsiteCaptureRequest",
        "CatalogSettings",
        "EntityDNSRefresh",
        "AssetAdoptionRequest",
        "AssetLookupRequest",
        "Body_import_data_api_data_import_post",
        "DeleteData",
        "EntityFieldReview",
        "ContactDiscoveryRequest",
        "ContactBatchRequest",
        "ContactReviewRequest",
        "ContactUseRequest",
        "ContactRouteRequest",
        "VerificationRequest",
        "OutreachPolicyValues",
        "Body_upload_api_receipt_api_imports_api_receipt_post",
        "CatalogSelection",
        "CredentialsUpdate",
        "EntityIPAssociation",
        "ImportSelection",
        "PendingLeadAssociation",
        "PendingLeadDisposition",
        "PendingLeadStart",
        "EntityDetailsAdoption",
        "ObservationScopeChange",
        "PreparationVersion",
        "PreparationReset",
        "PreparationValues",
        "CleanupData",
        "RebuildData",
        "OwnershipTransfer",
        "FindingReactivation",
    }
    assert (
        set(schema["components"]["schemas"]) - set(contract["components"]["schemas"]) == additions
    )
    for name in additions:
        del schema["components"]["schemas"][name]
    assert schema["components"]["schemas"]["SourceJobRequest"]["properties"].pop("local_only") == {
        "default": False,
        "title": "Local Only",
        "type": "boolean",
    }
    addressee = schema["components"]["schemas"]["DraftValues"]["properties"].pop(
        "addressee_revision"
    )
    assert addressee == {
        "default": "legacy",
        "enum": ["legacy", "addressee-2026-11-08-v2"],
        "title": "Addressee Revision",
        "type": "string",
    }
    appendix_choice = schema["components"]["schemas"]["DraftValues"]["properties"].pop(
        "include_appendix"
    )
    assert appendix_choice == {
        "default": True,
        "title": "Include Appendix",
        "type": "boolean",
    }
    assert schema["components"]["schemas"]["DraftValues"]["properties"].pop(
        "recipient_edition"
    ) == {
        "default": "full-v1",
        "enum": ["full-v1", "compact-v1"],
        "title": "Recipient Edition",
        "type": "string",
    }
    introduction = schema["components"]["schemas"]["DraftValues"]["properties"].pop(
        "introduction_revision"
    )
    assert introduction == {
        "default": "legacy",
        "enum": [
            "legacy",
            "introduction-2026-11-07-review-1",
            "introduction-2026-11-13-notification-1",
            "introduction-2026-11-13-notification-2",
        ],
        "title": "Introduction Revision",
        "type": "string",
    }
    revision = schema["components"]["schemas"]["DraftValues"]["properties"].pop(
        "vulnerability_revision"
    )
    assert revision == {
        "default": "legacy",
        "enum": [
            "legacy",
            "vulnerabilities-2026-11-07-review-1",
            "vulnerabilities-2026-11-11-editorial-1",
            "vulnerabilities-2026-11-13-readability-1",
        ],
        "title": "Vulnerability Revision",
        "type": "string",
    }
    narrative = schema["components"]["schemas"]["DraftValues"]["properties"].pop(
        "narrative_revision"
    )
    assert narrative == {
        "default": "",
        "maxLength": 100,
        "title": "Narrative Revision",
        "type": "string",
    }
    attribution = schema["components"]["schemas"]["DraftValues"]["properties"].pop(
        "attribution_revision"
    )
    assert attribution == {
        "default": "legacy",
        "enum": ["legacy", "attribution-2026-11-07-review-1"],
        "title": "Attribution Revision",
        "type": "string",
    }
    information = schema["components"]["schemas"]["DraftValues"]["properties"].pop(
        "information_revision"
    )
    assert information == {
        "default": "legacy",
        "enum": [
            "legacy",
            "information-2026-11-07-review-1",
            "information-2026-11-07-review-2",
            "information-2026-11-10-v1",
        ],
        "title": "Information Revision",
        "type": "string",
    }
    report_pages = schema["components"]["schemas"]["DraftValues"]["properties"].pop(
        "report_explainer_snapshots"
    )
    assert report_pages == {
        "items": {"additionalProperties": True, "type": "object"},
        "maxItems": 100,
        "title": "Report Explainer Snapshots",
        "type": "array",
    }
    finding_pages = schema["components"]["schemas"]["DraftValues"]["properties"].pop(
        "finding_explainer_snapshots"
    )
    assert finding_pages == {**report_pages, "title": "Finding Explainer Snapshots"}
    finding_revision = schema["components"]["schemas"]["DraftValues"]["properties"].pop(
        "finding_explainer_revision"
    )
    assert finding_revision == {
        "default": "legacy",
        "enum": ["legacy", "finding-explainers-2026-11-10-v1"],
        "title": "Finding Explainer Revision",
        "type": "string",
    }
    draft_fields = schema["components"]["schemas"]["DraftValues"]["properties"]
    assert draft_fields.pop("observation_scope") == {
        "additionalProperties": {"additionalProperties": True, "type": "object"},
        "maxProperties": 10000,
        "title": "Observation Scope",
        "type": "object",
    }
    for field, title in (
        ("observation_scope_archive", "Observation Scope Archive"),
        ("sender_profile", "Sender Profile"),
    ):
        expected_field = {"additionalProperties": True, "title": title, "type": "object"}
        if field == "sender_profile":
            expected_field["maxProperties"] = 10
        assert draft_fields.pop(field) == expected_field
    title_setting = schema["components"]["schemas"]["SettingsUpdate"]["properties"]["analyst_title"]
    assert title_setting["default"] == ""
    title_setting["default"] = "Special Agent"
    for field, title in (
        ("accretion_priority_cities", "Accretion Priority Cities"),
        ("accretion_priority_products", "Accretion Priority Products"),
    ):
        assert schema["components"]["schemas"]["SettingsUpdate"]["properties"].pop(field) == {
            "items": {"type": "string"},
            "maxItems": 20,
            "title": title,
            "type": "array",
        }
    closing = schema["components"]["schemas"]["DraftValues"]["properties"].pop("closing_revision")
    assert closing == {
        "default": "legacy",
        "enum": [
            "legacy",
            "closing-2026-11-07-review-1",
            "closing-2026-11-07-review-2",
            "closing-2026-11-08-final-1",
        ],
        "title": "Closing Revision",
        "type": "string",
    }
    appendix = schema["components"]["schemas"]["DraftValues"]["properties"].pop("appendix_revision")
    assert appendix == {
        "default": "legacy",
        "enum": [
            "appendix-2026-11-13-compact-3",
            "appendix-2026-11-13-compact-2",
            "appendix-2026-11-10-compact-1",
            "legacy",
            "appendix-2026-11-07-review-1",
            "appendix-2026-11-08-final-1",
        ],
        "title": "Appendix Revision",
        "type": "string",
    }
    entity_fields = schema["components"]["schemas"]["EntityProfileValues"]["properties"]
    assert entity_fields.pop("contact_phone") == {
        "default": "",
        "maxLength": 100,
        "title": "Contact Phone",
        "type": "string",
    }
    assert entity_fields.pop("notes") == {
        "default": "",
        "maxLength": 50000,
        "title": "Notes",
        "type": "string",
    }
    recipient_choice = schema["paths"]["/api/reports/{report_id}/{format}"]["get"][
        "parameters"
    ].pop()
    assert recipient_choice == {
        "name": "include_appendix",
        "in": "query",
        "required": False,
        "schema": {"type": "boolean", "default": False, "title": "Include Appendix"},
    }
    product_selection = schema["paths"]["/api/eclipse"]["get"].pop("parameters")
    assert product_selection == [
        {
            "name": "product_id",
            "in": "query",
            "required": False,
            "schema": {"type": "string", "maxLength": 100, "default": "", "title": "Product Id"},
        }
    ]
    assert schema["paths"]["/api/eclipse"]["get"]["responses"].pop("422") == {
        "description": "Validation Error",
        "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/HTTPValidationError"}}
        },
    }
    evidence = schema["paths"]["/api/eclipse/observations/{observation_id}"]["get"]
    condition_parameter = [p for p in evidence["parameters"] if p["name"] == "finding_id"]
    assert condition_parameter == [
        {
            "name": "finding_id",
            "in": "query",
            "required": False,
            "schema": {"type": "string", "maxLength": 100, "default": "", "title": "Finding Id"},
        }
    ]
    # Field source links optionally retain the dark-matter projection. Default
    # requests preserve the released behavior; reject any broader enum or a
    # newly required parameter instead of silently dropping schema differences.
    intake_parameter = [p for p in evidence["parameters"] if p["name"] == "intake"]
    assert intake_parameter == [
        {
            "name": "intake",
            "in": "query",
            "required": False,
            "schema": {
                "enum": ["", "dark_matter"],
                "type": "string",
                "default": "",
                "title": "Intake",
            },
        }
    ]
    evidence["parameters"] = [
        p for p in evidence["parameters"] if p["name"] not in {"finding_id", "intake"}
    ]
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
