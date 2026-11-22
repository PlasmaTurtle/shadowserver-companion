"""Lossless compact snapshots, bounded decoding and recipient-only transport."""

from contextlib import closing

from copy import deepcopy
import hashlib
import io
import json
import sqlite3
from zipfile import ZipFile

import pytest

from modules.workspace.components import compact_json
from modules.investigations.components.package_integrity import (
    validated_inventory,
    verification_scope,
    write_recipient_export,
)


def test_shared_artwork_is_stored_once_and_literal_source_fields_round_trip():
    font = "SYNTHETIC_FONT_漢字" * 10000
    image = "SYNTHETIC_IMAGE" * 2000
    document = {
        "section_reviews": [{"font": font, "image": image} for _ in range(20)],
        "section_validations": [{"font": font, "image": image} for _ in range(20)],
        "unknown_source_fields": {
            compact_json.REFERENCE: "literal source value",
            compact_json.LITERAL: {compact_json.REFERENCE: font},
        },
        "values": [False, None, 0, 1.5, "", {"unicode": "é漢字"}],
    }
    original = deepcopy(document)
    encoded = compact_json.dumps(document)
    restored = compact_json.loads(encoded)
    assert document == original == restored
    assert len(encoded.encode()) < len(json.dumps(document, ensure_ascii=False).encode()) * 0.2
    assert len(json.loads(encoded)["strings"]) == 2
    assert restored["section_reviews"][0]["font"] is restored["section_validations"][0]["font"]


@pytest.mark.parametrize("mutation", ["changed", "missing", "unknown-format", "invalid-reference"])
def test_compact_resources_fail_closed(mutation):
    packed = compact_json.pack({"master": "SYNTHETIC" * 1000})
    digest = next(iter(packed["strings"]))
    if mutation == "changed":
        packed["strings"][digest] = "changed"
    elif mutation == "missing":
        packed["strings"].clear()
    elif mutation == "unknown-format":
        packed["storage_format"] = "shadowserver-shared-strings-v999"
    else:
        packed["document"]["master"]["unexpected"] = True
    with pytest.raises(ValueError):
        compact_json.unpack(packed)


def test_expansion_budget_and_duplicate_keys_are_rejected(monkeypatch):
    packed = compact_json.pack(["A" * 1500, "A" * 1500])
    monkeypatch.setattr(compact_json, "MAX_EXPANDED_STRING_BYTES", 2000)
    with pytest.raises(ValueError, match="expanded content"):
        compact_json.dumps(["A" * 1500, "A" * 1500])
    with pytest.raises(ValueError, match="expanded content"):
        compact_json.unpack(packed)
    with pytest.raises(ValueError, match="Duplicate JSON"):
        compact_json.loads('{"draft":{},"draft":{"notes":"ambiguous"}}')


def test_oversized_validation_writes_no_record_or_event(monkeypatch):
    from modules.investigations.components.repositories.reviews import SectionReviewRepository

    monkeypatch.setattr(compact_json, "MAX_EXPANDED_STRING_BYTES", 2000)
    with closing(sqlite3.connect(":memory:")) as db, db:
        db.row_factory = sqlite3.Row
        db.execute(
            "CREATE TABLE section_validations(id,case_id,section_key,revision,validated_at,validated_by,content_hash,snapshot_json)"
        )
        db.execute(
            "CREATE TABLE section_events(case_id,section_key,action,actor,created_at,revision,validation_id)"
        )
        with pytest.raises(ValueError, match="expanded content"):
            SectionReviewRepository(None).save_validation(
                db,
                "case",
                "closing",
                "Synthetic Analyst",
                {"content_hash": "fixture", "snapshot": "A" * 1500, "frozen_context": "A" * 1500},
            )
        assert db.execute("SELECT count(*) FROM section_validations").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM section_events").fetchone()[0] == 0


def test_literal_escape_depth_is_counted_before_writing(monkeypatch):
    monkeypatch.setattr(compact_json, "MAX_DEPTH", 3)
    value = {compact_json.LITERAL: {compact_json.LITERAL: "source value"}}
    with pytest.raises(ValueError, match="nesting"):
        compact_json.dumps(value)


def test_unique_resource_budget_applies_before_write_and_on_read(monkeypatch):
    document = {"font": "A" * 1500, "image": "B" * 1500}
    packed = compact_json.pack(document)
    monkeypatch.setattr(compact_json, "MAX_UNIQUE_STRING_BYTES", 2000)
    with pytest.raises(ValueError, match="unique resources"):
        compact_json.dumps(document)
    with pytest.raises(ValueError, match="unique resources"):
        compact_json.unpack(packed)


def test_legacy_plain_snapshot_is_read_without_rewriting():
    raw = b'{\n  "schema_version": 7, "draft": {"name": "legacy"}\n}'
    assert compact_json.loads(raw) == json.loads(raw)
    assert raw == b'{\n  "schema_version": 7, "draft": {"name": "legacy"}\n}'


def test_history_pool_shares_verified_strings_but_does_not_skip_integrity():
    raw = compact_json.dumps({"master": "SYNTHETIC" * 1000})
    pool = {}
    first = compact_json.loads(raw, resource_pool=pool)
    second = compact_json.loads(raw, resource_pool=pool)
    assert first["master"] is second["master"]
    bad = json.loads(raw)
    bad["strings"][next(iter(pool))] = "corrupt"
    with pytest.raises(ValueError, match="integrity"):
        compact_json.loads(json.dumps(bad), resource_pool=pool)


def _package(tmp_path):
    contents = {
        "notification.pdf": b"CERTIFIED PDF",
        "supporting-appendix.pdf": b"CERTIFIED APPENDIX",
        "snapshot.json": compact_json.dumps({"draft": {"notes": "PRIVATE NOTE"}}).encode(),
        "work-log.pdf": b"INTERNAL WORK LOG",
    }
    for name, content in contents.items():
        (tmp_path / name).write_bytes(content)
    manifest = {
        "report_id": "report-fixture",
        "revision": 2,
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()},
    }
    raw = json.dumps(manifest).encode()
    (tmp_path / "manifest.json").write_bytes(raw)
    return manifest, raw


@pytest.mark.parametrize("include_appendix", [False, True])
def test_recipient_export_cannot_leak_internal_files(tmp_path, include_appendix):
    manifest, raw = _package(tmp_path)
    output = io.BytesIO()
    with ZipFile(output, "w") as archive:
        write_recipient_export(archive, tmp_path, manifest, raw, include_appendix=include_appendix)
    with ZipFile(output) as archive:
        expected = {"notification.pdf", "recipient-manifest.json"}
        if include_appendix:
            expected.add("supporting-appendix.pdf")
        assert set(archive.namelist()) == expected
        metadata = json.loads(archive.read("recipient-manifest.json"))
        assert set(metadata["files"]) == expected - {"recipient-manifest.json"}
        assert b"PRIVATE NOTE" not in b"".join(archive.read(name) for name in archive.namelist())


def test_verification_reuse_is_scoped_and_export_rechecks_bytes(tmp_path, monkeypatch):
    from modules.investigations.components import package_integrity

    manifest, raw = _package(tmp_path)
    reads = []
    real_read = package_integrity.read_member

    def observed(folder, name, digest=None):
        reads.append(name)
        return real_read(folder, name, digest)

    monkeypatch.setattr(package_integrity, "read_member", observed)
    with verification_scope():
        validated_inventory(tmp_path, {"notification.pdf"})
        count = len(reads)
        with verification_scope():
            validated_inventory(tmp_path, {"notification.pdf", "snapshot.json"})
        assert len(reads) == count
        (tmp_path / "notification.pdf").write_bytes(b"CHANGED AFTER CHECK")
        with ZipFile(io.BytesIO(), "w") as archive:
            with pytest.raises(ValueError, match="changed files"):
                write_recipient_export(archive, tmp_path, manifest, raw)
    with pytest.raises(ValueError, match="changed files"):
        validated_inventory(tmp_path, {"notification.pdf"})


def test_addressee_copy_is_pinned_until_presentation_adoption():
    from modules.investigations.components import approved_template
    from modules.investigations.components.report_drafts import hydrated_draft
    from modules.investigations.components.report_layouts import (
        adopt_current_layouts,
        layout_update_available,
    )
    from modules.workspace.databases.workspace_defaults import DEFAULT_SETTINGS

    lead = {
        "company": "Synthetic Business",
        "domain": "example.com",
        "entries": [],
        "entity_profile": {},
        "draft_revision": 2,
        "case": {"stage": "in_progress", "draft_revision": 2},
        "draft": {
            "template_revision": approved_template.REVISION,
            "contact_name": approved_template.LEGACY_ADDRESSEE,
        },
    }
    old = hydrated_draft(lead, DEFAULT_SETTINGS)
    assert old["contact_name"] == approved_template.LEGACY_ADDRESSEE
    assert old["addressee_revision"] == "legacy"
    assert layout_update_available(old)
    adopt_current_layouts(old)
    assert old["contact_name"] == approved_template.ADDRESSEE
    assert old["addressee_revision"] == approved_template.ADDRESSEE_REVISION
    assert lead["draft"]["contact_name"] == approved_template.LEGACY_ADDRESSEE
