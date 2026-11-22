"""Release invariants: provenance, grouping, migration, source failures and real adapter."""

from tests.support.qualification import registry_factory, capture_website

import copy
import hashlib
import io
import json
from modules.workspace.components import compact_json
import sqlite3
import zipfile
from pathlib import Path

import httpx
import pytest
import requests
from tests.session_helpers import TestClient

from attribution import AttributionModule, EvidenceStore, RdapProvider, Settings, verify_export
from modules.accretion.components.intake import EntryValidator, SourceObservation, read_entries
from modules.workspace.components.api import create_app
from modules.attribution.components.attribution_bridge import RegistrationAttribution
from modules.library.components.cve_sources import verify, summarize
from modules.accretion.components.intake_service import IntakeService
from modules.workspace.components.store import Store
from modules.workspace.databases.migrations import SCHEMA_VERSION
from tests.support.workbench import (
    FakeRegistry,
    csv_bytes,
    observations,
    import_rows,
    ready,
    attach,
    app,
    client,
)
from tests.schema_helpers import legacy_database


def cve_record(cve_id="CVE-2025-12345", state="PUBLISHED"):
    return {
        "cveMetadata": {"cveId": cve_id, "state": state, "dateUpdated": "2026-11-06T00:00:00Z"},
        "containers": {
            "cna": {
                "descriptions": [
                    {
                        "lang": "en",
                        "value": "Synthetic record, not a real vulnerability assessment.",
                    }
                ],
                "affected": [
                    {
                        "vendor": "Fixture",
                        "product": "Example",
                        "versions": [{"version": "1.0", "status": "affected"}],
                    }
                ],
                "references": [{"url": "https://example.com/advisory"}],
            },
            "adp": [{"references": [{"url": "https://example.com/program-reference"}]}],
        },
    }


def response(body, status=200):
    r = requests.Response()
    r.status_code = status
    r.headers["Content-Type"] = "application/json"
    r._content = json.dumps(body).encode()
    r._content_consumed = True
    return r


def test_version_optional_only_for_cve_and_numbered_subdomain_preserved():
    f = {
        **observations()[0],
        "region": "NORTH CAROLINA",
        "hostname": "mail2.example.com",
        "tag": "cve-2025-12345",
    }
    del f["version"]
    item = SourceObservation("report.csv", "CSV", 2, f)
    assert EntryValidator({"North Carolina"}).validate_entry(item).source.fields == f
    assert "version" not in item.fields
    for tag in ("eol-php", "cve-2025-12345;eol", "php"):
        altered = SourceObservation("report.csv", "CSV", 2, {**f, "tag": tag})
        assert EntryValidator({"North Carolina"}).rejection_reason(altered) == "missing_version"
    numeric = SourceObservation(
        "report.csv", "CSV", 2, {**f, "hostname": "1happy1horse1supply.com"}
    )
    assert EntryValidator({"North Carolina"}).validate_entry(numeric)
    assert EntryValidator({"North Carolina"}, exclude_numeric_roots=True).validate_entry(numeric)


def test_fixture_colors_cannot_affect_filter_decisions():
    path = Path(__file__).parent / "fixtures/selection_policy_sample.csv"
    sources = list(read_entries(path, ""))
    validator = EntryValidator({"North Carolina"})
    yellow = []
    for entry in sources:
        original = validator.rejection_reason(entry)
        altered = SourceObservation(
            entry.workbook,
            entry.sheet,
            entry.row,
            {**entry.fields, "review_color": "red", "expected_result": "reject"},
        )
        assert validator.rejection_reason(altered) == original
        if entry.fields["review_color"] == "yellow":
            yellow.append(original)
    assert yellow == [None] * 4


@pytest.mark.parametrize(
    "state,status", [("PUBLISHED", "published"), ("REJECTED", "rejected"), ("RESERVED", "reserved")]
)
def test_cve_state_and_snapshot_preserved(tmp_path, monkeypatch, state, status):
    store = Store(tmp_path)
    calls = []

    def fetch(*args, **kwargs):
        calls.append(args[0])
        return response(cve_record(state=state))

    monkeypatch.setattr("modules.library.components.intelligence.acquisition._response_get", fetch)
    result = verify(store, "cve-2025-12345")
    assert result["verification_status"] == status
    assert (
        hashlib.sha256(store.path(result["record_path"]).read_bytes()).hexdigest()
        == result["body_sha256"]
    )
    cached = verify(store, "CVE-2025-12345")
    assert cached["from_cache"] and len(calls) == 2
    assert cached["retrieved_at"] == result["retrieved_at"]
    if state == "PUBLISHED":
        assert "https://example.com/program-reference" in result["references"]
        assert result["affected"][0]["product"] == "Example"


@pytest.mark.parametrize(
    "code,status", [(404, "not_found"), (429, "deferred"), (503, "unavailable")]
)
def test_cve_service_failure_does_not_invent_published_record(tmp_path, monkeypatch, code, status):
    monkeypatch.setattr(
        "modules.library.components.intelligence.acquisition._response_get",
        lambda *a, **k: response({"error": "unavailable"}, code),
    )
    result = verify(Store(tmp_path), "CVE-2025-12345")
    assert result["verification_status"] == status and result["cvss"] is None
    assert not result["record_path"] and result["errors"]
    assert all(
        attempt.get("response", {}).get("response_retention") == "metadata-only"
        for attempt in result["acquisition"]
    )


def test_wrong_cve_id_or_incomplete_record_not_verified(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "modules.library.components.intelligence.acquisition._response_get",
        lambda *a, **k: response(cve_record("CVE-2025-99999")),
    )
    result = verify(Store(tmp_path), "CVE-2025-12345")
    assert result["verification_status"] == "unavailable"
    assert "does not match" in result["errors"][0]
    with pytest.raises(ValueError):
        summarize(
            "CVE-2025-12345", {"cveMetadata": {"cveId": "CVE-2025-12345", "state": "PUBLISHED"}}
        )


def test_new_entity_named_for_hostname_and_rename_preserves_hostname(client, app):
    import_rows(client, app)
    lead = client.get("/api/leads").json()[0]
    assert lead["company"] == "mail.example.com"
    result = client.put(
        "/api/entities/" + lead["id"] + "/name",
        json={"name": "Example Supply LLC", "expected_revision": 0},
    )
    assert result.status_code == 200, result.text
    value = result.json()
    assert value["company"] == "Example Supply LLC"
    assert value["hostnames"] == [{"name": "mail.example.com", "root_domain": "example.com"}]
    assert value["entries"][0]["source"]["fields"]["hostname"] == "mail.example.com"
    stale = client.put(
        "/api/entities/" + lead["id"] + "/name", json={"name": "Stale edit", "expected_revision": 0}
    )
    assert stale.status_code == 422


def test_merge_keeps_all_rows_source_draft_and_completed_files(client, app):
    import_rows(client, app)
    first = client.get("/api/leads").json()[0]["id"]
    ready(client, first)
    report = client.post("/api/leads/" + first + "/finalize").json()
    original = app.state.store.path(report["path"]) / "snapshot.json"
    digest = hashlib.sha256(original.read_bytes()).hexdigest()

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
    rows = [{**observations()[0], "hostname": "mail2.another.com", "ip": "8.8.4.4"}]
    import_rows(client, app, rows, "another.csv")
    target = next(x for x in client.get("/api/leads").json() if x["id"] != first)
    target_case = client.get("/api/leads/" + target["id"]).json()
    assert (
        client.put(
            "/api/cases/" + target_case["case_id"] + "/plan",
            json={
                "expected_version": target_case["case"]["version"],
                "next_action": "Locate contact",
            },
        ).status_code
        == 200
    )
    source = client.get("/api/leads/" + first).json()
    result = client.post(
        "/api/entities/" + first + "/merge",
        json={
            "target_id": target["id"],
            "source_revision": source["entity_revision"],
            "target_revision": target["draft_revision"],
        },
    )
    assert result.status_code == 200, result.text
    merged = client.get("/api/entities/" + target["id"]).json()
    assert len(merged["entries"]) == 5 and len(merged["domain_groups"]) == 2
    assert len(merged["cases"]) == 2
    source_case = client.get("/api/cases/" + source["case_id"]).json()
    assert source_case["case"]["entity_id"] == target["id"] and len(source_case["entries"]) == 3
    assert len(source_case["scope_source_entries"]) == 4
    assert len(client.get("/api/leads").json()) == 1
    assert len(client.get("/api/leads?q=mail.example.com").json()) == 1
    assert client.get("/api/leads/" + first).json()["id"] == target["id"]
    assert (
        merged["reports"][0]["entity_id"] == target["id"]
        and merged["reports"][0]["lead_id"] == first
    )
    assert hashlib.sha256(original.read_bytes()).hexdigest() == digest
    prior = client.get("/api/entities/" + first + "/archived-draft.json").json()
    assert prior["draft"]["company"] == "Example Company"
    assert client.get("/api/dashboard").json()["counts"]["completed"] == 1
    exported = client.get("/api/leads/" + target["id"] + "/json").json()
    assert sum(len(g["entries"]) for g in exported["validated_leads"]) == 5
    assert exported["validated_leads"][0]["entries"][0]["ip"] == exported["whois"][0]["ip"]
    # A handled repeat resolves the merged owner and stops at the local gate.
    # The new raw observation remains in Dark Matter, not in active case scope.
    app.state.intake.attribution_factory = registry_factory(FakeRegistry)
    import_rows(
        client,
        app,
        [{**observations()[0], "ip": "8.8.8.8", "timestamp": "2026-11-06 15:00:00"}],
        "next.csv",
    )
    assert len(client.get("/api/leads").json()) == 1
    assert len(client.get("/api/entities/" + target["id"]).json()["entries"]) == 5
    archived = app.state.store.dark_matter.query(q="next.csv")
    assert archived["total"] == 1
    assert archived["items"][0]["reason"] == "no_actionable_findings"
    # A later observation joins the entity inventory without silently expanding
    # the certified notification's scope or changing its historical package.
    prior_case = client.get("/api/cases/" + source["case_id"]).json()
    assert len(prior_case["entries"]) == 3
    assert len(prior_case["scope_source_entries"]) == 4
    assert prior_case["case"]["stage"] == "pending_notification"
    assert hashlib.sha256(original.read_bytes()).hexdigest() == digest


def test_schema_one_upgrade_preserves_report_and_creates_backup(client, app):
    import_rows(client, app)
    lead_id = client.get("/api/leads").json()[0]["id"]
    ready(client, lead_id)
    report = client.post("/api/leads/" + lead_id + "/finalize").json()
    store = app.state.store
    before = store.path(report["path"]) / "notification.pdf"
    digest = hashlib.sha256(before.read_bytes()).hexdigest()
    legacy_database(store, version=1)
    migrated = Store(store.root)
    assert migrated.lead(lead_id)["hostnames"]
    assert migrated.lead(lead_id)["reports"][0]["entity_id"] == lead_id
    assert list((store.root / "backups").glob(f"before-schema-{SCHEMA_VERSION}-*.sqlite3"))
    assert hashlib.sha256(before.read_bytes()).hexdigest() == digest
    Store(store.root)  # Idempotent reopen.


def test_production_adapter_raw_bundle_and_stop_after_match(tmp_path, monkeypatch):
    import modules.attribution.components.attribution_bridge as bridge

    calls = []

    def server(request):
        url = str(request.url)
        calls.append(url)
        if url == "https://data.iana.org/rdap/ipv4.json":
            data = {"services": [[["0.0.0.0/0"], ["https://rdap.arin.net/registry/"]]]}
        else:
            domain = "example.com" if url.endswith("/8.8.8.8") else "other.com"
            ip = url.rsplit("/", 1)[-1]
            data = {
                "objectClassName": "ip network",
                "handle": "TEST",
                "startAddress": ip,
                "endAddress": ip,
                "entities": [
                    {
                        "objectClassName": "entity",
                        "handle": "TESTORG",
                        "vcardArray": ["vcard", [["email", {}, "text", "it@" + domain]]],
                    }
                ],
            }
        return httpx.Response(
            200,
            headers={"content-type": "application/rdap+json"},
            stream=httpx.ByteStream(json.dumps(data).encode()),
        )

    def open_module(path, settings, *, cancel_event=None):
        store = EvidenceStore(path)
        provider = RdapProvider(
            store, settings, transport=httpx.MockTransport(server), cancel_event=cancel_event
        )
        module = AttributionModule(
            store, providers=[provider], settings=settings, cancel_event=cancel_event
        )
        module._owns_store = True
        module._owned = [provider]
        return module

    monkeypatch.setattr(bridge.AttributionModule, "open", open_module)
    application = create_app(tmp_path / "data", worker=False, capture=capture_website)
    with TestClient(application) as client:
        client.headers["X-Workbench-Token"] = client.get("/api/bootstrap").json()["token"]
        imported = client.post(
            "/api/imports",
            files=[("files", ("fixture.csv", csv_bytes(observations()), "text/csv"))],
        ).json()[0]
        application.state.intake.process(imported["id"])
        lead = client.get("/api/leads").json()[0]
        detail = client.get("/api/leads/" + lead["id"]).json()
        assert detail["entries"][0]["ip"] == "8.8.8.8"
        assert len(calls) == 3 and not any("/9.9.9.9" in c for c in calls)
        assert len(detail["entries"]) == 4 and detail["attribution"]["result_id"]
        assert "case_id" not in detail and detail["cases"] == []
        record = client.get("/api/leads/" + lead["id"] + "/json")
        assert record.status_code == 200, record.text
        assert record.json()["entity_id"] == lead["id"]
        assert len(record.json()["validated_leads"][0]["entries"]) == 4
        assert record.json()["whois"][0]["result_id"] == detail["attribution"]["result_id"]
        bundle = client.get("/api/leads/" + lead["id"] + "/attribution.zip")
        assert bundle.status_code == 200
        with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
            archive.extractall(tmp_path / "export")
        directory = next((tmp_path / "export").iterdir())
        assert verify_export(directory)["valid"]
        assert not application.state.store.all("SELECT * FROM cases")
        assert client.get("/api/pending-leads").json()[0]["entity_id"] == lead["id"]
        ready(client, lead["id"])
        report = client.post("/api/leads/" + lead["id"] + "/finalize")
        assert report.status_code == 200, report.text
        package = application.state.store.path(report.json()["path"])
        assert list((package / "registration").glob("*/responses/*.json"))
        backup = client.post("/api/backup")
        with zipfile.ZipFile(io.BytesIO(backup.content)) as archive:
            assert "data/attribution.sqlite3" in archive.namelist()


def test_cve_only_import_completes_with_preserved_reference_bytes(client, app, monkeypatch):
    from modules.library.tests.support.cve_catalog import catalog_record

    monkeypatch.setattr(
        "modules.library.components.intelligence.acquisition.catalog_record",
        lambda *_: catalog_record(),
    )
    monkeypatch.setattr(
        "modules.library.components.intelligence.acquisition._response_get",
        lambda *a, **k: pytest.fail("Notification intake must use the local CVE catalog"),
    )
    row = {**observations()[0], "ip": "8.8.8.8", "tag": "cve-2025-12345"}
    del row["version"]
    import_rows(client, app, [row])
    lead_id = client.get("/api/leads").json()[0]["id"]
    detail = client.get("/api/leads/" + lead_id).json()
    record = detail["draft"]["cve_records"][0]
    assert record["verification_status"] == "published"
    assert record["from_catalog"] and record["local_only"]
    assert "version" not in detail["entries"][0]["source"]["fields"]
    assert "versions include" not in detail["draft"]["narrative"]
    ready(client, lead_id, validate=False)
    attach(client, lead_id, "cve")
    ready(client, lead_id)
    result = client.post("/api/leads/" + lead_id + "/finalize")
    assert result.status_code == 200, result.text
    directory = app.state.store.path(result.json()["path"])
    snapshot = compact_json.loads((directory / "snapshot.json").read_text(encoding="utf-8"))
    archived = snapshot["draft"]["cve_records"][0]
    assert (
        hashlib.sha256((directory / archived["record_path"]).read_bytes()).hexdigest()
        == record["body_sha256"]
    )
    assert snapshot["assets"][0]["version"] == ""
