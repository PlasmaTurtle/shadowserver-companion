"""Reusable synthetic acceptance fixtures and builders."""

from tests.support.workbench import import_rows, observations, validate_sections

CVE = "CVE-2025-12345"


def open_case(client, app, tag="eol-php"):
    rows = observations()
    for row in rows:
        row["tag"] = tag
    # A fresh workspace has no local catalog. Real Evaluate/Library selection
    # retains that unavailable state without contacting a provider.
    import_rows(client, app, rows)
    return client.get("/api/cases/" + client.get("/api/cases").json()[0]["id"]).json()


def save_case(client, lead, **changes):
    fields = {**lead["draft"], **changes}
    response = client.put(
        "/api/leads/" + lead["id"] + "/draft",
        params={"case_id": lead["case_id"]},
        json={"expected_revision": lead["draft_revision"], "fields": fields},
    )
    assert response.status_code == 200, response.text
    return response.json()


def review_case(client, lead, **changes):
    lead = save_case(
        client,
        lead,
        company="Acceptance Example",
        sender_name="Acceptance Analyst",
        website_verified=True,
        reviewed=True,
        **changes,
    )
    # Adopting sources or disposition changes clears review. Review is a second,
    # explicit action once the new content is available to the analyst.
    if not lead["draft"]["reviewed"]:
        lead = save_case(client, lead, reviewed=True)
    return lead


def certify(client, lead):
    lead = validate_sections(client, lead)
    response = client.post(
        "/api/leads/" + lead["id"] + "/finalize", params={"case_id": lead["case_id"]}
    )
    assert response.status_code == 200, response.text
    return response.json()
