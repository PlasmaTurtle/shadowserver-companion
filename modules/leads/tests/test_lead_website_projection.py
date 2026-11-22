"""Lead images and website actions consume the retained qualification capture."""

import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from tests.support.workbench import app, client, observations
from tests.support.qualification import capture_website
from modules.investigations.components import website_evidence
from modules.leads.tests.support.lead_queue import queue_import


@pytest.mark.parametrize("remove_admitted_binding", [False, True])
def test_lead_and_case_use_the_exact_admitted_capture(client, app, remove_admitted_binding):
    store = app.state.store
    queue_import(client, app)
    lead = client.get("/api/pending-leads").json()[0]
    admitted = lead["website"]
    for url in (admitted["requested_url"], "https://sibling.example.com/"):
        png, meta = capture_website(url)
        meta["captured_at"] = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        capture = website_evidence.retain(store, png, meta, root_domain=lead["root_domain"])
        with store.transaction() as db:
            website_evidence.bind(
                db, capture["id"], lead["entity_id"], root_domain=lead["root_domain"]
            )
            if url == admitted["requested_url"]:
                # A refreshed job cannot replace the source-level admission.
                db.execute(
                    "UPDATE jobs SET qualification=json_set(qualification,'$.website.id',?) WHERE id=?",
                    (capture["id"], lead["job_id"]),
                )
    if remove_admitted_binding:
        with store.transaction() as db:
            db.execute("DELETE FROM website_capture_entities WHERE capture_id=?", (admitted["id"],))
    assert client.get("/api/entities/" + lead["entity_id"]).json()["website"]["id"] == capture["id"]
    expected = None if remove_admitted_binding else admitted
    assert client.get("/api/pending-leads").json()[0]["website"] == expected
    assert client.get("/api/pending-leads/" + lead["id"]).json()["website"] == expected
    response = client.post(
        "/api/pending-leads/" + lead["id"] + "/start", json={"expected_revision": lead["revision"]}
    )
    assert response.status_code == 200, response.text
    assert store.all(
        "SELECT capture_id FROM website_capture_cases WHERE case_id=?",
        (response.json()["case_id"],),
    ) == ([] if remove_admitted_binding else [{"capture_id": admitted["id"]}])


def test_lead_entity_and_case_share_capture_without_recapturing(client, app):
    rows = observations()
    rows[2]["tag"] = "CVE-2025-12345;eol-php"
    queue_import(client, app, rows)
    lead = client.get("/api/pending-leads").json()[0]
    website = lead["website"]
    assert website and website["final_url"].startswith(("http://", "https://"))
    assert "path" not in website and "preview_path" not in website
    entity = client.get("/api/entities/" + lead["entity_id"]).json()
    assert entity["website"] == website
    exported = app.state.store.export_lead(lead["entity_id"])
    assert exported["website_evidence"] == [
        {
            "capture_id": website["id"],
            **{
                key: website[key]
                for key in ("requested_url", "final_url", "captured_at", "capture_status", "sha256")
            },
        }
    ]
    image = client.get(website["image_url"])
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"
    retained = app.state.store.one("SELECT * FROM website_captures WHERE id=?", (website["id"],))
    assert hashlib.sha256(image.content).hexdigest() == retained["preview_sha256"]
    original = client.get(website["image_url"], params={"original": True})
    assert original.content == app.state.store.path(retained["path"]).read_bytes()
    assert {"eol", "cve"} == set(lead["finding_kinds"])
    result = client.post(
        "/api/pending-leads/" + lead["id"] + "/start", json={"expected_revision": lead["revision"]}
    )
    assert result.status_code == 200, result.text
    case = client.get("/api/cases/" + result.json()["case_id"]).json()
    adopted = next(item for item in case["evidence"] if item["sha256"] == website["sha256"])
    assert (
        adopted["path"] == retained["path"] and adopted["preview_path"] == retained["preview_path"]
    )
    case_export = app.state.store.export_lead(lead["entity_id"], case["case_id"])
    reference = case_export["website_evidence"][0]
    assert reference["capture_id"] == website["id"]
    assert reference["evidence_id"] == adopted["id"]
    assert reference["sha256"] == website["sha256"]
    assert reference["final_url"] == website["final_url"]
    assert set(reference) == {
        "capture_id",
        "evidence_id",
        "requested_url",
        "final_url",
        "captured_at",
        "capture_status",
        "sha256",
    }
    from modules.investigations.components.report_snapshot import snapshot

    frozen = snapshot(
        app.state.store,
        lead["entity_id"],
        case["case_id"],
        include_reviews=False,
        capture_sections=(),
    )
    assert frozen["qualified_lead"]["website_evidence"] == case_export["website_evidence"]
    assert app.state.store.one("SELECT count(*) n FROM website_captures")["n"] == 1
    app.state.store.path(retained["preview_path"]).write_bytes(b"changed")
    assert client.get(website["image_url"]).status_code == 409
    assert client.get("/api/website-evidence/missing/image").status_code == 404


def test_explicit_scope_extension_retains_original_proof_and_covers_old_and_new_rows(client, app):
    from modules.attribution.components.attribution_bridge import coverage_matches
    from modules.investigations.components.cases import Cases
    from modules.leads.components.lead_queue import LeadQueue

    queue_import(client, app)
    queue = LeadQueue(app.state.store)
    first = queue.list()[0]
    case_id = queue.start(first["id"], first["revision"])["case_id"]
    before = Cases(app.state.store).view(case_id)
    proof = before["domain_groups"][0]["attribution"]
    queue_import(
        client,
        app,
        [{**row, "version": "8.0.1", "timestamp": "2026-11-09 12:00:00"} for row in observations()],
        "new.csv",
    )
    current = queue.list()[0]
    queue.start(
        current["id"],
        current["revision"],
        case_id=case_id,
        expected_case_version=before["case"]["version"],
    )
    after = Cases(app.state.store).view(case_id)
    assert len(before["evidence"]) == 1 and before["evidence"] == after["evidence"]
    assert app.state.store.one("SELECT count(*) n FROM website_captures")["n"] == 1
    assert current["website"]["id"] == first["website"]["id"]
    extended_proof = after["domain_groups"][0]["attribution"]
    assert extended_proof["ip"] == proof["ip"] and extended_proof["result_id"] == proof["result_id"]
    assert all(coverage_matches(entry, extended_proof) for entry in after["entries"])
    assert len(after["entries"]) > len(before["entries"])
    exported = app.state.store.export_lead(first["entity_id"])
    assert all(
        coverage_matches(entry, exported["whois"][0])
        for entry in exported["validated_leads"][0]["entries"]
    )
