"""Contact quality regressions reconstructed from retained public captures."""

import pytest

from workbench.contact_discovery.extract import parse_html, score_link

ROOT = "https://example.org/"
HOSTS = {"example.org"}


@pytest.mark.parametrize("partial", [False, True])
@pytest.mark.parametrize(
    "markup",
    [
        "<h2>Phone</h2><p>+1 617-307-7912 (Int’l)<br>+1 617-307-7973 (Fax)</p>",
        "<p>Phone: +1 617-307-7912; Fax: +1 617-307-7973</p>",
        '<p>Phone: <a href="tel:+16173077912">+1 617-307-7912</a> '
        '<a href="tel:+16173077973">+1 617-307-7973</a> (Fax)</p>',
        '<p><a href="tel:+16173077973">Fax us</a></p><p>Phone: +1 617-307-7912</p>',
    ],
)
def test_fax_is_not_a_phone_suggestion_and_adjacent_voice_number_survives(markup, partial):
    result = parse_html(markup, ROOT, HOSTS, partial=partial)
    phones = [c for c in result["candidates"] if c["kind"] == "phone"]
    assert phones
    assert all("7973" not in c["value"] for c in phones)
    assert any("7912" in c["value"] for c in phones)
    assert all(c.get("partial_source", False) == partial for c in phones)


def test_recruiting_mailbox_is_not_promoted_by_broad_product_support_card():
    result = parse_html(
        "<section><h2>Final Mile Carriers</h2><p>Get support for carriers using our technology. "
        'For assistance, <a href="mailto:dna.recruiting@example.org">email us</a>.</p></section>'
        '<section><h2>Carrier Tech Support</h2><p><a href="mailto:help@example.org">'
        "Email us</a></p></section>",
        ROOT,
        HOSTS,
    )
    values = {c["value"]: c for c in result["candidates"]}
    restricted = values["dna.recruiting@example.org"]
    assert restricted["purpose"] == "hr"
    assert restricted["recommended_for_outreach"] is False
    assert restricted["routing_label"] == "Recruiting / employment address"
    assert "Get support" in restricted["excerpt"]
    assert values["help@example.org"]["purpose"] == "product_support"


def test_plain_mailbox_does_not_establish_technical_role():
    result = parse_html("<p>security@example.org</p><p>support@example.org</p>", ROOT, HOSTS)
    assert all(c["purpose"] == "general" for c in result["candidates"])


def test_published_department_labels_remain_nonroutine():
    result = parse_html(
        "<section><h2>Press &amp; Analyst Relations</h2><p>press@example.org</p></section>"
        "<section><h2>People Support Center</h2><p>people.support@example.org</p></section>",
        ROOT,
        HOSTS,
    )
    assert {c["value"]: c["purpose"] for c in result["candidates"]} == {
        "press@example.org": "media",
        "people.support@example.org": "hr",
    }


@pytest.mark.parametrize(
    "path,label",
    [
        ("about-us/leadership/jane-smith", "Jane Smith, Chief Technology Officer"),
        ("team/security-director", "Security Director"),
        ("about-us/equipment", "About our equipment"),
        ("about-us/our-history", "Our history"),
        ("contact-us/press-media-inquiry", "Press / media inquiries"),
        ("contact-us/migration", "Explore migration incentives"),
        ("contact-us/leased-equipment", "Leased Equipment"),
    ],
)
def test_individual_bios_and_unrelated_about_pages_do_not_consume_budget(path, label):
    assert score_link(ROOT + path, label) == 0


def test_contact_directory_remains_available_without_expanding_bios():
    assert score_link(ROOT + "team", "Team") > 0
    assert score_link(ROOT + "about-us/contact", "Contact us") > 0
    assert score_link(ROOT + "security/team", "Report a security incident") > 100
