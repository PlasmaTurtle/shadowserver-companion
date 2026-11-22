"""Duplicate routes show current evidence without losing adverse history."""

import json

from modules.entities.tests.support.contacts import entity_only
from modules.entities.tests.support.contacts import contact_result
from modules.entities.components.contact_discovery import ContactDiscovery, candidate_key
from modules.entities.tests.support.contact_discovery import FixtureFetcher, html
from modules.entities.components.contact_records import ContactRecords
from modules.workspace.components.store import Store


def test_equivalent_phone_formats_show_current_record_with_all_saved_sources(tmp_path):
    store = Store(tmp_path / "data")
    entity = entity_only(store)
    records = ContactRecords(store)
    with store.transaction() as db:
        db.execute(
            "INSERT INTO entity_profiles VALUES(?,?)",
            (
                entity,
                json.dumps({"contact_phone": "(828) 555-0101", "contact_name": "Manual name"}),
            ),
        )
    for value in ("+1 (828) 555-0101", "828-555-0101"):
        result = ContactDiscovery(
            fetcher=FixtureFetcher(
                {"https://example.com/": html(f"<p>IT department phone: {value}</p>")}
            )
        ).discover("example.com", source_url="https://example.com/")
        records.save_run(records.scope(entity), result)
    state = records.state(entity)
    assert len(state["candidates"]) == 2
    assert len(state["contacts"]) == 1
    contact = state["contacts"][0]
    assert contact["value"] == "828-555-0101"
    assert not contact["missing_from_latest"]
    assert contact["known"] and contact["name"] == "Manual name"
    assert len(contact["sources"]) == 2
    records.route_decision(
        entity, contact["id"], "unusable", "Number disconnected", contact["revision"]
    )
    unavailable = records.state(entity)
    assert len(unavailable["contacts"]) == 1
    assert unavailable["contacts"][0]["unusable"]
    assert all(c["unusable"] for c in unavailable["candidates"])
    assert not unavailable["contact_readiness"]["has_usable_contact"]


def test_legacy_fax_and_recruiting_evidence_is_retained_without_bad_suggestions(tmp_path):
    store = Store(tmp_path / "data")
    entity = entity_only(store)
    records = ContactRecords(store)
    result = contact_result()
    fax = result["candidates"][0]
    fax.update(
        kind="phone",
        value="+1 617-307-7973",
        purpose="general",
        key=candidate_key("phone", "+1 617-307-7973"),
    )
    fax["sources"][0]["excerpt"] = "Phone — +1 617-307-7912 (Intl) +1 617-307-7973 (Fax)"
    result["candidates"].append(
        {
            **fax,
            "kind": "email",
            "value": "dna.recruiting@example.com",
            "purpose": "product_support",
            "key": candidate_key("email", "dna.recruiting@example.com"),
        }
    )
    records.save_run(records.scope(entity), result)
    before = store.all("SELECT * FROM contact_candidates")
    state = records.state(entity)
    by_value = {c["value"]: c for c in state["contacts"]}
    assert by_value["+1 617-307-7973"]["fax"]
    assert not by_value["+1 617-307-7973"]["usable"]
    assert not by_value["+1 617-307-7973"]["can_adopt"]
    assert by_value["dna.recruiting@example.com"]["purpose"] == "hr"
    assert all(not c["routine_suggestion"] for c in state["contacts"])
    assert before == store.all("SELECT * FROM contact_candidates")
    assert len(state["candidates"]) == 2 and len(state["runs"]) == 1
