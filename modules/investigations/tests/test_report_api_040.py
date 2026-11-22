"""Source adoption, case wording, and immutable source-selection boundaries."""

import copy

from tests.support.workbench import app, client, validate_sections, reopen_sections

from modules.investigations.tests.support.report_api import (
    opened,
    save,
    source,
)


def test_blocks_pinned_and_explicit_adoption_preserves_case_wording(client, app):
    lead = opened(client, app)
    original = copy.deepcopy(lead["draft"]["explainer_snapshots"])
    assert original
    revision = lead["draft_revision"]
    again = client.get("/api/leads/" + lead["id"]).json()
    assert again["draft_revision"] == revision
    block = original[0]  # Shared optional blocks are pinned even when not selected by default.
    response = client.put(
        "/api/explainers/" + block["id"],
        json={
            "title": block["title"],
            "body": "New shared revision.",
            "sources": block["sources"],
            "expected_revision": block["revision"],
        },
    )
    assert response.status_code == 200
    unchanged = client.get("/api/leads/" + lead["id"]).json()
    assert unchanged["draft"]["explainer_snapshots"] == original
    overrides = {block["id"]: {"body": "Case-specific advisory wording."}}
    updated = save(
        client,
        unchanged,
        narrative="Keep this narrative.",
        explainer_overrides=overrides,
        reviewed=True,
    )
    assert updated.status_code == 200, updated.text
    lead = updated.json()
    assert not lead["draft"]["reviewed"]
    latest = client.get("/api/explainers").json()
    result = save(client, lead, explainer_snapshots=latest, reviewed=True)
    assert result.status_code == 200, result.text
    lead = result.json()
    assert "began reviewing Shadowserver observations" in lead["draft"]["narrative"]
    assert lead["draft"]["explainer_overrides"] == overrides
    assert not lead["draft"]["reviewed"]
    result = save(client, lead, reviewed=True)
    assert result.status_code == 200 and result.json()["draft"]["reviewed"]
    assert client.get("/api/explainers").json()[0]["body"] != overrides[block["id"]]["body"]


def test_published_source_quotes_are_read_only_and_case_scoped(client, app, monkeypatch):
    lead = opened(client, app, cve=True)
    monkeypatch.setattr("modules.workspace.components.api.enrich", lambda *args, **kwargs: source())
    fetched = client.post("/api/cves/CVE-2025-12345/retrieve").json()
    response = save(
        client,
        lead,
        cve_records=[fetched],
        narrative="Analyst-written introduction.",
        reviewed=True,
    )
    assert response.status_code == 200, response.text
    lead = response.json()
    assert not lead["draft"]["reviewed"]
    altered = {**fetched, "description": "An altered quote."}
    response = save(client, lead, cve_records=[altered])
    assert response.status_code == 422 and "read-only" in response.text
    unrelated = {**fetched, "id": "CVE-2025-99999"}
    assert save(client, lead, cve_records=[unrelated]).status_code == 422
    assert (
        save(
            client,
            lead,
            cve_dispositions={"CVE-2025-99999": {"action": "exclude", "reason": "Not ours"}},
        ).status_code
        == 422
    )
    assert save(client, lead, reviewed=True).json()["draft"]["reviewed"]


def test_official_text_fallback_needs_no_cve_image_but_retains_website(client, app):
    lead = opened(client, app, cve=True)
    disposition = {
        "action": "fallback",
        "reason": "Captured the vendor advisory during an API outage.",
        "description": "Exact published fixture description.",
        "publisher": "Fixture vendor",
        "source_url": "https://example.com/security/advisory",
        "retrieved_at": "2026-11-06T12:00:00Z",
        "evidence_text": "Exact published fixture description.",
    }
    response = save(
        client,
        lead,
        company="Example",
        sender_name="Analyst",
        website_verified=False,
        cve_dispositions={"CVE-2025-12345": disposition},
        reviewed=True,
    )
    assert response.status_code == 200, response.text
    lead = response.json()
    assert any(item["kind"] == "website" for item in lead["evidence"])
    assert not any(item["kind"] == "cve" for item in lead["evidence"])
    # Structured attribution and section review replace the redundant website
    # checkbox. Its legacy value must never fabricate a website-review claim.
    assert not lead["draft"]["website_verified"]
    assert "website" not in {item["key"] for item in lead["readiness"]}
    response = save(client, lead, reviewed=True)
    lead = response.json()
    assert not all(item["ok"] for item in lead["readiness"])
    lead = validate_sections(client, lead)
    assert all(item["ok"] for item in lead["readiness"]), lead["readiness"]
    # Removing a citation also renumbers attribution markers and changes the
    # Information-owned Appendix D source register.
    lead = reopen_sections(
        client,
        lead,
        "Review an explicit exclusion after the source fallback.",
        keys=["vulnerabilities", "attribution", "information", "closing"],
    )
    exclusion = {
        "CVE-2025-12345": {
            "action": "exclude",
            "reason": "Awaiting clarification from publisher.",
        }
    }
    excluded = save(client, lead, cve_dispositions=exclusion)
    # The current introduction summarizes selected findings, so it must also
    # be reopened before an exclusion changes its reviewed content.
    assert excluded.status_code == 422, excluded.text
    assert "Introduction" in excluded.json()["detail"]
    lead = reopen_sections(
        client,
        lead,
        "Update the reviewed introduction summary for the exclusion.",
        keys=["introduction"],
    )
    excluded = save(client, lead, cve_dispositions=exclusion)
    assert excluded.status_code == 200, excluded.text
    assert len(excluded.json()["entries"]) == len(lead["entries"])
    assert not excluded.json()["draft"]["reviewed"]


def test_untrusted_template_and_fallback_links_rejected(client, app):
    lead = opened(client, app, cve=True)
    assert (
        save(
            client, lead, report_template={"id": "standard", "version": 1, "font_size": 100}
        ).status_code
        == 422
    )
    assert (
        save(
            client, lead, report_template={"id": "standard", "version": 1, "script": "bad"}
        ).status_code
        == 422
    )
    bad = {"action": "fallback", "source_url": "javascript:alert(1)"}
    assert save(client, lead, cve_dispositions={"CVE-2025-12345": bad}).status_code == 422
    snapshots = copy.deepcopy(lead["draft"]["explainer_snapshots"])
    snapshots[0]["body"] = "Tampered revision text."
    assert save(client, lead, explainer_snapshots=snapshots).status_code == 422


def test_block_source_metadata_roundtrip_and_pinned_revisions(client, app):
    url = "https://example.com/security/guidance"
    metadata = {
        "url": url,
        "publisher": "Example Publisher",
        "title": "Published security guidance",
        "retrieved_at": "2026-11-06T12:30:00Z",
        "date_published": "2026-01-01",
        "date_updated": "",
    }
    body = {
        "title": "Guidance",
        "body": "Published advisory context.",
        "sources": url,
        "source_metadata": [metadata],
    }
    created = client.post("/api/explainers", json=body)
    assert created.status_code == 200, created.text
    block_id = created.json()["id"]
    blocks = client.get("/api/explainers").json()
    block = next(b for b in blocks if b["id"] == block_id)
    assert block["source_metadata"] == [metadata]
    boot_block = next(
        b for b in client.get("/api/bootstrap").json()["explainers"] if b["id"] == block_id
    )
    assert boot_block == block
    lead = opened(client, app)
    # Select this already captured revision and review it on a subsequent save.
    response = save(client, lead, selected_explainers=[block_id])
    assert response.status_code == 200, response.text
    lead = response.json()
    pinned = next(b for b in lead["draft"]["explainer_snapshots"] if b["id"] == block_id)
    assert pinned["source_metadata"] == [metadata]
    changed_metadata = {**metadata, "retrieved_at": "2026-11-07T12:30:00Z"}
    changed = client.put(
        "/api/explainers/" + block_id,
        json={
            **body,
            "source_metadata": [changed_metadata],
            "expected_revision": block["revision"],
        },
    )
    assert changed.status_code == 200, changed.text
    unchanged = client.get("/api/leads/" + lead["id"]).json()
    assert (
        next(b for b in unchanged["draft"]["explainer_snapshots"] if b["id"] == block_id) == pinned
    )
    assert app.state.store.one(
        "SELECT payload FROM cache WHERE key=?", (f"block-sources:{block_id}:1",)
    )
    assert app.state.store.one(
        "SELECT payload FROM cache WHERE key=?", (f"block-sources:{block_id}:2",)
    )
    unrelated = {**metadata, "url": "https://unlisted.example/guidance"}
    assert (
        client.put(
            "/api/explainers/" + block_id,
            json={**body, "source_metadata": [unrelated], "expected_revision": 2},
        ).status_code
        == 422
    )
    assert (
        client.put(
            "/api/explainers/" + block_id,
            json={
                **body,
                "source_metadata": [{**metadata, "retrieved_at": "unknown"}],
                "expected_revision": 2,
            },
        ).status_code
        == 422
    )
