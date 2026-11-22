"""Reusable synthetic local risk fixtures and builders."""

import gzip
import hashlib
import json
from datetime import datetime, timezone

from modules.library.components.cve_catalog.risk import RiskStore
from modules.library.tests.support.cve_sources import ID

NOW = datetime(2026, 11, 11, 4, tzinfo=timezone.utc)


def epss_bytes(score="0.7", day="2026-11-10", extra=""):
    return gzip.compress(
        (
            f"#model_version:v2026.06.15,score_date:{day}\ncve,epss,percentile\n{ID},{score},0.99\n"
            + extra
        ).encode()
    )


def kev_raw():
    return {
        "catalogVersion": "2026.11.10",
        "dateReleased": "2026-11-10T12:00:00Z",
        "count": 1,
        "vulnerabilities": [
            {
                "cveID": ID,
                "vendorProject": "Example",
                "product": "Server",
                "vulnerabilityName": "Synthetic flaw",
                "dateAdded": "2026-11-10",
                "shortDescription": "Synthetic",
                "requiredAction": "Apply vendor update",
                "dueDate": "2026-12-01",
                "knownRansomwareCampaignUse": "Unknown",
            }
        ],
    }


class Feeds:
    def __init__(self):
        self.epss = epss_bytes()
        self.kev = json.dumps(kev_raw()).encode()
        self.calls = []
        self.failure = {}

    def download(self, provider, target, **kwargs):
        self.calls.append(provider)
        if provider in self.failure:
            raise self.failure[provider]
        body = getattr(self, provider)
        target.write_bytes(body)
        return {
            "url": "https://epss.empiricalsecurity.com/scores.csv.gz"
            if provider == "epss"
            else "https://raw.githubusercontent.com/cisagov/kev-data/develop/known_exploited_vulnerabilities.json",
            "sha256": hashlib.sha256(body).hexdigest(),
            "bytes": len(body),
        }


def risk(tmp_path):
    transport = Feeds()
    store = RiskStore(tmp_path / "working", transport=transport, clock=lambda: NOW)
    return store, transport
