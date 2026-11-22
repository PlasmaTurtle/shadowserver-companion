"""Independent DNS sources, comparison semantics, and bounded concurrent requests."""
import httpx

from attribution import AttributionModule, CandidateIP, EvidenceStore, Settings
from attribution.public_dns import DualPublicDnsProvider
from attribution.models import json_bytes


def provider(store, *, differing=False, failing=False):
    calls = []

    def serve(request):
        source = request.url.host
        assert source in {"dns.google", "cloudflare-dns.com"}
        if source == "cloudflare-dns.com":
            assert request.headers["accept"] == "application/dns-json"
            assert request.url.path == "/dns-query"
            if failing:
                return httpx.Response(503, stream=httpx.ByteStream(b"{}"))
        calls.append(str(request.url))
        name, kind = request.url.params["name"], request.url.params["type"]
        number = {"A": 1, "AAAA": 28, "PTR": 12}[kind]
        values = [] if kind != "A" else [
            "1.1.1.1" if differing and source == "cloudflare-dns.com" else "8.8.8.8"]
        body = {"Status": 0, "TC": False, "RD": True, "RA": True, "AD": False,
                "CD": False, "Question": [{"name": name, "type": number}],
                "Answer": [{"name": name, "type": number, "TTL": 300, "data": v} for v in values]}
        return httpx.Response(200, headers={"content-type": "application/dns-json"},
                              stream=httpx.ByteStream(json_bytes(body)))
    return DualPublicDnsProvider(store, Settings(interval=0, timeout=2, operation_budget=4),
                                 transport=httpx.MockTransport(serve)), calls


def test_both_resolver_snapshots_retained_and_reused_without_relabeling(tmp_path):
    with EvidenceStore(tmp_path / "dns.sqlite3") as store:
        dns, calls = provider(store)
        result = AttributionModule(store, providers=[dns]).attribute(
            "example.com", [CandidateIP("one", "8.8.8.8", "mail.example.com")])
        assert result.status == "matched"
        ev = result.evidence[0]
        assert ev.details["resolver_comparison"]["status"] == "agreement"
        assert len(ev.supporting_snapshot_ids) == 2
        assert {store.snapshot(i).source_url.split('/')[2] for i in ev.supporting_snapshot_ids} == {
            "dns.google", "cloudflare-dns.com"}
        again = dns.collect("8.8.8.8", "example.com", hostname="mail.example.com", offline=True)
        assert again.cache_hits == 2 and again.network_requests == 0
        assert len(calls) == 2


def test_different_answers_are_visible_but_failure_is_not_disagreement(tmp_path):
    with EvidenceStore(tmp_path / "dns.sqlite3") as store:
        dns, _ = provider(store, differing=True)
        result = dns.collect("8.8.8.8", "example.com", hostname="mail.example.com")
        assert result.status == "matched"
        assert result.evidence.details["resolver_comparison"]["status"] == "disagreement"
        assert "dns_resolver_disagreement" in result.warnings
        dns, _ = provider(store, failing=True)
        failed = dns.collect("8.8.8.8", "example.com", hostname="mail.example.com", refresh=True)
        assert failed.status == "matched"
        assert failed.evidence.details["resolver_comparison"]["status"] == "incomplete"
        assert "dns_resolver_disagreement" not in failed.warnings
        assert len(failed.evidence.details["resolver_results"]) == 2


def test_forward_connections_compare_each_address_family(tmp_path):
    with EvidenceStore(tmp_path / "dns.sqlite3") as store:
        dns, calls = provider(store, differing=True)
        result = dns.resolve_addresses("example.com")
        assert len(calls) == 4
        assert len(result["answers"]) == 4
        assert result["comparison"] == {"status": "disagreement", "records": [
            {"record_type": "A", "status": "disagreement"},
            {"record_type": "AAAA", "status": "agreement"}]}
