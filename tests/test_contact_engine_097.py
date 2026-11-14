"""Finite routing and coverage regressions based on observed enterprise failures.

Fixtures reconstruct the recorded failure patterns; they are not website captures.
"""

import asyncio
import hashlib

import pytest

from workbench.contact_discovery import ContactDiscovery, DiscoveryLimits, FetchResponse
from workbench.contact_discovery.policy import DiscoveryError, approved_url
from workbench.contact_discovery.transport import ERROR_BODY_LIMIT, bounded_fetch
from test_contact_discovery_090 import FixtureFetcher, html

ROOT = "https://example.org/"
WWW = "https://www.example.org/"
SECURITY = ".well-known/security.txt"


def run(pages, root="example.org", **kwargs):
    fetcher = FixtureFetcher(pages)
    result = ContactDiscovery(fetcher=fetcher, limits=kwargs.pop("limits", None)).discover(
        root, **kwargs
    )
    return result, fetcher.calls


def test_apex_www_redirect_pair_is_automatic_and_security_files_keep_exact_hosts():
    result, calls = run(
        {
            ROOT: FetchResponse(301, {"location": WWW}),
            WWW: html('<a href="/contact">Contact</a>'),
            ROOT + SECURITY: FetchResponse(
                200,
                {"content-type": "text/plain"},
                b"Contact: mailto:apex@example.org\nExpires: 2099-01-01T00:00:00Z",
            ),
            WWW + SECURITY: FetchResponse(
                200,
                {"content-type": "text/plain"},
                b"Contact: mailto:web@example.org\nExpires: 2099-01-01T00:00:00Z",
            ),
            WWW + "contact": html("<p>Company office: hello@example.org</p>"),
        }
    )
    assert result["resolved_hostname"] == "www.example.org"
    assert result["aliases"] == ["www.example.org"]
    assert ROOT + SECURITY in calls and WWW + SECURITY in calls
    by_value = {c["value"]: c for c in result["candidates"]}
    assert by_value["apex@example.org"]["sources"][0]["url"] == ROOT + SECURITY
    assert by_value["web@example.org"]["sources"][0]["url"] == WWW + SECURITY
    assert (
        result["request_count"] == result["page_request_count"] + result["redirect_request_count"]
    )
    assert result["outcome"] == "reporting_route_found"


def test_starting_www_can_redirect_to_apex_without_allowing_sibling_host():
    result, calls = run(
        {
            WWW: FetchResponse(301, {"location": ROOT}),
            ROOT: html("<p>Security contact: sec@example.org</p>"),
        },
        root="www.example.org",
    )
    assert result["aliases"] == ["example.org"] and ROOT in calls
    result, calls = run({ROOT: FetchResponse(302, {"location": "https://login.example.org/"})})
    assert all("login.example.org" not in url for url in calls)
    assert any(i["code"] == "redirect_outside_scope" for i in result["issues"])


def test_two_redirect_allowance_and_six_page_slots_are_independently_bounded():
    links = "".join(f'<a href="/contact-{i}">Contact office {i}</a>' for i in range(8))
    pages = {
        ROOT: FetchResponse(301, {"location": WWW}),
        WWW: html(links),
        ROOT + SECURITY: FetchResponse(301, {"location": WWW + SECURITY}),
    }
    pages.update({WWW + f"contact-{i}": html("<p>General office</p>") for i in range(8)})
    result, calls = run(pages)
    assert len(calls) == result["request_count"] == 8
    assert result["page_request_count"] == 6 and result["redirect_request_count"] == 2
    assert len(calls) == len(set(calls))
    assert result["status"] == "partial"
    assert any(c["state"] == "unvisited" for c in result["coverage"])


def test_redirect_chain_stops_and_does_not_borrow_unlimited_page_slots():
    pages = {
        ROOT: FetchResponse(302, {"location": "/one"}),
        ROOT + "one": FetchResponse(302, {"location": "/two"}),
        ROOT + "two": FetchResponse(302, {"location": "/three"}),
    }
    result, calls = run(pages)
    assert ROOT + "three" not in calls
    assert result["redirect_request_count"] == 2
    assert any(i["code"] == "redirect_limit" for i in result["issues"])


def test_promising_reporting_link_gets_one_additional_hop_without_recursing():
    result, calls = run(
        {
            ROOT: html('<a href="/contact">Contact</a><a href="/careers/team">Our team</a>'),
            ROOT + "contact": html('<a href="/responsible-disclosure">Report a vulnerability</a>'),
            ROOT + "responsible-disclosure": html(
                '<p>Cybersecurity report: infosec@example.org</p><a href="/security/deeper">Report security issue</a>'
            ),
            ROOT + "security/deeper": html("<p>deep@example.org</p>"),
        }
    )
    assert ROOT + "responsible-disclosure" in calls
    assert ROOT + "security/deeper" not in calls
    assert any(
        c["value"] == "infosec@example.org" and c["purpose"] == "security"
        for c in result["candidates"]
    )


def test_targeted_source_does_not_repeat_homepage_or_security_file():
    result, calls = run(
        {
            ROOT + "contact": html('<a href="/disclosure">Report a vulnerability</a>'),
            ROOT + "disclosure": html("<p>Security report: soc@example.org</p>"),
        },
        source_url=ROOT + "contact?utm_source=footer",
    )
    assert calls == [ROOT + "contact"]
    assert result["source_url"] == ROOT + "contact"
    bad, calls = run({}, source_url="https://login.example.org/contact")
    assert not calls and bad["status"] == "failed"


@pytest.mark.parametrize(
    "query",
    [
        "cm_sp=footer-_-navigation-_-responsible+disclosure",
        "utm_source=x&utm_campaign=security",
        "gclid=x&fbclid=y",
    ],
)
def test_only_known_tracking_queries_are_removed(query):
    assert approved_url(ROOT + "contact?" + query, {"example.org"}) == ROOT + "contact"


@pytest.mark.parametrize(
    "query",
    ["next=https://evil.example", "utm_source=x&redirect=y", "foo=x", "utm_custom=x", "utm_source"],
)
def test_unknown_or_malformed_queries_remain_unfetched(query):
    with pytest.raises(DiscoveryError):
        approved_url(ROOT + "contact?" + query, {"example.org"})


def test_blocked_and_checked_empty_sources_have_distinct_coverage():
    blocked, _ = run({ROOT: FetchResponse(403, {"content-type": "text/html"}, b"blocked")})
    empty, _ = run({ROOT: html("<p>Company information</p>")})
    assert blocked["outcome"] == "blocked"
    assert next(c for c in blocked["coverage"] if c["url"] == ROOT)["state"] == "blocked"
    assert empty["outcome"] == "checked_no_suitable_contact"
    assert next(c for c in empty["coverage"] if c["url"] == ROOT)["state"] == "checked_empty"
    assert empty["next_step"] == ""


def test_javascript_shell_requires_manual_rendering_not_empty_contact_claim():
    result, _ = run(
        {
            ROOT: html(
                '<html><head><title>Security portal</title></head><body><div id="root"></div><script src="/app.js"></script></body></html>'
            )
        }
    )
    assert result["status"] == "partial" and result["outcome"] == "incomplete"
    assert result["coverage"][0]["state"] == "incomplete"
    assert any(i["code"] == "render_required" for i in result["issues"])


def test_error_bodies_have_small_cap_and_do_not_exhaust_useful_page_bytes():
    body = b"large404" * 200000
    result, calls = run(
        {
            ROOT: html('<a href="/contact">Contact</a>'),
            ROOT + SECURITY: FetchResponse(404, {"content-type": "text/html"}, body),
            ROOT + "contact": html("<p>Cybersecurity report: soc@example.org</p>"),
        }
    )
    captured = next(s for s in result["snapshots"] if s["url"] == ROOT + SECURITY)
    assert captured["captured_bytes"] == ERROR_BODY_LIMIT
    assert "body" not in captured and captured["derived_evidence"] is None
    assert captured["truncated"] and captured["hash_scope"] == "captured_prefix"
    assert captured["sha256"] == hashlib.sha256(body[:ERROR_BODY_LIMIT]).hexdigest()
    assert (
        next(c for c in result["coverage"] if c["url"] == ROOT + SECURITY)["state"] == "not_found"
    )
    assert result["outcome"] == "reporting_route_found"


def test_truncated_prefix_keeps_complete_contacts_and_truthful_hash():
    page = '<a href="/report">Responsible disclosure</a><p>security@example.org</p><a href="mailto:cut@example'
    result, calls = run(
        {
            ROOT: html(page + "x" * 500),
            ROOT + "report": html("<p>Cybersecurity report: full@example.org</p>"),
        },
        limits=DiscoveryLimits(max_page_bytes=len(page)),
    )
    snapshot = result["snapshots"][0]
    assert snapshot["truncated"] and snapshot["sha256"] == hashlib.sha256(page.encode()).hexdigest()
    assert ROOT + "report" in calls
    assert any(c["value"] == "security@example.org" for c in result["candidates"])
    assert not any(c["value"] == "cut@example" for c in result["candidates"])
    assert result["status"] == "partial"
    assert result["coverage"][0]["state"] == "incomplete"


def test_published_external_reporting_route_is_visible_but_never_requested():
    result, calls = run(
        {
            ROOT: html(
                '<a href="https://form.vendor.example/disclosure?form=123">Responsible disclosure report</a>'
            )
        }
    )
    assert all("vendor.example" not in u for u in calls)
    candidate = next(c for c in result["candidates"] if c.get("external_destination"))
    assert candidate["original_url"].endswith("?form=123")
    assert not candidate["review_required"] and candidate["sources"][0]["url"] == ROOT
    coverage = next(c for c in result["coverage"] if c["url"] == candidate["value"])
    assert coverage["state"] == "unvisited" and coverage["referrer_url"] == ROOT


def test_redirect_to_already_checked_page_preserves_prior_coverage():
    result, calls = run(
        {
            ROOT: html("<p>Company office: hello@example.org</p>"),
            ROOT + SECURITY: FetchResponse(302, {"location": ROOT}),
        }
    )
    assert calls.count(ROOT) == 1
    homepage = next(c for c in result["coverage"] if c["url"] == ROOT)
    assert homepage["state"] == "checked" and homepage["status_code"] == 200
    redirect = next(c for c in result["coverage"] if c["url"] == ROOT + SECURITY)
    assert redirect["redirect_url"] == ROOT


def test_external_redirect_retains_safe_review_destination_without_fetching():
    target = "https://provider.example/disclosure?form=123"
    result, calls = run({ROOT: FetchResponse(302, {"location": target})})
    assert target not in calls
    assert result["snapshots"][0]["redirect_url"] == target
    assert result["coverage"][0]["redirect_url"] == target
    result, calls = run(
        {ROOT: FetchResponse(302, {"location": "https://secret:password@provider.example/"})}
    )
    assert "redirect_url" not in result["snapshots"][0]


def test_general_contact_later_classified_as_emergency_is_not_recommended():
    result, _ = run(
        {
            ROOT: html('<p>Phone: 855-555-0100</p><a href="/contact">Contact</a>'),
            ROOT + "contact": html("<p>Pipeline emergency: 855-555-0100</p>"),
        }
    )
    phone = next(c for c in result["candidates"] if c["kind"] == "phone")
    assert phone["purpose"] == "physical_emergency"
    assert not phone["recommended_for_outreach"]


def test_failed_attempt_records_time_while_budget_deferred_page_does_not():
    def broken(url, **kwargs):
        raise DiscoveryError("dns_failed", "Synthetic DNS failure")

    result = ContactDiscovery(fetcher=broken).discover("example.org")
    assert all(item["state"] == "unreadable" and item["checked_at"] for item in result["coverage"])
    result, calls = run(
        {ROOT: html('<a href="/contact">Contact</a>')}, limits=DiscoveryLimits(max_requests=1)
    )
    deferred = [item for item in result["coverage"] if item["state"] == "unvisited"]
    assert deferred and all(item["checked_at"] is None for item in deferred)


@pytest.mark.parametrize("root,parent", [("www.github.io", "github.io"), ("www.co.uk", "co.uk")])
def test_www_named_registrable_company_never_expands_to_public_or_private_suffix(root, parent):
    from workbench.contact_discovery.policy import approved_scope

    _, aliases = approved_scope(root)
    assert parent not in aliases and aliases == ("www." + root,)
    url = "https://" + root + "/"
    result, calls = run(
        {url: FetchResponse(301, {"location": "https://" + parent + "/"})}, root=root
    )
    assert not any(u.startswith("https://" + parent + "/") for u in calls)
    assert any(i["code"] == "redirect_outside_scope" for i in result["issues"])
