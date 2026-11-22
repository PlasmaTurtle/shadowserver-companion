"""Demonstration evidence satisfies the real exhibit without bypassing checks."""

from copy import deepcopy
import socket

import pytest

from modules.investigations.components.attribution_model import _item
from modules.workspace.components.demo import (
    demonstration_attribution,
    retained_demonstration_attribution,
)


def item(proof):
    return _item(
        {"hostname": "example.test", "source": proof, "citation": 1},
        {},
        {"entries": [{"ip": "192.0.2.1", "source": {"fields": {"hostname": "mail.example.test"}}}]},
    )


def test_complete_demo_record_and_unvalidated_example_use_normal_policy(monkeypatch):
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail("Network request"))
    proof = demonstration_attribution("Synthetic Organization", "example.test", "192.0.2.1")
    display = item(proof)
    assert display["supported"] is True and display["review_required"] is False
    assert display["validated_by"] == "Demonstration evaluator (synthetic)"
    assert display["validated_at"]
    assert "Synthetic evidence" in proof["record"]["notice"]
    pending = demonstration_attribution(
        "Synthetic Organization", "example.test", "192.0.2.1", evaluated=False
    )
    assert item(pending)["review_required"] is True
    assert item(pending)["validated_at"] is None
    wrong = deepcopy(proof)
    wrong["record"]["startAddress"] = "192.0.2.2"
    wrong["record"]["endAddress"] = "192.0.2.2"
    assert item(wrong)["supported"] is False


@pytest.mark.parametrize("evaluated", [True, False])
def test_retained_demo_uses_real_evidence_references_and_restore_validation(
    tmp_path, monkeypatch, evaluated
):
    import json
    from dataclasses import asdict
    from attribution import EvidenceStore
    from modules.accretion.components.intake import (
        SourceObservation,
        CandidateObservation,
        CandidateGroup,
    )
    from modules.accretion.components.intake_service import IntakeService
    from modules.attribution.components.attribution_bridge import coverage_covers
    from modules.attribution.components.attribution_approval_evidence import checked_proof
    from modules.workspace.components.store import Store
    from modules.workspace.components.workspace_data_attribution import validate_attribution_data

    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail("Network request"))
    store = Store(tmp_path / "demo")
    group = CandidateGroup(
        "example.test",
        [
            CandidateObservation(
                SourceObservation(
                    "demo.csv", "CSV", index + 2, {"hostname": "mail.example.test", "ip": ip}
                ),
                ip,
                False,
            )
            for index, ip in enumerate(("8.8.8.8", "8.8.4.4"))
        ],
    )
    proof = retained_demonstration_attribution(
        store, group, "SYNTHETIC ORGANIZATION", evaluated=evaluated
    )
    assert proof["synthetic"] is True
    assert coverage_covers((asdict(entry) for entry in group.observations), proof)
    assert bool(proof["evaluated_at"]) is evaluated
    with EvidenceStore(store.root / "attribution.sqlite3") as evidence:
        assert checked_proof(proof, group.root_domain, evidence)
        result = evidence.result(proof["result_id"])
        assert result["settings"] == {"synthetic": True, "network_requests": 0}
        assert evidence.snapshot(proof["snapshot_id"]).record() == proof["record"]
    intake = IntakeService(store)
    imported = intake.enqueue("demo.csv", b"hostname,ip\nmail.example.test,8.8.8.8\n")
    with store.transaction() as db:
        db.execute(
            "INSERT INTO jobs(id,import_id,domain,payload,attribution_result_id) VALUES(?,?,?,?,?)",
            (
                "demo-job",
                imported["id"],
                group.root_domain,
                json.dumps([asdict(entry) for entry in group.observations]),
                proof["result_id"],
            ),
        )
    validate_attribution_data(store)
    with EvidenceStore(store.root / "attribution.sqlite3") as evidence:
        with evidence._db:
            evidence._db.execute("DELETE FROM results WHERE id=?", (proof["result_id"],))
    with pytest.raises(ValueError, match="missing or belongs"):
        validate_attribution_data(store)
