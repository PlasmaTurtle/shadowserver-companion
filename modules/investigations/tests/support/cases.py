"""Reusable synthetic cases fixtures and builders."""

from tests.support.workbench import import_rows, ready


def opened(client, app):
    import_rows(client, app)
    return client.get("/api/leads/" + client.get("/api/leads").json()[0]["id"]).json()


def certified(client, app):
    lead = opened(client, app)
    ready(client, lead["id"])
    response = client.post("/api/leads/" + lead["id"] + "/finalize")
    assert response.status_code == 200, response.text
    return client.get("/api/cases/" + lead["case_id"]).json(), response.json()


def attempt(lead, report=None, outcome="delivered", **changes):
    return dict(
        expected_version=lead["case"]["version"],
        report_id=report["id"] if report else None,
        occurred_at="2026-11-06T14:30:00-05:00",
        channel="email",
        outcome=outcome,
        recipient="Technology team",
        destination="it@example.com",
        notes="Report received.",
        recorded_by="Test Analyst",
        information_source="administrative",
        **changes,
    )


def closing_values(lead, disposition="notified"):
    return dict(
        expected_version=lead["case"]["version"],
        disposition=disposition,
        conclusion="Outreach concluded with the recorded outcome.",
        closed_by="Test Analyst",
        reviewed=True,
    )
