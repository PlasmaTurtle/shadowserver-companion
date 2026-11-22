"""Artifact readers agree on retained manifest bytes and strict JSON objects."""

import json

import pytest

from modules.investigations.components import package_files, package_integrity
from tests.support.export_security import make_package


@pytest.mark.parametrize("legacy", [False, True])
def test_retained_evidence_package_format_is_read_without_rewriting(tmp_path, legacy):
    folder = tmp_path / "package"
    make_package(folder, legacy=legacy)
    raw = (folder / "manifest.json").read_bytes()
    expected = json.loads(raw)
    assert package_files.parsed_manifest(folder) == (expected, raw)
    assert package_integrity.validated_inventory(folder, set(expected["files"])) == (expected, raw)
    assert (folder / "manifest.json").read_bytes() == raw


@pytest.mark.parametrize(
    "identity",
    [
        {"notification_id": "legacy-entity", "revision": 1},
        {
            "schema_version": 3,
            "report_id": "report",
            "case_id": "case",
            "entity_id": "entity",
            "revision": 1,
        },
        {
            "schema_version": 5,
            "report_id": "report",
            "case_id": "case",
            "entity_id": "entity",
            "revision": 2,
            "draft_revision": 4,
            "expected_version": 8,
        },
        {"closure_id": "closure", "case_id": "case", "expected_version": 8},
    ],
)
def test_historical_and_current_metadata_keep_values_and_original_bytes(tmp_path, identity):
    manifest = {
        **identity,
        "files": {},
        "extension": {"label": "Café", "values": [None, False, 1.5]},
    }
    raw = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\r\n").encode()
    (tmp_path / "manifest.json").write_bytes(raw)
    assert package_files.parsed_manifest(tmp_path) == (manifest, raw)
    assert package_integrity.parsed_manifest(tmp_path) == (manifest, raw)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"files":{},"files":{}}',
        b"[]",
        b'{"value":NaN}',
        b'{"value":1e999}',
        b'{"name":"\\ud800"}',
        b'{"value":' + b"[" * 70 + b"0" + b"]" * 70 + b"}",
    ],
)
def test_artifact_readers_reject_ambiguous_or_invalid_metadata_consistently(tmp_path, raw):
    (tmp_path / "manifest.json").write_bytes(raw)
    for read in (package_files.parsed_manifest, package_integrity.parsed_manifest):
        with pytest.raises(ValueError):
            read(tmp_path)
    assert (tmp_path / "manifest.json").read_bytes() == raw
