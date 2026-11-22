"""One real registration proof covers related rows without changing source data."""

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
import sqlite3
from types import SimpleNamespace

import httpx
import pytest
from attribution import AttributionModule, EvidenceStore, RdapProvider, Settings

from modules.accretion.components.intake.records import (
    SourceObservation,
    CandidateObservation,
    CandidateGroup,
)
from modules.attribution.components.attribution_bridge import RegistrationAttribution
from modules.attribution.components.attribution_reuse import reuse_attribution, reusable_proof


def group(*addresses, root="example.com"):
    return CandidateGroup(
        root,
        [
            CandidateObservation(
                SourceObservation(
                    "scan.csv", "CSV", index + 1, {"hostname": "login." + root, "ip": ip}
                ),
                ip,
                False,
            )
            for index, ip in enumerate(addresses)
        ],
    )


@pytest.fixture
def bridge(tmp_path):
    calls = []

    def server(request):
        calls.append(str(request.url))
        if request.url.host == "data.iana.org":
            record = {"services": [[["0.0.0.0/0"], ["https://rdap.arin.net/registry/"]]]}
        else:
            ip = request.url.path.rsplit("/", 1)[-1]
            record = {
                "objectClassName": "ip network",
                "startAddress": ip,
                "endAddress": ip,
                "entities": [
                    {
                        "objectClassName": "entity",
                        "handle": "EXAMPLE",
                        "roles": ["registrant"],
                        "vcardArray": ["vcard", [["email", {}, "text", "admin@example.com"]]],
                    }
                ],
            }
        return httpx.Response(
            200,
            headers={"content-type": "application/rdap+json"},
            stream=httpx.ByteStream(json.dumps(record).encode()),
        )

    with EvidenceStore(tmp_path / "attribution.sqlite3") as evidence:
        provider = RdapProvider(
            evidence, Settings(interval=0, retries=0), transport=httpx.MockTransport(server)
        )
        adapter = object.__new__(RegistrationAttribution)
        adapter.module = AttributionModule(evidence, providers=[provider])
        try:
            yield adapter, calls
        finally:
            provider.close()


def test_first_match_covers_group_without_reordering_or_fabricating_rows(bridge):
    adapter, calls = bridge
    sources = group("8.8.8.8", "8.8.4.4")
    original = asdict(sources)
    decision = adapter.qualify(sources)
    assert decision.status == "qualified"
    assert decision.proof["ip"] == "8.8.8.8"
    assert asdict(sources) == original
    assert [row["ip"] for row in decision.coverage] == ["8.8.8.8", "8.8.4.4"]
    assert [row["relationship"] for row in decision.coverage] == [
        "matched_address",
        "shared_root_domain",
    ]
    assert decision.coverage[1]["source"]["row"] == 2
    assert not any(url.endswith("/8.8.4.4") for url in calls)
    assert not hasattr(adapter, "result_id")


def test_saved_proof_covers_a_changed_address_without_enumerating_approvals(bridge):
    adapter, calls = bridge
    first = adapter.qualify(group("8.8.8.8"))
    original = deepcopy(first.proof)
    calls.clear()
    # A valid saved automatic proof needs no workspace approval query.
    workspace = SimpleNamespace()
    changed = group("8.8.4.4")
    decision = reuse_attribution(
        workspace, changed, adapter.module.store, entity_id="entity", saved_proof=first.proof
    )
    assert decision.proof["ip"] == "8.8.8.8"
    assert decision.coverage[0]["ip"] == "8.8.4.4"
    assert decision.coverage[0]["proof_result_id"] == first.result_id
    assert decision.coverage[0]["relationship"] == "shared_root_domain"
    assert first.proof == original
    assert calls == []


@pytest.mark.parametrize(
    "field", ["record", "ip", "attribution", "policy", "evaluated_at", "body_sha256"]
)
def test_embedded_proof_tampering_is_rejected_against_immutable_store(bridge, field):
    adapter, _ = bridge
    proof = deepcopy(adapter.qualify(group("8.8.8.8")).proof)
    proof[field] = {"untrusted": "value"} if isinstance(proof[field], dict) else "changed"
    assert not reusable_proof(
        SimpleNamespace(), proof, "example.com", adapter.module.store, "entity"
    )


def test_stale_proof_and_explicit_refresh_require_fresh_attribution(bridge):
    adapter, _ = bridge
    sources = group("8.8.8.8")
    proof = adapter.qualify(sources).proof
    assert not reusable_proof(
        SimpleNamespace(),
        proof,
        sources.root_domain,
        adapter.module.store,
        "entity",
        clock=datetime.now(timezone.utc) + timedelta(days=8),
    )
    assert (
        reuse_attribution(
            SimpleNamespace(),
            sources,
            adapter.module.store,
            entity_id="entity",
            saved_proof=proof,
            refresh=True,
        )
        is None
    )


def test_missing_legacy_result_is_not_a_reusable_proof(bridge):
    adapter, _ = bridge
    proof = adapter.qualify(group("8.8.8.8")).proof
    del proof["result_id"]
    assert not reusable_proof(
        SimpleNamespace(), proof, "example.com", adapter.module.store, "entity"
    )


def test_bulk_coverage_validation_is_linear_and_rejects_scope_tampering(bridge, monkeypatch):
    from modules.attribution.components import attribution_bridge as owner

    adapter, _ = bridge
    sources = group(*(["8.8.8.8"] * 256))
    decision = adapter.qualify(sources)
    proof = {**decision.proof, "coverage": list(decision.coverage)}
    entries = [asdict(entry) for entry in sources.observations]
    calls = []
    normalize = owner.domain_identity

    def counted(value):
        calls.append(value)
        return normalize(value)

    monkeypatch.setattr(owner, "domain_identity", counted)
    assert owner.coverage_covers(entries, proof)
    assert len(calls) <= 2 * len(entries) + 2
    altered = deepcopy(entries)
    altered[-1]["source"]["row"] = 999
    assert not owner.coverage_covers(altered, proof)
    broken = deepcopy(proof)
    broken["coverage"][-1]["proof_ip"] = "9.9.9.9"
    assert not owner.coverage_covers(entries, broken)


def test_actual_recorded_review_is_required_for_manual_reuse(bridge):
    adapter, _ = bridge
    evidence = adapter.module.store
    # Build a legitimate partial through the same RDAP matcher; do not turn a
    # matched result into a review by editing stored result bytes.
    provider = adapter.module.providers[0]
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "application/rdap+json"},
            stream=httpx.ByteStream(
                json.dumps(
                    {
                        "objectClassName": "ip network",
                        "startAddress": "8.8.8.8",
                        "endAddress": "8.8.8.8",
                        "entities": [
                            {
                                "objectClassName": "entity",
                                "handle": "EXAMPLE",
                                "roles": ["registrant"],
                                "vcardArray": [
                                    "vcard",
                                    [["fn", {}, "text", "Example Organization"]],
                                ],
                            }
                        ],
                    }
                ).encode()
            ),
        )
    )
    adapter.qualify(group("8.8.8.8"))  # retain the legitimate IANA bootstrap
    provider.client.client.close()
    provider.client.client = httpx.Client(transport=transport)
    decision = adapter.qualify(group("8.8.8.8"), refresh=True)
    result = evidence.result(decision.result_id)
    assert result["status"] == "review"
    from modules.attribution.components.attribution_bridge import attribution_record

    review = {
        "id": "review",
        "result_id": decision.result_id,
        "evidence_index": 0,
        "decision": "accept",
        "reviewer": "analyst",
        "note": "Checked",
        "reviewed_at": result["evaluated_at"],
    }
    proof = attribution_record(
        evidence,
        decision.result_id,
        "example.com",
        result["policy"],
        result["partial_evidence"][0],
        review=review,
    )
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(
        "CREATE TABLE leads(id TEXT, merged_into TEXT); CREATE TABLE jobs(id TEXT, domain TEXT, payload TEXT); "
        "CREATE TABLE attribution_reviews(id TEXT,job_id TEXT,lead_id TEXT,result_id TEXT,evidence_index INTEGER,decision TEXT,reviewer TEXT,note TEXT,reviewed_at TEXT);"
    )
    db.execute("INSERT INTO leads VALUES('entity',NULL)")
    db.execute("INSERT INTO jobs VALUES('job','example.com',?)", (json.dumps([{"ip": "8.8.8.8"}]),))
    db.execute(
        "INSERT INTO attribution_reviews VALUES(?,?,?,?,?,?,?,?,?)",
        (
            "review",
            "job",
            "entity",
            *[
                review[k]
                for k in (
                    "result_id",
                    "evidence_index",
                    "decision",
                    "reviewer",
                    "note",
                    "reviewed_at",
                )
            ],
        ),
    )

    @contextmanager
    def read_snapshot():
        yield db

    workspace = SimpleNamespace(read_snapshot=read_snapshot)
    assert reusable_proof(workspace, proof, "example.com", evidence, "entity")
    db.execute("DELETE FROM attribution_reviews")
    assert not reusable_proof(workspace, proof, "example.com", evidence, "entity")
    db.close()
