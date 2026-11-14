"""Case source capture retains prior attempts, excludes future and unrelated data."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

from workbench.source_capture import capture_sources


@pytest.mark.parametrize(
    ("job_domain", "proof_domain"), [("example.com", "example.com"), ("EXAMPLE.COM", "Example.Com")]
)
def test_capture_is_case_scoped_and_does_not_adopt_future_attribution(
    tmp_path, monkeypatch, job_domain, proof_domain
):
    class FakeEvidence:
        def __init__(self, *args):
            pass

        def close(self):
            pass

        def result(self, ident):
            dates = {
                "selected": "2026-11-05T14:00:00Z",
                "prior": "2026-11-05T13:00:00Z",
                "future": "2026-11-06T14:00:00Z",
            }
            return {
                "result_id": ident,
                "root_domain": "example.com",
                "evaluated_at": dates[ident],
                "status": "matched" if ident == "selected" else "no_match",
                "attempts": [{"snapshot_ids": [ident + "-snapshot"]}],
            }

        def snapshot(self, ident):
            raw = json.dumps({"name": ident}).encode()
            digest = hashlib.sha256(raw).hexdigest()
            return SimpleNamespace(
                body=raw,
                body_sha256=digest,
                metadata=lambda: {
                    "snapshot_id": ident,
                    "body_sha256": digest,
                    "retrieved_at": "2026-11-05T12:00:00Z",
                },
                record=lambda: json.loads(raw),
            )

    monkeypatch.setattr("workbench.source_capture.EvidenceStore", FakeEvidence)

    class Store:
        root = tmp_path

        def all(self, sql, args):
            if "JOIN imports" in sql:
                return []
            if "SELECT DISTINCT" in sql:
                return [
                    {
                        "id": "job",
                        "domain": job_domain,
                        "attempts": json.dumps(
                            [{"result_id": r} for r in ("prior", "selected", "future")]
                        ),
                    }
                ]
            return [
                {
                    "result_id": args[0],
                    "reviewed_at": "2026-11-05T13:30:00Z",
                    "note": "Original review",
                },
                {
                    "result_id": args[0],
                    "reviewed_at": "2026-11-07T13:30:00Z",
                    "note": "Future review",
                },
            ]

    data = {
        "case_id": "case",
        "cves": [],
        "draft": {"cve_records": []},
        "qualified_lead": {
            "whois": [
                {
                    "result_id": "selected",
                    "attribution": {"root_domain": proof_domain},
                    "review": {"reviewed_at": "2026-11-05T14:30:00Z"},
                }
            ]
        },
    }
    capture_sources(Store(), data)
    assert [r["result_id"] for r in data["attribution_history"]] == ["prior", "selected"]
    assert all(len(r["analyst_reviews"]) == 1 for r in data["attribution_history"])
    assert len(data["source_snapshots"]) == 2
    assert not data["source_integrity_issues"]


def test_catalog_appendix_filters_unrelated_entries_but_retains_actual_response_hash(tmp_path):
    raw = {
        "catalogVersion": "2026.11.07",
        "dateReleased": "2026-11-07T12:00:00Z",
        "count": 2,
        "vulnerabilities": [
            {"cveID": "CVE-2099-1234", "knownRansomwareCampaignUse": "Known"},
            {"cveID": "CVE-2099-9999", "vendorProject": "Unrelated vendor"},
        ],
    }
    for item in raw["vulnerabilities"]:
        for key, value in {
            "vendorProject": "Synthetic vendor",
            "product": "Synthetic product",
            "vulnerabilityName": "Synthetic finding",
            "dateAdded": "2026-11-01",
            "shortDescription": "Synthetic description",
            "requiredAction": "Apply update",
            "dueDate": "2026-11-30",
        }.items():
            item.setdefault(key, value)
    original = json.dumps(raw).encode()
    path = tmp_path / "catalog.json"
    path.write_bytes(original)
    digest = hashlib.sha256(original).hexdigest()

    class Store:
        root = tmp_path

        def path(self, value):
            return tmp_path / value

    data = {
        "cves": ["CVE-2099-1234"],
        "draft": {
            "cve_records": [
                {
                    "id": "CVE-2099-1234",
                    "sources": [
                        {
                            "publisher": "CISA KEV",
                            "record_path": "catalog.json",
                            "sha256": digest,
                            "retrieved_at": "2026-11-07T12:01:00Z",
                        }
                    ],
                }
            ]
        },
        "qualified_lead": {"whois": []},
    }
    capture_sources(Store(), data)
    source = data["source_snapshots"][0]
    assert source["body_sha256"] == digest
    assert source["record"]["count"] == 2
    assert len(source["record"]["vulnerabilities"]) == 1
    assert path.read_bytes() == original
    assert not data["source_integrity_issues"]


def test_missing_or_corrupt_saved_source_does_not_fabricate_success(tmp_path):
    class Store:
        root = tmp_path

        def path(self, value):
            return tmp_path / value

    data = {
        "cves": ["CVE-2099-1234"],
        "draft": {
            "cve_records": [
                {
                    "id": "CVE-2099-1234",
                    "source": "NVD",
                    "record_path": "absent.json",
                    "body_sha256": "a" * 64,
                }
            ]
        },
        "qualified_lead": {},
    }
    capture_sources(Store(), data)
    assert data["source_integrity_issues"]
    assert data["source_snapshots"][0]["availability"] == "unavailable"
    assert data["source_snapshots"][0]["record"] is None
    assert "retrieved_at" not in data["source_snapshots"][0]
