"""Inherited analyst decisions retain their original scope and evidence in reports."""

from copy import deepcopy
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from attribution import EvidenceStore, verify_export
from attribution.models import (
    AttributionEvidence,
    AttributionResult,
    CandidateIP,
    DomainMatch,
    ResponseSnapshot,
    json_bytes,
)
from modules.attribution.tests.support.attribution_display import case_lead, entry
from modules.investigations.tests.support.attribution_exhibit import inputs
from modules.attribution.components.attribution_bridge import attribution_record
from modules.attribution.components.attribution_display import attribution_summaries
from modules.investigations.components.attribution_model import build_attribution_exhibit
from modules.investigations.components.report_drafts import attribution_summary
from modules.investigations.components.report_package import _package_attribution


ORIGINAL_REVIEW = "2026-11-12T10:00:00Z"
CURRENT_RETRIEVAL = "2026-11-13T11:00:00Z"
CURRENT_EVALUATION = "2026-11-13T11:01:00Z"


@pytest.fixture
def inherited(tmp_path):
    workspace = SimpleNamespace(root=tmp_path)
    proofs = []
    with EvidenceStore(tmp_path / "attribution.sqlite3") as store:
        for index, ip in enumerate(("8.8.8.8", "8.8.4.4")):
            retrieved = CURRENT_RETRIEVAL if index else "2026-11-12T09:00:00Z"
            evaluated = CURRENT_EVALUATION if index else "2026-11-12T09:01:00Z"
            url = "https://rdap.arin.net/registry/ip/" + ip
            raw = {
                "objectClassName": "ip network",
                "startAddress": ip,
                "endAddress": ip,
                "entities": [
                    {
                        "objectClassName": "entity",
                        "handle": "EXAMPLE-ORG",
                        "roles": ["registrant"],
                        "vcardArray": ["vcard", [["fn", {}, "text", "Example Organization"]]],
                    }
                ],
            }
            snapshot = replace(
                ResponseSnapshot.create(
                    url, url, 200, {"content-type": "application/rdap+json"}, json_bytes(raw)
                ),
                retrieved_at=retrieved,
            )
            evidence = AttributionEvidence(
                "rdap_keyword",
                ip,
                "ARIN",
                url,
                retrieved,
                snapshot.snapshot_id,
                (snapshot.snapshot_id,),
                DomainMatch(
                    "example.com",
                    "",
                    "/entities/0/vcardArray/1/0/3",
                    "Example Organization",
                    "EXAMPLE-ORG",
                    ("registrant",),
                    "entity_name",
                ),
                {
                    "entry_id": "0",
                    "network_start": ip,
                    "network_end": ip,
                    "matched_words": ["example"],
                },
            )
            result = AttributionResult(
                f"result-{index}",
                "example.com",
                "review",
                evaluated,
                (CandidateIP("0", ip, "remote.example.com"),),
                None,
                None,
                (),
                (),
                {"id": "test-policy", "version": "test-policy"},
                {},
                partial_evidence=(evidence,),
            )
            store.save_snapshot(snapshot)
            store.save_result(result)
            saved = store.result(result.result_id)
            review = (
                None
                if index
                else {
                    "id": "original-decision",
                    "result_id": result.result_id,
                    "evidence_index": 0,
                    "decision": "accept",
                    "reviewer": "Original Analyst",
                    "reviewed_at": ORIGINAL_REVIEW,
                    "note": "Confirmed registrant for domain.",
                }
            )
            proofs.append(
                attribution_record(
                    store,
                    result.result_id,
                    result.root_domain,
                    result.policy,
                    saved["partial_evidence"][0],
                    review=review,
                )
            )
    source, current = proofs
    current["review"] = deepcopy(source["review"])
    current["approval_reuse"] = {
        "basis": "Previously accepted domain-to-registrant association",
        "recognized_at": CURRENT_EVALUATION,
        **{
            "source_" + key: source[key]
            for key in ("result_id", "snapshot_id", "body_sha256", "ip")
        },
        "review_id": source["review"]["id"],
        "registrant_identity": {
            "authority": "https://rdap.arin.net/registry/",
            "handle": "EXAMPLE-ORG",
            "name": "example organization",
        },
        "source_proof": deepcopy(source),
    }
    return workspace, source, current


def exhibit(proof):
    parts = inputs("rdap_keyword", count=1)
    parts[2][0]["source"] = proof
    parts[0]["qualified_lead"]["validated_leads"][0]["entries"][0]["ip"] = proof["ip"]
    return build_attribution_exhibit(*parts)["items"][0]


def test_reused_approval_keeps_original_decision_and_current_evidence_times(inherited):
    workspace, source, proof = inherited
    before = deepcopy(proof)
    (card,) = attribution_summaries(workspace, case_lead(proof, [entry("support", proof["ip"])]))
    item = exhibit(proof)
    for projection in (card, item):
        assert projection["supported"] is True
        assert projection["validated_at"] == CURRENT_EVALUATION
        assert projection["validated_by"] == "Attribution Module"
        assert projection["retrieved_at"] == CURRENT_RETRIEVAL
    assert card["method"] == "registrant_approval_reuse"
    assert card["validation_kind"] == "automatic"
    assert card["details"]["prior_approval_at"] == ORIGINAL_REVIEW
    assert card["details"]["approval_source_result_id"] == source["result_id"]
    assert "no new analyst decision" in card["match_summary"]
    assert item["method_label"] == "Prior registrant approval reused"
    assert item["prior_approval_at"] == ORIGINAL_REVIEW
    assert "Original Analyst" in item["explanation"] and ORIGINAL_REVIEW in item["explanation"]
    draft = attribution_summary(proof)
    assert "Original approval: Original Analyst on " + ORIGINAL_REVIEW in draft
    assert "Current evidence evaluated: " + CURRENT_EVALUATION in draft
    assert proof == before


@pytest.mark.parametrize(
    "change", ["source_ip", "different_registrant", "missing_reuse", "missing_source"]
)
def test_invalid_inheritance_cannot_appear_as_a_new_analyst_approval(inherited, change):
    workspace, _, proof = inherited
    if change == "source_ip":
        proof["approval_reuse"]["source_ip"] = "1.1.1.1"
    elif change == "different_registrant":
        proof["record"]["entities"][0]["handle"] = "OTHER-ORG"
    elif change == "missing_reuse":
        del proof["approval_reuse"]
    else:
        del proof["approval_reuse"]["source_proof"]
    (card,) = attribution_summaries(workspace, case_lead(proof, [entry("support", proof["ip"])]))
    assert card["supported"] is False
    item = exhibit(proof)
    assert item["supported"] is False and item["review_required"] is True


def test_package_exports_both_results_with_decision_only_on_its_original_result(
    inherited, tmp_path
):
    workspace, source, proof = inherited
    before = deepcopy((source, proof))
    destination = tmp_path / "package"
    _package_attribution(workspace, [proof, source, proof], destination)
    registration = destination / "registration"
    assert sorted(path.name for path in registration.iterdir()) == ["result-0", "result-1"]
    for result_id in ("result-0", "result-1"):
        assert verify_export(registration / result_id)["valid"]
    decisions = json.loads(
        (registration / "result-0" / "analyst-reviews.json").read_text(encoding="utf-8")
    )
    assert decisions == [source["review"]]
    assert not (registration / "result-1" / "analyst-reviews.json").exists()
    assert (
        json.loads((registration / "result-1" / "attribution.json").read_text(encoding="utf-8"))[
            "status"
        ]
        == "review"
    )
    assert (source, proof) == before


def test_corrupt_original_approval_response_blocks_package(inherited, tmp_path):
    workspace, source, proof = inherited
    with EvidenceStore(workspace.root / "attribution.sqlite3") as store:
        with store._db:
            store._db.execute(
                "UPDATE snapshots SET body=? WHERE id=?", (b"{}", source["snapshot_id"])
            )
    destination = tmp_path / "package"
    with pytest.raises(ValueError, match="prior registrant approval failed"):
        _package_attribution(workspace, [proof], destination)
    assert not destination.exists()
