"""A precise lookup stays small and preserves its captured source."""

from hashlib import sha256

from modules.entities.components.contact_discovery import ContactDiscovery, FetchResponse
from modules.entities.tests.support.contact_discovery import FixtureFetcher, html

ROOT = "https://example.org/"


def test_specific_page_lookup_does_not_follow_navigation_or_security_file():
    page = ROOT + "contact"
    body = '<p>Technical support: help@example.org</p><a href="/team">Our team</a>'
    fetcher = FixtureFetcher({page: html(body), ROOT + "team": html("Unrelated biographies")})
    result = ContactDiscovery(fetcher=fetcher).discover("example.org", source_url=page)
    assert fetcher.calls == [page]
    assert result["request_count"] == 1
    assert result["candidates"][0]["value"] == "help@example.org"
    assert result["outcome"] == "referral_found"
    assert result["snapshots"][0]["sha256"] == sha256(body.encode()).hexdigest()


def test_specific_page_redirect_keeps_partial_complete_contact_without_extra_navigation():
    page = ROOT + "contact"
    final = ROOT + "contact-us"
    fetcher = FixtureFetcher(
        {
            page: FetchResponse(301, {"location": "/contact-us"}, b""),
            final: FetchResponse(
                200,
                {"content-type": "text/html"},
                b'<p>Security contact: security@example.org</p><a href="/support">Support</a><p>cut',
                True,
            ),
        }
    )
    result = ContactDiscovery(fetcher=fetcher).discover("example.org", source_url=page)
    assert fetcher.calls == [page, final]
    assert result["request_count"] == 2 and result["page_request_count"] == 1
    assert result["outcome"] == "reporting_route_found"
    assert result["status"] == "partial"
    assert result["candidates"][0]["sources"][0]["truncated"]
