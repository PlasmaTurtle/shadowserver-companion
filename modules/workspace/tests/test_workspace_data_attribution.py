"""Restore must reject missing/corrupt evidence before replacing user records."""

import json
from contextlib import closing
import sqlite3

import pytest

from attribution import AttributionResult, EvidenceStore
from attribution.models import Attempt, ResponseSnapshot
from modules.workspace.components.store import Store
from modules.workspace.components.workspace_data_attribution import validate_attribution_data


@pytest.fixture
def restored(tmp_path):
    store = Store(tmp_path / "replacement")
    with store.transaction() as db:
        db.execute(
            """INSERT INTO imports(id,fingerprint,sha256,name,path,created_at,config)
            VALUES('import','fingerprint','digest','fixture.csv','originals/fixture.csv','now','{}')"""
        )
        db.execute(
            """INSERT INTO jobs(id,import_id,domain,payload,attribution_result_id)
            VALUES('job','import','example.com','{}','result')"""
        )
    return store


def retained_result(store, *, root="example.com", result_id="result", save_snapshot=True):
    response = ResponseSnapshot.create(
        "https://registry.example/ip/8.8.8.8",
        "https://registry.example/ip/8.8.8.8",
        200,
        {"content-type": "application/json"},
        b'{"objectClassName":"ip network","name":"Fixture"}',
    )
    result = AttributionResult(
        result_id=result_id,
        root_domain=root,
        status="no_match",
        evaluated_at="2026-11-08T00:00:00Z",
        candidates=(),
        matched_entry_id=None,
        matched_ip=None,
        evidence=(),
        attempts=(
            Attempt(
                "entry",
                "8.8.8.8",
                "rdap",
                "no_match",
                "fixture",
                snapshot_ids=(response.snapshot_id,),
            ),
        ),
        policy={"id": "fixture"},
        settings={},
    )
    with EvidenceStore(store.root / "attribution.sqlite3") as evidence:
        if save_snapshot:
            evidence.save_snapshot(response)
        evidence.save_result(result)
    return response, result


def retained_proof(store, proof):
    with store.transaction() as db:
        db.execute(
            """INSERT INTO leads(id,domain,created_at,updated_at,attribution,attribution_entry_id)
            VALUES('lead','example.com','now','now',?,'entry')""",
            (json.dumps(proof),),
        )
        db.execute(
            "INSERT INTO domain_groups VALUES('example.com','lead','entry',?)",
            (json.dumps(proof),),
        )
        db.execute("INSERT INTO hostnames VALUES('mail.example.com','example.com')")
        db.execute(
            """INSERT INTO entries(id,lead_id,payload,ip,hostname,tag,version,root_domain)
            VALUES('entry','lead','{}','8.8.8.8','mail.example.com','','','example.com')"""
        )


def test_empty_legacy_workspace_does_not_require_evidence_database(tmp_path):
    store = Store(tmp_path / "legacy")
    validate_attribution_data(store)
    assert not (store.root / "attribution.sqlite3").exists()


def test_legacy_embedded_proof_is_not_required_to_have_new_identifiers(tmp_path):
    store = Store(tmp_path / "legacy")
    retained_proof(store, {"registry": "Legacy registry", "record": {"contact": "example.com"}})
    validate_attribution_data(store)
    assert not (store.root / "attribution.sqlite3").exists()


def test_restore_requires_referenced_database(restored):
    with pytest.raises(ValueError, match="missing its referenced attribution database"):
        validate_attribution_data(restored)


def test_restore_checks_complete_lookup_and_preserves_captured_bytes(restored):
    response, result = retained_result(restored)
    validate_attribution_data(restored)
    with EvidenceStore(restored.root / "attribution.sqlite3") as evidence:
        assert evidence.snapshot(response.snapshot_id).body == response.body
        assert evidence.result(result.result_id) == json.loads(json.dumps(result.to_dict()))


@pytest.mark.parametrize("root,result_id", [("other.example", "result"), ("example.com", "other")])
def test_restore_rejects_missing_or_wrong_domain_result(restored, root, result_id):
    retained_result(restored, root=root, result_id=result_id)
    with pytest.raises(ValueError, match="missing or belongs to another domain"):
        validate_attribution_data(restored)


def test_restore_rejects_missing_attempt_response(restored):
    retained_result(restored, save_snapshot=False)
    with pytest.raises(ValueError, match="missing a referenced attribution response"):
        validate_attribution_data(restored)


def test_restore_rejects_corrupt_captured_body(restored):
    response, _ = retained_result(restored)
    with closing(sqlite3.connect(restored.root / "attribution.sqlite3")) as db:
        db.execute("UPDATE snapshots SET body=? WHERE id=?", (b"{}", response.snapshot_id))
        db.commit()
    with pytest.raises(ValueError, match="Evidence integrity check failed"):
        validate_attribution_data(restored)


def test_restore_checks_superseded_results_as_well_as_current(restored):
    retained_result(restored)
    retained_result(restored, result_id="older", save_snapshot=False)
    with pytest.raises(ValueError, match="missing a referenced attribution response"):
        validate_attribution_data(restored)


def test_restore_rejects_body_that_differs_from_case_recorded_digest(restored):
    response, _ = retained_result(restored)
    retained_proof(
        restored,
        {"result_id": "result", "snapshot_id": response.snapshot_id, "body_sha256": "0" * 64},
    )
    with pytest.raises(ValueError, match="differs from its recorded SHA-256"):
        validate_attribution_data(restored)
