"""A saved analyst decision transfers only to the same authoritative registrant."""

from contextlib import closing
from copy import deepcopy
import io
import json
import subprocess
import sys
from zipfile import ZipFile

import httpx
import pytest

from attribution import AttributionModule, CandidateIP, EvidenceStore, RdapProvider, Settings
from workbench.attribution_approval import (
    approved_proofs,
    reusable_review,
    snapshot_approval_matches,
    valid_approval_reuse,
)
from workbench.intake import EntryValidator, UnvalidatedEntry, ValidatedLeads
from workbench.intake_service import IntakeService
from workbench.store import Store
from test_workbench import csv_bytes, observations


def test_evidence_validation_does_not_import_intake_or_workflow_services():
    subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
import workbench.attribution_approval_evidence
for name in ('workbench.attribution_approval', 'workbench.lead_queue',
             'workbench.intake_service', 'workbench.cases', 'workbench.store'):
    assert name not in sys.modules, name
""",
        ],
        check=True,
    )


@pytest.fixture
def approval(tmp_path, monkeypatch):
    import workbench.attribution_bridge as bridge

    store = Store(tmp_path / "data")
    state = {
        "name": "Example Medical Center",
        "handle": "EXAMPLE-REGISTRANT",
        "roles": ["registrant"],
        "base": "https://rdap.arin.net/registry/",
    }

    def server(request):
        url = str(request.url)
        if "data.iana.org" in url:
            record = {"services": [[["0.0.0.0/0"], [state["base"]]]]}
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
                        "handle": state["handle"],
                        "roles": state["roles"],
                        "vcardArray": ["vcard", [["fn", {}, "text", state["name"]]]],
                    }
                ],
            }
        return httpx.Response(
            200,
            headers={"content-type": "application/rdap+json"},
            stream=httpx.ByteStream(json.dumps(record).encode()),
        )

    def open_module(path, settings=None):
        evidence_store = EvidenceStore(path)
        provider = RdapProvider(
            evidence_store,
            Settings(interval=0, retries=0),
            transport=httpx.MockTransport(server),
        )
        module = AttributionModule(evidence_store, providers=[provider])
        module._owns_store = True
        module._owned = [provider]
        return module

    monkeypatch.setattr(bridge.AttributionModule, "open", open_module)
    intake = IntakeService(store)
    fields = {**observations()[0], "ip": "8.8.8.8", "timestamp": "2026-11-12 10:00:00"}
    imported = intake.enqueue("scan_http_vulnerable.csv", csv_bytes([fields]))
    intake.process(imported["id"])
    job = store.one("SELECT * FROM jobs WHERE import_id=?", (imported["id"],))
    assert job["status"] == "review"
    decision = intake.review_group(job["id"], job["attribution_result_id"], 0, "accept")
    with open_module(store.root / "attribution.sqlite3") as module:
        yield store, state, module, decision, fields


def target(approval, *, root="example.com", ip="8.8.4.4"):
    store, state, module, decision, fields = approval
    entry = EntryValidator({"North Carolina"}).validate_entry(
        UnvalidatedEntry(
            "older.csv",
            "CSV",
            1,
            {
                **fields,
                "hostname": "mail." + root,
                "ip": ip,
                "timestamp": "2026-11-11 10:00:00",
            },
        )
    )
    group = ValidatedLeads(root, [entry])
    result = module.attribute(root, [CandidateIP("0", ip, "mail." + root)], refresh=True)
    return group, result.result_id


def test_new_endpoint_uses_original_domain_registrant_decision_and_its_own_evidence(approval):
    store, state, module, decision, _ = approval
    group, result_id = target(approval)
    proof, anchor = reusable_review(store, group, module.store, result_id)
    assert anchor == 0
    assert proof["ip"] == "8.8.4.4"
    assert proof["result_id"] == result_id
    assert proof["review"] == decision["review"]
    assert proof["review"]["result_id"] != result_id
    reuse = proof["approval_reuse"]
    assert reuse["source_ip"] == "8.8.8.8"
    assert reuse["source_result_id"] == decision["review"]["result_id"]
    assert reuse["source_snapshot_id"] != proof["snapshot_id"]
    assert snapshot_approval_matches(proof, "example.com")
    assert valid_approval_reuse(proof, "example.com", module.store)
    assert len(store.all("SELECT * FROM attribution_reviews")) == 1
    assert module.store.result(result_id)["status"] == "review"


@pytest.mark.parametrize(
    "change",
    [
        {"handle": "DIFFERENT-REGISTRANT"},
        {"name": "Example Completely Different Business"},
        {"roles": ["technical"]},
        {"handle": ""},
    ],
)
def test_same_name_or_handle_alone_does_not_inherit_approval(approval, change):
    store, state, module, _, _ = approval
    state.update(change)
    group, result_id = target(approval)
    assert reusable_review(store, group, module.store, result_id) is None


def test_identical_registrant_at_another_registry_namespace_is_not_reused(approval):
    store, state, module, _, _ = approval
    state["base"] = "https://rdap.arin.net/other-registry/"
    # Clear only the mocked bootstrap cache so the next fixture exposes the new
    # namespace. Production helper never performs a request or alters a cache.
    with module.store._db:
        module.store._db.execute("DELETE FROM cache")
    group, result_id = target(approval)
    assert reusable_review(store, group, module.store, result_id) is None


def test_another_domain_on_same_ip_does_not_inherit_approval(approval):
    store, state, module, _, _ = approval
    group, result_id = target(approval, root="example.net", ip="8.8.8.8")
    assert reusable_review(store, group, module.store, result_id) is None


def test_source_approval_must_exist_and_belong_to_current_entity(approval):
    store, state, module, decision, _ = approval
    assert len(list(approved_proofs(store, "example.com", module.store, decision["lead_id"]))) == 1
    assert not list(approved_proofs(store, "other.net", module.store, decision["lead_id"]))
    assert not list(approved_proofs(store, "example.com", module.store, "unrelated"))
    group, result_id = target(approval)
    with store.transaction() as db:
        db.execute("DELETE FROM attribution_reviews")
    assert reusable_review(store, group, module.store, result_id) is None


def test_legacy_compacted_job_uses_original_immutable_candidate(approval):
    store, state, module, decision, _ = approval
    with store.transaction() as db:
        db.execute("UPDATE jobs SET payload='[]'")
    proofs = list(approved_proofs(store, "example.com", module.store, decision["lead_id"]))
    assert len(proofs) == 1
    assert proofs[0]["ip"] == "8.8.8.8"
    assert proofs[0]["review"] == decision["review"]
    group, result_id = target(approval)
    assert reusable_review(store, group, module.store, result_id)


@pytest.mark.parametrize("which", ["source", "target"])
def test_corrupt_saved_response_prevents_reuse(approval, which):
    store, state, module, _, _ = approval
    group, result_id = target(approval)
    proof, _ = reusable_review(store, group, module.store, result_id)
    sid = (
        proof["snapshot_id"] if which == "target" else proof["approval_reuse"]["source_snapshot_id"]
    )
    with module.store._db:
        module.store._db.execute("UPDATE snapshots SET body=? WHERE id=?", (b"{}", sid))
    assert not valid_approval_reuse(proof, "example.com", module.store)
    assert reusable_review(store, group, module.store, result_id) is None


@pytest.mark.parametrize(
    "change",
    [
        lambda proof: proof["approval_reuse"].update(source_ip="9.9.9.9"),
        lambda proof: proof["review"].update(result_id=proof["result_id"]),
        lambda proof: proof["evidence"]["details"].update(network_start="9.9.9.9"),
        lambda proof: proof["approval_reuse"]["registrant_identity"].update(handle="OTHER"),
        lambda proof: proof["attribution"].update(root_domain="other.net"),
    ],
)
def test_frozen_snapshot_rejects_inconsistent_provenance(approval, change):
    store, state, module, _, _ = approval
    group, result_id = target(approval)
    proof, _ = reusable_review(store, group, module.store, result_id)
    broken = deepcopy(proof)
    change(broken)
    assert not snapshot_approval_matches(broken, "example.com")
    assert not valid_approval_reuse(broken, "example.com", module.store)


def test_source_capture_explicitly_includes_prior_approval_outside_case_imports(approval):
    from workbench.source_capture import capture_sources

    store, state, module, decision, _ = approval
    group, result_id = target(approval)
    proof, _ = reusable_review(store, group, module.store, result_id)
    data = {"qualified_lead": {"whois": [proof]}, "cves": [], "draft": {}}
    capture_sources(store, data)
    history = {item["result_id"]: item for item in data["attribution_history"]}
    assert set(history) == {result_id, decision["review"]["result_id"]}
    original = history[decision["review"]["result_id"]]
    assert original["case_evidence_status"] == "source of reused analyst approval"
    assert len(original["analyst_reviews"]) == 1
    assert history[result_id]["analyst_reviews"] == []
    assert not data["source_integrity_issues"]


def test_workspace_restore_checks_nested_approval_provenance(approval):
    from workbench.workspace_data_attribution import validate_attribution_data

    store, state, module, _, _ = approval
    group, result_id = target(approval)
    proof, _ = reusable_review(store, group, module.store, result_id)
    with store.transaction() as db:
        db.execute("UPDATE domain_groups SET attribution=?", (json.dumps(proof),))
    validate_attribution_data(store)
    proof["approval_reuse"]["source_body_sha256"] = "0" * 64
    with store.transaction() as db:
        db.execute("UPDATE domain_groups SET attribution=?", (json.dumps(proof),))
    with pytest.raises(ValueError, match="inherited attribution"):
        validate_attribution_data(store)


def test_entity_and_group_exports_include_the_original_approval(approval):
    from session_helpers import TestClient
    from workbench.api import create_app

    store, state, module, decision, fields = approval
    intake = IntakeService(store)
    imported = intake.enqueue(
        "newer.csv",
        csv_bytes(
            [
                {
                    **fields,
                    "ip": "8.8.4.4",
                    "timestamp": "2026-11-13 10:00:00",
                }
            ]
        ),
    )
    intake.process(imported["id"])
    job = store.one("SELECT * FROM jobs WHERE import_id=?", (imported["id"],))
    assert job["status"] == "qualified"
    source_id = decision["review"]["result_id"]
    result_id = job["attribution_result_id"]
    assert result_id != source_id
    app = create_app(store.root, worker=False)
    with TestClient(app) as client:
        client.headers["X-Workbench-Token"] = client.get("/api/bootstrap").json()["token"]
        response = client.get(f"/api/leads/{decision['lead_id']}/attribution.zip")
        assert response.status_code == 200, response.text
        with ZipFile(io.BytesIO(response.content)) as archive:
            original = json.loads(archive.read(f"{source_id}/analyst-reviews.json"))
            assert len(original) == 1 and original[0]["decision"] == "accept"
            assert f"{result_id}/analyst-reviews.json" not in archive.namelist()
            assert (
                json.loads(archive.read(f"{result_id}/approval-reuse.json"))["source_result_id"]
                == source_id
            )
        response = client.get(f"/api/groups/{job['id']}/attribution.zip")
        assert response.status_code == 200, response.text
        with ZipFile(io.BytesIO(response.content)) as archive:
            original = json.loads(archive.read(f"prior-approval/{source_id}/analyst-reviews.json"))
            assert len(original) == 1 and original[0]["decision"] == "accept"
            assert "analyst-reviews.json" not in archive.namelist()
            assert json.loads(archive.read("approval-reuse.json"))["source_result_ids"] == [
                source_id
            ]
