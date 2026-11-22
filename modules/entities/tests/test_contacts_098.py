"""Entity-owned contact suggestions work before case creation or attribution."""

from hashlib import sha256
import json
from zipfile import ZipFile

from modules.entities.tests.support.contacts import attributed_entity, contact_result
from modules.investigations.components.cases import Cases
from modules.entities.components.contact_records import ContactRecords
from modules.workspace.components.store import Store
from modules.workspace.components.workspace_data import export_workspace, unpack_workspace
from modules.entities.components.contact_validation import validate_contact_data

from modules.entities.tests.support.contacts import (
    entity_only,
)


def test_entity_only_contact_capture_exports_and_restores_larger_source(tmp_path):
    store = Store(tmp_path / "data")
    entity_id = entity_only(store)
    contacts = ContactRecords(store)
    scope = contacts.scope(entity_id)
    assert scope["basis"] == "entity_domain" and scope["attribution_ref"] is None
    assert not store.all("SELECT * FROM cases")
    result = contact_result()
    body = result["snapshots"][0]["body"] + b" " * (1024 * 1024 + 100)
    result["snapshots"][0].update(body=body, sha256=sha256(body).hexdigest())
    result["bytes_received"] = len(body)
    contacts.save_run(scope, result)
    state = contacts.state(entity_id)
    assert state["contacts"][0]["usable"]
    assert not state["contacts"][0]["review_required"]
    validate_contact_data(store)
    evidence = contacts.export(entity_id)
    with ZipFile(evidence) as archive:
        captured = [name for name in archive.namelist() if name.endswith(".contact.json")]
        assert len(captured) == 1
        content = archive.read(captured[0])
        derived = json.loads(content)
        assert derived["source"]["sha256"] == sha256(body).hexdigest()
        assert derived["contacts"][0]["value"] == "security@example.com"
        assert len(content) < 4096 and body not in content
        assert not any("/attribution/" in name for name in archive.namelist())
    evidence.unlink()
    backup = export_workspace(store)
    restored_path = tmp_path / "restored"
    unpack_workspace(backup, restored_path)
    restored = ContactRecords(Store(restored_path))
    assert restored.state(entity_id)["contacts"][0]["value"] == "security@example.com"
    assert not restored.store.all("SELECT * FROM cases")
    backup.unlink()


def test_unconfirmed_selection_fills_only_blank_fields_without_report_changes(tmp_path):
    store = Store(tmp_path / "data")
    entity = attributed_entity(store)
    contacts = ContactRecords(store)
    case_id = Cases(store).create(entity["id"])["case_id"]
    with store.transaction() as db:
        db.execute("UPDATE cases SET contact_name=? WHERE id=?", ("Typed Name", case_id))
    result = contact_result()
    result["candidates"][0].update(name="Published Name", role="IT Director")
    contacts.save_run(contacts.scope(entity["id"]), result)
    candidate = contacts.state(entity["id"])["candidates"][0]
    assert candidate["decision"] == "pending" and candidate["usable"]
    before = store.one("SELECT * FROM cases WHERE id=?", (case_id,))
    selected = contacts.use(
        Cases(store), case_id, candidate["id"], before["version"], candidate["revision"]
    )
    assert selected["contact_plan"]["contact_name"] == "Typed Name"
    assert selected["contact_plan"]["contact_email"] == "security@example.com"
    assert selected["contact_plan"]["contact_role"] == "IT Director"
    assert set(selected["filled_fields"]) == {"contact_email", "contact_role"}
    after = store.one("SELECT * FROM cases WHERE id=?", (case_id,))
    assert after["draft"] == before["draft"] and after["draft_revision"] == before["draft_revision"]
    assert store.all("SELECT * FROM contact_reviews") == []


def test_saved_and_discovered_contacts_are_unified_without_repeat_lookup(tmp_path):
    store = Store(tmp_path / "data")
    entity_id = entity_only(store)
    with store.transaction() as db:
        db.execute(
            "INSERT INTO entity_profiles VALUES(?,?)",
            (
                entity_id,
                json.dumps(
                    {
                        "contact_email": "security@example.com",
                        "contact_name": "Alex Example",
                        "contact_title": "IT Director",
                        "contact_phone": "+1 (828) 555-0101",
                    }
                ),
            ),
        )
    contacts = ContactRecords(store)
    known = contacts.state(entity_id)["contacts"]
    assert {c["kind"] for c in known} == {"email", "phone"}
    assert all(c["known"] for c in known)
    contacts.save_run(contacts.scope(entity_id), contact_result())
    combined = contacts.state(entity_id)["contacts"]
    assert len(combined) == 2
    email = next(c for c in combined if c["kind"] == "email")
    assert email["known"] and email["sources"]
    assert email["name"] == "Alex Example" and email["role"] == "IT Director"


def test_legacy_attributed_capture_keeps_its_original_provenance(tmp_path):
    store = Store(tmp_path / "data")
    entity = attributed_entity(store)
    contacts = ContactRecords(store)
    scope = contacts.scope(entity["id"])
    assert scope["attribution_ref"] and "basis" not in scope
    contacts.save_run(scope, contact_result())
    candidate = contacts.state(entity["id"])["candidates"][0]
    contacts.review(entity["id"], candidate["id"], "confirm", candidate["revision"])
    before = store.all("SELECT * FROM contact_reviews")
    backup = export_workspace(store)
    unpack_workspace(backup, tmp_path / "legacy-restored")
    restored = ContactRecords(Store(tmp_path / "legacy-restored"))
    assert restored.store.all("SELECT * FROM contact_reviews") == before
    assert restored.state(entity["id"])["runs"][0]["attribution_ref"] == scope["attribution_ref"]
    backup.unlink()


def test_entity_only_contact_history_survives_merge(tmp_path):
    store = Store(tmp_path / "data")
    source = entity_only(store)
    target = entity_only(store, "target", "other.example")
    contacts = ContactRecords(store)
    contacts.save_run(contacts.scope(source), contact_result())
    store.merge_entities(source, target, 0, 0)
    assert contacts.state(target)["contacts"][0]["value"] == "security@example.com"
    validate_contact_data(store)


def test_name_only_known_contact_is_available_without_claiming_delivery_route(tmp_path):
    store = Store(tmp_path / "data")
    entity_id = entity_only(store)
    with store.transaction() as db:
        db.execute(
            "INSERT INTO entity_profiles VALUES(?,?)",
            (entity_id, json.dumps({"contact_name": "Alex Example", "contact_title": ""})),
        )
    state = ContactRecords(store).state(entity_id)
    assert len(state["contacts"]) == 1
    assert state["contacts"][0]["kind"] == "person"
    assert state["contacts"][0]["value"] == "Alex Example"
    assert not state["contact_readiness"]["has_usable_contact"]
