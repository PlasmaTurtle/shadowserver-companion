"""Coverage and routing decisions remain evidence-bound, scoped, and delivery-neutral."""

from copy import deepcopy
from hashlib import sha256
import json
from uuid import uuid4

import pytest

from modules.entities.tests.support.contacts_api import fixture, finished
from modules.entities.tests.support.contacts import records, contact_result
from modules.investigations.components.cases import Cases
from modules.entities.components.contact_discovery import candidate_key
from modules.entities.components.contact_validation import validate_contact_data

from modules.entities.components.contact_discovery.engine import REVISION


def captured(
    *,
    url="https://example.com/",
    purpose="security",
    value="security@example.com",
    present=True,
    state="checked",
):
    result = contact_result(value=value, candidates=present)
    result.update(
        discovery_revision=REVISION,
        aliases=["www.example.com"],
        source_url=url,
        outcome="reporting_route_found" if present else "checked_no_suitable_contact",
        next_step="Review the published route." if present else "Try another published source.",
    )
    snapshot = result["snapshots"][0]
    snapshot["url"] = url
    result["coverage"] = [
        {
            "url": url,
            "state": state,
            "checked_at": result["finished_at"],
            "snapshot_id": snapshot["id"],
            "status_code": 200,
            "candidate_count": int(present),
            "next_step": result["next_step"],
        }
    ]
    if present:
        result["candidates"][0]["sources"][0]["url"] = url
        result["candidates"][0]["purpose"] = purpose
    return result


def test_focused_api_validates_scope_before_job_and_passes_exact_source(fixture):
    app, client, entity, _, _ = fixture
    calls = []

    class Core:
        def discover(self, root, *, aliases, source_url=None, cancel_event=None):
            calls.append((root, aliases, source_url))
            return captured(url=source_url)

    jobs = app.state.contact_discovery_jobs
    jobs.core_factory = Core
    endpoint = f"/api/entities/{entity['id']}/contacts/discover"
    for url in (
        "https://security.example.com/report",
        "https://external.example/report",
        "http://example.com/contact",
        "https://example.com:444/contact",
    ):
        assert client.post(endpoint, json={"source_url": url}).status_code == 422
    assert calls == []
    response = client.post(endpoint, json={"source_url": "https://www.example.com/contact"})
    assert response.status_code == 200, response.text
    assert finished(jobs, response.json()["id"])["state"] == "completed"
    assert calls == [("example.com", ("www.example.com",), "https://www.example.com/contact")]
    state = client.get(endpoint.removesuffix("/discover")).json()
    assert state["latest_run"]["source_url"] == "https://www.example.com/contact"
    assert state["latest_run"]["coverage"][0]["state"] == "checked"
    assert state["latest_run"]["next_step"] == "Review the published route."
    assert state["contact_readiness"]["has_usable_contact"] is True


def test_cache_never_reuses_full_search_for_focused_page(fixture):
    app, client, entity, _, calls = fixture
    endpoint = f"/api/entities/{entity['id']}/contacts/discover"
    jobs = app.state.contact_discovery_jobs
    for body in (
        {},
        {"source_url": "https://example.com/contact"},
        {"source_url": "https://example.com/contact"},
        {"source_url": "https://example.com/security"},
    ):
        response = client.post(endpoint, json=body)
        result = finished(jobs, response.json()["id"])
        assert result["state"] == "completed"
    assert len(calls) == 3


def test_focused_empty_lookup_preserves_unchecked_publication(records):
    _, contacts, entity = records
    contacts.save_run(contacts.scope(entity["id"]), captured(url="https://example.com/security"))
    original = contacts.state(entity["id"])["candidates"][0]
    contacts.review(entity["id"], original["id"], "confirm", original["revision"])
    contacts.save_run(
        contacts.scope(entity["id"]),
        captured(url="https://example.com/contact", present=False, state="checked_empty"),
    )
    state = contacts.state(entity["id"])
    assert not state["candidates"][0]["missing_from_latest"]
    assert state["candidates"][0]["usable"]
    assert state["best_route_id"] == original["id"]


@pytest.mark.parametrize(
    "checked_state,missing",
    [
        ("checked_empty", True),
        ("not_found", True),
        ("blocked", False),
        ("incomplete", False),
        ("unvisited", False),
    ],
)
def test_negative_evidence_only_applies_to_checked_source(records, checked_state, missing):
    _, contacts, entity = records
    contacts.save_run(contacts.scope(entity["id"]), captured())
    contacts.save_run(contacts.scope(entity["id"]), captured(present=False, state=checked_state))
    assert contacts.state(entity["id"])["candidates"][0]["missing_from_latest"] is missing


def test_route_metadata_changes_stay_visible_and_cannot_be_forged(records):
    store, contacts, entity = records
    original = captured()
    route = original["candidates"][0]
    route.update(
        kind="form",
        value="https://vendor.example/disclosure",
        key=candidate_key("form", "https://vendor.example/disclosure"),
        route_type="published_link",
        external_destination=True,
        routing_label="Report a security issue",
        routing_options=[{"label": "Webmaster", "purpose": "it"}],
        original_url="https://vendor.example/disclosure",
    )
    contacts.save_run(contacts.scope(entity["id"]), original)
    candidate = contacts.state(entity["id"])["candidates"][0]
    assert "Routing instruction: Report a security issue" in candidate["provenance_text"]
    contacts.review(entity["id"], candidate["id"], "confirm", candidate["revision"])
    revised = captured()
    revised["candidates"][0] = deepcopy(route)
    revised["candidates"][0]["sources"] = captured()["candidates"][0]["sources"]
    revised["candidates"][0]["sources"][0]["snapshot_id"] = revised["snapshots"][0]["id"]
    revised["candidates"][0]["routing_options"] = [
        {"label": "Customer support", "purpose": "product_support"}
    ]
    contacts.save_run(contacts.scope(entity["id"]), revised)
    candidate = contacts.state(entity["id"])["candidates"][0]
    assert candidate["source_changed"] and not candidate["review_required"]
    validate_contact_data(store, entity["id"])
    row = store.one("SELECT payload FROM contact_candidates WHERE id=?", (candidate["id"],))
    forged = json.loads(row["payload"])
    forged["routing_label"] = "Invented security destination"
    with store.transaction() as db:
        db.execute(
            "UPDATE contact_candidates SET payload=? WHERE id=?",
            (json.dumps(forged), candidate["id"]),
        )
    with pytest.raises(ValueError, match="retained published"):
        contacts.review(entity["id"], candidate["id"], "confirm", candidate["revision"])


def test_physical_emergency_is_retained_but_not_suggested_or_adoptable(records):
    store, contacts, entity = records
    result = captured(purpose="physical_emergency")
    route = result["candidates"][0]
    route.update(kind="phone", value="855-945-5762", key=candidate_key("phone", "855-945-5762"))
    contacts.save_run(contacts.scope(entity["id"]), result)
    candidate = contacts.state(entity["id"])["candidates"][0]
    contacts.review(entity["id"], candidate["id"], "confirm", candidate["revision"])
    state = contacts.state(entity["id"])
    candidate = state["candidates"][0]
    assert not candidate["usable"] and not candidate["can_adopt"] and state["best_route_id"] is None
    assert not state["contact_readiness"]["has_usable_contact"]
    case = Cases(store).create(entity["id"])
    version = store.one("SELECT version FROM cases WHERE id=?", (case["case_id"],))["version"]
    with pytest.raises(ValueError, match="physical-emergency"):
        contacts.use(Cases(store), case["case_id"], candidate["id"], version, candidate["revision"])


def test_eight_captured_responses_persist_and_ninth_is_rejected(records):
    store, contacts, entity = records
    result = captured()
    for index in range(7):
        snapshot = deepcopy(result["snapshots"][0])
        snapshot.update(
            id=uuid4().hex,
            url=f"https://example.com/page-{index}",
            status_code=302 if index < 2 else 200,
        )
        result["snapshots"].append(snapshot)
    result["request_count"] = 8
    saved = contacts.save_run(contacts.scope(entity["id"]), result)
    assert len(saved["snapshots"]) == 8
    validate_contact_data(store, entity["id"])
    result["request_count"] = 9
    with pytest.raises(ValueError, match="capture budget"):
        contacts.save_run(contacts.scope(entity["id"]), result)


def test_conflicting_purpose_never_becomes_automated_best_route(records):
    _, contacts, entity = records
    result = captured(purpose="other")
    result["candidates"][0].update(purpose_conflict=True, recommended_for_outreach=False)
    contacts.save_run(contacts.scope(entity["id"]), result)
    state = contacts.state(entity["id"])
    assert state["best_route_id"] is None
    assert state["candidates"][0]["routine_suggestion"] is False
