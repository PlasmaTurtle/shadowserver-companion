"""Asset retries retain scope and evidence; choosing evidence is an explicit edit."""

from tests.support.qualification import registry_factory, capture_website

from contextlib import closing

import io
import json
import sqlite3
import threading
import time
import zipfile

import pytest

from attribution import AttributionModule, EvidenceStore, Settings, verify_export
from attribution.models import AttributionEvidence, DomainMatch, ProviderResult, ResponseSnapshot
from modules.attribution.components.asset_attribution import AssetAttributionJobs, asset_state
from tests.support.workbench import app, client, import_rows, observations


class Provider:
    name = "rdap"

    def __init__(self, store, calls, *, gate=None, started=None, partial=False, fail=False):
        self.store, self.calls = store, calls
        self.gate, self.started, self.partial, self.fail = gate, started, partial, fail

    def collect(self, ip, root_domain, **options):
        self.calls.append((ip, root_domain, options))
        if self.started:
            self.started.set()
        if self.gate:
            assert self.gate.wait(5)
        if self.fail:
            raise RuntimeError("Fixture provider failed")
        raw = json.dumps(
            {
                "objectClassName": "ip network",
                "startAddress": ip,
                "endAddress": ip,
                "remarks": [{"description": [root_domain]}],
            }
        ).encode()
        snapshot = ResponseSnapshot.create(
            "https://rdap.arin.net/registry/ip/" + ip,
            "https://rdap.arin.net/registry/ip/" + ip,
            200,
            {"content-type": "application/rdap+json"},
            raw,
        )
        self.store.save_snapshot(snapshot)
        evidence = AttributionEvidence(
            "rdap_keyword" if self.partial else "rdap",
            ip,
            "Fixture registry",
            snapshot.source_url,
            snapshot.retrieved_at,
            snapshot.snapshot_id,
            (),
            DomainMatch(root_domain, root_domain, "/remarks/0/description/0", root_domain),
            {"network_start": ip, "network_end": ip, "matched_words": ["example"]},
        )
        return ProviderResult(
            "no_match" if self.partial else "matched",
            None if self.partial else evidence,
            snapshot_ids=(snapshot.snapshot_id,),
            partial_evidence=(evidence,) if self.partial else (),
        )


def module_factory(calls, **provider_options):
    def factory(path, settings, cancel_event):
        store = EvidenceStore(path)
        module = AttributionModule(
            store,
            providers=[Provider(store, calls, **provider_options)],
            settings=Settings(interval=0, retries=0),
            cancel_event=cancel_event,
        )
        module._owns_store = True
        return module

    return factory


def scope(client, app, extra=()):
    import_rows(client, app, [*observations()[:4], *extra])
    return client.get("/api/cases/" + client.get("/api/cases").json()[0]["id"]).json()


def finished(jobs, identity):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = jobs.get(identity)
        if job["status"] not in ("running", "queued", "cancelling"):
            return job
        time.sleep(0.01)
    raise AssertionError("Asset job did not finish")


def selected_asset(lead):
    return next(entry["id"] for entry in lead["entries"] if entry["ip"] == "9.9.9.9")


def test_explicit_asset_refresh_retains_scope_evidence_and_adoption(client, app, tmp_path):
    lead = scope(client, app, [observations()[0]])
    jobs = app.state.asset_attribution_jobs
    calls = []
    jobs.module_factory = module_factory(calls)
    before = app.state.store.one("SELECT * FROM cases WHERE id=?", (lead["case_id"],))
    path = "/api/cases/" + lead["case_id"] + "/assets/attribution"
    assert client.get(path).json()["remaining"] == 0
    assert client.post(path, json={}).status_code == 422
    response = client.post(path, json={"entry_id": selected_asset(lead)})
    assert response.status_code == 200, response.text
    job = finished(jobs, response.json()["id"])
    assert job["status"] == "completed" and job["completed"] == 1 and not job["errors"]
    assert {call[0] for call in calls} == {"9.9.9.9"}
    assert client.get(path).json()["remaining"] == 0
    assert app.state.store.one("SELECT * FROM cases WHERE id=?", (lead["case_id"],)) == before
    assert client.post(path, json={}).status_code == 422
    lookup = job["results"][0]
    saved = client.get("/api/asset-attribution/results/" + lookup["id"]).json()
    evidence = saved["result"]["evidence"][0]
    assert len(saved["snapshots"][evidence["snapshot_id"]]["body_sha256"]) == 64
    zipped = client.get("/api/asset-attribution/results/" + lookup["id"] + "/evidence.zip")
    assert zipped.status_code == 200
    folder = tmp_path / "unpacked"
    with zipfile.ZipFile(io.BytesIO(zipped.content)) as archive:
        archive.extractall(folder)
    assert verify_export(folder)["valid"]
    adopt = "/api/asset-attribution/results/" + lookup["id"] + "/adopt"
    assert (
        client.post(adopt, json={"expected_revision": before["draft_revision"] + 1}).status_code
        == 422
    )
    response = client.post(adopt, json={"expected_revision": before["draft_revision"]})
    assert response.status_code == 200, response.text
    group = app.state.store.one("SELECT * FROM case_groups WHERE case_id=?", (lead["case_id"],))
    assert group["attribution_entry_id"] == lookup["entry_id"]
    assert json.loads(group["attribution"])["result_id"] == lookup["result_id"]
    after = app.state.store.one("SELECT * FROM cases WHERE id=?", (lead["case_id"],))
    assert after["draft_revision"] == before["draft_revision"] + 1
    assert (
        json.loads(app.state.store.one("SELECT attribution FROM domain_groups")["attribution"])[
            "ip"
        ]
        == "8.8.8.8"
    )

    from modules.investigations.components.report_snapshot import snapshot

    report = snapshot(app.state.store, lead["id"], lead["case_id"], capture_sections=())
    assert report["qualified_lead"]["whois"][0]["result_id"] == lookup["result_id"]
    assert evidence["snapshot_id"] in {item["id"] for item in report["source_snapshots"]}
    assert not report["source_integrity_issues"]


def test_cancel_duplicates_scope_and_failure_are_bounded(client, app):
    lead = scope(client, app)
    jobs, calls = app.state.asset_attribution_jobs, []
    started, gate = threading.Event(), threading.Event()
    jobs.module_factory = module_factory(calls, gate=gate, started=started)
    job = jobs.start(lead["case_id"], selected_asset(lead))
    assert started.wait(2) and jobs.busy()
    try:
        with pytest.raises(ValueError, match="already running"):
            jobs.start(lead["case_id"], selected_asset(lead))
        with pytest.raises(ValueError, match="outside"):
            jobs.start(lead["case_id"], "another-case-entry")
        private = next(entry for entry in lead["entries"] if entry["private_ip"])
        with pytest.raises(ValueError, match="No remaining"):
            jobs.start(lead["case_id"], private["id"])
        assert jobs.cancel(job["id"])["status"] == "cancelling"
    finally:
        gate.set()
    result = finished(jobs, job["id"])
    assert result["status"] == "cancelled" and len(calls) == 1 and not jobs.busy()
    jobs.module_factory = module_factory(calls, fail=True)
    result = finished(jobs, jobs.start(lead["case_id"], selected_asset(lead))["id"])
    assert result["status"] == "completed" and result["errors"]
    assert not jobs.busy()


def test_partial_match_cannot_be_adopted_and_finished_checks_survive_restart(client, app):
    lead = scope(client, app)
    jobs, calls = app.state.asset_attribution_jobs, []
    jobs.module_factory = module_factory(calls, partial=True)
    result = finished(jobs, jobs.start(lead["case_id"], selected_asset(lead))["id"])
    assert {record["status"] for record in result["results"]} == {"review"}
    record = result["results"][0]
    response = client.post(
        "/api/asset-attribution/results/" + record["id"] + "/adopt",
        json={"expected_revision": lead["draft_revision"]},
    )
    assert response.status_code == 422 and "exact match" in response.text
    fresh = AssetAttributionJobs(app.state.store)
    try:
        state = fresh.state(lead["case_id"])
        assert state["job"] is None
        assert (
            sum(
                (asset["latest_lookup"] or {}).get("status") == "review"
                for asset in state["assets"]
            )
            == 1
        )
        assert state["remaining"] == 0
        assert all(asset["supported"] for asset in state["assets"] if asset["eligible"])
    finally:
        fresh.close()


def test_frozen_case_and_frozen_sections_block_adoption(client, app, monkeypatch):
    lead = scope(client, app)
    jobs = app.state.asset_attribution_jobs
    jobs.module_factory = module_factory([])
    result = finished(jobs, jobs.start(lead["case_id"], selected_asset(lead))["id"])
    route = "/api/asset-attribution/results/" + result["results"][0]["id"] + "/adopt"
    from modules.investigations.components.reviews.queries import SectionReviewQueries

    def locked(self, db, case_id, keys):
        assert "attribution" in keys and "vulnerabilities" in keys
        raise ValueError("Reopen these frozen sections")

    monkeypatch.setattr(SectionReviewQueries, "assert_editable", locked)
    assert (
        "frozen sections"
        in client.post(route, json={"expected_revision": lead["draft_revision"]}).text
    )
    with app.state.store.transaction() as db:
        db.execute("UPDATE cases SET stage='pending_notification' WHERE id=?", (lead["case_id"],))
    assert (
        "Revise the certified report"
        in client.post(route, json={"expected_revision": lead["draft_revision"]}).text
    )


def test_corrupt_saved_evidence_is_not_supported_or_adoptable(client, app):
    lead = scope(client, app)
    jobs = app.state.asset_attribution_jobs
    jobs.module_factory = module_factory([])
    result = finished(jobs, jobs.start(lead["case_id"], selected_asset(lead))["id"])
    lookup = result["results"][0]
    saved = client.get("/api/asset-attribution/results/" + lookup["id"]).json()
    selected = client.post(
        "/api/asset-attribution/results/" + lookup["id"] + "/adopt",
        json={"expected_revision": lead["draft_revision"]},
    )
    assert selected.status_code == 200
    snapshot_id = saved["result"]["evidence"][0]["snapshot_id"]
    with closing(sqlite3.connect(app.state.store.root / "attribution.sqlite3")) as db, db:
        for (name,) in db.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='snapshots'"
        ):
            db.execute('DROP TRIGGER "' + name + '"')
        db.execute("UPDATE snapshots SET body=? WHERE id=?", (b"{}", snapshot_id))
    state = jobs.state(lead["case_id"])
    row = next(row for row in state["assets"] if row["entry_id"] == lookup["entry_id"])
    assert row["status"] == "evidence_unavailable" and not row["supported"]
    assert (
        client.post(
            "/api/asset-attribution/results/" + lookup["id"] + "/adopt",
            json={"expected_revision": lead["draft_revision"]},
        ).status_code
        == 422
    )


def test_group_coverage_supports_related_hostnames_without_extra_asset_lookups(client, app):
    lead = scope(client, app, [{**observations()[2], "hostname": "other.example.com"}])
    state, entries = asset_state(app.state.store, lead["case_id"])
    assert state["remaining"] == 0
    assert all(row["supported"] for row in state["assets"] if row["eligible"])
    assert {row["support_basis"] for row in state["assets"] if row["eligible"]} == {
        "matched_address",
        "group_attribution",
    }
    assert not app.state.store.all("SELECT * FROM case_asset_attributions")


def test_entity_merge_keeps_case_with_asset_lookup_history(client, app):
    from tests.support.workbench import FakeRegistry

    lead = scope(client, app)
    jobs = app.state.asset_attribution_jobs
    jobs.module_factory = module_factory([])
    result = finished(jobs, jobs.start(lead["case_id"], selected_asset(lead))["id"])

    class Other(FakeRegistry):
        def lookup(self, ip):
            record = super().lookup(ip)
            return type(record)(
                record.ip,
                record.registry,
                record.source_url,
                record.retrieved_at,
                {"contact": "support@another.com"},
            )

    app.state.intake.attribution_factory = registry_factory(Other)
    import_rows(
        client,
        app,
        [{**observations()[0], "hostname": "mail.another.com", "ip": "8.8.4.4"}],
        "other.csv",
    )
    target = next(row for row in client.get("/api/leads").json() if row["id"] != lead["id"])
    source = client.get("/api/leads/" + lead["id"]).json()
    response = client.post(
        "/api/entities/" + lead["id"] + "/merge",
        json={
            "target_id": target["id"],
            "source_revision": source["entity_revision"],
            "target_revision": target["draft_revision"],
        },
    )
    assert response.status_code == 200, response.text
    assert (
        app.state.store.one("SELECT entity_id FROM cases WHERE id=?", (lead["case_id"],))[
            "entity_id"
        ]
        == target["id"]
    )
    assert (
        len(
            app.state.store.all(
                "SELECT * FROM case_asset_attributions WHERE case_id=?", (lead["case_id"],)
            )
        )
        == 1
    )
    assert (
        client.get("/api/asset-attribution/results/" + result["results"][0]["id"]).status_code
        == 200
    )
    assert app.state.store.all("PRAGMA foreign_key_check") == []
