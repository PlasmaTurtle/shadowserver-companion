"""Additive storage, refresh history and evidence export behavior."""

import hashlib
import json
import zipfile

import pytest

from schema_helpers import restore_schema
from test_contacts_invariants_090 import attributed_entity, contact_result
from workbench.contact_records import ContactRecords
from workbench.migrations import SCHEMA_VERSION
from workbench.store import Store
from workbench.workspace_data import export_workspace, unpack_workspace


@pytest.fixture
def saved(tmp_path):
    store = Store(tmp_path / "data")
    entity = attributed_entity(store)
    return store, ContactRecords(store), entity


def test_schema_seven_upgrade_preserves_manual_profile(tmp_path):
    store = Store(tmp_path / "legacy")
    entity = attributed_entity(store)
    with store.transaction() as db:
        db.execute(
            "INSERT INTO entity_profiles VALUES(?,?)",
            (entity["id"], json.dumps({"contact_email": "manual@example.com"})),
        )
        restore_schema(db, 7)
        db.execute("PRAGMA user_version=7")
    restored = Store(store.root)
    assert restored.one("PRAGMA user_version")["user_version"] == SCHEMA_VERSION
    assert restored.lead(entity["id"])["entity_profile"]["contact_email"] == "manual@example.com"
    assert list((store.root / "backups").glob(f"before-schema-{SCHEMA_VERSION}-*.sqlite3"))


def test_refresh_preserves_decision_ignores_dynamic_page_noise_and_tracks_meaningful_change(saved):
    store, records, entity = saved
    scope = records.scope(entity["id"])
    result = contact_result()
    records.save_run(scope, result)
    candidate = records.state(entity["id"])["candidates"][0]
    records.review(entity["id"], candidate["id"], "confirm", candidate["revision"])
    second = contact_result()
    second["snapshots"][0]["body"] += b"<footer>New unrelated copyright</footer>"
    second["snapshots"][0]["sha256"] = hashlib.sha256(second["snapshots"][0]["body"]).hexdigest()
    records.save_run(scope, second)
    current = records.state(entity["id"])["candidates"][0]
    assert current["id"] == candidate["id"] and current["decision"] == "confirmed"
    assert not current["review_required"] and len(current["sources"]) == 2
    third = contact_result()
    third["candidates"][0]["purpose"] = "general"
    records.save_run(scope, third)
    current = records.state(entity["id"])["candidates"][0]
    assert (
        current["decision"] == "confirmed"
        and current["source_changed"]
        and not current["review_required"]
    )
    records.review(entity["id"], current["id"], "confirm", current["revision"])
    assert not records.state(entity["id"])["candidates"][0]["source_changed"]
    assert len(store.all("SELECT * FROM contact_reviews")) == 2


def test_partial_refresh_does_not_assert_contact_disappearance(saved):
    _, records, entity = saved
    scope = records.scope(entity["id"])
    records.save_run(scope, contact_result())
    result = contact_result(candidates=False)
    result["status"] = "partial"
    records.save_run(scope, result)
    assert not records.state(entity["id"])["candidates"][0]["missing_from_latest"]


def test_merge_retains_sources_decisions_and_original_ownership(saved):
    store, records, entity = saved
    records.save_run(records.scope(entity["id"]), contact_result())
    candidate = records.state(entity["id"])["candidates"][0]
    records.review(entity["id"], candidate["id"], "confirm", candidate["revision"])
    attributed_entity(store, "other.example", "target")
    store.merge_entities(entity["id"], "target", 0, 0)
    state = records.state("target")
    assert state["candidates"][0]["decision"] == "confirmed"
    assert state["runs"][0]["original_entity_id"] == entity["id"]
    assert state["runs"][0]["entity_id"] == "target"
    assert records.state(entity["id"])["entity_id"] == "target"
    path = records.export("target")
    assert zipfile.is_zipfile(path)
    path.unlink()


def test_scope_rejects_unapproved_root_and_export_has_full_capture_chain(saved):
    store, records, entity = saved
    with pytest.raises(ValueError, match="outside"):
        records.scope(entity["id"], "evil.example")
    records.save_run(records.scope(entity["id"]), contact_result(value="security@external.example"))
    path = records.export(entity["id"])
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        assert all(not name.endswith(".html") for name in names)
        assert any("/attribution/" in name and name.endswith("result.json") for name in names)
        assert any(name.endswith(".contact.json") for name in names)
        assert not any(name.endswith(".body.txt") for name in names)
        projection = json.loads(archive.read("provenance.json"))
        assert "security@external.example" in projection["candidates"][0]["provenance_text"]
        assert "body" not in projection["runs"][0]["snapshots"][0]
    path.unlink()
    backup = export_workspace(store)
    unpack_workspace(backup, store.root.parent / "restored")
    restored = ContactRecords(Store(store.root.parent / "restored"))
    assert restored.state(entity["id"])["candidates"][0]["value"] == "security@external.example"
    backup.unlink()


def test_invalid_capture_does_not_leave_partial_files_or_rows(saved):
    store, records, entity = saved
    result = contact_result()
    result["candidates"][0]["sources"][0]["url"] = "https://evil.example/"
    with pytest.raises(ValueError, match="saved source"):
        records.save_run(records.scope(entity["id"]), result)
    assert not store.all("SELECT * FROM contact_runs")
    assert not list((store.root / "evidence" / "contact-discovery").rglob("*.txt"))


def test_refresh_keeps_normalized_contact_identity_and_rejects_false_keys(saved):
    _, records, entity = saved
    scope = records.scope(entity["id"])
    records.save_run(scope, contact_result())
    candidate = records.state(entity["id"])["candidates"][0]
    records.review(entity["id"], candidate["id"], "confirm", candidate["revision"])
    records.save_run(scope, contact_result(value="Security@Example.com"))
    current = records.state(entity["id"])["candidates"][0]
    assert current["id"] == candidate["id"] and current["decision"] == "confirmed"
    assert current["value"] == "Security@Example.com"
    changed = contact_result(value="unrelated@external.example")
    changed["candidates"][0]["key"] = candidate["key"]
    with pytest.raises(ValueError, match="key"):
        records.save_run(scope, changed)
