"""Source identity, bounded gzip, and receipt handoff without live API calls."""

import gzip
import hashlib
import io
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from test_intake_profiles_070 import Registry, csv_bytes, row
from workbench.api_import import enqueue_download, receipt_acquisition
from workbench.eclipse import Eclipse
from workbench.intake.files import read_entries
from workbench.intake.records import UnvalidatedEntry
from workbench.intake.validation import EntryValidator
from workbench.intake_service import IntakeService
from workbench.report_profiles import observation_envelope, resolve_profile
from workbench.routes.intake import register
from workbench.store import Store


def receipt(data, name="scan-http_vulnerable.csv.gz", **changes):
    result = {
        "path": "/downloader/private/local/path",
        "original_filename": name,
        "subscription": "fixture-subscription",
        "report_type": "scan_http_vulnerable",
        "report_date": "2026-11-01",
        "retrieved_at": "2026-11-08T12:00:00Z",
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "source_fingerprint": "a" * 64,
        "validation": "csv_valid",
        "reused": False,
        "schema_reference": None,
    }
    result.update(changes)
    parts = [result[k] for k in ("subscription", "report_type", "report_date", "original_filename")]
    result["logical_id"] = hashlib.sha256(
        json.dumps(parts, ensure_ascii=True, separators=(",", ":")).encode()
    ).hexdigest()
    return result


def setup_intake(tmp_path):
    store = Store(tmp_path / "workspace")
    registry = Registry()
    return store, IntakeService(store, lookup_factory=lambda: registry), registry


def source_bytes():
    return csv_bytes(
        [row(tag="CVE-2099-10001", timestamp="2026-11-01T03:00:00Z", future_field="preserved")]
    )


def test_occurrence_identity_uses_file_content_and_keeps_references_consistent():
    source = UnvalidatedEntry("report.csv", "CSV", 2, row())
    profile = resolve_profile(source.fields)
    first = observation_envelope(source, profile, {}, source_sha256="a" * 64)
    changed = observation_envelope(source, profile, {}, source_sha256="b" * 64)
    renamed = observation_envelope(
        UnvalidatedEntry("renamed.csv", "CSV", 2, row()), profile, {}, source_sha256="a" * 64
    )
    assert first["observation_ref"] != changed["observation_ref"]
    assert first["observation_ref"] == renamed["observation_ref"]
    assert first["observation_ref"] == hashlib.sha256(f"{'a' * 64}:CSV:2".encode()).hexdigest()
    assert first["schema_version"] == 2
    assert first["identity_basis"] == "file_sha256_sheet_row"
    assert all(p["service_ref"] == first["observation_ref"] for p in first["products"])
    with pytest.raises(ValueError, match="SHA-256"):
        observation_envelope(source, profile, {}, source_sha256="report.csv")


def test_inline_identity_no_longer_collides_for_different_rows_with_same_filename():
    a = UnvalidatedEntry("report.csv", "CSV", 2, row(ip="8.8.8.8"))
    b = UnvalidatedEntry("report.csv", "CSV", 2, row(ip="9.9.9.9"))
    assert (
        observation_envelope(a, {}, {})["observation_ref"]
        != observation_envelope(b, {}, {})["observation_ref"]
    )


def test_gzip_reader_preserves_original_fields_and_enforces_expansion_limit(tmp_path):
    data = source_bytes()
    path = tmp_path / "report.csv.gz"
    compressed = gzip.compress(data)
    path.write_bytes(compressed)
    entries = list(read_entries(path, ""))
    assert entries[0].fields["future_field"] == "preserved"
    assert entries[0].sheet == "CSV" and entries[0].row == 2
    assert path.read_bytes() == compressed
    with pytest.raises(ValueError, match="Expanded CSV"):
        list(read_entries(path, "", max_csv_bytes=len(data) - 1))
    path.write_bytes(compressed[:-4])
    with pytest.raises((EOFError, OSError)):
        list(read_entries(path, ""))


def test_manual_gzip_intake_is_retained_and_uses_full_source_digest(tmp_path):
    store, intake, _ = setup_intake(tmp_path)
    content = gzip.compress(source_bytes())
    result = intake.enqueue("scan-http_vulnerable.csv.gz", content)
    intake.process(result["id"])
    saved = store.one("SELECT * FROM imports WHERE id=?", (result["id"],))
    assert saved["status"] == "done", saved["error"]
    assert store.path(saved["path"]).read_bytes() == content
    entry = json.loads(
        store.one("SELECT payload FROM jobs WHERE import_id=?", (result["id"],))["payload"]
    )[0]
    assert entry["normalized"]["source_sha256"] == saved["sha256"]
    assert "narrative_date_basis" not in entry["normalized"]["acquisition"]


def test_receipt_handoff_keeps_dates_originals_and_distinct_import_status(tmp_path):
    store, intake, _ = setup_intake(tmp_path)
    content = gzip.compress(source_bytes())
    path = tmp_path / "download.csv.gz"
    path.write_bytes(content)
    proof = receipt(content)
    result = enqueue_download(intake, path, proof, narrative_date_basis="emailed_row_plus_one")
    assert result["downloaded"] and not result["imported"]
    intake.process(result["id"])
    saved = store.one("SELECT * FROM imports WHERE id=?", (result["id"],))
    assert saved["status"] == "done", saved["error"]
    config = json.loads(saved["config"])
    acquired = config["acquisition"]
    assert acquired["report_date"] == "2026-11-01"
    assert acquired["retrieved_at"] == "2026-11-08T12:00:00Z"
    assert acquired["catalog_coverage"] == "unknown"
    assert "path" not in acquired["receipt"]
    assert store.path(saved["path"]).read_bytes() == content
    assert enqueue_download(intake, path, proof, narrative_date_basis="emailed_row_plus_one") == {
        "id": result["id"],
        "duplicate": True,
        "downloaded": True,
        "imported": True,
    }


def test_overlapping_subscriptions_keep_receipts_without_duplicate_work(tmp_path):
    store, intake, _ = setup_intake(tmp_path)
    content = gzip.compress(source_bytes())
    path = tmp_path / "download.csv.gz"
    path.write_bytes(content)
    a = enqueue_download(intake, path, receipt(content))
    b = enqueue_download(intake, path, receipt(content, subscription="another-subscription"))
    assert a["id"] == b["id"] and b["duplicate"]
    saved = store.one("SELECT * FROM imports WHERE id=?", (a["id"],))
    proofs = json.loads(saved["config"])["acquisition_receipts"]
    assert len(proofs) == 2
    assert {r["receipt"]["subscription"] for r in proofs} == {
        "fixture-subscription",
        "another-subscription",
    }


def test_api_receipt_enters_qualification_without_narrative_date_policy(tmp_path):
    store, intake, registry = setup_intake(tmp_path)
    content = gzip.compress(source_bytes())
    path = tmp_path / "download.csv.gz"
    path.write_bytes(content)
    result = enqueue_download(intake, path, receipt(content))
    intake.process(result["id"])
    saved = store.one("SELECT * FROM imports WHERE id=?", (result["id"],))
    assert saved["status"] == "done"
    assert json.loads(saved["rejected"]) == {}
    assert registry.calls and store.all("SELECT * FROM jobs")
    mapped = Eclipse(store).snapshot()
    assert "receipt-date" not in mapped["observations"][0]["disposition_reason"]


def test_reevaluation_retains_prior_policy_and_original_then_deduplicates(tmp_path):
    store, intake, _ = setup_intake(tmp_path)
    original = csv_bytes([row(hostname="example.org")])
    first = intake.enqueue("scan-http_vulnerable.csv", original)
    intake.process(first["id"])
    config = store.settings()
    config["accretion_priority_cities"] = ["Charlotte"]
    with store.transaction() as db:
        db.execute("UPDATE settings SET value=? WHERE key='profile'", (json.dumps(config),))
    second = intake.reevaluate(first["id"])
    assert second["id"] != first["id"] and not second["duplicate"]
    assert intake.reevaluate(first["id"])["id"] == second["id"]
    saved = store.one("SELECT * FROM imports WHERE id=?", (first["id"],))
    assert json.loads(saved["config"])["accretion_priority_cities"] == []
    assert store.path(saved["path"]).read_bytes() == original
    store.path(saved["path"]).write_bytes(original + b"\n")
    with pytest.raises(ValueError, match="Retained original has changed"):
        intake.reevaluate(first["id"])


def test_receipt_checksum_failure_and_stream_limits_leave_no_import(tmp_path):
    store, intake, _ = setup_intake(tmp_path)
    content = gzip.compress(source_bytes())
    proof = receipt(content)
    with pytest.raises(ValueError, match="do not match"):
        intake.enqueue_stream(
            proof["original_filename"],
            io.BytesIO(content + b"x"),
            acquisition=receipt_acquisition(proof),
        )
    with pytest.raises(ValueError, match="limit"):
        intake.enqueue_stream("report.csv", io.BytesIO(b"x" * 11), max_bytes=10)
    assert not store.all("SELECT * FROM imports")
    assert not list((store.root / "originals").iterdir())


@pytest.mark.parametrize(
    "change",
    [
        {"secret": "do-not-retain"},
        {"retrieved_at": "2026-11-08T12:00:00"},
        {"original_filename": "../report.csv.gz"},
        {"size_bytes": True},
        {"validation": "pending"},
        {"sha256": "x" * 64},
    ],
)
def test_invalid_or_nonpublic_receipt_is_rejected(change):
    proof = receipt(b"csv")
    proof.update(change)
    with pytest.raises(ValueError):
        receipt_acquisition(proof)


def test_invalid_hostname_samples_are_explicit_and_valid_domains_are_ordinary(tmp_path):
    validator = EntryValidator({"North Carolina"}, com_only=True, exclude_numeric_roots=True)
    assert (
        validator.rejection_reason(
            UnvalidatedEntry("report.csv", "CSV", 2, row(hostname="not a host"))
        )
        == "invalid_hostname"
    )
    for hostname in ("example.org", "example2.com", "mail2.example2.net"):
        assert validator.validate_entry(
            UnvalidatedEntry("report.csv", "CSV", 2, row(hostname=hostname))
        )
    store, intake, _ = setup_intake(tmp_path)
    result = intake.enqueue("scan-http_vulnerable.csv", csv_bytes([row(hostname="not a host")] * 8))
    intake.process(result["id"])
    saved = store.one("SELECT * FROM imports WHERE id=?", (result["id"],))
    assert json.loads(saved["rejected"]) == {"invalid_hostname": 8}
    examples = json.loads(saved["config"])["intake_stats"]["rejection_examples"]["invalid_hostname"]
    assert len(examples) == 5 and examples[0]["row"] == 2


def test_receipt_http_handoff_and_capability_gate(tmp_path):
    store, intake, _ = setup_intake(tmp_path)
    app = FastAPI()
    register(app, store=store, intake=intake)
    content = gzip.compress(source_bytes())
    proof = receipt(content)
    with TestClient(app) as client:
        capabilities = client.get("/api/intake/capabilities").json()
        assert capabilities["api_live_selection"] is False
        assert ".csv.gz" in capabilities["manual_formats"]
        response = client.post(
            "/api/imports/api-receipt",
            files={"report": (proof["original_filename"], content)},
            data={"receipt": json.dumps(proof)},
        )
        assert response.status_code == 200, response.text
        assert response.json()["downloaded"] and not response.json()["imported"]
        detail = client.get("/api/imports/" + response.json()["id"]).json()
        assert detail["acquisition"]["report_date"] == "2026-11-01"
        malformed = client.post(
            "/api/imports/api-receipt",
            files={"report": (proof["original_filename"], content)},
            data={"receipt": "{"},
        )
        assert malformed.status_code == 400
