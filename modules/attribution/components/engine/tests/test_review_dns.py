"""Fallback behavior against synthetic DNS/RDAP; never queries live services."""

import base64

import dns.message
import dns.rcode
import dns.resolver
import dns.rrset
import httpx
import pytest

from attribution import (
    AttributionModule,
    CandidateIP,
    DnsProvider,
    EvidenceRenderer,
    EvidenceStore,
    RegistrationNameMatcher,
    verify_export,
)
from attribution_test_support.rdap import ARIN, entity, network

from attribution_test_support.dns import (
    Resolver,
)


def named_record(name="Cedar Harbor Valley Medical Center", **changes):
    card = entity("unrelated.test")
    card["vcardArray"][1][1][3] = name
    return network(entities=[card], **changes)


def test_registration_words_are_taken_from_source_fields_only():
    record = named_record()
    record["notices"] = [{"description": ["remote2 com ignore medical"]}]
    matches = list(RegistrationNameMatcher().find_matches(record, "cedarharborvalley.com"))
    match, details = matches[0]
    assert details["matched_words"] == ("cedar", "harbor", "valley")
    assert match.value == "Cedar Harbor Valley Medical Center"
    assert match.field_path == "/entities/0/vcardArray/1/1/3"
    assert not match.matched_domain
    assert not list(RegistrationNameMatcher().find_matches(record, "remote2.com"))


@pytest.mark.parametrize(
    "domain,name,words",
    [
        ("summit.com", "IT", ("it",)),
        ("1happy1horse1supply.com", "Happy Horse Supply LLC", ("happy", "horse", "supply")),
        ("xometry.com", "Xometry Incorporated", ("xometry",)),
        ("cedar-harbor-valley.com", "CEDAR, HARBOR; VALLEY", ("cedar", "harbor", "valley")),
        ("xn--bcher-kva.de", "Bücher GmbH", ("bücher",)),
    ],
)
def test_any_word_is_retained_including_short_words(domain, name, words):
    matches = list(RegistrationNameMatcher().find_matches(named_record(name), domain))
    assert matches[0][1]["matched_words"] == words


def test_individual_names_are_not_organization_names():
    record = named_record("Valley Person")
    record["entities"][0]["vcardArray"][1].append(["kind", {}, "text", "individual"])
    assert not list(RegistrationNameMatcher().find_matches(record, "cedarharborvalley.com"))


def test_partial_does_not_stop_group_and_exact_match_wins(rig):
    module, provider, server, store = rig
    server.routes[ARIN + "ip/8.8.8.8"] = named_record()
    server.routes[ARIN + "ip/8.8.4.4"] = network("cedarharborvalley.com")
    result = module.attribute(
        "cedarharborvalley.com", [CandidateIP("first", "8.8.8.8"), CandidateIP("second", "8.8.4.4")]
    )
    assert result.status == "matched" and result.matched_entry_id == "second"
    assert result.partial_evidence[0].details["entry_id"] == "first"
    assert result.evidence[0].method == "rdap"


def test_partial_kept_with_timeout_on_later_entity_and_exported(rig, tmp_path):
    module, provider, server, store = rig
    record = named_record()
    record["entities"].append(
        {
            "objectClassName": "entity",
            "handle": "MORE",
            "links": [{"rel": "self", "href": ARIN + "entity/MORE"}],
        }
    )
    server.routes[ARIN + "ip/8.8.8.8"] = record

    def timeout(request):
        raise httpx.ReadTimeout("fixture timeout")

    server.routes[ARIN + "entity/MORE"] = timeout
    result = module.attribute("cedarharborvalley.com", [CandidateIP("row", "8.8.8.8")])
    assert result.status == "review" and result.matched_entry_id is None and not result.evidence
    assert result.attempts[0].status == "deferred"
    assert result.partial_evidence[0].details["matched_words"] == ("cedar", "harbor", "valley")
    folder = tmp_path / "export"
    EvidenceRenderer(store).export(result.result_id, folder)
    assert verify_export(folder)["valid"]
    assert "<mark>Cedar</mark>" in (folder / "evidence.html").read_text(encoding="utf-8")
    assert store.result(result.result_id)["status"] == "review"


def test_exact_email_matches_before_partial_names(rig):
    module, provider, server, store = rig
    record = named_record()
    record["entities"][0]["vcardArray"][1][-1][3] = "tech@cedarharborvalley.com"
    server.routes[ARIN + "ip/8.8.8.8"] = record
    result = module.attribute("cedarharborvalley.com", [CandidateIP("row", "8.8.8.8")])
    assert result.status == "matched" and not result.partial_evidence


def test_forward_dns_uses_reported_hostname_preserves_wire_response_and_cache(tmp_path):
    resolver = Resolver({("mail.example.com.", "A"): ["8.8.8.8"]})
    with EvidenceStore(tmp_path / "evidence.sqlite3") as store:
        provider = DnsProvider(store, resolver=resolver)
        module = AttributionModule(store, providers=[provider])
        candidate = CandidateIP("row", "8.8.8.8", "mail.example.com")
        result = module.attribute("example.com", [candidate])
        assert result.status == "matched" and result.evidence[0].method == "dns"
        assert resolver.calls == [("mail.example.com.", "A")]
        record = store.snapshot(result.evidence[0].snapshot_id).record()
        assert record["answers"] == ["8.8.8.8"]
        assert dns.message.from_wire(base64.b64decode(record["responses"][0]["wire_base64"])).answer
        offline = module.attribute("example.com", [candidate], offline=True)
        assert offline.status == "matched" and offline.evidence[0].from_cache
        assert len(resolver.calls) == 1


def test_reverse_requires_root_boundary_and_forward_confirmation(tmp_path):
    resolver = Resolver(
        {
            ("mail.example.com.", "A"): [],
            ("8.8.8.8.in-addr.arpa.", "PTR"): ["badexample.com.", "vpn.example.com."],
            ("vpn.example.com.", "A"): ["8.8.8.8"],
        }
    )
    with EvidenceStore(tmp_path / "evidence.sqlite3") as store:
        result = DnsProvider(store, resolver=resolver).collect(
            "8.8.8.8", "example.com", hostname="mail.example.com"
        )
        assert result.status == "matched" and result.reason == "dns_reverse_confirmed"
        assert ("badexample.com.", "A") not in resolver.calls
        assert result.evidence.match.matched_domain == "vpn.example.com"
        resolver.records[("vpn.example.com.", "A")] = ["8.8.4.4"]
        failed = DnsProvider(store, resolver=resolver).collect(
            "8.8.8.8", "example.com", hostname="mail.example.com", refresh=True
        )
        assert failed.status == "no_match"


def test_dns_nxdomain_is_no_match_but_timeout_is_retryable(tmp_path):
    resolver = Resolver({("mail.example.com.", "A"): "NXDOMAIN"})
    with EvidenceStore(tmp_path / "evidence.sqlite3") as store:
        provider = DnsProvider(store, resolver=resolver)
        assert (
            provider.collect("8.8.8.8", "example.com", hostname="mail.example.com").status
            == "no_match"
        )
        resolver.records[("mail.example.com.", "A")] = dns.resolver.LifetimeTimeout(
            timeout=1, errors=[]
        )
        result = provider.collect(
            "8.8.8.8", "example.com", hostname="mail.example.com", refresh=True
        )
        assert result.status == "deferred" and result.snapshot_ids
        assert any(store.snapshot(s).record()["status"] == "error" for s in result.snapshot_ids)


def test_ipv6_forward_match_and_nonpublic_skipped(tmp_path):
    resolver = Resolver({("v6.example.com.", "AAAA"): ["2606:4700:4700::1111"]})
    with EvidenceStore(tmp_path / "evidence.sqlite3") as store:
        module = AttributionModule(store, providers=[DnsProvider(store, resolver=resolver)])
        result = module.attribute(
            "example.com",
            [
                CandidateIP("private", "10.0.0.1", "v6.example.com"),
                CandidateIP("v6", "2606:4700:4700::1111", "v6.example.com"),
            ],
        )
        assert result.status == "matched" and len(resolver.calls) == 1
        assert len(result.candidates) == 2


def test_same_ip_different_hostname_can_find_later_dns_match(tmp_path):
    resolver = Resolver({("second.example.com.", "A"): ["8.8.8.8"]})
    with EvidenceStore(tmp_path / "evidence.sqlite3") as store:
        module = AttributionModule(store, providers=[DnsProvider(store, resolver=resolver)])
        result = module.attribute(
            "example.com",
            [
                CandidateIP("first", "8.8.8.8", "first.example.com"),
                CandidateIP("second", "8.8.8.8", "second.example.com"),
            ],
        )
        assert result.status == "matched" and result.matched_entry_id == "second"
