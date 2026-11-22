"""Reusable synthetic template fixtures and builders."""

from tests.support.workbench import import_rows


def open_lead(client, app):
    import_rows(client, app)
    return client.get("/api/leads/" + client.get("/api/leads").json()[0]["id"]).json()


def save(client, lead, **changes):
    draft = {**lead["draft"], **changes}
    r = client.put(
        "/api/leads/" + lead["id"] + "/draft",
        json={"expected_revision": lead["draft_revision"], "fields": draft},
    )
    assert r.status_code == 200, r.text
    return r.json()
