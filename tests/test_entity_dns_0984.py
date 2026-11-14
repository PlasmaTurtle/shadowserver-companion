"""Root DNS supplements are cached observations, never implicit ownership edits."""

from contextlib import closing
from copy import deepcopy
import hashlib
import json
import sqlite3
import threading
import time

import httpx
import pytest
from attribution import EvidenceStore, Settings
from attribution.google_dns import GooglePublicDnsProvider
from attribution.models import json_bytes

from workbench.entity_dns import EntityDNS, root_scopes
from workbench.repositories.sources import SourceRepository
from workbench.store import Store
from test_workbench import app, client, import_rows


def answer(name, kind, values=(), **updates):
    number = {"A": 1, "AAAA": 28}[kind]
    result = {
        "Status": 0,
        "TC": False,
        "RD": True,
        "RA": True,
        "AD": False,
        "CD": False,
        "Question": [{"name": name, "type": number}],
        "Answer": [{"name": name, "type": number, "TTL": 300, "data": value} for value in values],
    }
    result.update(updates)
    return result


class DNSFixture:
    def __init__(self):
        self.calls = []
        self.fail = False
        self.gate = None
        self.records = {}

    def __call__(self, request):
        assert request.url.host == "dns.google" and request.url.scheme == "https"
        assert request.url.path == "/resolve"
        assert request.url.params["cd"] == "false"
        assert request.url.params["edns_client_subnet"] == "0.0.0.0/0"
        name, kind = request.url.params["name"], request.url.params["type"]
        assert name.endswith(".") and kind in ("A", "AAAA")
        self.calls.append((name, kind))
        if self.gate:
            self.gate.wait(2)
        if self.fail:
            return httpx.Response(
                503, headers={"retry-after": "600"}, stream=httpx.ByteStream(b"{}")
            )
        data = self.records.get(
            (name, kind),
            answer(name, kind, ["8.8.8.8"] if kind == "A" else ["2606:4700:4700::1111"]),
        )
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            stream=httpx.ByteStream(json_bytes(data)),
        )

    def factory(self, evidence, settings, **kwargs):
        return GooglePublicDnsProvider(
            evidence,
            Settings(timeout=2, operation_budget=6, interval=0),
            transport=httpx.MockTransport(self),
            **kwargs,
        )


def entity(domain="mail.navarac.com", **changes):
    return {
        "id": "entity-one",
        "domain": domain,
        "entries": [{"id": "row-one", "hostname": domain, "ip": "1.1.1.1"}],
        "hostnames": [],
        **changes,
    }


def wait(service, item):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        state = service.status(item)
        if not state["running"]:
            assert state["job"]["status"] == "complete", state
            return state
        time.sleep(0.01)
    pytest.fail("Root DNS job did not finish")


def test_registrable_domains_use_psl_and_preserve_subdomain_scope():
    item = entity(
        hostnames=[
            "autodiscover.navarac.com",
            "Mail.Example.CO.UK.",
            "a.b.github.io",
            "localhost",
            "mail.internal",
            "co.uk",
            "8.8.8.8",
            "http://bad.com",
        ]
    )
    roots = {r["root_domain"]: r["reported_hostnames"] for r in root_scopes(item)}
    assert roots == {
        "navarac.com": ["autodiscover.navarac.com", "mail.navarac.com"],
        "example.co.uk": ["mail.example.co.uk"],
        "b.github.io": ["a.b.github.io"],
    }


def test_first_read_has_no_network_or_attribution_database(tmp_path):
    server = DNSFixture()
    store = Store(tmp_path)
    service = EntityDNS(store, provider_factory=server.factory)
    state = service.status(entity())
    assert state["needs_lookup"] and state["roots"][0]["root_domain"] == "navarac.com"
    assert server.calls == []
    assert not (tmp_path / "attribution.sqlite3").exists()


def test_background_forward_lookup_keeps_original_row_and_caches_both_families(tmp_path):
    server = DNSFixture()
    store = Store(tmp_path)
    service = EntityDNS(store, provider_factory=server.factory)
    item = entity()
    original = deepcopy(item)
    service.start(item)
    state = wait(service, item)
    assert server.calls == [("navarac.com.", "A"), ("navarac.com.", "AAAA")]
    assert item == original
    lookup = state["roots"][0]["lookup"]
    assert {ip for a in lookup["answers"] for ip in a["addresses"]} == {
        "8.8.8.8",
        "2606:4700:4700::1111",
    }
    assert not state["needs_lookup"] and not lookup["stale"]
    with EvidenceStore(tmp_path / "attribution.sqlite3") as evidence:
        assert evidence.stats()["results"] == 0
        for a in lookup["answers"]:
            raw = evidence.snapshot(a["source"]["snapshot_id"])
            assert (
                raw.body_sha256
                == hashlib.sha256(raw.body).hexdigest()
                == a["source"]["body_sha256"]
            )
            assert raw.retrieved_at == a["source"]["retrieved_at"]
    again = EntityDNS(store, provider_factory=server.factory)
    again.start({**item, "id": "same-root-other-entity"})
    assert len(server.calls) == 2
    assert again.status(item)["roots"][0]["lookup"]["revision_id"] == lookup["revision_id"]


def test_forward_query_reuses_existing_google_evidence_cache_and_validates_alias_chain(tmp_path):
    server = DNSFixture()
    server.records[("navarac.com.", "A")] = answer(
        "navarac.com.",
        "A",
        Answer=[
            {"name": "navarac.com.", "type": 5, "TTL": 90, "data": "edge.example.com."},
            {"name": "edge.example.com.", "type": 1, "TTL": 300, "data": "8.8.8.8"},
            {"name": "unrelated.com.", "type": 1, "TTL": 300, "data": "9.9.9.9"},
        ],
    )
    with EvidenceStore(tmp_path / "evidence.sqlite3") as evidence:
        provider = server.factory(evidence, None)
        first = provider.resolve_addresses("navarac.com")
        second = provider.resolve_addresses("navarac.com", offline=True)
        assert first["answers"][0]["addresses"] == ["8.8.8.8"]
        assert first["answers"][0]["cname_chain"] == ["edge.example.com"]
        assert first["answers"][0]["ttl"] == 90
        assert second["network_requests"] == 0 and second["cache_hits"] == 2
        assert (
            second["answers"][0]["source"]["retrieved_at"]
            == first["answers"][0]["source"]["retrieved_at"]
        )
        assert len(server.calls) == 2


def test_nonpublic_dns_answers_are_not_connection_nodes_and_never_contacted(tmp_path):
    server = DNSFixture()
    server.records[("navarac.com.", "A")] = answer(
        "navarac.com.", "A", ["10.0.0.1", "127.0.0.1", "8.8.8.8"]
    )
    server.records[("navarac.com.", "AAAA")] = answer("navarac.com.", "AAAA", ["::1", "fc00::1"])
    service = EntityDNS(Store(tmp_path), provider_factory=server.factory)
    service.start(entity())
    lookup = wait(service, entity())["roots"][0]["lookup"]
    assert lookup["answers"][0]["addresses"] == ["8.8.8.8"]
    assert lookup["answers"][0]["nonpublic_addresses_omitted"] == 2
    assert lookup["answers"][1]["addresses"] == []
    assert len(server.calls) == 2


def test_failed_refresh_retains_previous_answers_and_retry_backoff(tmp_path):
    server = DNSFixture()
    service = EntityDNS(Store(tmp_path), provider_factory=server.factory)
    service.start(entity())
    before = wait(service, entity())["roots"][0]["lookup"]
    server.fail = True
    service.start(entity(), refresh=True)
    state = wait(service, entity())
    after = state["roots"][0]["lookup"]
    assert after["retained_previous_answers"]
    assert after["answers"] == before["answers"]
    assert after["warnings"] == ["dns_rate_limited"]
    assert after["next_attempt_at"] > time.time() + 590
    calls = len(server.calls)
    service.start(entity())
    assert not service.status(entity())["running"] and len(server.calls) == calls


def test_status_does_not_pair_finished_refresh_with_previous_cache(tmp_path, monkeypatch):
    release_refresh = threading.Event()

    class ControlledDNSFixture(DNSFixture):
        def __call__(self, request):
            if self.fail:
                assert release_refresh.wait(5), "status reader did not release the refresh"
            return super().__call__(request)

    server = ControlledDNSFixture()
    service = EntityDNS(Store(tmp_path), provider_factory=server.factory)
    item = entity()
    service.start(item)
    before = wait(service, item)["roots"][0]["lookup"]
    finished = threading.Event()
    original_run = service._run

    def finish_signalled(*args):
        try:
            original_run(*args)
        finally:
            finished.set()

    monkeypatch.setattr(service, "_run", finish_signalled)
    server.fail = True
    service.start(item, refresh=True)
    original_cached = service._cached
    reader = threading.get_ident()

    def finish_after_cache_read(root):
        value = original_cached(root)
        if threading.get_ident() == reader:
            # The old result has been read. Force the refresh to commit and
            # complete before status() can assemble its progress/result pair.
            release_refresh.set()
            assert finished.wait(5)
        return value

    monkeypatch.setattr(service, "_cached", finish_after_cache_read)
    state = service.status(item)
    assert state["roots"][0]["lookup"]["revision_id"] == before["revision_id"]
    assert state["running"], "completion must not be advertised alongside the previous lookup"
    current = service.status(item)
    assert current["job"]["status"] == "complete"
    assert current["roots"][0]["lookup"]["retained_previous_answers"]
    assert current["roots"][0]["lookup"]["revision_id"] != before["revision_id"]


def test_malformed_dns_response_is_not_displayed(tmp_path):
    server = DNSFixture()
    server.records[("navarac.com.", "A")] = answer("different.com.", "A", ["8.8.8.8"])
    service = EntityDNS(Store(tmp_path), provider_factory=server.factory)
    service.start(entity())
    lookup = wait(service, entity())["roots"][0]["lookup"]
    assert lookup["warnings"] == ["dns_invalid_response"]
    assert [a["record_type"] for a in lookup["answers"]] == ["AAAA"]


def test_tampered_captured_bytes_invalidate_summary(tmp_path):
    server = DNSFixture()
    store = Store(tmp_path)
    service = EntityDNS(store, provider_factory=server.factory)
    service.start(entity())
    lookup = wait(service, entity())["roots"][0]["lookup"]
    with EvidenceStore(tmp_path / "attribution.sqlite3") as evidence:
        with evidence._db:
            evidence._db.execute(
                "UPDATE snapshots SET body=? WHERE id=?",
                (b"{}", lookup["answers"][0]["source"]["snapshot_id"]),
            )
    state = service.status(entity())
    assert state["needs_lookup"] and state["roots"][0]["lookup"] is None


def test_demo_and_invalid_hostnames_do_not_start_network(tmp_path):
    server = DNSFixture()
    service = EntityDNS(Store(tmp_path), provider_factory=server.factory)
    assert service.start(entity(demo=True))["disabled"]
    assert not service.start(entity("mail.internal"))["needs_lookup"]
    assert not service.start(entity("127.0.0.1"))["total_roots"]
    assert server.calls == []


def test_duplicate_job_returns_immediately_without_duplicate_queries(tmp_path):
    server = DNSFixture()
    server.gate = threading.Event()
    service = EntityDNS(Store(tmp_path), provider_factory=server.factory)
    started = time.monotonic()
    service.start(entity())
    service.start(entity())
    assert time.monotonic() - started < 0.5
    assert service.status(entity())["running"]
    server.gate.set()
    wait(service, entity())
    assert len(server.calls) == 2


def test_entity_api_adds_dns_without_modifying_case_or_entity_revision(client, app):
    import_rows(client, app)
    item = client.get("/api/entities").json()[0]
    url = f"/api/entities/{item['id']}"
    before = client.get(url).json()
    server = DNSFixture()
    service = app.state.entity_dns
    service.provider_factory = server.factory
    response = client.post(url + "/connections/dns", json={"refresh": False})
    assert response.status_code == 200
    wait(service, before)
    after = client.get(url).json()
    assert after["dns_connections"]["roots"][0]["lookup"]
    assert {k: v for k, v in after.items() if k != "dns_connections"} == {
        k: v for k, v in before.items() if k != "dns_connections"
    }
    assert client.get(url + "/connections/dns").json()["running"] is False
    assert client.post("/api/entities/unknown/connections/dns", json={}).status_code == 404


def test_corrupt_optional_summary_does_not_block_entity_read(tmp_path):
    store = Store(tmp_path)
    service = EntityDNS(store)
    # Modern writes reject malformed JSON. Preserve the reader regression with
    # an actual earlier schema, where such optional cache rows could exist.
    with pytest.raises(sqlite3.IntegrityError, match="Invalid server-owned JSON"):
        with store.transaction() as db:
            db.execute(
                "INSERT INTO cache VALUES(?,?,?)", ("entity-dns:v1:navarac.com", "broken", "now")
            )
    from schema_helpers import restore_schema

    with closing(store.connect()) as db:
        restore_schema(db, 16)
    with store.transaction() as db:
        db.execute(
            "INSERT INTO cache VALUES(?,?,?)", ("entity-dns:v1:navarac.com", "broken", "now")
        )
    assert service.status(entity())["needs_lookup"]
    with store.transaction() as db:
        SourceRepository.put(
            db,
            "entity-dns:v1:navarac.com",
            {"hostname": "navarac.com", "expires_at": "forever", "next_attempt_at": "forever"},
        )
    store.migrate()
    # Syntactically valid JSON still needs DNS-specific shape validation after
    # upgrade; an optional malformed summary cannot block the entity read.
    assert service.status(entity())["needs_lookup"]


def test_entity_identity_root_is_not_relabelled_as_reported_hostname():
    item = entity("navarac.com", entries=[{"hostname": "mail.navarac.com"}])
    assert root_scopes(item)[0]["reported_hostnames"] == ["mail.navarac.com"]
