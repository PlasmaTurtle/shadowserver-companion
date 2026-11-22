"""Delivered coverage follows saved recipient scope without changing history."""

import pytest

from tests.support.workbench import app, client, import_rows, observations
from tests.support.acceptance import CVE, open_case, review_case, certify
from modules.investigations.tests.support.cases import attempt, closing_values
from modules.investigations.components.cve_state import cve_excluded, excluded_cves
from modules.entities.components.finding_history import entity_finding_history
from modules.library.components.intelligence_index import notification_records
from modules.investigations.components.report_composition import resolved_record


@pytest.mark.parametrize("reason,excluded", [("", False), (" \n\t", False), ("Reviewed", True)])
def test_reasoned_cve_scope_has_one_predicate(reason, excluded):
    draft = {
        "cve_dispositions": {CVE: {"action": "exclude", "reason": reason}},
        "cve_records": [{"id": CVE, "verification_status": "unavailable"}],
    }
    assert cve_excluded(CVE, draft) is excluded
    assert (CVE in excluded_cves(draft)) is excluded
    assert (resolved_record(CVE, draft)[1] == "excluded") is excluded
    assert bool(notification_records(draft)) is not excluded


def history(store, entity_id):
    with store.read_snapshot() as db:
        return entity_finding_history(db, entity_id)["items"]


def assert_excluded_cve_not_covered(items):
    cves = [item for item in items if item["finding"] == CVE and item["ip"] != "10.1.2.3"]
    assert cves
    assert all(not item["notifications"] and item["state"] != "covered" for item in cves)


def test_excluded_cve_has_no_delivery_coverage_after_close_and_new_scan(client, app):
    lead = review_case(
        client,
        open_case(client, app, CVE + ";eol-php"),
        cve_dispositions={
            CVE: {
                "action": "exclude",
                "reason": "Synthetic review: CVE claim unsupported; EOL remains in scope.",
            }
        },
    )
    report = certify(client, lead)
    store = app.state.store
    folder = store.path(report["path"])
    files = {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    sources = store.all("SELECT id,payload FROM entries ORDER BY id")
    lead = client.get("/api/cases/" + lead["case_id"]).json()
    response = client.post(
        "/api/cases/" + lead["case_id"] + "/attempts", json=attempt(lead, report)
    )
    assert response.status_code == 200, response.text
    delivered = response.json()
    assert_excluded_cve_not_covered(delivered["finding_history"]["items"])
    assert any(
        item["notifications"]
        for item in delivered["finding_history"]["items"]
        if item["finding"].startswith("eol-php") and item["ip"] != "10.1.2.3"
    )
    attempts = store.all("SELECT * FROM contact_attempts")
    response = client.post(
        "/api/cases/" + lead["case_id"] + "/close", json=closing_values(delivered)
    )
    assert response.status_code == 200, response.text
    prior_history = history(store, lead["id"])
    assert_excluded_cve_not_covered(prior_history)
    assert sources == store.all("SELECT id,payload FROM entries ORDER BY id")
    rows = [
        {**row, "tag": CVE + ";eol-php", "timestamp": "2026-12-01 02:00:00"}
        for row in observations()
    ]
    import_rows(client, app, rows, "later-scan.csv", start_notifications=False)
    items = history(store, lead["id"])
    assert_excluded_cve_not_covered(items)
    # Existing handled scope stops before qualification. The new source stays
    # available in Dark Matter without creating another canonical finding event.
    assert items == prior_history
    archived = [
        item
        for item in store.dark_matter.query(limit=100)["items"]
        if item["reason"] == "no_actionable_findings"
    ]
    assert archived and all(
        str(item["raw_fields"]["timestamp"]).startswith("2026-12-01") for item in archived
    )
    assert attempts == store.all("SELECT * FROM contact_attempts")
    assert files == {
        str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob("*") if p.is_file()
    }
    historical = client.get("/api/cases/" + lead["case_id"]).json()
    assert historical["case"]["stage"] == "closed"
    assert historical["reports"][0]["id"] == report["id"]
