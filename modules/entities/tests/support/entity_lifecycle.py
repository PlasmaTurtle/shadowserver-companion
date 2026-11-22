"""Reusable synthetic entity lifecycle fixtures and builders."""

from modules.leads.tests.support.lead_queue import queue_import
from tests.support.workbench import observations


def setup_entities(client, app):
    queue_import(client, app, [observations()[2]], "original.csv")
    source = app.state.store.one("SELECT id FROM leads WHERE domain='example.com'")["id"]
    queue_import(
        client, app, [{**observations()[0], "hostname": "portal.unrelated.com"}], "target.csv"
    )
    target = app.state.store.one("SELECT id FROM leads WHERE domain='unrelated.com'")["id"]
    return source, target


def plan_transfer(client, source, target, hostname="example.com"):
    response = client.get(
        f"/api/entities/{source}/ownership-transfer",
        params={"hostname": hostname, "target_entity_id": target},
    )
    assert response.status_code == 200, response.text
    return response.json()


def transfer(client, source, plan, **changes):
    return client.post(
        f"/api/entities/{source}/ownership-transfer",
        json={
            k: plan[k]
            for k in (
                "hostname",
                "target_entity_id",
                "source_revision",
                "target_revision",
                "review_token",
            )
        }
        | {"reason": "Confirmed sale to an unrelated business", **changes},
    )
