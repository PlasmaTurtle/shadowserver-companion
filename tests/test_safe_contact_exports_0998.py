"""Contact exports cross a content boundary, not merely a filename boundary."""

from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

from workbench import contact_evidence
from workbench.report_package import _package_contact_research


def _snapshot(*, derived=False):
    result = {
        "id": "source-one",
        "url": "https://example.test/contact",
        "retrieved_at": "2026-11-13T12:00:00Z",
        "status_code": 200,
        "content_type": "text/html",
        "sha256": "1" * 64,
        "hash_scope": "captured_body",
        "path": "evidence/contact-discovery/run-one/01-response.body.txt",
    }
    if derived:
        result.update(
            retention="contact-extract-v1",
            artifact_sha256="2" * 64,
            path="evidence/contact-discovery/run-one/01-response.contact.json",
        )
    return result


@pytest.mark.parametrize("exists", [False, True])
def test_legacy_contact_bodies_are_never_opened_or_reexported(tmp_path, monkeypatch, exists):
    source = tmp_path / "source"
    source.mkdir()
    legacy = _snapshot()
    original = source / legacy["path"]
    if exists:
        original.parent.mkdir(parents=True)
        original.write_bytes(b"Synthetic legacy response that must not be copied")
    saved = deepcopy(legacy)
    research = {"runs": [{"id": "run-one", "snapshots": [legacy]}]}
    destination = tmp_path / "package"
    (destination / "evidence").mkdir(parents=True)

    def forbidden_read(*args, **kwargs):
        pytest.fail("Legacy contact body reached the evidence reader")

    monkeypatch.setattr(contact_evidence, "snapshot_content", forbidden_read)
    _package_contact_research(SimpleNamespace(root=source), research, destination)
    assert legacy["package_availability"] == "omitted"
    assert "path" not in legacy
    assert legacy["original_path"] == saved["path"]
    for key in ("url", "retrieved_at", "sha256", "hash_scope"):
        assert legacy[key] == saved[key]
    assert not list((destination / "evidence").iterdir())
    if exists:
        assert original.read_bytes() == b"Synthetic legacy response that must not be copied"


def test_package_copies_only_bytes_returned_by_validated_extract_reader(tmp_path, monkeypatch):
    captured = _snapshot(derived=True)
    original_hash = captured["sha256"]
    original_path = captured["path"]
    research = {"runs": [{"id": "run-one", "snapshots": [captured]}]}
    (tmp_path / "evidence").mkdir()
    raw = json.dumps({"contact": "security@example.test", "representation": "derived"}).encode()
    expected_digest = hashlib.sha256(raw).hexdigest()
    captured["artifact_sha256"] = expected_digest
    calls = []

    def validated_read(store, run_id, metadata):
        calls.append((run_id, metadata["path"]))
        return raw

    monkeypatch.setattr(contact_evidence, "snapshot_content", validated_read)
    _package_contact_research(SimpleNamespace(root=tmp_path), research, tmp_path)
    assert calls == [("run-one", original_path)]
    assert captured["package_availability"] == "available"
    assert captured["sha256"] == original_hash
    assert captured["artifact_sha256"] == expected_digest
    assert captured["original_path"] == original_path
    assert captured["path"].endswith(".contact.json")
    assert (tmp_path / captured["path"]).read_bytes() == raw
    assert not list(tmp_path.rglob("*.body.txt"))


@pytest.mark.parametrize(
    "error", [ValueError("Invalid extract schema"), FileNotFoundError("Missing")]
)
def test_missing_or_invalid_derived_contact_is_explicitly_unavailable(tmp_path, monkeypatch, error):
    captured = _snapshot(derived=True)
    research = {"runs": [{"id": "run-one", "snapshots": [captured]}]}
    (tmp_path / "evidence").mkdir()

    def rejected_read(*args, **kwargs):
        raise error

    monkeypatch.setattr(contact_evidence, "snapshot_content", rejected_read)
    _package_contact_research(SimpleNamespace(root=tmp_path), research, tmp_path)
    assert captured["package_availability"] == "unavailable"
    assert captured["package_issue"] == str(error)
    assert "path" not in captured
    assert not list((tmp_path / "evidence").iterdir())


def test_evidence_reader_never_links_a_legacy_website_body(tmp_path):
    from test_evidence_workspace_0981 import evidence_package

    data, files = evidence_package(tmp_path)
    reader = (tmp_path / "Evidence_Record.html").read_text()
    assert 'href="evidence/contact.txt"' not in reader
    assert "Original captured response" not in reader
    assert "Source metadata only" in reader
    assert "Contact research snapshot" in reader
    assert (tmp_path / "evidence/contact.txt").read_bytes() == files["evidence/contact.txt"]


def test_safe_export_can_validate_legacy_metadata_without_reopening_old_file(tmp_path, monkeypatch):
    from test_contacts_098 import entity_only
    from test_contacts_invariants_090 import contact_result
    from workbench.contact_records import ContactRecords
    from workbench.store import Store
    from workbench.workspace_data_contacts import validate_contact_data
    from workbench import workspace_data_contacts

    store = Store(tmp_path / "data")
    entity_id = entity_only(store)
    contacts = ContactRecords(store)
    contacts.save_run(contacts.scope(entity_id), contact_result())
    row = store.one("SELECT * FROM contact_runs")
    historical = json.loads(row["payload"])
    for captured in historical["snapshots"]:
        captured.pop("retention", None)
        captured.pop("artifact_sha256", None)
        captured["path"] = "evidence/contact-discovery/" + row["id"] + "/legacy.body.txt"
    with store.transaction() as db:
        for trigger in db.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='contact_runs'"
        ).fetchall():
            db.execute('DROP TRIGGER "' + trigger["name"].replace('"', '""') + '"')
        db.execute(
            "UPDATE contact_runs SET payload=? WHERE id=?", (json.dumps(historical), row["id"])
        )
    # The compatibility branch must not access the historical payload at all;
    # identity/provenance checks still run against the saved database records.

    def forbidden_read(*args, **kwargs):
        raise ValueError("Legacy response access forbidden")

    monkeypatch.setattr(workspace_data_contacts, "snapshot_path", forbidden_read)
    validate_contact_data(store, entity_id, allow_unavailable_legacy=True)
    with pytest.raises(ValueError, match="Legacy response access forbidden"):
        validate_contact_data(store, entity_id)


def test_safe_export_never_relaxes_validation_of_a_derived_artifact(tmp_path, monkeypatch):
    from test_contacts_098 import entity_only
    from test_contacts_invariants_090 import contact_result
    from workbench.contact_records import ContactRecords
    from workbench.store import Store
    from workbench.workspace_data_contacts import validate_contact_data
    from workbench import workspace_data_contacts

    store = Store(tmp_path / "data")
    entity_id = entity_only(store)
    contacts = ContactRecords(store)
    contacts.save_run(contacts.scope(entity_id), contact_result())
    monkeypatch.setattr(workspace_data_contacts, "is_derived_snapshot", lambda _: True)

    def invalid_read(*args, **kwargs):
        raise ValueError("Derived artifact integrity failure")

    monkeypatch.setattr(workspace_data_contacts, "snapshot_path", invalid_read)
    with pytest.raises(ValueError, match="Derived artifact integrity failure"):
        validate_contact_data(store, entity_id, allow_unavailable_legacy=True)


@pytest.mark.parametrize("legacy_image", [False, True])
def test_existing_certified_internal_export_omits_legacy_contact_bodies(
    tmp_path, monkeypatch, legacy_image
):
    from test_export_security_072 import make_package
    from workbench import package_integrity

    folder = tmp_path / "certified"
    originals = make_package(folder, legacy=legacy_image)
    name = "evidence/contact-" + "7" * 64 + ".body.txt"
    raw = b"INERT_LEGACY_CONTACT_BODY_MUST_NOT_BE_REEXPORTED"
    originals[name] = raw
    (folder / name).write_bytes(raw)
    snapshot = json.loads(originals["snapshot.json"])
    snapshot["contact_research"] = {
        "runs": [
            {
                "id": "old-run",
                "snapshots": [
                    {
                        "path": name,
                        "sha256": hashlib.sha256(raw).hexdigest(),
                        "url": "https://example.test/",
                    }
                ],
            }
        ]
    }
    originals["snapshot.json"] = json.dumps(snapshot).encode()
    (folder / "snapshot.json").write_bytes(originals["snapshot.json"])
    manifest = {"files": {key: hashlib.sha256(body).hexdigest() for key, body in originals.items()}}
    manifest_bytes = json.dumps(manifest).encode()
    (folder / "manifest.json").write_bytes(manifest_bytes)
    originals["manifest.json"] = manifest_bytes
    package_integrity.validated_inventory(folder, {"snapshot.json", "notification.pdf"})
    read = package_integrity.read_member

    def guarded_read(root, member, digest=None):
        if member == name:
            pytest.fail("Old raw contact body was reopened during internal export")
        return read(root, member, digest)

    monkeypatch.setattr(package_integrity, "read_member", guarded_read)
    stream = io.BytesIO()
    with ZipFile(stream, "w") as archive:
        package_integrity.write_export(archive, folder, manifest, manifest_bytes)
    with ZipFile(stream) as archive:
        assert name not in archive.namelist()
        assert archive.read("snapshot.json") == originals["snapshot.json"]
        assert archive.read("certified-manifest.json") == manifest_bytes
        transport = json.loads(archive.read("export-manifest.json"))
        assert transport["omitted_files"][name]["sha256"] == hashlib.sha256(raw).hexdigest()
        assert set(archive.namelist()) == set(transport["files"]) | {"export-manifest.json"}
        for member, expected in transport["files"].items():
            assert hashlib.sha256(archive.read(member)).hexdigest() == expected
        assert raw not in b"".join(archive.read(member) for member in archive.namelist())
    assert all((folder / key).read_bytes() == body for key, body in originals.items())
