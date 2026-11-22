"""Reusable synthetic attribution review fixtures and builders."""

import json

import httpx
import pytest
from attribution import AttributionModule, EvidenceStore, RdapProvider, Settings

from modules.workspace.components.api import create_app
from tests.session_helpers import TestClient
from tests.support.qualification import capture_website
from tests.support.workbench import csv_bytes, observations


@pytest.fixture
def review_app(tmp_path, monkeypatch, request):
    import modules.attribution.components.attribution_bridge as bridge

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

    def open_module(path, settings=None, cancel_event=None):
        store = EvidenceStore(path)
        provider = RdapProvider(
            store, Settings(interval=0, retries=0), transport=httpx.MockTransport(server)
        )
        module = AttributionModule(store, providers=[provider], cancel_event=cancel_event)
        module._owns_store = True
        module._owned = [provider]
        return module

    monkeypatch.setattr(bridge.AttributionModule, "open", open_module)
    app = create_app(tmp_path / "data", worker=False, capture=capture_website)
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
