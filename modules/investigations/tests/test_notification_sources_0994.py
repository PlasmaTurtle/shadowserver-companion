"""Local-only notification sources and independent section evidence ownership."""

import hashlib
import json

import pytest

from modules.entities.tests.support.contacts import attributed_entity
from modules.library.tests.support.cve_catalog import catalog_record
from modules.library.tests.support.cve_sources import ID
from modules.investigations.tests.support.website_capture import captured, done
from tests.support.workbench import app, client, import_rows, ready, reopen_sections
from modules.investigations.components.cases import Cases
from modules.library.components.intelligence import acquisition, service
from modules.library.components.intelligence.local import local_record
from modules.library.components.intelligence.selection_identity import selection_key
from modules.workspace.components.store import Store


def no_network(*args, **kwargs):
    pytest.fail("Notification source selection must not make a network request")


def test_case_creation_populates_immutable_local_cves(tmp_path, monkeypatch):
    store = Store(tmp_path / "working")
    entity = attributed_entity(store)
    with store.transaction() as db:
        row = db.execute("SELECT id,payload FROM entries").fetchone()
        original = json.loads(row["payload"])
        original["source"]["fields"]["tag"] = ID
        db.execute(
            "UPDATE entries SET payload=?,tag=? WHERE id=?", (json.dumps(original), ID, row["id"])
        )
    monkeypatch.setattr(
        acquisition, "catalog_record", lambda *_: catalog_record("Original wording")
    )
    monkeypatch.setattr(acquisition, "_response_get", no_network)
    monkeypatch.setattr(acquisition, "_wait_for_nvd", no_network)
    case = Cases(store).create(entity["id"])
    selected = case["draft"]["cve_records"]
    assert len(selected) == 1 and selected[0]["id"] == ID
    record = selected[0]
    assert record["description"] == "Original wording"
    assert record["local_only"] and record["from_catalog"]
    assert record["verification_status"] == "published"
    assert store.one("SELECT key FROM cache WHERE key=?", (selection_key(record),))
    before = store.path(record["record_path"]).read_bytes()
    assert hashlib.sha256(before).hexdigest() == record["body_sha256"]
    monkeypatch.setattr(acquisition, "catalog_record", lambda *_: catalog_record("New wording"))
    assert local_record(store, ID)["description"] == "New wording"
    assert Cases(store).view(case["case_id"])["draft"]["cve_records"] == selected
    assert store.path(record["record_path"]).read_bytes() == before


@pytest.mark.parametrize("function", [service.verify, service.enrich])
def test_missing_catalog_is_explicit_without_fallback(tmp_path, monkeypatch, function):
    monkeypatch.setattr(acquisition, "catalog_record", lambda *_: None)
    monkeypatch.setattr(acquisition, "_response_get", no_network)
    monkeypatch.setattr(acquisition, "_wait_for_nvd", no_network)
    result = function(Store(tmp_path / "working"), ID, refresh=True, local_only=True)
    assert result["local_catalog_missing"]
    assert result["verification_status"] == "unavailable"
    assert not result["sources"]
    assert "no external request" in result["errors"][0]
    assert result["kev"] is None and result["epss"] is None


def test_capture_with_closing_frozen_preserves_closing_snapshot(client, app):
    import_rows(client, app)
    entity_id = client.get("/api/leads").json()[0]["id"]
    lead = ready(client, entity_id)
    lead = reopen_sections(client, lead, "Add website evidence", ["attribution"])
    case_id = lead["case_id"]
    closing = next(r for r in lead["section_reviews"] if r["key"] == "closing")
    assert closing["status"] == "validated"
    saved = app.state.store.one(
        "SELECT snapshot_json FROM section_validations WHERE id=?", (closing["validation_id"],)
    )
    app.state.website_jobs.capture = lambda url, **kwargs: (
        captured()[0],
        {**captured()[1], "requested_url": url, "final_url": url},
    )
    hostname = app.state.website_jobs.scope(case_id)[1][0]
    result = client.post(f"/api/cases/{case_id}/website-capture", json={"hostname": hostname})
    assert result.status_code == 200, result.text
    finished = done(app.state.website_jobs, result.json()["id"])
    assert finished["state"] == "completed", finished
    assert (
        app.state.store.one(
            "SELECT snapshot_json FROM section_validations WHERE id=?", (closing["validation_id"],)
        )
        == saved
    )
    after = client.get(f"/api/cases/{case_id}").json()
    assert (
        next(r for r in after["section_reviews"] if r["key"] == "closing")["status"] == "validated"
    )


def test_case_condition_projection_keeps_original_source(tmp_path):
    from modules.accretion.components.intake.versions import entry_fields

    store = Store(tmp_path / "working")
    entity = attributed_entity(store)
    case = Cases(store).create(entity["id"])
    entry = case["entries"][0]
    before = store.one("SELECT payload FROM entries WHERE id=?", (entry["id"],))["payload"]
    with store.transaction() as db:
        db.execute(
            "INSERT INTO case_entry_conditions VALUES(?,?,?)",
            (case["case_id"], entry["id"], json.dumps([ID])),
        )
    scoped = Cases(store).view(case["case_id"])["entries"][0]
    assert entry_fields(scoped)["tag"] == ID
    assert scoped["source"] == entry["source"]
    assert store.one("SELECT payload FROM entries WHERE id=?", (entry["id"],))["payload"] == before
    with store.read_snapshot() as db:
        assert Cases(store).repository.reported_tags(db, case["case_id"]) == [ID]


def test_attribution_only_support_does_not_become_a_generic_finding():
    from modules.investigations.components.case_conditions import project
    from modules.investigations.components.notification_narrative_v2 import presentation_groups
    from modules.investigations.components.report_explainers import canonical_source_types

    entry = {
        "ip": "8.8.8.8",
        "source": {
            "fields": {"hostname": "mail.example.com", "tag": "eol-exchange", "version": "14.2"}
        },
        "normalized": {"profile": {"id": "scan_exchange"}},
    }
    support = project(entry, [])
    assert support["source"] == entry["source"]
    assert presentation_groups({"entries": [support]}, {}) == []
    assert canonical_source_types({"entries": [support]}) == []


def test_eol_condition_identity_preserves_scanner_tag_explainer():
    from modules.investigations.components.case_conditions import project
    from modules.investigations.components.finding_explainers import select_finding_explainers
    from modules.accretion.components.intake.versions import entry_fields

    entry = project(
        {
            "ip": "8.8.8.8",
            "source": {
                "fields": {"hostname": "mail.example.com", "tag": "eol-php", "version": "5.6.40"}
            },
            "normalized": {"profile": {"id": "scan_http_vulnerable"}},
        },
        ["eol-php:5.6"],
    )
    assert entry_fields(entry)["tag"] == "eol-php"
    assert entry["normalized"]["active_conditions"] == ["eol-php:5.6"]
    assert [s["id"] for s in select_finding_explainers({"entries": [entry]})] == ["http_eol_php"]


def test_new_case_keeps_only_new_condition_from_a_mixed_source_row(client, app):
    from modules.accretion.tests.support.awareness import ingest
    from modules.leads.components.lead_queue import LeadQueue
    from modules.accretion.components.intake.versions import entry_fields

    store = app.state.store
    queue = LeadQueue(store)
    old_cve, new_cve = "CVE-2024-12345", "CVE-2024-23456"
    ingest(client, app, tag=old_cve)
    incoming = queue.list()[0]
    prior_id = queue.start(incoming["id"], incoming["revision"])["case_id"]
    # This test isolates source scope from the separately exercised closure API.
    with store.transaction() as db:
        db.execute("UPDATE cases SET stage='closed' WHERE id=?", (prior_id,))
    before = Cases(store).view(prior_id)
    ingest(client, app, tag=old_cve + ";" + new_cve, timestamp="2026-11-06 01:02:03")
    incoming = queue.list()[0]
    current_id = queue.start(incoming["id"], incoming["revision"])["case_id"]
    current = Cases(store).view(current_id)
    assert [record["id"] for record in current["draft"]["cve_records"]] == [new_cve]
    assert all(old_cve not in entry_fields(entry)["tag"] for entry in current["entries"])
    assert any(old_cve in entry["source"]["fields"]["tag"] for entry in current["entries"])
    assert Cases(store).view(prior_id)["entries"] == before["entries"]
