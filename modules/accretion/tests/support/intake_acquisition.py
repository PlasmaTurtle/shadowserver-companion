"""Reusable synthetic intake acquisition fixtures and builders."""

import hashlib
import json


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
