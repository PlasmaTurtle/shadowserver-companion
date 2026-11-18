"""Canonical event identity and admission survive delivery and workflow changes."""

from contextlib import closing
import hashlib
import json

import pytest

from test_workbench import app, client, observations, ready
from test_lead_queue_098 import queue_import
from workbench.awareness import associate, counts, finding_ids, link_asset, mark_handled
from workbench.dark_matter import browse
from workbench.lead_queue import LeadQueue
from workbench.store import Store
from schema_helpers import remove_awareness_schema


def ingest(client, app, **changes):
    row = {**observations()[2], **changes}
    result, _ = queue_import(client, app, [row], "scan_http_vulnerable.csv")
    assert (
        app.state.store.one("SELECT status FROM imports WHERE id=?", (result["id"],))["status"]
        == "done"
    )
    return result


def tally(store):
    with store.read_snapshot() as db:
        return counts(db)


def test_reordered_delivery_deduplicates_events_and_cve_memberships(client, app):
    rows = [
        {**observations()[2], "tag": "CVE-2024-12345;CVE-2024-23456"},
        {**observations()[2], "hostname": "web.example.com", "tag": "CVE-2024-12345"},
    ]
    queue_import(client, app, rows, "scan_http_vulnerable.csv")
    before = tally(app.state.store)
    queue_import(client, app, list(reversed(rows)), "scan_http_vulnerable.csv")
    after = tally(app.state.store)
    assert before == after
    assert after["observations"] == 2 and after["findings"] == 3
    assert after["observation_days"] == 1
    assert len(app.state.store.all("SELECT * FROM awareness_sources")) == 4
    assert len(LeadQueue(app.state.store).list()) == 1


def test_repeat_measurements_count_density_not_findings(client, app):
    ingest(client, app, timestamp="2026-11-01 01:00:00")
    ingest(client, app, timestamp="2026-11-01 02:00:00")
    ingest(client, app, timestamp="2026-11-02 01:00:00")
    values = tally(app.state.store)
    assert values["observations"] == 3
    assert values["findings"] == 1
    assert values["observation_days"] == 2
    assert values["dark_matter_observations"] == 0


def test_same_cve_changed_version_location_severity_keeps_identity(client, app):
    ingest(client, app, tag="CVE-2024-12345")
    before = app.state.store.one("SELECT id FROM awareness_findings")["id"]
    ingest(
        client,
        app,
        tag="CVE-2024-12345",
        timestamp="2026-11-05 01:02:03",
        version="9.9.99",
        city="Asheville",
    )
    rows = app.state.store.all("SELECT * FROM awareness_findings")
    assert len(rows) == 1 and rows[0]["id"] == before
    assert rows[0]["first_seen"] < rows[0]["last_seen"]
    assert browse(app.state.store)["total"] == 0


def test_unadmitted_repeat_cannot_revoke_approval_and_shared_ip_cannot_merge(client, app):
    result = ingest(client, app)
    store = app.state.store
    entry = json.loads(store.one("SELECT payload FROM entries")["payload"])
    with store.transaction() as db:
        first = associate(db, entry, import_id=result["id"], admitted=False, reason="later_retry")
        other = json.loads(json.dumps(entry))
        other["source"]["fields"]["hostname"] = "other.example.org"
        other["source"]["row"] = 900
        other["normalized"].pop("observation_ref", None)
        unresolved = associate(
            db, other, import_id=result["id"], admitted=False, reason="attribution_missing"
        )
    assert first["asset_id"] != unresolved["asset_id"]
    assert (
        store.one(
            "SELECT admitted FROM awareness_observations WHERE id=?", (first["observation_id"],)
        )["admitted"]
        == 1
    )
    assert (
        store.one("SELECT entity_id FROM awareness_assets WHERE id=?", (unresolved["asset_id"],))[
            "entity_id"
        ]
        is None
    )
    assert browse(store)["total"] == 1


def test_manual_rebrand_adds_asset_without_manufacturing_observation(client, app):
    ingest(client, app)
    store = app.state.store
    entity = store.one("SELECT id FROM leads")["id"]
    before = tally(store)
    with store.transaction() as db:
        linked = link_asset(db, "example.org", entity)
        assert linked["entity_id"] == entity
    assert tally(store) == before
    assert len(store.all("SELECT * FROM awareness_assets")) == 2


def test_handled_cve_remains_approved_and_new_cve_adds_only_new_scope(client, app):
    ingest(client, app, tag="CVE-2024-12345")
    store = app.state.store
    queue = LeadQueue(store)
    row = queue.list()[0]
    case_id = queue.start(row["id"], row["revision"])["case_id"]
    old_case = store.one("SELECT * FROM cases WHERE id=?", (case_id,))
    # mark_handled is also called by new scope creation. Explicitly exercising
    # its public contract makes this independent of catalog capture adapters.
    with store.transaction() as db:
        mark_handled(db, json.loads(store.one("SELECT payload FROM entries")["payload"]), case_id)
    ingest(client, app, tag="CVE-2024-12345", timestamp="2026-11-05 01:02:03", version="8.9.9")
    assert queue.list() == []
    assert browse(store)["total"] == 0
    ingest(client, app, tag="CVE-2024-12345;CVE-2024-23456", timestamp="2026-11-06 01:02:03")
    rows = queue.list()
    assert len(rows) == 1
    entry = queue.detail(rows[0]["id"])["entries"][0]
    assert entry["normalized"]["active_cves"] == ["CVE-2024-23456"]
    assert store.one("SELECT * FROM cases WHERE id=?", (case_id,)) == old_case


def test_schema14_backfill_recovers_original_events_without_rewriting_cases(client, app):
    ingest(client, app, timestamp="2026-11-01 01:00:00")
    ingest(client, app, timestamp="2026-11-02 01:00:00")
    store = app.state.store
    row = LeadQueue(store).list()[0]
    LeadQueue(store).start(row["id"], row["revision"])
    ready(client, row["entity_id"])
    assert len(store.all("SELECT * FROM section_validations")) == 5
    tables = ("imports", "cases", "case_entries", "case_groups", "section_validations")
    before = {table: store.all("SELECT * FROM " + table) for table in tables}
    originals = {
        r["path"]: hashlib.sha256(store.path(r["path"]).read_bytes()).hexdigest()
        for r in before["imports"]
    }
    with closing(store.connect()) as db:
        db.execute("PRAGMA foreign_keys=OFF")
        remove_awareness_schema(db)
        db.execute("PRAGMA user_version=14")
        db.commit()
    upgraded = Store(store.root)
    assert tally(upgraded)["observations"] == 2
    assert tally(upgraded)["findings"] == 1
    assert {table: upgraded.all("SELECT * FROM " + table) for table in tables} == before
    assert {
        path: hashlib.sha256(upgraded.path(path).read_bytes()).hexdigest() for path in originals
    } == originals
    assert upgraded.all("PRAGMA foreign_key_check") == []
    second = Store(store.root)
    assert tally(second) == tally(upgraded)


def test_undated_reexports_do_not_fabricate_observation_days(client, app):
    result = ingest(client, app)
    store = app.state.store
    source = json.loads(store.one("SELECT payload FROM entries")["payload"])
    source["source"]["fields"].pop("timestamp")
    source["normalized"].pop("observation_ref", None)
    with store.transaction() as db:
        source["source"]["row"] = 80
        a = associate(db, source, import_id=result["id"], admitted=False)
        source["source"]["row"] = 81
        b = associate(db, source, import_id=result["id"], admitted=False)
    assert a["observation_id"] == b["observation_id"]
    assert (
        store.one(
            "SELECT observed_at FROM awareness_observations WHERE id=?", (a["observation_id"],)
        )["observed_at"]
        == ""
    )


def test_unqualified_endpoint_cannot_replace_approved_representative(client, app):
    result = ingest(client, app, tag="CVE-2024-12345")
    store = app.state.store
    prior = store.one("SELECT * FROM awareness_findings")
    entry = json.loads(store.one("SELECT payload FROM entries")["payload"])
    entry["normalized"].pop("observation_ref", None)
    entry["source"]["row"] = 88
    entry["source"]["fields"].update(ip="9.9.9.9", timestamp="2026-11-07 01:00:00")
    entry["ip"] = "9.9.9.9"
    with store.transaction() as db:
        unqualified = associate(
            db, entry, import_id=result["id"], admitted=False, reason="new_endpoint"
        )
    after = store.one("SELECT * FROM awareness_findings")
    assert after == prior
    assert unqualified["observation_id"] != prior["latest_observation_id"]
    assert browse(store)["total"] == 1


def test_new_condition_on_known_measurement_requires_own_admission(client, app):
    result = ingest(client, app, tag="CVE-2024-12345")
    store = app.state.store
    entry = json.loads(store.one("SELECT payload FROM entries")["payload"])
    entry["normalized"].pop("observation_ref", None)
    entry["source"]["row"] = 99
    entry["source"]["fields"]["tag"] = "CVE-2024-12345;CVE-2024-23456"
    with store.transaction() as db:
        associate(db, entry, import_id=result["id"], admitted=False, reason="pending_qualification")
    assert tally(store)["observations"] == 1
    assert (
        store.one("SELECT admitted FROM awareness_findings WHERE condition='CVE-2024-12345'")[
            "admitted"
        ]
        == 1
    )
    assert (
        store.one("SELECT admitted FROM awareness_findings WHERE condition='CVE-2024-23456'")[
            "admitted"
        ]
        == 0
    )


def test_first_admission_marks_existing_unapproved_condition_changed(client, app):
    result = ingest(client, app)
    store = app.state.store
    entry = json.loads(store.one("SELECT payload FROM entries")["payload"])
    entry["normalized"].pop("observation_ref", None)
    entry["source"]["row"] = 77
    entry["source"]["fields"]["tag"] = "CVE-2024-12345"
    with store.transaction() as db:
        result0 = associate(db, entry, import_id=result["id"], admitted=False)
        fid = result0["finding_ids"][0]
        db.execute(
            "UPDATE awareness_findings SET changed_at='2000-01-01T00:00:00Z' WHERE id=?", (fid,)
        )
        associate(db, entry, import_id=result["id"], admitted=True)
    finding = store.one("SELECT * FROM awareness_findings WHERE id=?", (fid,))
    assert finding["admitted"] == 1 and finding["changed_at"] > "2000-01-01"


def test_generic_eol_keeps_products_separate_and_case_overlay_keeps_identity():
    entry = {
        "source": {
            "fields": {
                "hostname": "mail.example.com",
                "tag": "eol",
                "product": "PHP",
                "version": "5.6.40",
                "protocol": "tcp",
                "port": "443",
            }
        },
        "normalized": {},
    }
    original = finding_ids(entry)
    entry["normalized"].update(case_condition_scope=True, active_conditions=["eol-php:5.6"])
    assert finding_ids(entry) == original
    entry["source"]["fields"]["product"] = "Other Product"
    assert finding_ids(entry) != original


def test_multiple_endpoints_preserve_evidence_without_repeat_freshness(client, app):
    rows = [
        {**observations()[2], "ip": ip, "tag": "CVE-2024-12345"}
        for ip in ("1.1.1.1", "8.8.8.8", "9.9.9.9")
    ]
    queue_import(client, app, rows, "scan_http_vulnerable.csv")
    store = app.state.store
    before = store.one("SELECT changed_at,last_fingerprint FROM awareness_findings")
    lead = LeadQueue(store).list()[0]
    assert lead["finding_count"] == 1
    assert len(LeadQueue(store).detail(lead["id"])["entries"]) == 3
    for row in rows:
        row["timestamp"] = "2026-11-05 01:02:03"
    queue_import(client, app, list(reversed(rows)), "scan_http_vulnerable.csv")
    assert store.one("SELECT changed_at,last_fingerprint FROM awareness_findings") == before
    latest = LeadQueue(store).list()[0]
    assert len(LeadQueue(store).detail(latest["id"])["entries"]) == 3
    # A later scan containing one endpoint moves the current report evidence
    # to that endpoint while the prior six observations remain history.
    queue_import(
        client, app, [{**rows[1], "timestamp": "2026-11-06 01:02:03"}], "scan_http_vulnerable.csv"
    )
    current = LeadQueue(store).list()[0]
    assert len(LeadQueue(store).detail(current["id"])["entries"]) == 1
    assert tally(store)["observations"] == 7


def test_missing_original_backfill_retains_saved_evidence_and_reports_warning(client, app):
    result = ingest(client, app)
    store = app.state.store
    original = store.one("SELECT path FROM imports WHERE id=?", (result["id"],))["path"]
    store.path(original).unlink()
    entries = store.all("SELECT * FROM entries")
    with closing(store.connect()) as db:
        db.execute("PRAGMA foreign_keys=OFF")
        remove_awareness_schema(db)
        db.execute("PRAGMA user_version=14")
        db.commit()
    upgraded = Store(store.root)
    assert upgraded.all("SELECT * FROM entries") == entries
    assert tally(upgraded)["findings"] == 1
    assert (
        upgraded.one("SELECT import_id FROM awareness_migration_warnings")["import_id"]
        == result["id"]
    )


def test_latest_raw_fields_keep_matching_source_and_cve_baselines(client, app):
    result = ingest(client, app, tag="CVE-2024-12345")
    store = app.state.store
    entry = json.loads(store.one("SELECT payload FROM entries")["payload"])
    entry["normalized"].pop("observation_ref", None)
    entry["normalized"]["accretion_cves"] = {"CVE-2024-12345": {"kev": False}}
    entry["source"]["row"] = 80
    with store.transaction() as db:
        first = associate(db, entry, import_id=result["id"], admitted=True)
        entry["source"]["row"] = 81
        entry["source"]["fields"]["tag"] = "CVE-2024-23456"
        entry["normalized"]["accretion_cves"] = {"CVE-2024-23456": {"kev": False}}
        second = associate(db, entry, import_id=result["id"], admitted=True)
    assert first["observation_id"] == second["observation_id"]
    event = store.one("SELECT * FROM awareness_observations WHERE id=?", (first["observation_id"],))
    source = store.one("SELECT * FROM awareness_sources WHERE source_key=?", (event["source_key"],))
    assert source["row_number"] == 81
    assert json.loads(event["summary"])["tag"] == "CVE-2024-23456"
    assert set(json.loads(event["normalized"])["accretion_cves"]) == {
        "CVE-2024-12345",
        "CVE-2024-23456",
    }
    a = store.one(
        "SELECT latest_source_key FROM awareness_findings WHERE condition='CVE-2024-12345'"
    )
    b = store.one(
        "SELECT latest_source_key FROM awareness_findings WHERE condition='CVE-2024-23456'"
    )
    assert a != b
    assert (
        store.one(
            "SELECT row_number FROM awareness_sources WHERE source_key=?", (a["latest_source_key"],)
        )["row_number"]
        == 80
    )
    assert (
        store.one(
            "SELECT row_number FROM awareness_sources WHERE source_key=?", (b["latest_source_key"],)
        )["row_number"]
        == 81
    )
