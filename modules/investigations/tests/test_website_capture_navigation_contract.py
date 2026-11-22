"""Reported requests and rendered destinations remain distinct evidence facts."""

import json

import pytest

from modules.entities.tests.support.contacts import attributed_entity
from modules.investigations.components.cases import Cases
from modules.investigations.components.image_evidence import metadata_path
from modules.investigations.tests.support.website_capture import captured, done
from modules.workspace.components.api import create_app
from tests.session_helpers import TestClient


@pytest.mark.parametrize("scheme,port", [("https", 443), ("http", 80)])
@pytest.mark.parametrize("fallback", [False, True])
def test_redirected_capture_attaches_with_reported_request_and_actual_destination(
    tmp_path, scheme, port, fallback
):
    requested = f"{scheme}://mail.example.com/"
    final_url = "https://www.example.com/contact/"
    selected_url = "https://example.com/" if fallback else requested
    png, metadata = captured()
    metadata.update(
        requested_url=requested,
        final_url=final_url,
        root_domain="example.com",
        redirects=[selected_url, final_url],
        fallback_used=fallback,
        attempted_urls=[requested, selected_url] if fallback else [requested],
        attempts=[
            *(
                [{"url": requested, "outcome": "load_failed", "reason": "DNS resolution failed"}]
                if fallback
                else []
            ),
            {
                "url": selected_url,
                "outcome": "captured",
                "final_url": final_url,
                "http_status": 200,
            },
        ],
    )
    calls = []

    def acquisition(url, **kwargs):
        calls.append(url)
        return png, metadata

    app = create_app(tmp_path / "data", worker=False, website_capture=acquisition)
    store = app.state.store
    entity = attributed_entity(store)
    with store.transaction() as db:
        db.execute("UPDATE entries SET payload=json_set(payload,'$.source.fields.port',?)", (port,))
    case = Cases(store).create(entity["id"])
    before = store.one("SELECT version,draft_revision FROM cases WHERE id=?", (case["case_id"],))
    with TestClient(app) as client:
        started = client.post(
            f"/api/cases/{case['case_id']}/website-capture", json={"hostname": "mail.example.com"}
        )
        assert started.status_code == 200, started.text
        result = done(app.state.website_jobs, started.json()["id"])
        assert result["state"] == "completed", result
        assert calls == [requested]
        assert result["capture"] == metadata
        evidence = store.one("SELECT * FROM evidence WHERE id=?", (result["evidence_id"],))
        assert evidence["case_id"] == case["case_id"]
        assert evidence["lead_id"] == entity["id"]
        assert evidence["source_url"] == final_url
        assert evidence["included"] == 1
        assert store.path(evidence["path"]).read_bytes() == png
        saved = json.loads(store.path(metadata_path(evidence["id"])).read_text(encoding="utf-8"))
        assert saved["website_capture"] == metadata
        editor = client.get(f"/api/cases/{case['case_id']}").json()
        assert editor["evidence"][0]["capture"] == metadata
        assert editor["case"]["version"] == before["version"] + 1
        assert editor["draft_revision"] == before["draft_revision"] + 1
        assert editor["draft"]["reviewed"] is False


@pytest.mark.parametrize("wrong_request", ["https://example.com/", "http://mail.example.com/"])
def test_redirect_metadata_cannot_replace_the_reported_request(tmp_path, wrong_request):
    png, metadata = captured()
    metadata.update(requested_url=wrong_request, final_url="https://www.example.com/")
    app = create_app(
        tmp_path / "data", worker=False, website_capture=lambda *args, **kwargs: (png, metadata)
    )
    store = app.state.store
    entity = attributed_entity(store)
    case = Cases(store).create(entity["id"])
    before = store.one("SELECT * FROM cases WHERE id=?", (case["case_id"],))
    with TestClient(app) as client:
        started = client.post(
            f"/api/cases/{case['case_id']}/website-capture", json={"hostname": "mail.example.com"}
        )
        assert started.status_code == 200, started.text
        result = done(app.state.website_jobs, started.json()["id"])
        assert result["state"] == "failed"
        assert "provenance does not match" in result["message"]
        assert not store.all("SELECT * FROM evidence")
        assert not list((store.root / "evidence").iterdir())
        assert store.one("SELECT * FROM cases WHERE id=?", (case["case_id"],)) == before
