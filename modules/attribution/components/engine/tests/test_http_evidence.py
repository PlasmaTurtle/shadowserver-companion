import gzip
import hashlib
import json
import time
from dataclasses import replace
from datetime import datetime, timezone
from email.utils import format_datetime

import httpx
import pytest

from attribution import (
    AttributionModule,
    CandidateIP,
    EvidenceRenderer,
    EvidenceStore,
    RdapProvider,
    RootDomainPolicy,
    Settings,
    verify_export,
)
from attribution.cli import main
from attribution.http import response_ttl, retry_delay
from attribution_test_support.rdap import ARIN, RIPE, IANA4, network, response, entity


def test_original_snapshot_metadata_keeps_historical_fingerprint_shape():
    from attribution.models import ResponseSnapshot

    snapshot = ResponseSnapshot.create(
        "https://rdap.arin.net/registry/ip/8.8.8.8",
        "https://rdap.arin.net/registry/ip/8.8.8.8",
        200,
        {"content-type": "application/json"},
        b"{}",
    )
    metadata = snapshot.metadata()
    assert set(metadata) == {
        "snapshot_id",
        "requested_url",
        "source_url",
        "retrieved_at",
        "status_code",
        "headers",
        "body_sha256",
        "body_size",
    }
    body_size = metadata.pop("body_size")
    restored = ResponseSnapshot(body=snapshot.body, **metadata)
    assert body_size == len(snapshot.body) and restored == snapshot


def run(rig, domain="example.com", ip="8.8.8.8", **kw):
    return rig[0].attribute(domain, [CandidateIP("row", ip)], **kw)


def test_rate_limit_persists_and_is_scoped_to_registry(rig):
    rig[2].routes[ARIN + "ip/8.8.8.8"] = lambda req: response(
        status=429, headers={"retry-after": "3600"}
    )
    first = run(rig)
    assert first.status == "deferred" and first.attempts[0].retry_at > time.time() + 3500
    assert run(rig, ip="8.8.4.4").status == "deferred"
    assert len(rig[2].calls) == 2  # The second IP was not requested during cooldown.
    rig[2].routes[RIPE + "ip/193.0.6.139"] = network(
        startAddress="193.0.0.0", endAddress="193.255.255.255"
    )
    assert run(rig, ip="193.0.6.139").status == "matched"
    with EvidenceStore(rig[3].path) as second_store:
        assert second_store.cooldown("rdap.arin.net") > time.time() + 3500


@pytest.mark.parametrize(
    "target",
    [
        "http://rdap.arin.net/registry/ip/8.8.8.8",
        "https://127.0.0.1/a",
        "https://evil.example/a",
        "https://u:p@rdap.arin.net/a",
        "https://rdap.arin.net:8443/a",
    ],
)
def test_redirect_destination_is_validated(rig, target):
    rig[2].routes[ARIN + "ip/8.8.8.8"] = lambda req: response(
        status=302, headers={"location": target}
    )
    result = run(rig)
    assert result.status == "incomplete" and result.attempts[0].reason == "untrusted_destination"
    assert len(rig[2].calls) == 2


def test_authoritative_registry_redirect(rig):
    rig[2].routes[ARIN + "ip/8.8.8.8"] = lambda req: response(
        status=301, headers={"location": RIPE + "ip/8.8.8.8"}
    )
    rig[2].routes[RIPE + "ip/8.8.8.8"] = network()
    result = run(rig)
    assert result.status == "matched" and result.evidence[0].source_name == "RIPE NCC"
    assert len(result.attempts[0].snapshot_ids) == 3


def test_redirect_loop(rig):
    rig[2].routes[ARIN + "ip/8.8.8.8"] = lambda req: response(
        status=302, headers={"location": ARIN + "ip/8.8.8.8"}
    )
    result = run(rig)
    assert result.status == "incomplete" and result.attempts[0].reason == "redirect_loop"


def test_oversized_body_and_gzip_bomb(rig):
    rig[1].client.settings = replace(rig[1].client.settings, max_response_bytes=1024)
    rig[2].routes[ARIN + "ip/8.8.8.8"] = lambda req: response(raw=b"x" * 1025)
    assert run(rig).attempts[0].reason == "response_too_large"
    rig[2].routes[ARIN + "ip/8.8.8.8"] = lambda req: response(
        raw=gzip.compress(b"x" * 100000), headers={"content-encoding": "gzip"}
    )
    assert run(rig).attempts[0].reason == "response_too_large"


def test_compressed_record_preserves_decoded_body(rig):
    body = json.dumps(network()).encode()
    rig[2].routes[ARIN + "ip/8.8.8.8"] = lambda req: response(
        raw=gzip.compress(body), headers={"content-encoding": "gzip"}
    )
    result = run(rig)
    assert result.status == "matched"
    assert rig[3].snapshot(result.evidence[0].snapshot_id).body == body


@pytest.mark.parametrize(
    "raw,headers",
    [
        (b"{bad json", {}),
        (b"{}", {"content-type": "text/html"}),
        (b'{"objectClassName":"ip network","objectClassName":"domain"}', {}),
    ],
)
def test_invalid_response_receipts_are_saved_without_unvalidated_bytes(rig, raw, headers):
    rig[2].routes[ARIN + "ip/8.8.8.8"] = lambda req: response(raw=raw, headers=headers)
    result = run(rig)
    assert result.status == "incomplete"
    snapshot = rig[3].snapshot(result.attempts[0].snapshot_ids[-1])
    assert snapshot.body == b""
    assert snapshot.body_retention == "rejected_response"
    assert snapshot.received_body_sha256 == hashlib.sha256(raw).hexdigest()
    assert snapshot.received_body_size == len(raw)
    assert snapshot.body_sha256 == hashlib.sha256(b"").hexdigest()


@pytest.mark.parametrize("status", [200, 301, 302, 404, 429, 500, 503])
def test_untrusted_gateway_bodies_never_reach_evidence_storage_or_exports(rig, tmp_path, status):
    raw = (
        b'<html><script src="https://untrusted.invalid/payload.js"></script>capture-sentinel</html>'
    )
    headers = {"content-type": "text/html", "location": RIPE + "ip/8.8.8.8"}
    rig[2].routes[ARIN + "ip/8.8.8.8"] = lambda req: response(
        status=status, raw=raw, headers=headers
    )
    rig[2].routes[RIPE + "ip/8.8.8.8"] = network()
    result = run(rig)
    snapshots = [rig[3].snapshot(sid) for sid in result.attempts[0].snapshot_ids]
    receipts = [
        item for item in snapshots if item.received_body_sha256 == hashlib.sha256(raw).hexdigest()
    ]
    assert receipts and all(item.body == b"" for item in receipts)
    assert all(b"capture-sentinel" not in item.body for item in snapshots)
    target = tmp_path / "safe-export"
    EvidenceRenderer(rig[3]).export(result.result_id, target)
    assert not any(
        b"capture-sentinel" in path.read_bytes() for path in target.rglob("*") if path.is_file()
    )
    assert verify_export(target)["valid"]


def test_wrong_network_json_is_not_retained(rig):
    raw = json.dumps(network(startAddress="9.0.0.0", endAddress="9.255.255.255")).encode()
    rig[2].routes[ARIN + "ip/8.8.8.8"] = lambda req: response(raw=raw)
    result = run(rig)
    assert result.status == "incomplete"
    snapshot = rig[3].snapshot(result.attempts[0].snapshot_ids[-1])
    assert snapshot.body == b"" and snapshot.body_retention == "rejected_response"
    assert snapshot.received_body_sha256 == hashlib.sha256(raw).hexdigest()


def test_export_omits_legacy_html_without_mutating_historical_snapshot(rig, tmp_path):
    from attribution.models import json_bytes

    raw = b"<html><script>legacy-capture-sentinel</script></html>"
    rig[2].routes[ARIN + "ip/8.8.8.8"] = lambda req: response(
        raw=raw, headers={"content-type": "text/html"}
    )
    result = run(rig)
    receipt = rig[3].snapshot(result.attempts[0].snapshot_ids[-1])
    legacy = replace(
        receipt,
        body=raw,
        body_sha256=hashlib.sha256(raw).hexdigest(),
        body_retention="original",
        received_body_sha256="",
        received_body_size=None,
    )
    with rig[3]._db:
        rig[3]._db.execute(
            "UPDATE snapshots SET metadata=?,body=? WHERE id=?",
            (json_bytes(legacy.metadata()).decode(), raw, legacy.snapshot_id),
        )
    target = tmp_path / "legacy-export"
    EvidenceRenderer(rig[3]).export(result.result_id, target)
    assert not any(
        b"legacy-capture-sentinel" in path.read_bytes()
        for path in target.rglob("*")
        if path.is_file()
    )
    meta = next(
        item
        for item in json.loads((target / "responses.json").read_text(encoding="utf-8"))
        if item["snapshot_id"] == legacy.snapshot_id
    )
    assert meta["body_retention"] == "legacy_unvalidated_response" and meta["body_file"] is None
    assert meta["received_body_sha256"] == legacy.body_sha256
    assert rig[3].snapshot(legacy.snapshot_id) == legacy
    assert verify_export(target)["valid"]


def test_no_store_prevents_reuse_but_evidence_is_retained(rig):
    rig[2].routes[ARIN + "ip/8.8.8.8"] = lambda req: response(
        network(), headers={"cache-control": "no-store"}
    )
    a, b = run(rig), run(rig)
    assert a.evidence[0].snapshot_id != b.evidence[0].snapshot_id
    assert rig[3].snapshot(a.evidence[0].snapshot_id)


def test_missing_or_mismatched_entity_is_incomplete(rig):
    rig[2].routes[ARIN + "ip/8.8.8.8"] = network(
        entities=[{"handle": "A", "links": [{"rel": "self", "href": ARIN + "entity/A"}]}]
    )
    rig[2].routes[ARIN + "entity/A"] = lambda req: response(status=404)
    assert run(rig).status == "incomplete"
    rig[2].routes[ARIN + "entity/A"] = entity(handle="UNRELATED")
    assert run(rig, refresh=True).status == "incomplete"


def test_retry_after_date_and_cache_headers():
    future = format_datetime(datetime.fromtimestamp(time.time() + 120, timezone.utc), usegmt=True)
    assert 115 < retry_delay(future) <= 120
    assert retry_delay("NaN") == 30
    assert retry_delay("-1") == 0
    assert response_ttl({"cache-control": 'max-age="300"', "age": "10"}, 86400) == 290
    assert response_ttl({"cache-control": "no-cache"}, 86400) == 0


def test_persistent_cache_across_module_instances(rig):
    rig[2].routes[ARIN + "ip/8.8.8.8"] = network()
    first = run(rig)
    with EvidenceStore(rig[3].path) as store:

        def forbidden(req):
            raise AssertionError("Offline mode made a request")

        provider = RdapProvider(
            store, Settings(interval=0), transport=httpx.MockTransport(forbidden)
        )
        module = AttributionModule(store, providers=[provider])
        result = module.attribute("example.com", [CandidateIP("new-row", "8.8.8.8")], offline=True)
        provider.close()
    assert (
        result.status == "matched"
        and result.evidence[0].retrieved_at == first.evidence[0].retrieved_at
    )


def test_export_and_integrity_check(rig, tmp_path):
    rig[2].routes[ARIN + "ip/8.8.8.8"] = network(name='<script>alert("example.com")</script>')
    result = run(rig)
    target = tmp_path / "export"
    html = EvidenceRenderer(rig[3]).export(result.result_id, target).read_text(encoding="utf-8")
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert verify_export(target)["valid"]
    with pytest.raises(ValueError):
        EvidenceRenderer(rig[3]).export(result.result_id, target)
    (target / "attribution.json").write_text("modified")
    assert not verify_export(target)["valid"]


def test_export_manifest_cannot_read_outside_directory(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"files": {"../other": "abc"}}))
    with pytest.raises(ValueError):
        verify_export(tmp_path)


def test_cli_offline_result_and_saved_export(rig, tmp_path, capsys):
    rig[2].routes[ARIN + "ip/8.8.8.8"] = network()
    run(rig)
    output = tmp_path / "cli-export"
    assert (
        main(
            [
                "check",
                "example.com",
                "8.8.8.8",
                "--offline",
                "--db",
                rig[3].path,
                "--export",
                str(output),
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "matched" and payload["evidence"][0]["from_cache"]
    assert main(["verify", str(output)]) == 0
    assert json.loads(capsys.readouterr().out)["valid"]


def test_policy_rejects_wrong_ip_from_provider(rig):
    rig[2].routes[ARIN + "ip/8.8.8.8"] = network()
    good = rig[1].collect("8.8.8.8", "example.com")

    class BrokenProvider:
        name = "rdap"

        def collect(self, *args, **kwargs):
            return replace(good, evidence=replace(good.evidence, ip="8.8.4.4"))

    module = AttributionModule(rig[3], providers=[BrokenProvider()])
    result = module.attribute("example.com", [CandidateIP("row", "8.8.8.8")])
    assert result.status == "incomplete" and result.attempts[0].reason == "policy_rejected"


def test_tampered_saved_body_is_detected(rig, tmp_path):
    rig[2].routes[ARIN + "ip/8.8.8.8"] = network()
    result = run(rig)
    with rig[3]._db:
        rig[3]._db.execute(
            "UPDATE snapshots SET body=? WHERE id=?", (b"{}", result.evidence[0].snapshot_id)
        )
    with pytest.raises(ValueError, match="integrity"):
        EvidenceRenderer(rig[3]).export(result.result_id, tmp_path / "tampered-export")


def test_provider_extension_requires_explicit_acceptance(rig):
    rig[2].routes[ARIN + "ip/8.8.8.8"] = network()
    good = rig[1].collect("8.8.8.8", "example.com")

    class NewProvider:
        name = "test_provider"

        def describe(self):
            return {"version": "test-1"}

        def collect(self, *args, **kwargs):
            return replace(
                good,
                evidence=replace(
                    good.evidence, method=self.name, source_name="Test source", details={}
                ),
            )

    module = AttributionModule(rig[3], providers=[NewProvider()])
    assert module.attribute("example.com", [CandidateIP("row", "8.8.8.8")]).status == "incomplete"
    module = AttributionModule(
        rig[3], providers=[NewProvider()], policy=RootDomainPolicy(("test_provider",))
    )
    result = module.attribute("example.com", [CandidateIP("row", "8.8.8.8")])
    assert result.status == "matched" and result.evidence[0].details == {}
    assert result.settings["providers"]["test_provider"]["version"] == "test-1"


def test_expired_cache_requires_network_but_saved_export_still_works(rig, tmp_path):
    rig[2].routes[ARIN + "ip/8.8.8.8"] = network()
    first = run(rig)
    with rig[3]._db:
        rig[3]._db.execute("UPDATE cache SET expires=0")
    assert run(rig, offline=True).status == "deferred"
    target = tmp_path / "historic"
    EvidenceRenderer(rig[3]).export(first.result_id, target)
    assert verify_export(target)["valid"] and len(rig[2].calls) == 2


def test_html_gateway_404_is_incomplete(rig):
    rig[2].routes[ARIN + "ip/8.8.8.8"] = lambda req: response(
        status=404, raw=b"<h1>Gateway route missing</h1>", headers={"content-type": "text/html"}
    )
    assert run(rig).status == "incomplete"


def test_service_retry_then_success(rig, monkeypatch):
    rig[1].client.settings = replace(rig[1].client.settings, retries=1)
    monkeypatch.setattr("attribution.http.time.sleep", lambda delay: None)
    hits = 0

    def transient(request):
        nonlocal hits
        hits += 1
        return response(status=503) if hits == 1 else response(network())

    rig[2].routes[ARIN + "ip/8.8.8.8"] = transient
    result = run(rig)
    assert result.status == "matched" and hits == 2
    assert len(result.attempts[0].snapshot_ids) == 3


def test_history_recovers_saved_result_id(rig, capsys):
    rig[2].routes[ARIN + "ip/8.8.8.8"] = network()
    result = run(rig)
    assert main(["history", "--db", rig[3].path]) == 0
    assert json.loads(capsys.readouterr().out)[0]["result_id"] == result.result_id
