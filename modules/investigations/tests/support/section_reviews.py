"""Reusable synthetic section reviews fixtures and builders."""

from copy import deepcopy

from tests.support.workbench import import_rows, ready


def prepared(client, app, *, validate=True):
    import_rows(client, app)
    lead_id = client.get("/api/leads").json()[0]["id"]
    return ready(client, lead_id, validate=validate)


def status(lead, key):
    return next(r for r in lead["section_reviews"] if r["key"] == key)


def save(client, lead, **changes):
    draft = deepcopy(lead["draft"])
    draft.update(changes)
    return client.put(
        "/api/leads/" + lead["id"] + "/draft",
        json={"expected_revision": lead["draft_revision"], "fields": draft},
    )


def change(client, lead, ids, decision="exclude", **extra):
    return client.post(
        "/api/cases/" + lead["case_id"] + "/observation-scope",
        json={
            "expected_version": lead["case"]["version"],
            "expected_revision": lead["draft_revision"],
            "entry_ids": ids,
            "decision": decision,
            "reason": "Synthetic analyst review: source observation does not belong in this notification.",
            **extra,
        },
    )
