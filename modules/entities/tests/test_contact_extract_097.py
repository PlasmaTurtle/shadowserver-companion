"""Bounded parser regressions reconstructed from observed Fortune 500 failure patterns.

These are synthetic markup examples, not archived company website bodies.
"""

import pytest

from modules.entities.components.contact_discovery.extract import (
    candidate_key,
    contact_identity,
    parse_html,
    parse_security,
    purpose_role,
    score_link,
)

ROOT = "https://example.org/"
HOSTS = {"example.org"}


def contacts(markup):
    return parse_html(markup, ROOT, HOSTS)["candidates"]


@pytest.mark.parametrize(
    "text",
    [
        "Have a cybersecurity issue? Report it to infosec@example.org",
        "Cybersecurity report: soc@example.org",
        "Report a security concern to response@example.org",
    ],
)
def test_explicit_cybersecurity_sentence_is_security(text):
    assert purpose_role(text)[0] == "security"


def test_mailbox_prefix_is_not_evidence_of_purpose():
    assert contacts("<p>security@example.org</p>")[0]["purpose"] == "general"


@pytest.mark.parametrize("wrapper", ["{anchor}", "<p>{anchor}</p>", "<div><p>{anchor}</p></div>"])
def test_local_card_heading_survives_wrappers_without_neighbor_bleed(wrapper):
    a = wrapper.format(anchor='<a href="mailto:report@example.org">report@example.org</a>')
    b = wrapper.format(anchor='<a href="mailto:press@example.org">press@example.org</a>')
    result = contacts(f"<div><h2>Security</h2>{a}</div><div><h2>Media relations</h2>{b}</div>")
    assert {c["value"]: c["purpose"] for c in result} == {
        "report@example.org": "security",
        "press@example.org": "media",
    }
    assert not next(c for c in result if c["purpose"] == "media")["recommended_for_outreach"]


def test_product_support_heading_is_not_enterprise_security():
    result = contacts(
        '<div><h3>Shipper product support</h3><p><a href="mailto:shipper@example.org">shipper@example.org</a></p></div>'
    )
    assert result[0]["purpose"] == "product_support"
    assert "Shipper product support" in result[0]["excerpt"]


def test_form_keeps_all_choices_and_explicit_best_routing_instruction():
    result = contacts(
        '<form action="https://external.example/post"><label for="kind">Inquiry Type</label><select id="kind"><option value="">Choose</option><option>Customer service</option><option>Webmaster</option><option>Responsible Disclosure</option><option>Media relations</option></select></form>'
    )
    item = result[0]
    assert item["value"] == ROOT and item["kind"] == "form"
    assert item["routing_label"] == "Inquiry Type: Responsible Disclosure"
    assert item["routing_options"] == [
        {"label": "Customer service", "purpose": "general", "field_label": "Inquiry Type"},
        {"label": "Webmaster", "purpose": "it", "field_label": "Inquiry Type"},
        {"label": "Responsible Disclosure", "purpose": "security", "field_label": "Inquiry Type"},
        {"label": "Media relations", "purpose": "media", "field_label": "Inquiry Type"},
    ]


def test_external_reporting_route_retains_publication_but_is_never_crawl_link():
    url = "https://forms.example.net/report?ticket=visible"
    result = parse_html(f'<a href="{url}">Report a vulnerability</a>', ROOT, HOSTS)
    item = result["candidates"][0]
    assert item["route_type"] == "published_link" and item["external_destination"]
    assert item["value"] == url and item["original_url"] == url
    assert item["requires_review"] and result["links"] == []


@pytest.mark.parametrize(
    "label",
    [
        "Physical security emergency hotline",
        "Privacy Contact",
        "Media Relations",
        "Customer login",
        "Privacy Policy",
    ],
)
def test_url_security_keyword_cannot_promote_non_reporting_departments(label):
    result = parse_html(f'<a href="https://example.org/security/">{label}</a>', ROOT, HOSTS)
    assert result["candidates"] == []


@pytest.mark.parametrize(
    "target",
    [
        "http://example.net/report",
        "https://127.0.0.1/report",
        "https://user:pass@example.net/report",
        "https://example.net:8443/report",
        "javascript:alert(1)",
        "https://example.net\\@example.org/report",
    ],
)
def test_unsafe_published_destinations_are_not_candidates(target):
    assert contacts(f'<a href="{target}">Report a vulnerability</a>') == []


def test_security_txt_external_contact_is_reviewable_not_fetched():
    result = parse_security(
        "Contact: https://form.example.net/report\nExpires: 2099-01-01T00:00:00Z",
        ROOT + ".well-known/security.txt",
        HOSTS,
    )
    item = result["candidates"][0]
    assert item["purpose"] == "security" and item["external_destination"]
    assert item["route_type"] == "published_link" and not result["links"]


def test_truncated_html_offers_complete_contacts_and_links():
    result = parse_html(
        '<p>security@example.org</p><form>Contact us</form><a href="/disclosure">Report a vulnerability</a><a href="/partial">Report a vulnerability',
        ROOT,
        HOSTS,
        partial=True,
    )
    assert not result["limited"]
    assert [c["value"] for c in result["candidates"]] == [
        "security@example.org",
        ROOT,
        ROOT + "disclosure",
    ]
    assert all(c["partial_source"] for c in result["candidates"])
    assert result["links"] == [(ROOT + "disclosure", "Report a vulnerability")]


def test_javascript_shell_reports_unreadable_without_inventing_links():
    result = parse_html(
        '<title>Security portal</title><div id="root"></div><script src="bundle.js"></script>',
        ROOT,
        HOSTS,
    )
    assert result["render_required"] and not result["candidates"] and not result["links"]


def test_phone_dedupe_identity_does_not_change_saved_candidate_keys():
    assert contact_identity("phone", "+1 (800) 555-0100 ext. 2") == contact_identity(
        "phone", "1-800-555-0100 x2"
    )
    assert contact_identity("phone", "+1 (800) 555-0100 ext. 2") != contact_identity(
        "phone", "+1 (800) 555-0100 ext. 3"
    )
    assert contact_identity("phone", "800-555-0100") == contact_identity("phone", "+1 800-555-0100")
    assert contact_identity("phone", "+44 20 7946 0100") != contact_identity(
        "phone", "+1 207-946-0100"
    )
    # Historical candidate identity remains dependent on the retained published value.
    assert candidate_key("phone", "+1 (800) 555-0100") != candidate_key("phone", "1-800-555-0100")


@pytest.mark.parametrize(
    "label,path",
    [
        ("Responsible disclosure", "/policies/disclosure.html"),
        ("Report a vulnerability", "/disclosure"),
        ("Report a security concern", "/contact"),
    ],
)
def test_reporting_routes_outrank_ordinary_contact_links(label, path):
    assert score_link(ROOT.rstrip("/") + path, label) > score_link(ROOT + "contact", "Contact us")


@pytest.mark.parametrize(
    "path,label",
    [
        ("/careers/staff-professionals", "Our team"),
        ("/patients/support", "Support team"),
        ("/responsibility/people", "Team Members"),
    ],
)
def test_employee_culture_and_patient_articles_do_not_take_contact_slots(path, label):
    assert score_link(ROOT.rstrip("/") + path, label) == 0


def test_form_routing_does_not_inherit_neighbor_or_personal_role_options():
    result = contacts(
        '<form><label for="role">Your role</label><select id="role"><option>IT Director</option></select><p>Contact our customer service</p></form><form><label for="route">Inquiry Type</label><select id="route"><option>Webmaster</option></select></form>'
    )
    forms = [c for c in result if c["kind"] == "form"]
    assert len(forms) == 2
    assert forms[0]["routing_options"] == [] and forms[0]["purpose"] == "general"
    assert forms[1]["routing_options"] == [
        {"label": "Webmaster", "purpose": "it", "field_label": "Inquiry Type"}
    ]


def test_bold_department_paragraph_before_contact_list_keeps_group_boundaries():
    result = contacts(
        "<div>"
        "<p><b><span>Example Portal Tech Support:</span></b></p>"
        '<ul><li><a href="tel:1-866-555-0100">1-866-555-0100</a></li>'
        '<li><a href="mailto:portal@example.org">portal@example.org</a></li></ul>'
        "<p><strong>Human Resources:</strong></p>"
        '<ul><li><a href="mailto:people@example.org">people@example.org</a></li></ul>'
        "<p><b>Customer service:</b></p>"
        '<ul><li><a href="mailto:customers@example.org">customers@example.org</a></li></ul>'
        "</div>"
    )
    by_value = {item["value"]: item for item in result}
    assert by_value["portal@example.org"]["purpose"] == "product_support"
    assert by_value["1-866-555-0100"]["purpose"] == "product_support"
    assert by_value["people@example.org"]["purpose"] == "hr"
    assert by_value["customers@example.org"]["purpose"] == "general"
    assert "Example Portal Tech Support" in by_value["portal@example.org"]["excerpt"]
    assert "Example Portal" not in by_value["people@example.org"]["excerpt"]


def test_bold_keyword_inside_marketing_paragraph_is_not_a_department_heading():
    result = contacts(
        '<div><p>We deliver <b>Tech Support</b> for all our customers.</p><ul><li><a href="mailto:hello@example.org">hello@example.org</a></li></ul></div>'
    )
    assert result[0]["purpose"] == "general"


def test_accessible_anchor_label_preserves_dedicated_security_portal():
    result = parse_html(
        '<a href="https://security.example.org/" aria-label="Learn more about our dedicated Security site."><span>Learn More</span></a>',
        ROOT,
        HOSTS,
    )
    item = result["candidates"][0]
    assert item["value"] == "https://security.example.org/"
    assert item["route_type"] == "published_link" and item["requires_review"]
    assert "dedicated Security site" in item["excerpt"]
    assert result["links"] == []


def test_security_marketing_demo_is_not_a_reporting_route():
    result = parse_html(
        '<a href="//forms.example.org/quick-demos/security/form.html">Quick Demo Security and Trust Play Demo (2:39)</a><a href="/trust/security.html">Security</a>',
        ROOT,
        HOSTS,
    )
    assert result["candidates"] == []
    assert result["links"] == [(ROOT + "trust/security.html", "Security")]
    overview = parse_html('<a href="/information-security">Information security</a>', ROOT, HOSTS)
    assert overview["candidates"] == [] and overview["links"]
