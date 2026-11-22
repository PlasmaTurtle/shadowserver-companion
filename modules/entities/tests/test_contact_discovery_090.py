"""Synthetic-only contact discovery trust, evidence and finite-work regressions."""

import hashlib
import threading
import time

import pytest

from modules.entities.components.contact_discovery import (
    ContactDiscovery,
    DiscoveryLimits,
    FetchResponse,
)
from modules.entities.components.contact_discovery.policy import approved_url, DiscoveryError

from modules.entities.tests.support.contact_discovery import (
    FixtureFetcher,
    ROOT,
    SECURITY,
    html,
)


def discover(pages, **kwargs):
    fetcher = FixtureFetcher(pages)
    return ContactDiscovery(fetcher=fetcher, limits=kwargs.pop("limits", None)).discover(
        "example.org", **kwargs
    ), fetcher


def test_local_contact_role_sources_hashes_and_general_footer():
    page = """<html><title>Contact us</title><body><h1>Information technology and security</h1>
    <div><h3>Alex Smith</h3><span>IT Manager</span> <a href="mailto:alex@external.example">alex@external.example</a></div>
    <footer><p>Customer service <a href="mailto:help@example.org">help@example.org</a></p></footer>
    <p>Phone: +1 (212) 555-0100 ext. 25</p><p>Fax: +1 (212) 555-0199</p>
    <script>const secret = 'script@example.org'</script><style>.x {content: 'style@example.org'}</style>
    <!-- comment@example.org --><div hidden>hidden@example.org</div></body></html>"""
    result, _ = discover({ROOT: html(page)})
    contacts = {c["value"]: c for c in result["candidates"]}
    assert contacts["alex@external.example"]["purpose"] == "it"
    assert contacts["alex@external.example"]["name"] == "Alex Smith"
    assert contacts["help@example.org"]["purpose"] == "general"
    assert any(c["kind"] == "phone" and "25" in c["value"] for c in contacts.values())
    assert not any("0199" in c["value"] for c in contacts.values())
    assert not any(
        x in contacts
        for x in (
            "script@example.org",
            "style@example.org",
            "comment@example.org",
            "hidden@example.org",
        )
    )
    assert result["status"] == "relevant_found"
    snapshot = result["snapshots"][0]
    assert "body" not in snapshot
    assert snapshot["derived_evidence"]["contacts"]
    assert snapshot["sha256"] == hashlib.sha256(page.encode()).hexdigest()
    assert contacts["alex@external.example"]["sources"][0]["snapshot_id"] == snapshot["id"]
    assert all(not c["review_required"] for c in contacts.values())


def test_six_page_budget_prioritizes_one_additional_contact_hop():
    urls = ["contact", "security", "team", "leadership", "about", "support"]
    homepage = "".join(f'<a href="/{x}">{x}</a>' for x in urls)
    pages = {
        ROOT: html(homepage),
        ROOT + "contact": html(
            '<p>hello@example.org</p><a href="/second-level-contact">Contact</a>'
        ),
    }
    result, fetcher = discover(pages)
    assert result["request_count"] == 6
    assert len(fetcher.calls) == 6
    assert ROOT + "second-level-contact" in fetcher.calls
    assert ROOT + "support" in fetcher.calls
    assert ROOT + "team" not in fetcher.calls
    assert ROOT + "security" in fetcher.calls


def test_same_host_redirects_count_and_external_redirect_stops():
    pages = {
        ROOT: FetchResponse(302, {"location": "/contact"}),
        ROOT + "contact": html("<p>hello@example.org</p>"),
        SECURITY: FetchResponse(302, {"location": "https://evil.example/security.txt"}),
    }
    result, fetcher = discover(pages)
    assert result["request_count"] == 3
    assert result["status"] == "partial"
    assert all(url.startswith(ROOT) for url in fetcher.calls)
    assert any(i["code"] == "redirect_outside_scope" for i in result["issues"])


def test_www_is_automatic_and_sibling_is_always_blocked():
    pages = {
        ROOT: FetchResponse(301, {"location": "https://www.example.org/contact"}),
        "https://www.example.org/contact": html("hello@example.org"),
    }
    blocked, fetcher = discover(pages)
    assert "https://www.example.org/contact" in fetcher.calls
    allowed, fetcher = discover(pages, aliases=("www.example.org",))
    assert allowed["candidates"][0]["value"] == "hello@example.org"
    assert "https://www.example.org/contact" in fetcher.calls
    bad, fetcher = discover(pages, aliases=("api.example.org",))
    assert bad["status"] == "failed"
    assert fetcher.calls == []


@pytest.mark.parametrize(
    "url",
    [
        "http://example.org/contact",
        "https://example.org:444/",
        "https://u:p@example.org/",
        "https://%65xample.org/",
        "https://example.org/?secret=1",
        "https://example.org\\@evil.example/",
        "https://example.org.evil.example/",
        "https://example.org:\\n443/",
    ],
)
def test_url_policy_rejects_ambiguous_or_unapproved_urls(url):
    with pytest.raises(DiscoveryError):
        approved_url(url, {"example.org"})


def test_budget_counts_all_redirect_requests():
    pages = {ROOT: FetchResponse(302, {"location": "/1"})}
    pages.update(
        {ROOT + str(i): FetchResponse(302, {"location": "/" + str(i + 1)}) for i in range(1, 9)}
    )
    result, fetcher = discover(pages)
    assert len(fetcher.calls) == result["request_count"] == 4
    assert result["redirect_request_count"] == 2
    assert any(i["code"] == "redirect_limit" for i in result["issues"])


def test_bytes_are_bounded_exact_and_truncated_security_is_not_used():
    security = b"Contact: mailto:security@example.org\nExpires: 2099-01-01T00:00:00Z\n" + b"#" * 400
    result, _ = discover(
        {
            ROOT: html("<p>hi@example.org</p>"),
            SECURITY: FetchResponse(200, {"content-type": "text/plain"}, security),
        },
        limits=DiscoveryLimits(max_page_bytes=100, max_total_bytes=120),
    )
    assert result["bytes_received"] <= 120
    assert all(s["captured_bytes"] <= 100 and "body" not in s for s in result["snapshots"])
    for snapshot in result["snapshots"]:
        original = security if snapshot["url"] == SECURITY else b"<p>hi@example.org</p>"
        assert (
            snapshot["sha256"] == hashlib.sha256(original[: snapshot["captured_bytes"]]).hexdigest()
        )
    assert "security@example.org" not in [c["value"] for c in result["candidates"]]
    assert result["status"] == "partial"


def test_security_expiration_canonical_and_preference():
    security = (
        "Contact: mailto:soc@outsourced.example\nExpires: 2099-01-01T00:00:00Z\nCanonical: "
        + SECURITY
    )
    result, _ = discover(
        {
            ROOT: html("<p>soc@outsourced.example</p>"),
            SECURITY: FetchResponse(200, {"content-type": "text/plain"}, security.encode()),
        }
    )
    contact = result["candidates"][0]
    assert contact["purpose"] == "security"
    assert len(contact["sources"]) == 2
    for text in (
        security.replace("2099", "2001"),
        security.replace(SECURITY, "https://evil.example/security.txt"),
    ):
        result, _ = discover(
            {
                ROOT: html(""),
                SECURITY: FetchResponse(200, {"content-type": "text/plain"}, text.encode()),
            }
        )
        assert result["candidates"][0]["purpose"] == "other"
        assert any(i["code"].startswith("security_") for i in result["issues"])


def test_never_follows_external_form_action_and_returns_source_page():
    page = '<form action="https://form-vendor.example/post"><h2>Contact us</h2><label>Your message</label><input name="message"></form>'
    result, fetcher = discover({ROOT: html(page)})
    assert result["candidates"][0]["kind"] == "form"
    assert result["candidates"][0]["value"] == ROOT
    assert fetcher.calls == [ROOT, SECURITY]


def test_generic_footer_not_promoted_by_global_heading_or_other_contact():
    page = '<body><h1>Security and IT support</h1><a href="mailto:hello@example.org">Customer service</a><p>Security: sec@example.org; General: info@example.org</p></body>'
    result, _ = discover({ROOT: html(page)})
    purpose = {c["value"]: c["purpose"] for c in result["candidates"]}
    assert purpose == {
        "hello@example.org": "general",
        "sec@example.org": "security",
        "info@example.org": "general",
    }


def test_marketing_security_language_does_not_label_customer_service():
    page = '<section><h1>Security is our priority</h1><main>Our products</main><a href="mailto:hello@example.org">Customer service</a></section>'
    result, _ = discover({ROOT: html(page)})
    assert result["candidates"][0]["purpose"] == "general"


def test_irrelevant_scripts_jsonld_designers_and_pdf_are_not_extracted():
    page = '<script type="application/ld+json">{"email":"vendor@example.org"}</script><p>Website designed by <a href="mailto:designer@example.org">designer@example.org</a></p><a href="/contact.pdf">Contact</a>'
    result, fetcher = discover({ROOT: html(page)})
    assert result["candidates"] == []
    assert ROOT + "contact.pdf" not in fetcher.calls


def test_cancel_before_and_during_misbehaving_injected_fetch_finishes():
    cancelled = threading.Event()
    cancelled.set()
    result, fetcher = discover({ROOT: html("hello@example.org")}, cancel_event=cancelled)
    assert result["status"] == "cancelled"
    assert fetcher.calls == []
    cancelled.clear()
    release = threading.Event()
    entered = threading.Event()

    def stuck(url, **kwargs):
        entered.set()
        release.wait(2)
        return html("hello@example.org")

    timer = threading.Timer(0.1, cancelled.set)
    timer.start()
    start = time.monotonic()
    try:
        result = ContactDiscovery(fetcher=stuck).discover("example.org", cancel_event=cancelled)
        assert entered.is_set()
        assert time.monotonic() - start < 0.8
        assert result["status"] == "cancelled"
    finally:
        release.set()
        timer.join()


def test_whole_deadline_covers_stuck_fetch_and_parser(monkeypatch):
    release = threading.Event()

    def stuck(*args, **kwargs):
        release.wait(2)
        return html("")

    start = time.monotonic()
    try:
        result = ContactDiscovery(
            fetcher=stuck, limits=DiscoveryLimits(timeout=0.12, request_timeout=0.12)
        ).discover("example.org")
        assert time.monotonic() - start < 0.7
        assert result["status"] == "failed"
    finally:
        release.set()
    release = threading.Event()

    def stuck_parser(*args):
        release.wait(2)
        return {"title": "", "candidates": [], "links": []}

    monkeypatch.setattr(
        "modules.entities.components.contact_discovery.engine.parse_html", stuck_parser
    )
    start = time.monotonic()
    try:
        result, _ = discover(
            {ROOT: html("hello@example.org")},
            limits=DiscoveryLimits(timeout=0.12, request_timeout=0.12),
        )
        assert time.monotonic() - start < 0.7
        assert result["status"] == "partial"
    finally:
        release.set()


def test_candidate_work_and_output_caps_and_stable_keys():
    page = "".join(f"<p>contact{i}@example.org</p>" for i in range(5000))
    start = time.monotonic()
    result, _ = discover({ROOT: html(page)})
    assert len(result["candidates"]) == 50
    assert time.monotonic() - start < 3
    assert (
        result["candidates"][0]["key"] == hashlib.sha256(b"email\0contact0@example.org").hexdigest()
    )
    assert any(i["code"] == "candidate_limit" for i in result["issues"])
    assert result["status"] == "partial"


def test_unsupported_source_is_incomplete_not_evidence_of_contact_absence():
    result, _ = discover(
        {ROOT: FetchResponse(200, {"content-type": "application/pdf"}, b"%PDF fixture")}
    )
    assert result["status"] == "partial"
    assert result["candidates"] == []
    assert any(i["code"] == "unsupported_content" for i in result["issues"])


def test_limits_cannot_raise_safety_caps():
    with pytest.raises(ValueError):
        DiscoveryLimits(max_requests=9)
    with pytest.raises(ValueError):
        DiscoveryLimits(timeout=float("inf"))


def test_later_specific_listing_enriches_contact_without_losing_sources():
    result, _ = discover(
        {
            ROOT: html('<p>alex@example.org</p><a href="/team">Team</a>'),
            ROOT + "team": html(
                '<div><h3>Alex Smith</h3><span>IT Manager</span><a href="mailto:alex@example.org">alex@example.org</a></div>'
            ),
        }
    )
    contact = result["candidates"][0]
    assert contact["purpose"] == "it"
    assert contact["name"] == "Alex Smith"
    assert len(contact["sources"]) == 2


def test_ambiguous_shared_contact_does_not_choose_a_person():
    result, _ = discover(
        {
            ROOT: html(
                '<div><h3>Alex Smith</h3><span>IT Manager</span>team@example.org</div><a href="/team">Team</a>'
            ),
            ROOT + "team": html(
                "<div><h3>Jamie Jones</h3><span>IT Manager</span>team@example.org</div>"
            ),
        }
    )
    assert result["candidates"][0]["name"] == ""
    assert any(i["code"] == "contact_identity_conflict" for i in result["issues"])
