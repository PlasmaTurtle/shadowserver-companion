"""Entry readiness, registration identity and contact-first entity workflows."""

from copy import deepcopy
import json
import sqlite3
import pytest

from test_workbench import app, client
from test_lead_frontier_0991 import ingest
from test_contacts_api_090 import FixtureCore, finished
from test_accretion_intake import row, report, seed, run_import
from test_accretion_scoring import entry, vetted, ID
from workbench import accretion
from workbench.intake_service import IntakeService
from workbench.intake_progress import catalog_readiness, overview
from workbench.registry_profile import extract, seed_entity
from workbench.store import Store
from workbench.lead_queue import LeadQueue


def registration():
    return {
        "evidence": {
            "method": "rdap",
            "match": {
                "matched_domain": "example.com",
                "field_path": "/entities/0/vcardArray/1/3/3",
            },
        },
        "record": {
            "entities": [
                {
                    "handle": "ACME",
                    "roles": ["registrant"],
                    "vcardArray": [
                        "vcard",
                        [
                            ["kind", {}, "text", "org"],
                            ["fn", {}, "text", "Example Manufacturing"],
                            [
                                "adr",
                                {},
                                "text",
                                ["", "", "123 Main St", "Asheville", "NC", "28801", "US"],
                            ],
                            ["email", {}, "text", "it@example.com"],
                        ],
                    ],
                }
            ]
        },
        "source_url": "https://rdap.arin.net/registry/entity/ACME",
        "retrieved_at": "2026-11-12T12:00:00Z",
        "snapshot_id": "snapshot",
        "result_id": "result",
    }


def test_catalog_absent_partial_and_ready_states(tmp_path, monkeypatch):
    root = tmp_path / "work"
    assert catalog_readiness(root)["state"] == "missing"
    seed(root)
    assert catalog_readiness(root)["state"] == "partial"
    from workbench.cve_catalog.storage import CatalogStorage

    base = {"total": 300000, "bootstrap_complete": True, "stale": False, "last_success_at": "today"}
    monkeypatch.setattr(CatalogStorage, "status", lambda self: base)
    assert catalog_readiness(root)["state"] == "ready"
    base["stale"] = True
    assert catalog_readiness(root)["state"] == "stale"

    def broken(self):
        raise sqlite3.DatabaseError("unavailable")

    monkeypatch.setattr(CatalogStorage, "status", broken)
    assert catalog_readiness(root)["state"] == "unavailable"


def test_catalog_revision_allows_re_evaluating_the_same_original(tmp_path):
    store = Store(tmp_path / "work")
    intake = IntakeService(store)
    data = report([row()])
    first = intake.enqueue("scan_http_vulnerable.csv", data)
    assert intake.enqueue("scan_http_vulnerable.csv", data)["id"] == first["id"]
    seed(store.root)
    second = intake.enqueue("scan_http_vulnerable.csv", data)
    assert second["id"] != first["id"]
    config = json.loads(
        store.one("SELECT config FROM imports WHERE id=?", (first["id"],))["config"]
    )
    assert config["catalog_at_import"]["state"] == "missing"


def test_progress_tracks_stages_and_retains_missing_catalog_warning(tmp_path, monkeypatch):
    from workbench import intake_progress

    store = Store(tmp_path / "work")
    stages = []
    original = intake_progress.publish

    def record(*args, **kwargs):
        stages.append(args[3])
        return original(*args, **kwargs)

    monkeypatch.setattr(intake_progress, "publish", record)
    _, _, result, _ = run_import(store, [row(severity="critical"), row(hostname="bad host")])
    data = overview(store)
    assert data["current"]["progress"]["phase"] == "complete"
    assert data["current"]["catalog_at_scoring"]["state"] == "missing"
    assert data["current"]["stats"]["admitted_rows"] == 1
    assert data["recent"]["source_rows"] == 2
    assert sum(r["count"] for r in data["recent"]["failures"]) == 1
    assert all(stage in stages for stage in ("filter", "qualify", "urgency", "complete"))
    seed(store.root)
    assert overview(store)["current"]["catalog_at_scoring"]["state"] == "missing"
    assert overview(store)["catalog"]["state"] == "partial"


def test_provider_penalty_changes_rank_without_changing_evidence():
    evidence = {ID: vetted(kev=True, epss=0.95)}
    data = [entry()]
    ordinary = accretion.score_lead(data, root_domain="example.com", cve_records=evidence)
    provider = accretion.score_lead(data, root_domain="spectrum.com", cve_records=evidence)
    assert provider["aggregate"] == round(ordinary["aggregate"] * 0.1, 1)
    assert provider["aggregate"] <= 10 and provider["temperature"] == "cool"
    for key in ("quality", "urgency", "cves", "strongest_finding"):
        assert provider[key] == ordinary[key]
    assert provider["ranking_adjustments"][0]["id"] == "provider_outreach"
    for invalid in (True, -0.1, 1.1, float("nan")):
        with pytest.raises(ValueError):
            accretion.normalize_policy({"provider_outreach_multiplier": invalid})


def test_registration_extracts_only_the_matched_organization():
    source = registration()
    result = extract(source, "example.com")
    assert result["values"]["name"] == "Example Manufacturing"
    assert result["values"]["address"] == "123 Main St\nAsheville NC 28801\nUS"
    assert result["values"]["city"] == "Asheville"
    assert result["pointers"]["name"] == "/entities/0/vcardArray/1/1/3"
    source["evidence"]["match"]["matched_domain"] = "hosting.example.net"
    assert extract(source, "example.com") is None
    source = registration()
    source["record"]["name"] = "Example Network"
    source["evidence"]["match"]["field_path"] = "/name"
    assert extract(source, "example.com") is None


@pytest.mark.parametrize(
    "change", ["individual", "redacted", "dns", "missing_path", "keyword_pending"]
)
def test_registration_rejects_uncorrelated_or_unsuitable_identity(change):
    source = registration()
    if change == "individual":
        source["record"]["entities"][0]["vcardArray"][1][0][3] = "individual"
    elif change == "redacted":
        source["record"]["entities"][0]["vcardArray"][1][1][3] = "REDACTED FOR PRIVACY"
    elif change == "dns":
        source["evidence"]["method"] = "dns"
    elif change == "missing_path":
        source["evidence"]["match"]["field_path"] = "/entities/1/vcardArray"
    else:
        source["evidence"]["method"] = "rdap_keyword"
    assert extract(source, "example.com") is None


def test_registry_seed_preserves_cases_and_manual_fields(client, app):
    pending = ingest(client, app)
    store = app.state.store
    case = LeadQueue(store).start(pending["id"], pending["revision"])["case_id"]
    before = store.one("SELECT * FROM cases WHERE id=?", (case,))
    with store.transaction() as db:
        applied = seed_entity(db, pending["entity_id"], registration())
    assert set(applied) == {"name", "address", "city", "state"}
    entity = store.lead(pending["entity_id"])
    assert entity["company"] == "Example Manufacturing"
    assert entity["registry_profile_sources"]["address"]["snapshot_id"] == "snapshot"
    assert store.one("SELECT * FROM cases WHERE id=?", (case,)) == before
    newer = registration()
    newer["record"]["entities"][0]["vcardArray"][1][1][3] = "Another Company"
    with store.transaction() as db:
        assert seed_entity(db, pending["entity_id"], newer) == []
    assert store.lead(pending["entity_id"])["company"] == "Example Manufacturing"


def test_registry_migration_backfills_without_changing_case_history(client, app):
    from schema_helpers import restore_schema
    from workbench.migrations import SCHEMA_VERSION

    pending = ingest(client, app)
    store = app.state.store
    case = LeadQueue(store).start(pending["id"], pending["revision"])["case_id"]
    before = store.one("SELECT * FROM cases WHERE id=?", (case,))
    with store.transaction() as db:
        db.execute(
            "UPDATE leads SET attribution=? WHERE id=?",
            (json.dumps(registration()), pending["entity_id"]),
        )
        restore_schema(db, 13)
        db.execute("PRAGMA user_version=13")
    upgraded = Store(store.root)
    assert upgraded.lead(pending["entity_id"])["company"] == "Example Manufacturing"
    assert upgraded.one("SELECT * FROM cases WHERE id=?", (case,)) == before
    assert (
        len(list((store.root / "backups").glob(f"before-schema-{SCHEMA_VERSION}-*.sqlite3"))) == 1
    )
    Store(store.root)
    assert not upgraded.all("PRAGMA foreign_key_check")


def test_contact_directory_is_read_only_and_complete_details_need_no_review(client, app):
    row = ingest(client, app)
    store, jobs = app.state.store, app.state.contact_discovery_jobs
    jobs.core_factory = lambda: FixtureCore([])
    finished(jobs, jobs.automatic_once()["id"])
    with store.transaction() as db:
        seed_entity(db, row["entity_id"], registration())
    before = store.all("SELECT * FROM contact_reviews")
    response = client.get(
        "/api/contact-discovery/overviews", params={"entity_ids": row["entity_id"]}
    )
    assert response.status_code == 200
    contact = response.json()[row["entity_id"]]
    assert contact["email"] or contact["phone"]
    entity = client.get("/api/entities/" + row["entity_id"]).json()
    assert entity["entity_review"]["complete"] and not entity["review_required"]
    assert store.all("SELECT * FROM contact_reviews") == before
    listing = client.get("/api/entities").json()
    assert listing[0]["entity_profile"]["address"]
    assert client.get("/api/entities?review_required=true").json() == []


def test_find_all_queues_gaps_and_explicit_refresh_uses_same_background_worker(client, app):
    row = ingest(client, app)
    jobs = app.state.contact_discovery_jobs
    jobs.core_factory = lambda: FixtureCore([])
    finished(jobs, jobs.automatic_once()["id"])
    total = len(app.state.store.all("SELECT * FROM contact_runs"))
    response = client.post("/api/contact-discovery/find-all")
    assert response.status_code == 200 and response.json()["queued"] == 1
    assert jobs.automatic_once() is None  # Complete contacts are not re-searched.
    assert len(app.state.store.all("SELECT * FROM contact_runs")) == total
    response = client.post("/api/entities/" + row["entity_id"] + "/contacts/refresh")
    assert response.status_code == 200 and response.json()["queued"] == 1
    job = jobs.automatic_once()
    assert job is not None
    finished(jobs, job["id"])
    assert len(app.state.store.all("SELECT * FROM contact_runs")) == total + 1
