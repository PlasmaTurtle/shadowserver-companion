"""Content locks stay fast, presentation-independent, and legacy compatible."""

from copy import deepcopy
import json

import pytest

from test_workbench import app, client, validate_sections
from test_section_validation_050 import prepared, save, status
from workbench import compact_json, exhibit_rendering, report_execution
from workbench.report_composition import compose
from workbench.report_snapshot import snapshot
from workbench.repositories.reviews import SectionReviewRepository
from workbench.reviews.policy import fingerprints


def no_render(*args, **kwargs):
    pytest.fail("Freezing content invoked the renderer")


def forbid_rendering(monkeypatch):
    for name in (
        "png",
        "svg_pages",
        "layout_appendix",
        "layout_closing",
        "layout_information",
        "layout_attribution",
        "layout_vulnerabilities",
    ):
        monkeypatch.setattr(exhibit_rendering, name, no_render)
    monkeypatch.setattr(report_execution, "capture_content", no_render)
    monkeypatch.setattr(report_execution, "_run", no_render)


def test_all_five_freezes_save_content_without_rendering(client, app, monkeypatch):
    lead = prepared(client, app, validate=False)
    forbid_rendering(monkeypatch)
    lead = validate_sections(client, lead)
    assert all(row["fingerprint_version"] == 2 for row in lead["section_reviews"])
    rows = app.state.store.all("SELECT snapshot_json FROM section_validations")
    assert len(rows) == 5
    for row in rows:
        record = compact_json.loads(row["snapshot_json"])
        assert record["fingerprint_version"] == 2
        assert record["snapshot"]["fields"] == record["frozen_fields"]
        assert "rendered_masters" not in row["snapshot_json"]
        assert "exhibit_masters" not in record["snapshot"]
    assert not list(app.state.store.root.rglob(".render-*"))


@pytest.mark.parametrize("initial", [True, False])
def test_appendix_choice_keeps_all_content_locks(client, app, initial):
    lead = prepared(client, app, validate=False)
    response = save(client, lead, include_appendix=initial)
    assert response.status_code == 200, response.text
    lead = validate_sections(client, response.json())
    prior = {row["key"]: row["validation_id"] for row in lead["section_reviews"]}
    response = save(client, lead, include_appendix=not initial)
    assert response.status_code == 200, response.text
    assert all(row["status"] == "validated" for row in response.json()["section_reviews"])
    assert prior == {row["key"]: row["validation_id"] for row in response.json()["section_reviews"]}


def test_appendix_layout_and_rendered_cache_do_not_change_content_hash(client, app):
    lead = prepared(client, app, validate=False)
    data = snapshot(app.state.store, lead["id"], lead["case_id"], capture_sections=())
    before = fingerprints(data, lead)
    changed = deepcopy(data)
    changed["draft"]["appendix_revision"] = "legacy"
    changed["composition"] = compose(changed)
    assert {k: v["content_hash"] for k, v in fingerprints(changed, lead).items()} == {
        k: v["content_hash"] for k, v in before.items()
    }
    for exhibit in data["composition"]["exhibits"]:
        exhibit["rendered_masters"] = {"irrelevant": "output cache"}
        exhibit["compact_appendix"] = True
    for node in data["composition"]["sections"]:
        if node.get("model"):
            node["model"]["compact_appendix"] = True
    assert fingerprints(data, lead) == before


def test_legacy_frozen_record_is_preserved_and_compared_without_regeneration(
    client, app, monkeypatch
):
    lead = prepared(client, app, validate=False)
    store = app.state.store
    # A genuine pre-profile draft still depends on the then-current sender;
    # newly created reports instead pin identity until explicit adoption.
    with store.transaction() as db:
        draft = json.loads(
            db.execute("SELECT draft FROM cases WHERE id=?", (lead["case_id"],)).fetchone()[0]
        )
        draft.pop("sender_profile", None)
        db.execute("UPDATE cases SET draft=? WHERE id=?", (json.dumps(draft), lead["case_id"]))
    lead = client.get("/api/cases/" + lead["case_id"]).json()
    data = snapshot(store, lead["id"], lead["case_id"], include_reviews=False)
    historical = fingerprints(data, lead, sections=("closing",), version=1)["closing"]
    assert "fingerprint_version" not in historical
    repository = SectionReviewRepository(store)
    with store.transaction() as db:
        repository.save_validation(db, lead["case_id"], "closing", "Earlier Analyst", historical)
    old_row = repository.active(lead["case_id"])["closing"]
    forbid_rendering(monkeypatch)
    current = client.get("/api/cases/" + lead["case_id"]).json()
    assert status(current, "closing")["status"] == "validated"
    assert status(current, "closing")["fingerprint_version"] == 1
    assert status(current, "closing")["validated_by"] == "Earlier Analyst"
    # Presentation-only edits on an upgraded draft reuse the original review;
    # no migration rewrites its old timestamp, hash, content or artwork.
    changed = save(client, current, include_appendix=False, appendix_revision="legacy")
    assert changed.status_code == 200, changed.text
    current = changed.json()
    assert status(current, "closing")["status"] == "validated"
    current = validate_sections(client, current)
    assert repository.active(lead["case_id"])["closing"] == old_row
    assert status(current, "introduction")["fingerprint_version"] == 2
    # A substantive change must still expire the old review, even with the
    # presentation bridge active and renderer calls prohibited.
    settings = client.get("/api/bootstrap").json()["settings"]
    settings["analyst_name"] = "Changed Sender"
    assert client.put("/api/settings", json=settings).status_code == 200
    current = client.get("/api/cases/" + lead["case_id"]).json()
    assert status(current, "closing")["status"] == "stale"
    assert repository.active(lead["case_id"])["closing"] == old_row


def test_render_failure_does_not_remove_content_locks(client, app, monkeypatch):
    lead = prepared(client, app)
    prior = deepcopy(lead["section_reviews"])

    def failed(*args, **kwargs):
        raise ValueError("Synthetic output failure")

    monkeypatch.setattr("workbench.services.certification.prepare_package", failed)
    response = client.post("/api/leads/" + lead["id"] + "/finalize")
    assert response.status_code == 422, response.text
    current = client.get("/api/cases/" + lead["case_id"]).json()
    assert current["section_reviews"] == prior
    assert not app.state.store.all("SELECT id FROM reports")
