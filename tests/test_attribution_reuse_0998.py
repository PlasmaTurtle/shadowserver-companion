"""Analyst-approved identities survive reverse-date imports and changing rows.

All approvals below go through the production RDAP partial-match evaluator and
IntakeService.review_group. Only HTTP transport is replaced; no test inserts an
approved entity or fabricates an accepted attribution proof.
"""

from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import httpx
import pytest

from attribution import AttributionModule, EvidenceStore, RdapProvider, Settings
from attribution.public_dns import DualPublicDnsProvider
from test_workbench import csv_bytes
from workbench.intake_service import IntakeService
from workbench.store import Store


ROOTS = (
    "towerco.com",
    "yadtel.com",
    "wilkes.net",
    "centurylink.net",
    "lyme.net",
    "dc74.net",
    "totaluptime.net",
)


@pytest.fixture
def approval_pipeline(tmp_path, monkeypatch):
    import workbench.attribution_bridge as bridge

    state = SimpleNamespace(
        root="towerco.com",
        handle="APPROVED-ORG",
        name=None,
        calls=[],
        dns=False,
    )

    def server(request):
        url = str(request.url)
        state.calls.append(url)
        if request.url.host in ("dns.google", "cloudflare-dns.com"):
            name, kind = request.url.params["name"], request.url.params["type"]
            number = {"A": 1, "AAAA": 28, "PTR": 12}[kind]
            values = ["8.8.8.8"] if kind == "A" else []
            record = {
                "Status": 0,
                "TC": False,
                "RD": True,
                "RA": True,
                "AD": False,
                "CD": False,
                "Question": [{"name": name, "type": number}],
                "Answer": [
                    {"name": name, "type": number, "TTL": 300, "data": value} for value in values
                ],
            }
            return httpx.Response(
                200,
                headers={"content-type": "application/dns-json"},
                stream=httpx.ByteStream(json.dumps(record).encode()),
            )
        if "data.iana.org" in url:
            record = {
                "services": [
                    [["8.8.8.8/32", "8.8.4.4/32"], ["https://rdap.arin.net/registry/"]],
                    [["1.1.1.1/32"], ["https://rdap.db.ripe.net/"]],
                ]
            }
        else:
            ip = url.rsplit("/", 1)[-1]
            record = {
                "objectClassName": "ip network",
                "handle": "NETWORK-" + ip,
                "startAddress": ip,
                "endAddress": ip,
                "entities": [
                    {
                        "objectClassName": "entity",
                        "handle": state.handle,
                        "roles": ["registrant"],
                        "vcardArray": [
                            "vcard",
                            [
                                ["kind", {}, "text", "org"],
                                [
                                    "fn",
                                    {},
                                    "text",
                                    state.name or state.root.split(".")[0] + " Communications",
                                ],
                            ],
                        ],
                    }
                ],
            }
        return httpx.Response(
            200,
            headers={"content-type": "application/rdap+json"},
            stream=httpx.ByteStream(json.dumps(record).encode()),
        )

    def open_module(path, settings):
        evidence = EvidenceStore(path)
        provider = RdapProvider(
            evidence, Settings(interval=0, retries=0), transport=httpx.MockTransport(server)
        )
        providers = [provider]
        if state.dns:
            providers.append(
                DualPublicDnsProvider(
                    evidence, Settings(interval=0, retries=0), transport=httpx.MockTransport(server)
                )
            )
        module = AttributionModule(evidence, providers=providers)
        module._owns_store = True
        module._owned = providers
        return module

    monkeypatch.setattr(bridge.AttributionModule, "open", open_module)
    store = Store(tmp_path / "workspace")
    intake = IntakeService(store)

    def ingest(day, *, root=None, ports=("443",), ip="8.8.8.8"):
        root = root or state.root
        rows = [
            {
                "report_type": "scan_http_vulnerable",
                "hostname": "remote." + root,
                "ip": ip,
                "tag": "eol-php",
                "component_version": "7.3.25",
                "version": "",
                "severity": "critical",
                "http_code": "200",
                "region": "North Carolina",
                "city": "Charlotte",
                "geo": "US",
                "timestamp": f"2026-11-{day:02d} 01:02:03",
                "protocol": "tcp",
                "port": port,
            }
            for port in ports
        ]
        imported = intake.enqueue(f"scan_http_vulnerable_{day}_{root}.csv", csv_bytes(rows))
        intake.process(imported["id"])
        saved = store.one("SELECT * FROM imports WHERE id=?", (imported["id"],))
        assert saved["status"] == "done", saved["error"]
        job = store.one("SELECT * FROM jobs WHERE import_id=?", (imported["id"],))
        assert job, "Fixture must reach attribution rather than being filtered out"
        return job

    def approve(job):
        assert job["status"] == "review"
        with EvidenceStore(store.root / "attribution.sqlite3") as evidence:
            result = evidence.result(job["attribution_result_id"])
        assert result["status"] == "review" and not result["evidence"]
        assert result["partial_evidence"][0]["method"] == "rdap_keyword"
        accepted = intake.review_group(
            job["id"], job["attribution_result_id"], 0, "accept", "Verified registrant identity"
        )
        proof = json.loads(
            store.one(
                "SELECT attribution FROM domain_groups WHERE root_domain=?", (job["domain"],)
            )["attribution"]
        )
        assert proof["review"]["decision"] == "accept"
        return accepted["lead_id"], proof

    return SimpleNamespace(store=store, intake=intake, state=state, ingest=ingest, approve=approve)


@pytest.mark.parametrize("root", ROOTS)
def test_manual_approval_reused_for_nov12_then_nov11_and_nov10(approval_pipeline, root):
    p = approval_pipeline
    p.state.root = root
    entity_id, original = p.approve(p.ingest(12))
    p.state.calls.clear()

    for day in (11, 10):
        job = p.ingest(day)
        assert job["status"] == "qualified", job["attempts"]
        queued = p.store.one("SELECT * FROM lead_queue WHERE import_id=?", (job["import_id"],))
        assert queued["entity_id"] == entity_id and queued["qualified"] == 1

    assert p.state.calls == []
    assert p.store.one("SELECT count(*) n FROM attribution_reviews")["n"] == 1
    assert p.store.one("SELECT count(*) n FROM leads")["n"] == 1
    assert p.store.one("SELECT count(*) n FROM awareness_findings WHERE admitted=1")["n"] == 1
    assert p.store.one("SELECT count(*) n FROM awareness_observations WHERE admitted=1")["n"] == 3
    saved = json.loads(p.store.one("SELECT attribution FROM domain_groups")["attribution"])
    assert saved["retrieved_at"] == original["retrieved_at"]
    assert saved["evaluated_at"] == original["evaluated_at"]
    assert saved["review"] == original["review"]


def test_older_subset_reuses_approval_without_current_group_anchor(approval_pipeline):
    p = approval_pipeline
    entity_id, original = p.approve(p.ingest(12, ports=("443", "8443")))
    p.state.calls.clear()
    job = p.ingest(11, ports=("8443",))

    assert job["status"] == "qualified", "Already admitted hostname/IP/port needs no second review"
    assert (
        p.store.one("SELECT entity_id FROM lead_queue WHERE import_id=?", (job["import_id"],))[
            "entity_id"
        ]
        == entity_id
    )
    assert p.store.one("SELECT count(*) n FROM attribution_reviews")["n"] == 1
    assert p.state.calls == []
    with EvidenceStore(p.store.root / "attribution.sqlite3") as evidence:
        result = evidence.result(original["result_id"])
    assert result["partial_evidence"][0]["ip"] == original["ip"]
    assert result["evaluated_at"] == original["evaluated_at"]


@pytest.mark.parametrize("port", ["443", "8443"])
def test_elapsed_week_does_not_erase_approved_identity(approval_pipeline, monkeypatch, port):
    import workbench.intake_reuse as reuse

    p = approval_pipeline
    entity_id, original = p.approve(p.ingest(12))
    future = datetime.now(timezone.utc) + timedelta(days=8)

    class FutureDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return future if tz else future.replace(tzinfo=None)

    monkeypatch.setattr(reuse, "datetime", FutureDateTime)
    job = p.ingest(11, ports=(port,))
    assert job["status"] == "qualified", "Service freshness and identity approval are separate"
    assert (
        p.store.one("SELECT entity_id FROM lead_queue WHERE import_id=?", (job["import_id"],))[
            "entity_id"
        ]
        == entity_id
    )
    with EvidenceStore(p.store.root / "attribution.sqlite3") as evidence:
        result = evidence.result(original["result_id"])
    assert result["evaluated_at"] == original["evaluated_at"]


def test_new_endpoint_reuses_same_registrant_approval_with_its_own_evidence(approval_pipeline):
    p = approval_pipeline
    entity_id, original = p.approve(p.ingest(12))
    p.state.calls.clear()
    job = p.ingest(11, ip="8.8.4.4")

    assert job["status"] == "qualified", "The same registry registrant was already approved"
    assert any(url.endswith("/ip/8.8.4.4") for url in p.state.calls)
    assert job["attribution_result_id"] != original["result_id"]
    assert (
        p.store.one("SELECT entity_id FROM lead_queue WHERE import_id=?", (job["import_id"],))[
            "entity_id"
        ]
        == entity_id
    )
    with EvidenceStore(p.store.root / "attribution.sqlite3") as evidence:
        old = evidence.result(original["result_id"])
        current = evidence.result(job["attribution_result_id"])
    assert old["partial_evidence"][0]["ip"] == "8.8.8.8"
    assert current["partial_evidence"][0]["ip"] == "8.8.4.4"
    assert current["partial_evidence"][0]["method"] == "rdap_keyword"
    assert current["partial_evidence"][0]["retrieved_at"] >= original["retrieved_at"]
    assert old["evaluated_at"] == original["evaluated_at"]


@pytest.mark.parametrize("change", ["registrant", "registry", "name"])
def test_new_endpoint_different_registrant_or_registry_still_requires_review(
    approval_pipeline, change
):
    p = approval_pipeline
    p.approve(p.ingest(12))
    if change == "registrant":
        p.state.handle = "OTHER-ORG"
    if change == "name":
        p.state.name = "Towerco Unrelated Holdings"
    ip = "1.1.1.1" if change == "registry" else "8.8.4.4"
    job = p.ingest(11, ip=ip)
    assert job["status"] == "review"
    assert (
        p.store.one("SELECT admitted FROM awareness_observations WHERE ip=?", (ip,))["admitted"]
        == 0
    )


def test_shared_ip_and_same_registrant_do_not_approve_another_root(approval_pipeline):
    p = approval_pipeline
    p.state.name = "Towerco Yadtel Communications"
    p.approve(p.ingest(12, root="towerco.com"))
    job = p.ingest(11, root="yadtel.com")
    assert job["status"] == "review"
    queued = p.store.one("SELECT * FROM lead_queue WHERE import_id=?", (job["import_id"],))
    assert queued["entity_id"] is None and queued["qualified"] == 0


def test_newer_dns_is_not_rewritten_as_proof_of_an_older_different_endpoint(approval_pipeline):
    p = approval_pipeline
    p.state.dns = True
    newest = p.ingest(12)
    assert newest["status"] == "qualified"
    with EvidenceStore(p.store.root / "attribution.sqlite3") as evidence:
        original = evidence.result(newest["attribution_result_id"])
    assert original["evidence"][0]["method"] == "dns"
    assert original["evidence"][0]["ip"] == "8.8.8.8"

    older = p.ingest(11, ip="8.8.4.4")
    assert older["status"] == "review"
    with EvidenceStore(p.store.root / "attribution.sqlite3") as evidence:
        retained = evidence.result(newest["attribution_result_id"])
        current = evidence.result(older["attribution_result_id"])
    assert retained == original
    assert current["evidence"] == []
    assert current["partial_evidence"][0]["ip"] == "8.8.4.4"
    assert (
        p.store.one("SELECT admitted FROM awareness_observations WHERE ip='8.8.4.4'")["admitted"]
        == 0
    )


def test_explicit_retry_does_not_override_requested_new_review(approval_pipeline):
    p = approval_pipeline
    waiting = p.ingest(11)
    assert waiting["status"] == "review"
    p.intake.retry_group(waiting["id"], waiting["attribution_result_id"])
    p.approve(p.ingest(12))

    p.intake.process(waiting["import_id"])
    refreshed = p.store.one("SELECT * FROM jobs WHERE id=?", (waiting["id"],))
    assert refreshed["status"] == "review"
    assert refreshed["attribution_result_id"] != waiting["attribution_result_id"]


def test_older_endpoint_can_recover_its_own_prior_approval_after_anchor_changes(approval_pipeline):
    p = approval_pipeline
    owner, first = p.approve(p.ingest(10))
    p.state.handle = "SECOND-APPROVED-ORG"
    second_owner, second = p.approve(p.ingest(12, ip="8.8.4.4"))
    assert second_owner == owner
    p.state.calls.clear()

    older = p.ingest(11)
    assert older["status"] == "qualified"
    assert older["attribution_result_id"] == first["result_id"]
    assert p.state.calls == []
    assert p.store.one("SELECT count(*) n FROM attribution_reviews")["n"] == 2
    saved = json.loads(p.store.one("SELECT attribution FROM domain_groups")["attribution"])
    assert saved["result_id"] == second["result_id"], (
        "Older import must not replace newest evidence"
    )


def test_case_only_root_spelling_reuses_one_entity_and_approval(approval_pipeline):
    p = approval_pipeline
    p.state.root = "TOWERCO.COM"
    owner, original = p.approve(p.ingest(12))
    p.state.calls.clear()
    job = p.ingest(11, root="towerco.com")

    assert job["status"] == "qualified"
    assert job["attribution_result_id"] == original["result_id"]
    assert (
        p.store.one("SELECT entity_id FROM lead_queue WHERE import_id=?", (job["import_id"],))[
            "entity_id"
        ]
        == owner
    )
    assert p.store.one("SELECT count(*) n FROM leads")["n"] == 1
    assert p.store.one("SELECT count(*) n FROM domain_groups")["n"] == 1
    assert p.state.calls == []
