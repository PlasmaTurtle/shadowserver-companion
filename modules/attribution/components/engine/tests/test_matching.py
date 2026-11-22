import pytest

from attribution.matching import DomainMatcher, normalize_domain
from attribution.models import parse_json
from attribution_test_support.rdap import entity, network


@pytest.mark.parametrize(
    "value,expected",
    [
        ("example.com", True),
        ("mail.example.com", True),
        ("MAIL.Example.COM.", True),
        ("support@example.com", True),
        ("support@mx.example.com", True),
        ("https://www.example.com/contact", True),
        ("mailto:security@example.com", True),
        ("notexample.com", False),
        ("example.com.evil.net", False),
        ("https://evil.net/path/example.com", False),
        ("https://example.com@evil.net/", False),
        ("https://evil.net/?company=example.com", False),
        ("example.com-evil.net", False),
        ("evil-example.com", False),
        ("Contact https://www.example.com/contact.", True),
    ],
)
def test_text_boundaries(value, expected):
    assert (
        bool(DomainMatcher().find_match({"remarks": [{"description": [value]}]}, "example.com"))
        == expected
    )


def test_metadata_does_not_qualify():
    data = {
        "notices": [{"description": ["example.com"]}],
        "port43": "example.com",
        "links": [{"href": "https://example.com/terms"}],
        "networks": [network()],
        "autnums": [{"name": "example.com"}],
    }
    assert DomainMatcher().find_match(data, "example.com") is None


def test_structured_email_url_and_json_pointer():
    data = network()
    data["entities"] = [
        {
            "objectClassName": "entity",
            "handle": "ORG",
            "roles": ["registrant"],
            "entities": [entity("mail.example.com", "CONTACT", ["technical"])],
        }
    ]
    match = DomainMatcher().find_match(data, "example.com")
    assert match.field_path == "/entities/0/entities/0/vcardArray/1/2/3"
    assert match.entity_handle == "CONTACT" and match.entity_roles == ("technical",)
    assert match.value == "support@mail.example.com" and match.field_type == "email"


def test_unknown_registration_fields_preserved_and_matchable():
    match = DomainMatcher().find_match(
        {"vendor/field~1": "Registered to example.com"}, "example.com"
    )
    assert match.field_path == "/vendor~1field~01"


@pytest.mark.parametrize(
    "value",
    [
        "https://example.com",
        "example.com:443",
        "abuse@example.com",
        "8.8.8.8",
        "localhost",
        "x..com",
        "-x.com",
        "x.com..",
    ],
)
def test_invalid_target_domain(value):
    with pytest.raises(ValueError):
        normalize_domain(value)


def test_idna_and_case():
    assert normalize_domain("BÜCHER.example.") == "xn--bcher-kva.example"
    assert DomainMatcher().find_match({"description": "bücher.example"}, "xn--bcher-kva.example")


@pytest.mark.parametrize("body", [b'{"x": 1, "x": 2}', b'{"x": NaN}', b"[]", b"{"])
def test_invalid_json(body):
    with pytest.raises(ValueError):
        parse_json(body)
