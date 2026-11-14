"""Browser number round-trips and fast local jobs retain immutable source adoption."""

from copy import deepcopy

import pytest

from test_report_api_040 import opened, save, source
from test_workbench import app, client, ready
from test_cve_catalog_integration_0983 import catalog_record
from workbench.intelligence import acquisition, service


def browser_numbers(value):
    """JSON.stringify serializes an integral JavaScript Number without '.0'."""
    if type(value) is float and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {key: browser_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [browser_numbers(item) for item in value]
    return value


def scored_source():
    return {
        **source(),
        "cvss": 10.0,
        "cvss_assessments": [{"score": 10.0, "version": "3.1", "source": "NVD"}],
        "epss": 1.0,
        "kev": True,
        "record": {"metrics": {"baseScore": 10.0, "impactScore": 6.0}},
    }


def test_browser_number_roundtrip_saves_and_freezes_unchanged_sources(client, app, monkeypatch):
    lead = opened(client, app, cve=True)
    local = catalog_record()
    local["cve"]["metrics"]["cvssMetricV31"][0]["cvssData"]["baseScore"] = 10.0
    monkeypatch.setattr(acquisition, "catalog_record", lambda *_: local)
    monkeypatch.setattr("workbench.api.enrich", service.verify)
    fetched = client.post("/api/cves/CVE-2025-12345/retrieve").json()
    submitted = browser_numbers(fetched)
    assert type(fetched["cvss"]) is float and type(submitted["cvss"]) is int
    adopted = save(client, lead, cve_records=[submitted])
    assert adopted.status_code == 200, adopted.text
    frozen = ready(client, lead["id"])
    assert frozen["draft"]["cve_records"] == [submitted]
    assert all(section["status"] == "validated" for section in frozen["section_reviews"])


def test_immediately_completed_source_job_can_be_adopted_without_poll(client, app, monkeypatch):
    lead = opened(client, app, cve=True)
    monkeypatch.setattr(
        app.state.source_jobs,
        "start",
        lambda *_: {"id": "instant", "status": "completed", "results": [scored_source()]},
    )
    completed = client.post("/api/source-jobs", json={"cve_ids": ["CVE-2025-12345"]})
    assert completed.status_code == 200
    adopted = save(client, lead, cve_records=browser_numbers(completed.json()["results"]))
    assert adopted.status_code == 200, adopted.text


@pytest.mark.parametrize(
    "change",
    [
        {"description": "An analyst altered the published text."},
        {"cvss": 9.9},
        {"record": {"metrics": {"baseScore": 10, "impactScore": 5}}},
        {"kev": 1},
    ],
)
def test_source_number_compatibility_never_allows_text_metric_or_type_edits(
    client, app, monkeypatch, change
):
    lead = opened(client, app, cve=True)
    monkeypatch.setattr("workbench.api.enrich", lambda *args, **kwargs: scored_source())
    fetched = client.post("/api/cves/CVE-2025-12345/retrieve").json()
    changed = {**browser_numbers(fetched), **deepcopy(change)}
    rejected = save(client, lead, cve_records=[changed])
    assert rejected.status_code == 422 and "read-only" in rejected.text


def test_saved_source_boolean_cannot_be_changed_into_number(client, app, monkeypatch):
    lead = opened(client, app, cve=True)
    monkeypatch.setattr("workbench.api.enrich", lambda *args, **kwargs: scored_source())
    fetched = client.post("/api/cves/CVE-2025-12345/retrieve").json()
    adopted = save(client, lead, cve_records=[fetched])
    assert adopted.status_code == 200, adopted.text
    changed = {**fetched, "kev": 1}
    rejected = save(client, adopted.json(), cve_records=[changed])
    assert rejected.status_code == 422 and "read-only" in rejected.text
