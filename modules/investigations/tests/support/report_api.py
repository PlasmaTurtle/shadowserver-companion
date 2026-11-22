"""Reusable synthetic report api fixtures and builders."""

import copy

from tests.support.workbench import import_rows, observations


def opened(client, app, cve=False):
    rows = observations()
    if cve:
        rows = [{**row, "tag": "CVE-2025-12345"} for row in rows]
    import_rows(client, app, rows)
    lead_id = client.get("/api/leads").json()[0]["id"]
    return client.get("/api/leads/" + lead_id).json()


def save(client, lead, **fields):
    draft = copy.deepcopy(lead["draft"])
    draft.update(fields)
    return client.put(
        "/api/leads/" + lead["id"] + "/draft?case_id=" + lead["case_id"],
        json={"expected_revision": lead["draft_revision"], "fields": draft},
    )


def source():
    return {
        "id": "CVE-2025-12345",
        "verification_status": "published",
        "description": "Published fixture wording, with its original qualifiers.",
        "retrieved_at": "2026-11-06T12:00:00Z",
        "source": "NVD",
        "public_url": "https://nvd.nist.gov/vuln/detail/CVE-2025-12345",
        "sources": [],
        "cvss": None,
        "epss": None,
        "kev": None,
    }
