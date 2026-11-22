"""Discovery uses retained working websites without changing focused-source semantics."""

import json

import pytest

from modules.entities.components.contact_discovery import ContactDiscovery, FetchResponse
from modules.entities.components.contact_jobs import ContactDiscoveryJobs
from modules.entities.tests.support.contact_discovery import FixtureFetcher, html
from modules.entities.tests.support.contacts import attributed_entity
from modules.entities.tests.support.contacts_api import finished
from modules.investigations.components import website_evidence
from modules.workspace.components.store import Store
from tests.support.qualification import capture_website


@pytest.mark.parametrize("status", [404, 503])
def test_failed_apex_tries_www_within_existing_budget(status):
    fetcher = FixtureFetcher(
        {
            "https://example.org/": FetchResponse(status, {}, b""),
            "https://www.example.org/": html('<a href="/contact">Contact us</a>'),
            "https://www.example.org/contact": html(
                "<p>Security contact: security@example.org</p>"
            ),
        }
    )
    result = ContactDiscovery(fetcher=fetcher).discover("example.org")
    assert [c["value"] for c in result["candidates"]] == ["security@example.org"]
    assert result["resolved_hostname"] == "www.example.org"
    assert result["request_count"] <= 6
    assert len(fetcher.calls) == len(set(fetcher.calls))
    assert "https://www.example.org/.well-known/security.txt" in fetcher.calls


def test_focused_lookup_does_not_fall_back_to_other_host():
    fetcher = FixtureFetcher(
        {"https://www.example.org/": html("<p>Security contact: security@example.org</p>")}
    )
    result = ContactDiscovery(fetcher=fetcher).discover(
        "example.org", source_url="https://example.org/contact"
    )
    assert fetcher.calls == ["https://example.org/contact"]
    assert result["candidates"] == []


def test_automatic_discovery_starts_at_retained_www_and_crawls_contacts(tmp_path):
    store = Store(tmp_path / "workspace")
    entity = attributed_entity(store)
    url = "https://www.example.com/"
    png, metadata = capture_website(url)
    capture = website_evidence.retain(store, png, metadata, root_domain="example.com")
    with store.transaction() as db:
        website_evidence.bind(db, capture["id"], entity["id"], root_domain="example.com")
        db.execute("INSERT INTO entity_contact_queue(entity_id) VALUES(?)", (entity["id"],))
    fetcher = FixtureFetcher(
        {
            url: html('<a href="/contact">Contact us</a>'),
            url + "contact": html("<p>Security contact: security@example.com</p>"),
        }
    )
    jobs = ContactDiscoveryJobs(store, discovery_factory=lambda: ContactDiscovery(fetcher=fetcher))
    try:
        job = jobs.automatic_once()
        completed = finished(jobs, job["id"])
        assert completed["state"] == "completed", completed
        assert fetcher.calls[0] == url
        assert "https://example.com/" not in fetcher.calls
        assert url + "contact" in fetcher.calls
        saved = json.loads(store.one("SELECT payload FROM contact_runs")["payload"])
        assert saved["start_url"] == url
        assert saved["source_url"] == ""
        assert saved["candidates"][0]["value"] == "security@example.com"
        calls = list(fetcher.calls)
        cached = finished(jobs, jobs.start(entity["id"])["id"])
        assert cached["cached"] and fetcher.calls == calls
    finally:
        jobs.close()
