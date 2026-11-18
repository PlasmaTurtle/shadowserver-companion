from dataclasses import replace

import httpx
import pytest

from attribution import AttributionModule, CandidateIP, RdapProvider, Settings
from conftest import ARIN, RIPE, APNIC, AFRINIC, LACNIC, IANA4, entity, network, response


def run(rig, domain="example.com", ips=("8.8.8.8",), **kwargs):
    return rig[0].attribute(domain, [CandidateIP(str(i), ip) for i, ip in enumerate(ips)], **kwargs)


def test_first_match_preserves_every_candidate_and_stops(rig):
    module, _, server, store = rig
    server.routes[ARIN + "ip/8.8.8.8"] = network("unrelated.net")
    server.routes[ARIN + "ip/8.8.4.4"] = network()
    entries = [CandidateIP(str(i), ip) for i, ip in enumerate(
        ["10.0.0.1", "8.8.8.8", "8.8.8.8", "8.8.4.4"] + ["8.1.1.1"] * 66)]
    result = module.attribute("example.com", entries)
    assert result.status == "matched" and result.matched_entry_id == "3"
    assert len(result.candidates) == 70 and len(entries) == 70
    assert server.calls == [IANA4, ARIN + "ip/8.8.8.8", ARIN + "ip/8.8.4.4"]
    assert result.attempts[0].reason == "nonpublic_ip"
    assert result.attempts[2].reason == "duplicate_ip"
    assert store.result(result.result_id)["matched_ip"] == "8.8.4.4"


def test_private_and_invalid_inputs_are_retained(rig):
    result = run(rig, ips=("10.1.1.1", "fd00::1"))
    assert result.status == "no_eligible_ip" and len(result.candidates) == 2
    assert not rig[2].calls
    result = run(rig, ips=("not-an-ip", "10.1.1.1"))
    assert result.status == "incomplete" and not rig[2].calls


def test_ipv4_mapped_ipv6_deduplicates(rig):
    rig[2].routes[ARIN + "ip/8.8.8.8"] = network("unrelated.net")
    result = run(rig, ips=("::ffff:8.8.8.8", "8.8.8.8"))
    assert result.status == "no_match"
    assert result.attempts[1].reason == "duplicate_ip"
    assert rig[2].calls.count(ARIN + "ip/8.8.8.8") == 1


def test_native_ipv6(rig):
    rig[2].routes[ARIN + "ip/2606:4700::1111"] = network(startAddress="2606:4700::", endAddress="2606:4700:ffff:ffff:ffff:ffff:ffff:ffff")
    assert run(rig, ips=("2606:4700::1111",)).status == "matched"


@pytest.mark.parametrize("base,ip,start,end", [
    (ARIN, "8.8.8.8", "8.0.0.0", "8.255.255.255"),
    (RIPE, "193.0.6.139", "193.0.0.0", "193.255.255.255"),
    (APNIC, "1.1.1.1", "1.0.0.0", "1.255.255.255"),
    (AFRINIC, "196.216.2.1", "196.0.0.0", "196.255.255.255"),
    (LACNIC, "200.7.86.1", "200.0.0.0", "200.255.255.255"),
])
def test_all_five_registry_routes(rig, base, ip, start, end):
    rig[2].routes[base + "ip/" + ip] = network(startAddress=start, endAddress=end)
    result = run(rig, ips=(ip,))
    assert result.status == "matched" and result.evidence[0].source_url == base + "ip/" + ip


def test_longest_prefix_route(rig):
    rig[2].bootstrap4["services"].append([["8.8.8.0/24"], [RIPE]])
    rig[2].routes[RIPE + "ip/8.8.8.8"] = network()
    assert run(rig).evidence[0].source_name == "RIPE NCC"


def test_cache_is_per_ip_and_match_is_per_domain(rig):
    rig[2].routes[ARIN + "ip/8.8.8.8"] = network()
    first = run(rig)
    call_count = len(rig[2].calls)
    second = run(rig, "other.example")
    third = run(rig)
    assert second.status == "no_match" and third.status == "matched"
    assert len(rig[2].calls) == call_count
    assert first.evidence[0].snapshot_id == third.evidence[0].snapshot_id
    assert first.evidence[0].retrieved_at == third.evidence[0].retrieved_at
    assert third.evidence[0].from_cache


def test_no_inferred_range_cache(rig):
    rig[2].routes[ARIN + "ip/8.8.8.8"] = network("unrelated.net")
    rig[2].routes[ARIN + "ip/8.8.4.4"] = network()
    result = run(rig, ips=("8.8.8.8", "8.8.4.4"))
    assert result.matched_ip == "8.8.4.4" and len(rig[2].calls) == 3


def test_linked_entity_stops_before_other_links(rig):
    rig[2].routes[ARIN + "ip/8.8.8.8"] = network(entities=[
        {"handle": name, "objectClassName": "entity", "links": [{"rel": "self", "href": ARIN + "entity/" + name}]}
        for name in ("ORG-A", "ORG-B")])
    rig[2].routes[ARIN + "entity/ORG-A"] = entity(handle="ORG-A")
    result = run(rig)
    assert result.status == "matched" and result.evidence[0].source_url.endswith("entity/ORG-A")
    assert ARIN + "entity/ORG-B" not in rig[2].calls
    assert len(result.evidence[0].supporting_snapshot_ids) == 3


def test_nested_link_and_cycle_are_bounded(rig):
    ref = lambda h: {"objectClassName": "entity", "handle": h, "links": [{"rel": "self", "href": ARIN + "entity/" + h}]}
    rig[2].routes[ARIN + "ip/8.8.8.8"] = network(entities=[ref("A")])
    rig[2].routes[ARIN + "entity/A"] = {**entity("other.net", "A"), "entities": [ref("B")]}
    rig[2].routes[ARIN + "entity/B"] = {**entity("other.net", "B"), "entities": [ref("A")]}
    assert run(rig).status == "no_match"
    assert len(rig[2].calls) == 4


def test_link_budget_leaves_incomplete(rig):
    rig[1].settings = replace(rig[1].settings, max_entity_requests=0)
    rig[2].routes[ARIN + "ip/8.8.8.8"] = network(entities=[{"handle": "A", "links": [{"rel": "self", "href": ARIN + "entity/A"}]}])
    assert run(rig).status == "incomplete" and len(rig[2].calls) == 2


def test_redaction_with_and_without_positive_match(rig):
    rig[2].routes[ARIN + "ip/8.8.8.8"] = network(redacted=[{"name": {"description": "Contact"}}])
    assert run(rig).status == "matched"
    assert run(rig, "absent.example").status == "incomplete"


def test_404_is_a_no_record_result_and_is_cached(rig):
    rig[2].routes[ARIN + "ip/8.8.8.8"] = lambda req: response(status=404)
    result = run(rig)
    assert result.status == "no_match" and result.attempts[0].reason == "not_found"
    assert run(rig).status == "no_match" and len(rig[2].calls) == 2


@pytest.mark.parametrize("data", [network(startAddress="9.0.0.0", endAddress="9.0.0.255"),
    network(objectClassName="domain"), network(endAddress="2600::1")])
def test_wrong_network_never_qualifies(rig, data):
    rig[2].routes[ARIN + "ip/8.8.8.8"] = data
    assert run(rig).status == "incomplete"


def test_later_match_wins_over_earlier_timeout(rig):
    def timeout(req):
        raise httpx.ReadTimeout("secret proxy data must not be retained")
    rig[2].routes[ARIN + "ip/8.8.8.8"] = timeout
    rig[2].routes[ARIN + "ip/8.8.4.4"] = network()
    result = run(rig, ips=("8.8.8.8", "8.8.4.4"))
    assert result.status == "matched" and result.matched_ip == "8.8.4.4"
    assert "secret" not in result.attempts[0].message


def test_transient_error_is_not_cached_as_no_match(rig):
    def timeout(req):
        raise httpx.ReadTimeout("timeout")
    rig[2].routes[ARIN + "ip/8.8.8.8"] = timeout
    assert run(rig).status == "deferred"
    rig[2].routes[ARIN + "ip/8.8.8.8"] = network()
    assert run(rig).status == "matched"


def test_batch_shared_ip_uses_one_network_response(rig):
    rig[2].routes[ARIN + "ip/8.8.8.8"] = network()
    groups = [("example.com", [CandidateIP(str(i), "8.8.8.8")]) for i in range(20)]
    results = list(rig[0].attribute_many(groups, workers=4))
    assert len(results) == 20 and all(r.status == "matched" for r in results)
    assert len(rig[2].calls) == 2


def test_refresh_preserves_old_evidence(rig):
    rig[2].routes[ARIN + "ip/8.8.8.8"] = network()
    first = run(rig)
    rig[2].routes[ARIN + "ip/8.8.8.8"] = network("changed.net")
    assert run(rig, refresh=True).status == "no_match"
    assert rig[3].snapshot(first.evidence[0].snapshot_id).record()["entities"][0]["vcardArray"][1][2][3] == "support@example.com"


def test_offline_hit_and_miss(rig):
    assert run(rig, offline=True).status == "deferred" and not rig[2].calls
    rig[2].routes[ARIN + "ip/8.8.8.8"] = network()
    run(rig)
    assert run(rig, offline=True).status == "matched" and len(rig[2].calls) == 2

