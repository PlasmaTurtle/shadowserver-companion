"""A qualification screenshot remains one immutable artifact through a report."""

import hashlib
import json
import threading
from dataclasses import replace
from zipfile import ZipFile

import pytest

from modules.entities.tests.support.contacts import attributed_entity
from modules.accretion.components.qualification import Qualifier, complete_lead
from modules.accretion.tests.support.products import qualification_values
from modules.investigations.components.cases import Cases
from modules.investigations.components.image_evidence import metadata_path
from modules.investigations.components import website_evidence as evidence
from modules.investigations.tests.support.website_capture import captured
from modules.workspace.components.store import Store
from modules.workspace.components.workspace_data import export_workspace, unpack_workspace


def test_capture_can_exist_before_entity_and_case_then_be_adopted_without_recapture(tmp_path):
    store = Store(tmp_path / "data")
    png, metadata = captured("login_required")
    capture = evidence.retain(store, png, metadata, root_domain="example.com")
    assert not store.all("SELECT * FROM leads")
    assert not store.all("SELECT * FROM cases")
    assert evidence.get(store, capture["id"])["capture"] == metadata
    assert (
        hashlib.sha256(evidence.preview(store, capture["id"])).hexdigest()
        == capture["preview_sha256"]
    )

    entity = attributed_entity(store)
    with store.transaction() as db:
        evidence.bind(db, capture["id"], entity["id"], root_domain="example.com")
        public = evidence.projection(db, entity["id"])
    assert public["final_url"] == "https://www.example.com/"
    assert "path" not in public and "preview_path" not in public
    case = Cases(store).create(entity["id"])
    adopted = store.one("SELECT * FROM evidence WHERE case_id=?", (case["case_id"],))
    assert adopted["included"] == 1
    assert adopted["path"] == capture["path"]
    assert adopted["preview_path"] == capture["preview_path"]
    assert store.path(adopted["path"]).read_bytes() == png
    stored = json.loads(store.path(metadata_path(adopted["id"])).read_text(encoding="utf-8"))
    assert stored["website_capture"] == metadata
    assert stored["website_capture_id"] == capture["id"]
    integrity = {
        "path_sha256": hashlib.sha256(store.path(adopted["path"]).read_bytes()).hexdigest(),
        "preview_path_sha256": hashlib.sha256(
            store.path(adopted["preview_path"]).read_bytes()
        ).hexdigest(),
    }
    assert evidence.source_matches(
        store, {**adopted, "source_metadata": stored, "file_integrity": integrity}
    )
    altered = {**stored, "website_capture": {**metadata, "final_url": "https://spoof.example/"}}
    assert not evidence.source_matches(store, {**adopted, "source_metadata": altered})
    assert not evidence.source_matches(store, {**adopted, "source_metadata": {}})
    with store.transaction() as db:
        assert evidence.adopt_for_case(store, db, case["case_id"]) == [adopted["id"]]
    assert len(store.all("SELECT * FROM evidence")) == 1


def test_refresh_creates_new_revision_without_replacing_adopted_evidence(tmp_path):
    store = Store(tmp_path / "data")
    png, first_metadata = captured()
    first = evidence.retain(store, png, first_metadata, root_domain="example.com")
    entity = attributed_entity(store)
    with store.transaction() as db:
        evidence.bind(db, first["id"], entity["id"], root_domain="example.com")
    case = Cases(store).create(entity["id"])
    prior = store.one("SELECT * FROM evidence WHERE case_id=?", (case["case_id"],))
    metadata = {
        **first_metadata,
        "captured_at": "2026-11-12T20:00:00Z",
        "final_url": "https://example.com/new",
    }
    second = evidence.retain(store, png, metadata, root_domain="example.com")
    with store.transaction() as db:
        evidence.bind(db, second["id"], entity["id"], root_domain="example.com")
        assert evidence.latest_for_entity(db, entity["id"])["id"] == second["id"]
    assert first["id"] != second["id"]
    assert first["path"] != second["path"]
    assert store.one("SELECT * FROM evidence WHERE id=?", (prior["id"],)) == prior
    assert evidence.get(store, first["id"])["capture"] == first_metadata
    public = evidence.export_references(store, [prior])
    assert public == [
        {
            "evidence_id": prior["id"],
            "capture_id": first["id"],
            "sha256": first["sha256"],
            **{
                key: first_metadata[key]
                for key in ("requested_url", "final_url", "captured_at", "capture_status")
            },
        }
    ]
    store.path(metadata_path(prior["id"])).write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256"):
        evidence.export_references(store, [prior])


@pytest.mark.parametrize("same_host_revisions", [0, 1, 2])
def test_direct_legacy_case_uses_only_unique_reported_host_evidence(tmp_path, same_host_revisions):
    store = Store(tmp_path / "data")
    entity = attributed_entity(store)
    ids = []
    for host in ["mail.example.com"] * same_host_revisions + ["sibling.example.com"]:
        png, metadata = captured()
        metadata["requested_url"] = "https://" + host + "/"
        capture = evidence.retain(store, png, metadata, root_domain="example.com")
        with store.transaction() as db:
            evidence.bind(db, capture["id"], entity["id"], root_domain="example.com")
        ids.append(capture["id"])
    case = Cases(store).create(entity["id"])
    attached = store.all(
        "SELECT capture_id FROM website_capture_cases WHERE case_id=?", (case["case_id"],)
    )
    assert attached == ([{"capture_id": ids[0]}] if same_host_revisions == 1 else [])


@pytest.mark.parametrize("job_host", ["mail.example.com", "sibling.example.com"])
def test_legacy_qualification_id_must_belong_to_case_host(tmp_path, job_host):
    store = Store(tmp_path / "data")
    entity = attributed_entity(store)
    ids = []
    for host in (job_host, "mail.example.com"):
        png, metadata = captured()
        metadata["requested_url"] = "https://" + host + "/"
        capture = evidence.retain(store, png, metadata, root_domain="example.com")
        with store.transaction() as db:
            evidence.bind(db, capture["id"], entity["id"], root_domain="example.com")
        ids.append(capture["id"])
    # Old imports retained the group decision before individual admission events existed.
    with store.transaction() as db:
        db.execute(
            """INSERT INTO imports(id,fingerprint,sha256,name,path,created_at,config)
               VALUES('old','old','digest','source.csv','source.csv','2026-11-01','{}')"""
        )
        db.execute("UPDATE entries SET import_id='old' WHERE lead_id=?", (entity["id"],))
        db.execute(
            """INSERT INTO jobs(id,import_id,domain,payload,status,qualification)
               VALUES('before-admissions','old','example.com','[]','qualified',?)""",
            (json.dumps({"website": {"id": ids[0]}}),),
        )
    case = Cases(store).create(entity["id"])
    attached = store.all(
        "SELECT capture_id FROM website_capture_cases WHERE case_id=?", (case["case_id"],)
    )
    assert attached == ([{"capture_id": ids[0]}] if job_host == "mail.example.com" else [])


def test_manual_screenshot_reference_preserves_stated_source_without_browser_claims():
    assert evidence.reference_for_evidence(
        {
            "id": "manual",
            "sha256": "original-digest",
            "source_url": "https://example.com/",
            "captured_at": "2026-11-21T10:00:00Z",
            "path": "private/original.bin",
            "preview_path": "private/preview.png",
            "source_metadata": {},
        }
    ) == {
        "evidence_id": "manual",
        "sha256": "original-digest",
        "source_url": "https://example.com/",
        "captured_at": "2026-11-21T10:00:00Z",
    }


@pytest.mark.parametrize("changed", ["path", "preview_path", "metadata_path"])
def test_missing_or_changed_retained_capture_cannot_be_served_or_adopted(tmp_path, changed):
    store = Store(tmp_path / "data")
    capture = evidence.retain(store, *captured(), root_domain="example.com")
    store.path(capture[changed]).write_bytes(b"changed")
    with pytest.raises(ValueError):
        evidence.get(store, capture["id"])
    with pytest.raises(ValueError):
        evidence.preview(store, capture["id"])
    with pytest.raises(ValueError):
        evidence.validate_retained(store)


def test_diagnostic_and_unrelated_capture_never_become_lead_website(tmp_path):
    store = Store(tmp_path / "data")
    entity = attributed_entity(store)
    for status, final in (
        ("challenge", "https://example.com/"),
        ("captured", "https://unrelated.net/"),
    ):
        png, metadata = captured(status)
        metadata["final_url"] = final
        capture = evidence.retain(store, png, metadata, root_domain="example.com")
        with store.transaction() as db:
            with pytest.raises(ValueError, match="functioning related"):
                evidence.bind(db, capture["id"], entity["id"], root_domain="example.com")
    with store.read_snapshot() as db:
        assert evidence.latest_for_entity(db, entity["id"]) is None


def test_synthetic_reserved_domain_keeps_exact_relationship(tmp_path):
    store = Store(tmp_path / "data")
    png, metadata = captured()
    metadata.update(
        requested_url="https://mail.cedarworks.example/", final_url="https://cedarworks.example/"
    )
    capture = evidence.retain(store, png, metadata, root_domain="cedarworks.example")
    assert evidence.related_capture(capture, "cedarworks.example")


def test_precase_capture_survives_backup_and_restore_without_entity(tmp_path):
    store = Store(tmp_path / "source")
    capture = evidence.retain(store, *captured(), root_domain="example.com")
    archive = export_workspace(store)
    try:
        target = tmp_path / "restored"
        unpack_workspace(archive, target)
        restored = Store(target)
        assert not restored.all("SELECT * FROM leads")
        assert evidence.get(restored, capture["id"]) == evidence.get(store, capture["id"])
    finally:
        archive.unlink()


def test_manifestless_backup_rejects_changed_precase_capture_metadata(tmp_path):
    store = Store(tmp_path / "source")
    capture = evidence.retain(store, *captured(), root_domain="example.com")
    archive = export_workspace(store)
    damaged = tmp_path / "damaged.zip"
    try:
        with ZipFile(archive) as source, ZipFile(damaged, "w") as target:
            for name in source.namelist():
                if name == "manifest.json":
                    continue
                raw = source.read(name)
                if name == "data/" + capture["metadata_path"]:
                    raw = b"{}"
                target.writestr(name, raw)
        with pytest.raises(ValueError, match="SHA-256"):
            unpack_workspace(damaged, tmp_path / "restored")
    finally:
        archive.unlink()


def test_entity_merge_retains_capture_projection_and_case_artifact(tmp_path):
    store = Store(tmp_path / "source")
    capture = evidence.retain(store, *captured(), root_domain="example.com")
    source = attributed_entity(store, entity_id="source")
    target = attributed_entity(store, root="target.net", entity_id="target")
    with store.transaction() as db:
        evidence.bind(db, capture["id"], source["id"], root_domain="example.com")
    case = Cases(store).create(source["id"])
    before = store.one("SELECT * FROM evidence WHERE case_id=?", (case["case_id"],))
    source_revision = store.one("SELECT draft_revision FROM leads WHERE id=?", (source["id"],))[
        "draft_revision"
    ]
    target_revision = store.one("SELECT draft_revision FROM leads WHERE id=?", (target["id"],))[
        "draft_revision"
    ]
    store.merge_entities(source["id"], target["id"], source_revision, target_revision)
    with store.read_snapshot() as db:
        assert (
            evidence.projection(db, target["id"], root_domain="example.com")["id"] == capture["id"]
        )
    after = store.one("SELECT * FROM evidence WHERE id=?", (before["id"],))
    assert after == {**before, "lead_id": target["id"]}
    assert evidence.get(store, capture["id"])["path"] == before["path"]
    assert store.all("PRAGMA foreign_key_check") == []


def test_saved_unrelated_redirect_cannot_complete_a_qualified_lead(tmp_path):
    store = Store(tmp_path / "source")
    values = qualification_values()
    png, metadata = captured()
    related = evidence.retain(store, png, metadata, root_domain="example.com")
    completion_evidence = {
        "website": related,
        "findings": values["findings"],
        "ownership_token": values["ownership_token"],
    }
    lead = complete_lead(
        store,
        values["candidate"],
        values["attribution"],
        values["coverage"],
        completion_evidence,
    )
    assert lead.website["id"] == related["id"]
    assert lead.website["final_url"] == "https://www.example.com/"

    metadata["final_url"] = "https://unrelated.net/"
    capture = evidence.retain(store, png, metadata, root_domain="example.com")
    with pytest.raises(ValueError, match="functioning related"):
        complete_lead(
            store,
            values["candidate"],
            values["attribution"],
            values["coverage"],
            {**completion_evidence, "website": capture},
        )
    assert evidence.get(store, capture["id"])["capture"] == metadata


def test_capture_request_mismatch_stops_before_attribution(tmp_path):
    store = Store(tmp_path / "source")
    candidate = qualification_values()["candidate"]
    observation = candidate.group.observations[0]
    source = replace(
        observation.source,
        fields={**observation.source.fields, "hostname": "reported.example.com"},
    )
    group = replace(candidate.group, observations=(replace(observation, source=source),))
    calls = []

    def capture(url, **kwargs):
        calls.append(url)
        return captured()

    def forbidden_attribution(*args, **kwargs):
        pytest.fail("Capture request mismatch must stop before attribution")

    qualifier = Qualifier(
        store,
        {},
        threading.Event(),
        capture=capture,
        attribution_factory=forbidden_attribution,
    )
    try:
        decision = qualifier.qualify(replace(candidate, group=group))
    finally:
        qualifier.close()
    assert decision.status == "deferred" and decision.lead is None
    assert decision.reason == "website_capture_error"
    assert decision.attempts[-1]["status"] == "tool_error"
    assert calls == ["https://reported.example.com/"]
    assert not store.all("SELECT * FROM website_captures")


def test_related_capture_uses_normalized_dns_identity():
    assert evidence.related_capture({"final_url": "https://login.xn--bcher-kva.de/"}, "BÜCHER.de.")
    assert not evidence.related_capture({"final_url": "https://bucher.de/"}, "bücher.de")
