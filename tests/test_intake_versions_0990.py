"""Regression coverage for the real HTTP column layout and report start dates."""

from copy import deepcopy
import io
import json

import pytest

from test_accretion_intake import Registry, report, row
from test_intake_acquisition_095 import receipt
from test_lead_queue_098 import queue_import
from test_source_aware_narrative import case
from test_workbench import app, client, observations, ready
from workbench.api_import import receipt_acquisition
from workbench.intake import EntryValidator, UnvalidatedEntry
from workbench.intake.versions import entry_fields
from workbench.intake_service import IntakeService
from workbench.notification_narrative_v4 import generate_narrative as generate_v4, REVISION as V4
from workbench.notification_narrative_v5 import generate_narrative, REVISION
from workbench.outreach_template import apply_outreach_template, narrative_scope_issue
from workbench.report_profiles import observation_envelope, resolve_profile
from workbench.store import Store


@pytest.mark.parametrize(
    "version,component,expected",
    [
        ("", "php:7.2.24", None),
        (None, "php:5.4.16;apache:2.4.6", None),
        ("unknown", "php:7.4.33", None),
        ("PHP/7.4.33", "", None),
        ("PHP/7.4.33", "unknown", None),
        ("", "", "missing_version"),
        ("", "unknown", "placeholder_version"),
    ],
)
def test_eol_uses_observed_component_version_with_ordinary_version_fallback(
    version, component, expected
):
    fields = row(tag="eol-php", version=version, component_version=component)
    before = deepcopy(fields)
    source = UnvalidatedEntry("scan-http_vulnerable.csv", "CSV", 2, fields)
    profile = resolve_profile(fields, configured_type="scan_http_vulnerable")
    assert EntryValidator({"North Carolina"}).rejection_reason(source, profile=profile) == expected
    assert fields == before


def test_both_version_columns_keep_product_provenance_without_inventing_pairs():
    fields = row(version="ExampleApp/3.2", component_version="php:5.4.16;apache:2.4.6")
    source = UnvalidatedEntry("report.csv", "CSV", 2, fields)
    profile = resolve_profile(fields, configured_type="scan_http_vulnerable")
    normalized = observation_envelope(source, profile, {})
    assert normalized["raw_version"] == fields["component_version"]
    assert normalized["version_source_field"] == "component_version"
    assert [(p["product"], p["version"], p["source_field"]) for p in normalized["products"]] == [
        ("php", "5.4.16", "component_version"),
        ("apache", "2.4.6", "component_version"),
        ("ExampleApp", "3.2", "version"),
    ]
    projected = entry_fields({"source": {"fields": fields}, "normalized": normalized})
    assert projected["version"] == fields["component_version"]
    assert fields["version"] == "ExampleApp/3.2"
    legacy = {**normalized, "raw_version": "ExampleApp/3.2"}
    assert (
        entry_fields({"source": {"fields": fields}, "normalized": legacy})["version"]
        == "ExampleApp/3.2"
    )


def test_protocol_revision_does_not_become_component_software_evidence():
    fields = row(tag="protocol-condition", version="5.0", component_version="php:7.4.33")
    source = UnvalidatedEntry("report.csv", "CSV", 2, fields)
    profile = resolve_profile(fields, configured_type="scan_msrpc")
    normalized = observation_envelope(source, profile, {})
    assert normalized["raw_version"] == "5.0" and normalized["products"] == []
    source.fields["tag"] = "eol-php"
    assert (
        EntryValidator({"North Carolina"}).rejection_reason(source, profile=profile)
        == "missing_version"
    )


@pytest.mark.parametrize("api", [False, True])
def test_complete_import_reaches_ranked_queue_with_component_evidence(tmp_path, api):
    store = Store(tmp_path / "workspace")
    intake = IntakeService(store, lookup_factory=Registry)
    data = report(
        [
            row(
                tag="eol-php",
                severity="critical",
                version="",
                component_version="php:5.4.16;apache:2.4.6",
            ),
            row(
                hostname="other.example.org",
                tag="eol-php",
                severity="critical",
                version="",
                component_version="",
            ),
        ]
    )
    acquisition = (
        receipt_acquisition(receipt(data, name="scan-http_vulnerable.csv")) if api else None
    )
    imported = intake.enqueue_stream(
        "scan-http_vulnerable.csv", io.BytesIO(data), acquisition=acquisition
    )
    intake.process(imported["id"])
    result = store.one("SELECT * FROM imports WHERE id=?", (imported["id"],))
    assert result["status"] == "done", result["error"]
    assert result["valid_rows"] == 1 and result["groups_total"] == 1
    assert json.loads(result["rejected"]) == {"missing_version": 1}
    payload = json.loads(store.one("SELECT payload FROM jobs")["payload"])[0]
    assert payload["source"]["fields"]["version"] == ""
    assert payload["source"]["fields"]["component_version"] == "php:5.4.16;apache:2.4.6"
    assert len(payload["normalized"]["products"]) == 2
    score = json.loads(store.one("SELECT intake_score FROM lead_queue")["intake_score"])
    assert score["quality"] > 0
    assert store.path(result["path"]).read_bytes() == data
    assert intake.reevaluate(imported["id"])["duplicate"]


def test_prior_date_rejection_can_be_replayed_without_changing_old_audit(tmp_path, monkeypatch):
    store = Store(tmp_path / "workspace")
    intake = IntakeService(store, lookup_factory=Registry)
    data = report(
        [row(severity="critical", version="", component_version="php:7.4.33", tag="eol-php")]
    )
    acquired = receipt_acquisition(receipt(data, name="scan-http_vulnerable.csv"))
    with monkeypatch.context() as old:
        old.setattr("workbench.intake_service.POLICY_VERSION", 8)
        first = intake.enqueue_stream(
            "scan-http_vulnerable.csv", io.BytesIO(data), acquisition=acquired
        )
    with store.transaction() as db:
        db.execute(
            "UPDATE imports SET status='done',rejected=? WHERE id=?",
            (json.dumps({"api_narrative_date_review_required": 1}), first["id"]),
        )
    before = store.one("SELECT * FROM imports WHERE id=?", (first["id"],))
    replay = intake.reevaluate(first["id"])
    assert not replay["duplicate"] and replay["id"] != first["id"]
    intake.process(replay["id"])
    assert (
        store.one("SELECT valid_rows FROM imports WHERE id=?", (replay["id"],))["valid_rows"] == 1
    )
    assert store.one("SELECT * FROM imports WHERE id=?", (first["id"],)) == before


@pytest.mark.parametrize(
    "source_id,tag,version",
    [("scan_http_vulnerable", "CVE-2099-10001", "7.0.1"), ("scan_msrpc", "msrpc", "5.0")],
)
def test_narrative_uses_immutable_case_start_date_in_office_time(source_id, tag, version):
    lead, draft = case(source_id, tag, version)
    lead["case"] = {"created_at": "2026-11-13T02:30:00Z"}
    draft.update(narrative_revision=REVISION, report_date="2026-12-20")
    acquisition = {
        "kind": "shadowserver_api_receipt",
        "narrative_date_basis": "unconfirmed",
        "report_date": "2026-10-01",
        "retrieved_at": "2026-11-09T12:00:00Z",
    }
    lead["entries"][0]["normalized"]["acquisition"] = acquisition
    apply_outreach_template(lead, draft)
    text = draft["narrative"]
    assert text.startswith("On November 12, 2026,") and "began reviewing" in text
    assert "received" not in text and narrative_scope_issue(lead, draft) is None
    draft["report_date"] = "2027-01-01"
    acquisition["narrative_date_basis"] = "emailed_row_plus_one"
    lead["entries"][0]["source"]["fields"]["timestamp"] = ""
    assert generate_narrative(lead, draft) == text
    draft["narrative_revision"] = V4
    legacy = generate_v4(lead, draft)
    apply_outreach_template(lead, draft)
    assert draft["narrative"] == legacy and draft["narrative_revision"] == V4


def test_component_import_can_start_save_and_freeze_notification(client, app, monkeypatch):
    rows = observations()
    for fields in rows:
        fields.update(component_version=fields["version"], version="")
    queue_import(client, app, rows)
    queued = client.get("/api/pending-leads").json()[0]
    monkeypatch.setattr("workbench.cases.now", lambda: "2026-11-13T02:30:00Z")
    response = client.post(
        "/api/pending-leads/" + queued["id"] + "/start",
        json={"expected_revision": queued["revision"]},
    )
    assert response.status_code == 200, response.text
    lead = client.get("/api/cases/" + response.json()["case_id"]).json()
    assert lead["draft"]["narrative_revision"] == REVISION
    assert lead["draft"]["report_date"] == "2026-11-12"
    assert lead["draft"]["narrative"].startswith("On November 12, 2026,")
    assert all(group["version"] for group in lead["narrative_groups"])
    assert all(record["version"] for record in app.state.store.all("SELECT version FROM entries"))
    finished = ready(client, lead["id"], validate=True)
    frozen = next(
        section for section in finished["section_reviews"] if section["key"] == "vulnerabilities"
    )
    assert frozen["status"] == "validated"
    assert frozen["frozen_fields"]["narrative"].startswith("On November 12, 2026,")
