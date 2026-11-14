"""Legacy restore verifies saved source references even without a ZIP manifest."""

import hashlib
import json
from zipfile import ZipFile

import pytest

from workbench.repositories.sources import SourceRepository
from workbench.store import Store
from workbench.workspace_data import export_workspace, unpack_workspace
from workbench.workspace_data_captures import validate_capture_data


def captured(store, *, body=b'{"fixture":"original source"}'):
    relative = "evidence/cve/fixture-response.json"
    path = store.root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return {"record_path": relative, "sha256": hashlib.sha256(body).hexdigest()}


def bank_record(store, key, value):
    with store.transaction() as db:
        SourceRepository.put(db, key, value)


@pytest.mark.parametrize("damage", ["missing", "changed"])
def test_manifestless_backup_rejects_missing_or_changed_capture(tmp_path, damage):
    source = Store(tmp_path / "source")
    proof = captured(source)
    bank_record(source, "cve-version:saved", {"id": "CVE-2026-1234", "sources": [proof]})
    exported = export_workspace(source)
    legacy = tmp_path / "legacy.zip"
    try:
        with ZipFile(exported) as current, ZipFile(legacy, "w") as old:
            for name in current.namelist():
                if name == "manifest.json":
                    continue
                raw = current.read(name)
                if name == "data/" + proof["record_path"]:
                    if damage == "missing":
                        continue
                    raw = b'{"fixture":"different source"}'
                old.writestr(name, raw)
        with pytest.raises(ValueError, match="captured vulnerability source|SHA-256"):
            unpack_workspace(legacy, tmp_path / "replacement")
        assert (source.root / proof["record_path"]).read_bytes() == b'{"fixture":"original source"}'
    finally:
        exported.unlink()


@pytest.mark.parametrize(
    "key,container",
    [
        ("cve-reference:CVE-2026-1234", lambda p: {"attempts": [p]}),
        ("intelligence-version:old", lambda p: {"supplementary_records": [{"source": p}]}),
        ("risk-proof:kev", lambda p: p),
        ("risk-version:old", lambda p: {"source": p}),
        ("acquisition-version:old", lambda p: {"outcome": "http_error", "response": p}),
        ("risk-attempt:kev", lambda p: {"response": p}),
        ("risk-refresh:kev", lambda p: {"attempt": {"response": p}}),
    ],
)
def test_saved_risk_and_failed_attempt_captures_are_checked(tmp_path, key, container):
    store = Store(tmp_path / "replacement")
    proof = captured(store, body=b"Captured HTTP error response")
    bank_record(store, key, container(proof))
    validate_capture_data(store)
    (store.root / proof["record_path"]).unlink()
    with pytest.raises(ValueError, match="missing a captured vulnerability source"):
        validate_capture_data(store)


def test_legacy_embedded_records_and_raw_provider_path_fields_are_not_captures(tmp_path):
    store = Store(tmp_path / "legacy")
    bank_record(
        store,
        "cve-version:legacy",
        {
            "id": "CVE-2026-1234",
            "record": {
                "record_path": "../../not-a-local-capture",
                "sha256": "arbitrary-provider-data",
            },
            "acquisition": [{"outcome": "network_error", "response": None}],
            "sources": [{"public_url": "https://example.com/reference"}],
        },
    )
    bank_record(store, "risk:kev", {"record_path": "raw-catalog-field", "sha256": "raw"})
    validate_capture_data(store)


def test_legacy_declared_capture_without_digest_must_exist(tmp_path):
    store = Store(tmp_path / "legacy")
    proof = captured(store)
    proof.pop("sha256")
    bank_record(store, "cve-reference:CVE-2026-1234", proof)
    validate_capture_data(store)
    (store.root / proof["record_path"]).unlink()
    with pytest.raises(ValueError, match="missing a captured vulnerability source"):
        validate_capture_data(store)


def test_capture_cannot_escape_replacement_workspace(tmp_path):
    store = Store(tmp_path / "replacement")
    (tmp_path / "outside.json").write_text("outside")
    bank_record(store, "risk-proof:kev", {"record_path": "../outside.json"})
    with pytest.raises(ValueError, match="missing a captured vulnerability source"):
        validate_capture_data(store)


def test_pinned_draft_record_is_checked_without_bank_entry(tmp_path, monkeypatch):
    store = Store(tmp_path / "replacement")
    proof = captured(store)
    original_all = store.all

    def rows(sql, args=()):
        if sql == "SELECT draft FROM cases":
            return [{"draft": json.dumps({"cve_records": [proof]})}]
        return original_all(sql, args)

    monkeypatch.setattr(store, "all", rows)
    validate_capture_data(store)
    (store.root / proof["record_path"]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="SHA-256"):
        validate_capture_data(store)


@pytest.mark.parametrize("damage", ["missing", "changed"])
def test_excluded_finding_capture_is_verified_without_bank_or_active_selection(
    tmp_path, monkeypatch, damage
):
    store = Store(tmp_path / "replacement")
    proof = captured(store)
    original_all = store.all

    def rows(sql, args=()):
        if sql == "SELECT draft FROM cases":
            return [
                {
                    "draft": json.dumps(
                        {
                            "cve_records": [],
                            "observation_scope_archive": {
                                "cve_records": {
                                    "CVE-2026-1234": {"id": "CVE-2026-1234", "sources": [proof]}
                                }
                            },
                        }
                    )
                }
            ]
        return original_all(sql, args)

    monkeypatch.setattr(store, "all", rows)
    validate_capture_data(store)
    path = store.root / proof["record_path"]
    if damage == "missing":
        path.unlink()
    else:
        path.write_bytes(b"changed excluded source")
    with pytest.raises(ValueError, match="captured vulnerability source|SHA-256"):
        validate_capture_data(store)
