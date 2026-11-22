"""Entity details and contact completeness describe the same saved revision."""

import json

from modules.entities.components import contact_outcomes
from modules.workspace.components.store import Store
from modules.entities.tests.support.contacts import attributed_entity


def test_contact_change_during_entity_read_cannot_mix_revisions(tmp_path, monkeypatch):
    store = Store(tmp_path / "workspace")
    entity = attributed_entity(store)
    profile = {"address": "123 Synthetic Street", "contact_email": ""}
    with store.transaction() as db:
        db.execute("UPDATE leads SET company=? WHERE id=?", ("Example Business", entity["id"]))
        db.execute(
            "INSERT OR REPLACE INTO entity_profiles(entity_id,payload) VALUES(?,?)",
            (entity["id"], json.dumps(profile)),
        )
    original = contact_outcomes.directory_contact
    changed = []

    def change_contact_before_summary(workspace, entity_id, db=None):
        if not changed:
            with workspace.transaction() as writer:
                writer.execute(
                    "UPDATE entity_profiles SET payload=? WHERE entity_id=?",
                    (json.dumps({**profile, "contact_email": "new@example.com"}), entity_id),
                )
            changed.append(True)
        return original(workspace, entity_id, db)

    monkeypatch.setattr(contact_outcomes, "directory_contact", change_contact_before_summary)
    during = store.lead(entity["id"])
    assert changed == [True], "A read snapshot must allow the concurrent writer to finish"
    assert during["entity_profile"]["contact_email"] == ""
    assert during["entity_review"]["required"] is True

    after = store.lead(entity["id"])
    assert after["entity_profile"]["contact_email"] == "new@example.com"
    assert after["entity_review"]["required"] is False
    assert after["entity_review"]["complete"] is True
