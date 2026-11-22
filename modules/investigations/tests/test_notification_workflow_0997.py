"""Notification review: editor values, section ownership and certified checks."""

from copy import deepcopy
import json

import pytest

from modules.investigations.tests.support.cases import certified
from modules.investigations.tests.support.section_reviews import prepared, save, status
from tests.support.workbench import app, client, import_rows, observations, ready, reopen_sections
from modules.investigations.components import approved_template


@pytest.mark.parametrize("scoped", [False, True])
def test_finding_overrides_save_and_freeze_with_intake_version_and_scope(client, app, scoped):
    row = {
        **observations()[0],
        "ip": "8.8.8.8",
        "version": "HTTP/1.1",
        "component_version": "5.6.40",
        "tag": "eol-php;http" if scoped else "eol-php",
    }
    import_rows(client, app, [row], "http-component.csv")
    entity_id = client.get("/api/leads").json()[0]["id"]
    lead = ready(client, entity_id, validate=False)
    if scoped:
        # A later notification may select one condition from a multi-tag row.
        with app.state.store.transaction() as db:
            db.execute(
                "INSERT OR REPLACE INTO case_entry_conditions VALUES(?,?,?)",
                (lead["case_id"], lead["entries"][0]["id"], json.dumps(["eol-php:5.6"])),
            )
        lead = client.get("/api/cases/" + lead["case_id"]).json()
    original_entries = deepcopy(lead["entries"])
    original_payload = app.state.store.one("SELECT payload FROM entries")["payload"]
    group = lead["narrative_groups"][0]
    assert group["version"] == "5.6.40"
    assert group["key"] not in {
        item["key"] for item in approved_template.narrative_groups(lead, lead["draft"])
    }
    values = {group["key"]: {"software": "Reviewed PHP product", "affected_versions": ""}}
    draft = {**lead["draft"], "narrative_values": values}
    preview = client.post("/api/leads/" + entity_id + "/narrative", json=draft)
    assert preview.status_code == 200, preview.text
    assert preview.json()["groups"][0]["key"] == group["key"]
    unrelated = save(client, lead, narrative_values={"another-case": {"software": "Unrelated"}})
    assert unrelated.status_code == 422 and "this case" in unrelated.text
    saved = save(client, lead, narrative_values=values)
    assert saved.status_code == 200, saved.text
    lead = saved.json()
    assert lead["draft"]["narrative_values"] == values
    assert lead["draft"]["narrative"] == preview.json()["narrative"]
    assert "Reviewed PHP product" in lead["draft"]["narrative"]
    assert "5.6.40" in lead["draft"]["narrative"]
    assert "HTTP/1.1" not in lead["draft"]["narrative"]
    frozen = client.post(
        "/api/cases/" + lead["case_id"] + "/sections/vulnerabilities/validate",
        json={"expected_revision": lead["draft_revision"]},
    )
    assert frozen.status_code == 200, frozen.text
    assert status(frozen.json(), "vulnerabilities")["status"] == "validated"
    assert frozen.json()["entries"] == original_entries
    assert app.state.store.one("SELECT payload FROM entries")["payload"] == original_payload
    blocked = save(
        client,
        frozen.json(),
        narrative_values={group["key"]: {"software": "A changed product"}},
    )
    assert blocked.status_code == 422 and "Vulnerabilities" in blocked.text


def test_address_adoption_requires_both_affected_sections_to_be_open(client, app):
    lead = prepared(client, app)
    entity = client.get("/api/entities/" + lead["id"]).json()
    changed = client.put(
        "/api/entities/" + lead["id"] + "/profile",
        json={"expected_revision": entity["entity_revision"], "address": "42 New Street"},
    )
    assert changed.status_code == 200, changed.text
    lead = reopen_sections(client, lead, "Update the mailing address", ["introduction"])
    store = app.state.store
    before = store.one("SELECT * FROM cases WHERE id=?", (lead["case_id"],))
    attribution = status(lead, "attribution")
    url = "/api/cases/" + lead["case_id"] + "/entity-details"
    blocked = client.post(url, json={"expected_version": lead["case"]["version"]})
    assert blocked.status_code == 422 and "Attribution" in blocked.text
    assert store.one("SELECT * FROM cases WHERE id=?", (lead["case_id"],)) == before
    unchanged = client.get("/api/cases/" + lead["case_id"]).json()
    assert status(unchanged, "attribution") == attribution
    lead = reopen_sections(client, unchanged, "Update the attribution address", ["attribution"])
    adopted = client.post(url, json={"expected_version": lead["case"]["version"]})
    assert adopted.status_code == 200, adopted.text
    updated = adopted.json()
    model = next(e for e in updated["report_model"]["exhibits"] if e["type"] == "attribution")
    assert updated["draft"]["address"] == model["address"] == "42 New Street"
    for key in ("vulnerabilities", "information", "closing"):
        assert status(updated, key)["status"] == "validated"
        assert status(updated, key)["validation_id"] == status(lead, key)["validation_id"]


def test_certified_editor_keeps_one_readiness_decision_per_check(client, app):
    lead, report = certified(client, app)
    package = app.state.store.path(report["path"]) / "snapshot.json"
    original = package.read_bytes()
    for _ in range(2):
        current = client.get("/api/cases/" + lead["case_id"]).json()
        keys = [row["key"] for row in current["readiness"]]
        assert len(keys) == len(set(keys))
        assert len([key for key in keys if key.startswith("section_")]) == 5
        assert current["historical_report"]["snapshot_verified"]
        assert package.read_bytes() == original
