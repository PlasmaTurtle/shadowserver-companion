"""Complete contact fragments remain useful when later source bytes are cut off."""

import pytest

from workbench.contact_discovery.extract import parse_html, score_link

ROOT = "https://example.org/"
HOSTS = {"example.org"}


def parsed(markup):
    return parse_html(markup, ROOT, HOSTS, partial=True)


def test_completed_card_survives_cutoff_with_local_purpose_and_phone():
    result = parsed(
        '<section><h2>Technical support</h2><p>Email <a href="mailto:help@example.org">'
        "help@example.org</a></p><p>Phone: +1 (212) 555-0100</p></section>"
        "<section><h2>Media relations</h2><p>press@example.or"
    )
    by_value = {c["value"]: c for c in result["candidates"]}
    assert by_value["help@example.org"]["purpose"] == "it"
    assert any(c["kind"] == "phone" for c in result["candidates"])
    assert not any(c["value"].startswith("press@") for c in result["candidates"])
    assert all(c["partial_source"] for c in result["candidates"])
    assert not result["limited"]


def test_complete_anchor_does_not_borrow_unfinished_card_purpose():
    result = parsed(
        '<div><a href="mailto:hello@example.org">hello@example.org</a>'
        "<p>Information security team: unfinished context"
    )
    assert result["candidates"][0]["purpose"] == "general"
    assert "unfinished" not in result["candidates"][0]["excerpt"]


@pytest.mark.parametrize(
    "markup",
    [
        "<p>security@example.or",
        '<a href="mailto:security@example.org">security@example.or',
        '<a href="mailto:security@example.or',
        "<p>Phone: +1 (212) 555-01",
        "<form>Contact security <select><option>Webmaster</option>",
    ],
)
def test_incomplete_contact_elements_are_not_suggestions(markup):
    assert parsed(markup)["candidates"] == []


def test_complete_form_retains_routing_before_later_cutoff():
    result = parsed(
        '<form><label for="kind">Inquiry type</label><select id="kind">'
        "<option>General contact</option><option>Webmaster</option></select></form>"
        "<div>unfinished"
    )
    assert result["candidates"][0]["kind"] == "form"
    assert result["candidates"][0]["routing_label"] == "Inquiry type: Webmaster"
    assert result["candidates"][0]["purpose"] == "it"


def test_security_and_trust_routes_outrank_general_contact_pages():
    contact = score_link(ROOT + "contact", "Contact")
    assert score_link(ROOT + "company/trust-center", "Trust Center") > contact
    assert score_link(ROOT + "technical-support", "Technical Support") > contact
    assert score_link(ROOT + "support", "Support") > score_link(ROOT + "about", "About")


def test_technical_issue_referral_from_local_sentence():
    """Narrow reconstruction of Wasabi's captured support paragraph, not its page HTML."""
    result = parse_html(
        "<section><h2>Need Help?</h2><p>Having technical issues? Reach out to us "
        'by email at <a href="mailto:support@example.org">support@example.org</a> '
        "or by phone:</p></section>",
        ROOT,
        HOSTS,
    )
    contact = next(c for c in result["candidates"] if c["kind"] == "email")
    assert contact["purpose"] == "it"
    # The address alone does not establish a technical purpose.
    assert (
        parse_html("<p>support@example.org</p>", ROOT, HOSTS)["candidates"][0]["purpose"]
        == "general"
    )


def test_sentence_punctuation_does_not_hide_complete_email():
    result = parse_html("<p>Technical assistance: help@example.org.</p>", ROOT, HOSTS)
    assert result["candidates"][0]["value"] == "help@example.org"
    assert result["candidates"][0]["purpose"] == "it"


def test_combined_compliance_security_inquiries_do_not_become_security_reporting():
    result = parse_html(
        '<p><a href="mailto:office@example.org">Compliance &amp; Security Inquiries</a></p>',
        ROOT,
        HOSTS,
    )
    assert result["candidates"][0]["purpose"] == "compliance"


def test_reporting_and_support_rank_above_product_security_information():
    product = score_link(ROOT + "cloud-object-storage/security", "Security")
    assert score_link(ROOT + "company/trust-center", "Trust Center") > product
    assert score_link(ROOT + "support", "Support") > product
    assert (
        score_link(ROOT + "vulnerability-disclosure-program", "Vulnerability Disclosure Program")
        > product
    )
    assert score_link(ROOT + "blog/data-protection/security-concerns", "Security concerns") == 0
    assert score_link(ROOT + "news/responsible-disclosure", "Responsible disclosure") > product


def test_generic_trust_and_care_support_do_not_displace_company_contacts():
    """Reconstructed keyword collisions observed in the enterprise evaluation."""
    contact = score_link(ROOT + "company/contact-us", "Contact us")
    assert score_link(ROOT + "company/trust-x-alliance", "Trust X Alliance") < contact
    assert score_link(ROOT + "care-support/emergency", "Getting care during an emergency") < contact
    assert score_link(ROOT + "care-support/travel", "Travel without missing treatment") < contact
