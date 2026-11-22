"""Reusable synthetic cve catalog fixtures and builders."""

import gzip
import hashlib
import json
from datetime import datetime, timezone

from modules.library.tests.support.cve_sources import nvd

NOW = datetime(2026, 11, 11, 4, 0, tzinfo=timezone.utc)


def record(identifier="CVE-2026-1234", modified="2026-11-10T01:00:00.000", status="Analyzed"):
    return {
        "id": identifier,
        "published": "2026-01-01T00:00:00.000",
        "lastModified": modified,
        "vulnStatus": status,
        "descriptions": [{"lang": "en", "value": "Apache synthetic vulnerability"}],
        "metrics": {
            "cvssMetricV31": [
                {"type": "Primary", "cvssData": {"baseScore": 9.1, "baseSeverity": "CRITICAL"}}
            ]
        },
        "additiveFutureField": {"kept": True},
    }


def feed(folder, year, entries, *, modified="2026-11-09T03:00:00Z", corrupt=False):
    folder.mkdir(exist_ok=True)
    raw = json.dumps(
        {"format": "NVD_CVE", "version": "2.0", "vulnerabilities": [{"cve": r} for r in entries]}
    ).encode()
    zipped = gzip.compress(raw)
    (folder / f"nvdcve-2.0-{year}.json.gz").write_bytes(zipped)
    digest = "0" * 64 if corrupt else hashlib.sha256(raw).hexdigest().upper()
    (folder / f"nvdcve-2.0-{year}.meta").write_text(
        f"lastModifiedDate:{modified}\nsize:{len(raw)}\ngzSize:{len(zipped)}\nsha256:{digest}\n"
    )


class Pages:
    def __init__(self, pages=None):
        self.pages = list(pages or [])
        self.calls = []

    def api_page(self, start, end, index, *, cancel_event=None):
        self.calls.append((start, end, index))
        value = self.pages.pop(0) if self.pages else []
        if isinstance(value, BaseException):
            raise value
        if isinstance(value, dict):
            body = value
        else:
            body = {
                "totalResults": len(value),
                "startIndex": index,
                "resultsPerPage": len(value),
                "vulnerabilities": [{"cve": r} for r in value],
            }
        return json.dumps(
            body
        ).encode(), "https://services.nvd.nist.gov/rest/json/cves/2.0?fixture=1"


def catalog_record(description="Catalog wording", *, stale=False):
    cve = nvd(description)["vulnerabilities"][0]["cve"]
    return {
        "cve": cve,
        "source": {
            "url": "https://nvd.nist.gov/feeds/json/cve/2.0/nvdcve-2.0-2025.json.gz",
            "retrieved_at": "2026-11-01T00:00:00Z",
            "feed_sha256": "a" * 64,
            "record_sha256": hashlib.sha256(json.dumps(cve, sort_keys=True).encode()).hexdigest(),
        },
        "last_modified": cve["lastModified"],
        "catalog_checked_at": "2026-11-10T12:00:00Z",
        "catalog_stale": stale,
    }
