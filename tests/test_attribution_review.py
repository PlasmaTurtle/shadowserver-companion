"""Review decisions promote retained observations, with immutable lookup evidence."""

import hashlib
import io
import json
from workbench import compact_json
import zipfile
from contextlib import closing

import httpx
import pytest
from session_helpers import TestClient

from attribution import AttributionModule, EvidenceStore, RdapProvider, Settings, verify_export
from workbench.api import create_app
from workbench.intake_service import IntakeService
from test_workbench import csv_bytes, observations, ready


@pytest.fixture
def review_app(tmp_path, monkeypatch, request):
    import workbench.attribution_bridge as bridge

    state = {"exact": False, "calls": []}

    def server(request):
        url = str(request.url)
        state["calls"].append(url)
        if "data.iana.org" in url:
            record = {"services": [[["0.0.0.0/0"], ["https://rdap.arin.net/registry/"]]]}
        else:
            ip = url.rsplit("/", 1)[-1]
            props = [
                [
                    "fn",
                    {},
                    "text",
                    "Example Medical Center" if ip == "8.8.8.8" else "Unrelated Corporation",
                ]
            ]
            if state["exact"]:
                props.append(["email", {}, "text", "support@example.com"])
            record = {
                "objectClassName": "ip network",
                "handle": "FIXTURE",
                "startAddress": ip,
                "endAddress": ip,
                "entities": [
                    {
                        "objectClassName": "entity",
                        "handle": "FIXTUREORG",
                        "roles": ["registrant"],
                        "vcardArray": ["vcard", props],
                    }
                ],
            }
        return httpx.Response(
            200,
            headers={"content-type": "application/rdap+json"},
            stream=httpx.ByteStream(json.dumps(record).encode()),
        )

    def open_module(path, settings):
        store = EvidenceStore(path)
        provider = RdapProvider(
            store, Settings(interval=0, retries=0), transport=httpx.MockTransport(server)
        )
        module = AttributionModule(store, providers=[provider])
        module._owns_store = True
        module._owned = [provider]
        return module

    monkeypatch.setattr(bridge.AttributionModule, "open", open_module)
    app = create_app(tmp_path / "data", worker=False)
    with TestClient(app) as client:
        client.headers["X-Workbench-Token"] = client.get("/api/bootstrap").json()["token"]
        domain = getattr(request, "param", "example.com")
        rows = [{**row, "hostname": "remote2." + domain} for row in observations()[:4]]
        content = csv_bytes(rows)
        imported = client.post(
            "/api/imports", files=[("files", ("partial.csv", content, "text/csv"))]
        ).json()[0]
        app.state.intake.process(imported["id"])
        jobs = client.get("/api/imports/" + imported["id"]).json()["groups"]
        group = client.get("/api/groups/" + jobs[0]["id"]).json()
        yield app, client, group, state, content


def accept_payload(group):
    return {
        "result_id": group["attribution_result"]["result_id"],
        "evidence_index": 0,
        "decision": "accept",
        "note": "Reviewed organization and address range.",
    }


def test_review_accepts_selected_evidence_preserves_full_group_and_source(review_app, tmp_path):
    app, client, group, state, content = review_app
    assert group["status"] == "review" and not client.get("/api/leads").json()
    queue = client.get("/api/reviews").json()
    assert queue[0]["observations"] == 4 and queue[0]["assets"] == 4
    assert queue[0]["matches"][0]["details"]["matched_words"] == ["example"]
    assert client.get("/api/dashboard").json()["counts"]["review"] == 1
    assert len(state["calls"]) == 4  # Bootstrap + all three public IPs; no stop at the partial.
    calls = len(state["calls"])
    accepted = client.post("/api/groups/" + group["id"] + "/review", json=accept_payload(group))
    assert accepted.status_code == 200, accepted.text
    lead_id = accepted.json()["lead_id"]
    lead = client.get("/api/leads/" + lead_id).json()
    assert len(state["calls"]) == calls
    assert lead["entries"][0]["ip"] == "8.8.8.8" and len(lead["entries"]) == 4
    assert any(e["private_ip"] for e in lead["entries"])
    assert lead["entries"][0]["source"]["fields"]["unknown_extension"] == "KEEP THIS FIELD"
    assert lead["attribution"]["review"]["decision"] == "accept"
    assert lead["attribution"]["attribution"]["matched_domain"] == ""
    assert client.get("/api/dashboard").json()["counts"]["review"] == 0
    assert not client.get("/api/reviews").json()
    updated = client.get("/api/groups/" + group["id"]).json()
    assert updated["status"] == "qualified" and updated["attribution_result"]["status"] == "review"
    assert updated["reviews"][0]["lead_id"] == lead_id
    assert client.get("/api/imports/" + group["import_id"] + "/original").content == content
    imported = client.get("/api/imports/" + group["import_id"]).json()
    assert imported["qualified"] == 1
    assert imported["message"] == "All groups processed"
    assert (
        client.post(
            "/api/groups/" + group["id"] + "/review", json=accept_payload(group)
        ).status_code
        == 422
    )
    ready(client, lead_id)
    report = client.post("/api/leads/" + lead_id + "/finalize")
    assert report.status_code == 200, report.text
    path = app.state.store.path(report.json()["path"])
    snapshot = compact_json.loads((path / "snapshot.json").read_text())
    assert (
        snapshot["qualified_lead"]["whois"][0]["review"]["note"]
        == "Reviewed organization and address range."
    )
    assert "registration" in {p.name for p in path.iterdir()}
    bundle = client.get("/api/groups/" + group["id"] + "/attribution.zip")
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        archive.extractall(tmp_path / "export")
    assert verify_export(tmp_path / "export")["valid"]
    decisions = json.loads((tmp_path / "export/analyst-reviews.json").read_text())
    assert (
        decisions[0]["decision"] == "accept"
        and decisions[0]["result_id"] == group["attribution_result"]["result_id"]
    )
    assert "Analyst decision: accept" in (tmp_path / "export/evidence.html").read_text()


def test_dismiss_is_recorded_without_qualifying(review_app):
    app, client, group, state, content = review_app
    payload = {**accept_payload(group), "decision": "dismiss", "evidence_index": None}
    response = client.post("/api/groups/" + group["id"] + "/review", json=payload)
    assert response.status_code == 200 and response.json()["lead_id"] is None
    assert not client.get("/api/leads").json()
    updated = client.get("/api/groups/" + group["id"]).json()
    assert updated["status"] == "dismissed" and updated["reviews"][0]["decision"] == "dismiss"
    assert updated["partial_records"]
    assert updated["can_retry"]
    assert (
        client.post(
            "/api/groups/" + group["id"] + "/retry",
            json={"result_id": group["attribution_result"]["result_id"]},
        ).status_code
        == 200
    )
    app.state.intake.process(group["import_id"])
    retried = client.get("/api/groups/" + group["id"]).json()
    assert retried["status"] == "review" and len(retried["reviews"]) == 1
    assert client.get("/api/groups/" + group["id"] + "/attribution.zip").status_code == 200


@pytest.mark.parametrize("review_app", ["EXAMPLE.COM"], indirect=True)
def test_review_accepts_same_canonical_domain_without_changing_saved_group(review_app):
    app, client, group, state, content = review_app
    response = client.post("/api/groups/" + group["id"] + "/review", json=accept_payload(group))
    assert response.status_code == 200, response.text
    lead = client.get("/api/leads/" + response.json()["lead_id"]).json()
    assert lead["attribution"]["attribution"]["root_domain"] == "example.com"
    assert (
        app.state.store.one("SELECT domain FROM jobs WHERE id=?", (group["id"],))["domain"]
        == "EXAMPLE.COM"
    )


@pytest.mark.parametrize("review_app", ["EXAMPLE.COM"], indirect=True)
def test_canonical_provider_match_qualifies_original_uppercase_group(review_app):
    app, client, group, state, content = review_app
    state["exact"] = True
    response = client.post(
        "/api/groups/" + group["id"] + "/retry",
        json={"result_id": group["attribution_result"]["result_id"]},
    )
    assert response.status_code == 200
    app.state.intake.process(group["import_id"])
    updated = client.get("/api/groups/" + group["id"]).json()
    assert updated["status"] == "qualified"
    assert updated["domain"] == "EXAMPLE.COM"
    assert updated["attribution_result"]["root_domain"] == "example.com"


def test_retry_refreshes_records_and_preserves_prior_result(review_app):
    app, client, group, state, content = review_app
    old_id = group["attribution_result"]["result_id"]
    state["exact"] = True
    response = client.post("/api/groups/" + group["id"] + "/retry", json={"result_id": old_id})
    assert response.status_code == 200
    assert (
        client.post(
            "/api/groups/" + group["id"] + "/review", json=accept_payload(group)
        ).status_code
        == 422
    )
    app.state.intake.process(group["import_id"])
    updated = client.get("/api/groups/" + group["id"]).json()
    assert updated["status"] == "qualified" and updated["attribution_result"]["status"] == "matched"
    assert updated["attribution_result"]["result_id"] != old_id
    with EvidenceStore(app.state.store.root / "attribution.sqlite3") as store:
        assert store.result(old_id)["status"] == "review"
    assert len(client.get("/api/leads").json()) == 1


def test_bad_selection_and_stale_result_do_not_create_leads(review_app):
    app, client, group, state, content = review_app
    for changes in ({"evidence_index": 1000}, {"result_id": "0" * 32}):
        response = client.post(
            "/api/groups/" + group["id"] + "/review", json={**accept_payload(group), **changes}
        )
        assert response.status_code == 422
    response = client.post(
        "/api/groups/" + group["id"] + "/review",
        json=accept_payload(group),
        headers={"X-Workbench-Token": "invalid"},
    )
    assert response.status_code == 403
    assert not client.get("/api/leads").json()
    assert client.get("/api/groups/" + group["id"]).json()["status"] == "review"


def test_accept_verifies_saved_response_integrity(review_app):
    app, client, group, state, content = review_app
    sid = group["attribution_result"]["partial_evidence"][0]["snapshot_id"]
    with EvidenceStore(app.state.store.root / "attribution.sqlite3") as store:
        with store._db:
            store._db.execute("UPDATE snapshots SET body=? WHERE id=?", (b"{}", sid))
    response = client.post("/api/groups/" + group["id"] + "/review", json=accept_payload(group))
    assert response.status_code == 422 and "integrity" in response.text
    assert not client.get("/api/leads").json()
