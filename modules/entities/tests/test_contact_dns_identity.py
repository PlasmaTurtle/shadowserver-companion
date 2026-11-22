"""Contact requests use the same DNS identity as entity attribution."""

import pytest

from attribution.matching import normalize_domain
from modules.entities.components.contact_discovery import ContactDiscovery, FetchResponse
from modules.entities.components.contact_discovery.policy import (
    DiscoveryError,
    approved_scope,
    approved_url,
    hostname,
    public_address,
)
from modules.entities.tests.support.contact_discovery import FixtureFetcher, html


@pytest.mark.parametrize(
    "value,expected",
    [
        ("faß.de", "xn--fa-hia.de"),
        ("βόλος.gr", "xn--nxasmm1c.gr"),
        ("bücher.de", "xn--bcher-kva.de"),
        ("EXAMPLE.ORG.", "example.org"),
        ("example。org", "example.org"),
    ],
)
def test_contact_scope_and_url_share_attribution_idna_identity(value, expected):
    assert hostname(value) == normalize_domain(value) == expected
    root, aliases = approved_scope(value)
    assert root == expected and aliases == ("www." + expected,)
    assert approved_url("https://" + value + "/contact", {root, *aliases}) == (
        "https://" + expected + "/contact"
    )


def test_unicode_redirect_reaches_same_entity_contact_without_visiting_different_idna2003_host():
    root = "https://xn--fa-hia.de/"
    contact = root + "contact"
    fetcher = FixtureFetcher(
        {
            root: FetchResponse(302, {"location": "https://faß.de/contact"}, b""),
            contact: html("<p>Security contact: security@xn--fa-hia.de</p>"),
        }
    )
    result = ContactDiscovery(fetcher=fetcher).discover("xn--fa-hia.de", source_url=root)
    assert fetcher.calls == [root, contact]
    assert result["outcome"] == "reporting_route_found"
    assert result["candidates"][0]["value"] == "security@xn--fa-hia.de"
    assert result["candidates"][0]["sources"][0]["url"] == contact
    assert not any(item["code"] == "redirect_outside_scope" for item in result["issues"])
    with pytest.raises(DiscoveryError, match="outside"):
        approved_url("https://fass.de/contact", {"xn--fa-hia.de"})


@pytest.mark.parametrize(
    "value",
    [
        "example.org..",
        " example.org",
        "example.org ",
        "example.test",
        "example.123",
        "localhost",
        "127.0.0.1",
        "https://example.org",
        "xn--invalid-.org",
    ],
)
def test_contact_specific_destination_policy_remains(value):
    with pytest.raises(DiscoveryError) as failure:
        hostname(value)
    assert failure.value.code == "invalid_scope"


@pytest.mark.parametrize(
    "value,expected",
    [
        ("::ffff:8.8.8.8", True),
        ("::ffff:192.168.1.1", False),
        ("64:ff9b::808:808", False),
        ("2002:0808:0808::1", False),
        ("fe80::1%eth0", False),
    ],
)
def test_comparison_normalization_does_not_widen_public_contact_policy(value, expected):
    assert public_address(value) is expected
