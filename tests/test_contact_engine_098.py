"""Capture budgets and successful findings are independent of optional-page failures."""

import hashlib

import pytest

from workbench.contact_discovery import ContactDiscovery, DiscoveryLimits, FetchResponse
from workbench.contact_discovery.policy import MAX_PAGE_BYTES, MAX_TOTAL_BYTES
from test_contact_discovery_090 import FixtureFetcher, html

ROOT = "https://example.org/"


def test_larger_successful_page_extracts_contacts_without_retaining_its_scripts():
    body = (
        "<script>" + "x" * (1024 * 1024 + 100) + "</script><p>Security contact: soc@example.org</p>"
    )
    result = ContactDiscovery(fetcher=FixtureFetcher({ROOT: html(body)})).discover("example.org")
    snapshot = result["snapshots"][0]
    assert not snapshot["truncated"]
    assert result["outcome"] == "reporting_route_found"
    assert any(c["value"] == "soc@example.org" for c in result["candidates"])

    assert "body" not in snapshot
    assert snapshot["sha256"] == hashlib.sha256(body.encode()).hexdigest()
    assert snapshot["captured_bytes"] > 1024 * 1024
    assert snapshot["derived_evidence"]["contacts"][0]["value"] == "soc@example.org"


def test_partial_http_200_keeps_contact_and_has_single_capture_reason():
    prefix = "<p>Security contact: soc@example.org</p><p>cut@example.or"
    response = FetchResponse(200, {"content-type": "text/html"}, prefix.encode(), True)
    result = ContactDiscovery(fetcher=FixtureFetcher({ROOT: response})).discover("example.org")
    assert result["outcome"] == "reporting_route_found"
    assert [c["value"] for c in result["candidates"]] == ["soc@example.org"]
    assert result["coverage"][0]["status_code"] == 200
    assert result["coverage"][0]["state"] == "incomplete"
    assert [i["code"] for i in result["issues"]] == ["page_truncated"]
    assert result["snapshots"][0]["sha256"] == hashlib.sha256(prefix.encode()).hexdigest()


def test_contact_survives_blocked_optional_security_file():
    result = ContactDiscovery(
        fetcher=FixtureFetcher(
            {
                ROOT: html("<p>Security contact: soc@example.org</p>"),
                ROOT + ".well-known/security.txt": FetchResponse(403, {}, b"blocked"),
            }
        )
    ).discover("example.org")
    assert result["outcome"] == "reporting_route_found"
    assert result["candidates"][0]["value"] == "soc@example.org"
    assert result["status"] == "partial"


def test_shared_capture_caps_keep_time_and_requests_bounded():
    limits = DiscoveryLimits()
    assert limits.max_page_bytes == MAX_PAGE_BYTES == 4 * 1024 * 1024
    assert limits.max_total_bytes == MAX_TOTAL_BYTES == 12 * 1024 * 1024
    assert (limits.timeout, limits.request_timeout, limits.max_requests) == (30, 8, 8)
    with pytest.raises(ValueError):
        DiscoveryLimits(max_page_bytes=MAX_PAGE_BYTES + 1)
    with pytest.raises(ValueError):
        DiscoveryLimits(max_total_bytes=MAX_TOTAL_BYTES + 1)


def test_default_budget_reaches_trust_and_support_before_security_marketing():
    """Reconstructed Wasabi routing pattern, not an archived website replay."""
    fetcher = FixtureFetcher(
        {
            ROOT: html(
                '<a href="/cloud-object-storage/security">Security</a>'
                '<a href="/company/trust-center">Trust Center</a>'
                '<a href="/contact-us">Contact</a>'
                '<a href="/contact-us/migration">Explore migration incentives</a>'
                '<a href="/support">Support</a>'
            ),
            ROOT + "company/trust-center": html(
                "<p>Report a Security Incident: security@example.org</p>"
                '<a href="/vulnerability-disclosure-program">Vulnerability Disclosure Program</a>'
                '<a href="/company/sec-advisory">Security Advisory Summary</a>'
            ),
            ROOT + "vulnerability-disclosure-program": html(
                "<p>Disclosure program information</p>"
            ),
            ROOT + "support": html(
                "<h2>Need Help?</h2><p>Having technical issues? Email support@example.org.</p>"
            ),
            ROOT + "cloud-object-storage/security": html(
                '<a href="/blog/security-concerns">Security concerns</a>'
            ),
        }
    )
    result = ContactDiscovery(fetcher=fetcher).discover("example.org")
    by_value = {c["value"]: c for c in result["candidates"]}
    assert by_value["security@example.org"]["purpose"] == "security"
    assert by_value["support@example.org"]["purpose"] == "it"
    assert ROOT + "support" in fetcher.calls
    assert ROOT + "cloud-object-storage/security" not in fetcher.calls
    assert result["page_request_count"] <= 6
