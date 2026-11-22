"""Actual discovery engine -> jobs -> saved proof -> review -> plan -> export.

The injected fetcher returns synthetic company pages; the remaining application
pipeline is unchanged. This complements the live-browser test without sockets.
"""

import io
import json
import time
from zipfile import ZipFile

from modules.entities.tests.support.contact_discovery import SyntheticWebsite
from tests.session_helpers import TestClient
from modules.entities.tests.support.contacts import attributed_entity
from modules.workspace.components.api import create_app
from modules.investigations.components.cases import Cases
from modules.entities.components.contact_discovery import ContactDiscovery


def test_real_engine_api_provenance_review_and_refresh(tmp_path):
    (tmp_path / "control.json").write_text('{"mode":"normal"}', encoding="utf-8")
    app = create_app(
        tmp_path / "data",
        worker=False,
        contact_discovery_factory=lambda: ContactDiscovery(fetcher=SyntheticWebsite(tmp_path)),
    )
    entity = attributed_entity(app.state.store)
    case = Cases(app.state.store).create(entity["id"])
    prefix = "/api/entities/" + entity["id"] + "/contacts"
    with TestClient(app) as client:
        original_case = app.state.store.one("SELECT * FROM cases WHERE id=?", (case["case_id"],))
        assert client.get(prefix).json()["roots"][0]["eligible"]
        assert not (tmp_path / "requests.jsonl").exists()

        def run(refresh=False):
            response = client.post(
                prefix + "/discover", json={"root_domain": "example.com", "refresh": refresh}
            )
            assert response.status_code == 200, response.text
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                job = client.get("/api/contact-discovery/jobs/" + response.json()["id"]).json()
                if job["state"] not in ("queued", "running", "cancelling"):
                    assert job["state"] == "completed", job
                    return client.get(prefix).json()
                time.sleep(0.01)
            raise AssertionError("Synthetic contact pipeline exceeded its test deadline")

        state = run()
        assert state["latest_run"]["status"] == "relevant_found"
        assert state["latest_run"]["request_count"] <= 6
        assert (
            app.state.store.one("SELECT * FROM cases WHERE id=?", (case["case_id"],))
            == original_case
        )
        candidate = next(
            item for item in state["candidates"] if item["value"] == "security@example.com"
        )
        assert candidate["decision"] == "pending"
        assert candidate["sources"][0]["url"] == "https://example.com/.well-known/security.txt"
        assert "SHA-256" in candidate["provenance_text"]
        reviewed = client.post(
            prefix + "/" + candidate["id"] + "/review",
            json={
                "action": "confirm",
                "expected_revision": candidate["revision"],
            },
        )
        assert reviewed.status_code == 200, reviewed.text
        candidate = next(
            item for item in reviewed.json()["candidates"] if item["id"] == candidate["id"]
        )
        response = client.post(
            "/api/cases/" + case["case_id"] + "/contacts/" + candidate["id"] + "/use",
            json={
                "expected_version": original_case["version"],
                "expected_revision": candidate["revision"],
            },
        )
        assert response.status_code == 200, response.text
        used_case = app.state.store.one("SELECT * FROM cases WHERE id=?", (case["case_id"],))
        assert used_case["contact_email"] == "security@example.com"
        for key in ("draft", "draft_revision", "stage", "certified_report_id"):
            assert used_case[key] == original_case[key]

        refreshed = run(refresh=True)
        current = next(item for item in refreshed["candidates"] if item["id"] == candidate["id"])
        assert current["decision"] == "confirmed"
        assert len(refreshed["runs"]) == 2
        assert (
            app.state.store.one("SELECT * FROM cases WHERE id=?", (case["case_id"],)) == used_case
        )
        response = client.get(prefix + "/evidence.zip")
        assert response.status_code == 200, response.text
        with ZipFile(io.BytesIO(response.content)) as archive:
            names = archive.namelist()
            assert any(name.endswith(".contact.json") for name in names)
            metadata = [json.loads(archive.read(name)) for name in names if name.endswith(".json")]
            assert metadata
            assert "security@example.com" in json.dumps(metadata)
        requests = [
            json.loads(line)["url"]
            for line in (tmp_path / "requests.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert len(requests) <= 12
        assert all(url.startswith("https://example.com/") for url in requests)
