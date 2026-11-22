"""Reusable synthetic intake fixtures and builders."""

from tests.support.qualification import registry_factory, capture_website

import csv
import io

from modules.accretion.components.intake_service import IntakeService
from modules.library.components.cve_catalog.storage import CatalogStorage


class Registry:
    def __init__(self):
        self.calls = []

    def lookup(self, ip):
        self.calls.append(ip)
        return None

    def close(self):
        pass


def row(**changes):
    return {
        "hostname": "mail.example.com",
        "ip": "8.8.8.8",
        "tag": "CVE-2026-12345",
        "version": "Acme/1.2",
        "region": "North Carolina",
        "city": "Burnsville",
        "severity": "high",
        "timestamp": "2026-11-11 10:00:00",
        **changes,
    }


def report(rows):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def seed(root, identifier="CVE-2026-12345", *, score=9.8, rejected=False):
    catalog = CatalogStorage(root)
    raw = {
        "id": identifier,
        "published": "2026-11-01T10:00:00Z",
        "lastModified": "2026-11-10T10:00:00Z",
        "vulnStatus": "Rejected" if rejected else "Analyzed",
        "descriptions": [{"lang": "en", "value": "Synthetic CVE for intake validation"}],
        "metrics": {
            "cvssMetricV31": [
                {
                    "type": "Primary",
                    "cvssData": {
                        "version": "3.1",
                        "baseScore": score,
                        "baseSeverity": "CRITICAL" if score >= 9 else "HIGH",
                    },
                }
            ]
        },
    }
    with catalog.connection() as db:
        catalog.upsert(
            db,
            raw,
            {
                "url": "https://nvd.nist.gov/feeds/json/cve/2.0/nvdcve-2.0-2026.json.gz",
                "retrieved_at": "2026-11-11T10:00:00Z",
            },
        )
    return catalog


def run_import(store, rows):
    registry = Registry()
    intake = IntakeService(
        store, attribution_factory=registry_factory(lambda: registry), capture=capture_website
    )
    original = report(rows)
    import_id = intake.enqueue("scan-http_vulnerable.csv", original)["id"]
    intake.process(import_id)
    result = store.one("SELECT * FROM imports WHERE id=?", (import_id,))
    assert result["status"] == "done", result["error"]
    return intake, registry, result, original
