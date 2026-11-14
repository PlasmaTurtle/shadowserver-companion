"""Independent release-integrity regressions discovered during final review."""

import hashlib
import json
from workbench.source_capture import capture_sources


def test_failed_cve_response_keeps_metadata_without_reusing_body(tmp_path):
    body = json.dumps({"message": "The provider returned a rate limit response."}).encode()
    (tmp_path / "failed.json").write_bytes(body)
    digest = hashlib.sha256(body).hexdigest()
    source = {
        "publisher": "CVE Program",
        "record_path": "failed.json",
        "sha256": digest,
        "revision_id": "failed-response",
        "retrieved_at": "2026-11-07T12:00:00Z",
        "http_status": 429,
        "url": "https://cveawg.mitre.org/api/cve/CVE-2025-12345",
    }

    class Store:
        root = tmp_path

        def path(self, value):
            return tmp_path / value

    data = {
        "cves": ["CVE-2025-12345"],
        "draft": {
            "cve_records": [
                {
                    "id": "CVE-2025-12345",
                    "attempts": [source],
                    "acquisition": [
                        {
                            "id": "attempt",
                            "outcome": "rate_limited",
                            "source_snapshot_id": "failed-response",
                            "response": source,
                        }
                    ],
                }
            ]
        },
        "qualified_lead": {},
    }
    capture_sources(Store(), data)
    assert any(
        item.get("sha256") == digest
        and item["record"] is None
        and item["availability"] == "omitted"
        and "record_path" not in item
        for item in data["source_snapshots"]
    )
    assert len(data["source_snapshots"]) == 1
    assert data["source_snapshots"][0]["acquisition_outcomes"][0]["outcome"] == "rate_limited"
    assert data["source_snapshots"][0]["source_status"] == "captured_failed_response"
    assert not data["source_integrity_issues"]


def test_no_response_attempt_does_not_invent_source_bytes(tmp_path):
    class Store:
        root = tmp_path

        def path(self, value):
            raise AssertionError("A no-response attempt has no evidence file")

    data = {
        "cves": ["CVE-2025-12345"],
        "draft": {
            "cve_records": [
                {
                    "id": "CVE-2025-12345",
                    "refresh_acquisition": [
                        {
                            "id": "attempt",
                            "outcome": "unavailable",
                            "source_snapshot_id": None,
                            "error": "Timeout",
                        }
                    ],
                }
            ]
        },
        "qualified_lead": {},
    }
    capture_sources(Store(), data)
    assert data["source_snapshots"] == [] and data["source_integrity_issues"] == []
