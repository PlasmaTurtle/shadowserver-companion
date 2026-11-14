"""Named recursive resolver tests; every HTTP response is an in-process fixture."""
import asyncio
import hashlib
import threading
import time

import httpx
import pytest

from attribution import AttributionModule, CandidateIP, DnsProvider, EvidenceRenderer, EvidenceStore, Settings, verify_export
from attribution.google_dns import SOURCE_NAME, query_url
from attribution.models import LookupFailure, ResponseSnapshot, json_bytes
from test_review_dns import Resolver


def record(name, kind, values=(), **changes):
    number = {"A": 1, "AAAA": 28, "PTR": 12}[kind]
    result = {"Status": 0, "TC": False, "RD": True, "RA": True, "AD": False, "CD": False,
              "Question": [{"name": name, "type": number}],
              "Answer": [{"name": name, "type": number, "TTL": 60, "data": value} for value in values]}
    result.update(changes)
    return result


def response(data=None, status=200, raw=None, **headers):
    return httpx.Response(status, headers={"content-type": "application/json", **headers},
                          stream=httpx.ByteStream(raw if raw is not None else json_bytes(data)))


class Server:
    def __init__(self, routes=None):
        self.routes, self.calls, self.raw = routes or {}, [], {}

    def __call__(self, request):
        assert request.url.scheme == "https" and request.url.host == "dns.google"
        assert request.url.path == "/resolve"
        assert request.url.params["cd"] == "false"
        assert request.url.params["edns_client_subnet"] == "0.0.0.0/0"
        assert request.headers["accept-encoding"] == "identity"
        name, kind = request.url.params["name"], request.url.params["type"]
        assert name.endswith(".")
        self.calls.append((name, kind))
        item = self.routes.get((name, kind), record(name, kind))
        if callable(item):
            return item(request)
        self.raw[(name, kind)] = json_bytes(item)
        return response(raw=self.raw[(name, kind)])


def provider(store, server, **kwargs):
    return DnsProvider(store, Settings(interval=0, retries=0), transport=httpx.MockTransport(server), **kwargs)


def test_default_dns_uses_google_exact_bytes_citable_pointer_and_original_cache_provenance(tmp_path):
    server = Server({("mail.example.com.", "A"): record("mail.example.com.", "A", ["8.8.8.8"])})
    with EvidenceStore(tmp_path / "evidence.sqlite3") as store:
        dns = provider(store, server)
        module = AttributionModule(store, providers=[dns])
        candidate = CandidateIP("row", "8.8.8.8", "mail.example.com")
        first = module.attribute("example.com", [candidate])
        assert first.status == "matched"
        ev = first.evidence[0]
        snapshot = store.snapshot(ev.snapshot_id)
        assert ev.source_name == SOURCE_NAME
        assert ev.source_url == query_url("mail.example.com.", "A")
        assert ev.match.field_path == "/Answer/0/data" and ev.match.value == "8.8.8.8"
        assert snapshot.body == server.raw[("mail.example.com.", "A")]
        assert snapshot.body_sha256 == hashlib.sha256(snapshot.body).hexdigest()
        assert ev.details["resolver_kind"] == "public recursive resolver"
        assert dns.describe()["resolver"] == SOURCE_NAME
        second = module.attribute("example.com", [candidate], offline=True)
        assert second.evidence[0].from_cache
        assert second.evidence[0].retrieved_at == ev.retrieved_at
        assert second.evidence[0].snapshot_id == ev.snapshot_id
        assert second.attempts[0].network_requests == 0 and second.attempts[0].cache_hits == 1
        folder = tmp_path / "export"
        EvidenceRenderer(store).export(second.result_id, folder)
        assert verify_export(folder)["valid"]
        assert snapshot.body == (folder / "responses" / (snapshot.snapshot_id + ".json")).read_bytes()
        assert "Google Public DNS" in (folder / "evidence.html").read_text()
        assert len(server.calls) == 1


def test_google_does_not_relabel_legacy_workstation_cache_or_saved_results(tmp_path):
    resolver = Resolver({("mail.example.com.", "A"): ["8.8.8.8"]})
    with EvidenceStore(tmp_path / "evidence.sqlite3") as store:
        module = AttributionModule(store, providers=[DnsProvider(store, resolver=resolver)])
        result = module.attribute("example.com", [CandidateIP("row", "8.8.8.8", "mail.example.com")])
        before = store.snapshot(result.evidence[0].snapshot_id)
        google = provider(store, Server())
        offline = google.collect("8.8.8.8", "example.com", hostname="mail.example.com", offline=True)
        assert offline.status == "deferred" and not offline.evidence
        assert store.result(result.result_id)["evidence"][0]["source_name"] == "Workstation DNS resolver"
        assert store.snapshot(before.snapshot_id) == before


def test_cname_matches_only_reachable_owner_and_preserves_exact_address_pointer(tmp_path):
    data = record("mail.example.com.", "A", Answer=[
        {"name": "unrelated.test.", "type": 1, "TTL": 600, "data": "8.8.4.4"},
        {"name": "mail.example.com.", "type": 5, "TTL": 10, "data": "edge.provider.test."},
        {"name": "edge.provider.test.", "type": 1, "TTL": 60, "data": "8.8.8.8"}])
    with EvidenceStore(tmp_path / "evidence.sqlite3") as store:
        server = Server({("mail.example.com.", "A"): data})
        result = provider(store, server).collect("8.8.8.8", "example.com", hostname="mail.example.com")
        assert result.status == "matched" and result.evidence.match.field_path == "/Answer/2/data"
        assert result.evidence.details["cname_chain"] == ["edge.provider.test"]
        expires = store._db.execute("select expires from cache").fetchone()[0]
        assert 0 < expires - time.time() <= 10
        data["Answer"][2]["name"] = "unrelated.test."
        result = provider(store, server).collect("8.8.8.8", "example.com", hostname="mail.example.com", refresh=True)
        assert result.status == "no_match"


@pytest.mark.parametrize("change", [
    {"Question": [{"name": "other.example.com.", "type": 1}]},
    {"Question": [{"name": "mail.example.com.", "type": 28}]},
    {"Question": [{"name": "mail.example.com.", "type": True}]},
    {"Question": []}, {"TC": True}, {"CD": True}, {"RA": False}, {"Status": False},
    {"Status": 3}, {"Answer": [{"name": "mail.example.com.", "type": 1, "TTL": 60, "data": "2606:4700::1111"}]},
    {"Answer": [{"name": "mail.example.com.", "type": 5, "TTL": 60, "data": "mail.example.com."}]},
    {"Answer": [{"name": "mail.example.com.", "type": 5, "TTL": 60, "data": "a.example.com."},
                {"name": "mail.example.com.", "type": 5, "TTL": 60, "data": "b.example.com."}]},
])
def test_malformed_or_mismatched_answers_cannot_qualify(tmp_path, change):
    data = record("mail.example.com.", "A", ["8.8.8.8"], **change)
    with EvidenceStore(tmp_path / "evidence.sqlite3") as store:
        result = provider(store, Server({("mail.example.com.", "A"): data})).collect(
            "8.8.8.8", "example.com", hostname="mail.example.com")
        assert result.status == "deferred" and result.evidence is None
        assert "dns_invalid_response" in result.warnings
        assert result.snapshot_ids


def test_reverse_requires_root_boundary_and_forward_confirmation_over_https(tmp_path):
    server = Server({("8.8.8.8.in-addr.arpa.", "PTR"): record("8.8.8.8.in-addr.arpa.", "PTR",
                      ["badexample.com.", "vpn.example.com."]),
                     ("vpn.example.com.", "A"): record("vpn.example.com.", "A", ["8.8.8.8"])})
    with EvidenceStore(tmp_path / "evidence.sqlite3") as store:
        dns = provider(store, server)
        result = dns.collect("8.8.8.8", "example.com", hostname="mail.example.com")
        assert result.status == "matched" and result.reason == "dns_reverse_confirmed"
        assert result.evidence.match.matched_domain == "vpn.example.com"
        assert len(result.snapshot_ids) == 3 and len(server.calls) == 3
        assert ("badexample.com.", "A") not in server.calls
        server.routes[("vpn.example.com.", "A")] = record("vpn.example.com.", "A", ["8.8.4.4"])
        assert dns.collect("8.8.8.8", "example.com", hostname="mail.example.com", refresh=True).status == "no_match"


@pytest.mark.parametrize("dns_status,expected", [(3, "no_match"), (2, "deferred"), (5, "deferred")])
def test_dns_negative_is_distinct_from_service_error_and_never_negative_caches_failure(tmp_path, dns_status, expected):
    server = Server({("mail.example.com.", "A"): record("mail.example.com.", "A", Status=dns_status)})
    with EvidenceStore(tmp_path / "evidence.sqlite3") as store:
        dns = provider(store, server)
        result = dns.collect("8.8.8.8", "example.com", hostname="mail.example.com")
        assert result.status == expected
        snapshot = store.snapshot(result.snapshot_ids[0])
        if dns_status == 3:
            assert snapshot.record()["Status"] == dns_status
        else:
            assert snapshot.body == b"" and snapshot.body_retention == "rejected_response"
            assert snapshot.received_body_sha256 == hashlib.sha256(json_bytes(record("mail.example.com.", "A", Status=dns_status))).hexdigest()
        assert store.cached(query_url("mail.example.com.", "A")) is None


@pytest.mark.parametrize("status", [301, 403, 500])
def test_http_failure_is_saved_without_following_redirects_or_matching_body(tmp_path, status):
    server = Server({("mail.example.com.", "A"): lambda request: response(
        record("mail.example.com.", "A", ["8.8.8.8"]), status=status, location="https://evil.test/resolve")})
    with EvidenceStore(tmp_path / "evidence.sqlite3") as store:
        result = provider(store, server).collect("8.8.8.8", "example.com", hostname="mail.example.com")
        assert result.status == "deferred" and not result.evidence
        assert store.snapshot(result.snapshot_ids[0]).status_code == status
        assert result.reason == "dns_http_error"


@pytest.mark.parametrize("status", [200, 302, 403, 429, 500])
def test_dns_html_is_metadata_only_before_storage(tmp_path, status):
    raw = b'<html><script src="https://untrusted.invalid/example.js"></script>dns-capture-sentinel</html>'
    server = Server({("mail.example.com.", "A"): lambda request: response(
        raw=raw, status=status, **{"content-type": "text/html"})})
    with EvidenceStore(tmp_path / "evidence.sqlite3") as store:
        result = provider(store, server).collect("8.8.8.8", "example.com", hostname="mail.example.com")
        first = store.snapshot(result.snapshot_ids[0])
        assert first.body == b"" and first.body_retention == "rejected_response"
        assert first.received_body_sha256 == hashlib.sha256(raw).hexdigest()
        assert first.received_body_size == len(raw)
        assert not any(b"dns-capture-sentinel" in bytes(row[0]) for row in store._db.execute("SELECT body FROM snapshots"))


def test_rate_limit_stops_reverse_queries_and_is_shared_between_providers(tmp_path):
    server = Server({("mail.example.com.", "A"): lambda request: response({}, status=429, **{"retry-after": "60"})})
    with EvidenceStore(tmp_path / "evidence.sqlite3") as store:
        result = provider(store, server).collect("8.8.8.8", "example.com", hostname="mail.example.com")
        assert result.reason == "dns_rate_limited" and result.retry_at > time.time()
        assert len(server.calls) == 1
        provider(store, server).collect("8.8.4.4", "example.com", hostname="other.example.com")
        assert len(server.calls) == 1


def test_ipv6_and_nonpublic_input_are_handled_without_wrong_family_query(tmp_path):
    server = Server({("v6.example.com.", "AAAA"): record("v6.example.com.", "AAAA", ["2606:4700:4700::1111"])})
    with EvidenceStore(tmp_path / "evidence.sqlite3") as store:
        dns = provider(store, server)
        assert dns.collect("10.0.0.1", "example.com").status == "skipped"
        assert dns.collect("2606:4700:4700::1111", "example.com", hostname="v6.example.com").status == "matched"
        assert server.calls == [("v6.example.com.", "AAAA")]


def test_total_budget_bounds_delayed_headers_and_stops_further_queries(tmp_path):
    calls = []
    async def slow(request):
        calls.append(request)
        await asyncio.sleep(5)
        return response(record("mail.example.com.", "A", ["8.8.8.8"]))
    with EvidenceStore(tmp_path / "evidence.sqlite3") as store:
        dns = DnsProvider(store, Settings(interval=0, operation_budget=.08), transport=httpx.MockTransport(slow))
        started = time.monotonic()
        result = dns.collect("8.8.8.8", "example.com", hostname="mail.example.com")
        assert result.reason == "dns_budget_exhausted" and len(calls) == 1
        assert time.monotonic() - started < 1


def test_cancellation_interrupts_active_dns_capture_and_prevents_later_candidates(tmp_path):
    event, calls = threading.Event(), []
    async def slow(request):
        calls.append(request)
        event.set()
        await asyncio.sleep(5)
        return response(record("mail.example.com.", "A", ["8.8.8.8"]))
    with EvidenceStore(tmp_path / "evidence.sqlite3") as store:
        dns = DnsProvider(store, Settings(interval=0), cancel_event=event, transport=httpx.MockTransport(slow))
        started = time.monotonic()
        result = dns.collect("8.8.8.8", "example.com", hostname="mail.example.com")
        assert result.reason == "dns_cancelled" and len(calls) == 1 and not result.evidence
        assert time.monotonic() - started < 1
        with pytest.raises(LookupFailure, match="cancelled"):
            AttributionModule(store, providers=[dns], cancel_event=event).attribute(
                "example.com", [CandidateIP("row", "8.8.8.8")])
        assert len(calls) == 1


def test_oversized_and_duplicate_json_bodies_cannot_qualify(tmp_path):
    for raw in (b"x" * 1025, b'{"Status":0,"Status":0}'):
        server = Server({("mail.example.com.", "A"): lambda request: response(raw=raw)})
        with EvidenceStore(tmp_path / (str(len(raw)) + ".sqlite3")) as store:
            dns = DnsProvider(store, Settings(interval=0, max_response_bytes=1024), transport=httpx.MockTransport(server))
            result = dns.collect("8.8.8.8", "example.com", hostname="mail.example.com")
            assert result.status == "deferred" and not result.evidence
            assert result.reason in ("dns_response_too_large", "dns_invalid_response")


def test_cached_wrong_question_is_revalidated(tmp_path):
    with EvidenceStore(tmp_path / "evidence.sqlite3") as store:
        url = query_url("mail.example.com.", "A")
        snapshot = ResponseSnapshot.create(url, url, 200, {"content-type": "application/json"},
            json_bytes(record("other.example.com.", "A", ["8.8.8.8"])))
        store.save_snapshot(snapshot)
        store.cache(url, [snapshot], 60)
        result = provider(store, Server()).collect("8.8.8.8", "example.com", hostname="mail.example.com", offline=True)
        assert result.status == "deferred" and not result.evidence
        assert result.reason == "dns_invalid_response"
