"""Reusable synthetic catalog outreach fixtures and builders."""

import hashlib
import json
from datetime import datetime, timezone

from modules.library.components.cve_catalog import Catalog
from modules.library.components.cve_catalog.products import identity
from modules.library.components.cve_catalog.risk import KEV_FEED, RiskStore
from modules.observatory.tests.support.observations import observation

CRITICAL = "CVE-2026-80001"


HIGH_KEV = "CVE-2026-80002"


OTHER_CRITICAL_KEV = "CVE-2026-80003"


CRITICAL_KEV = "CVE-2026-80004"


REJECTED = "CVE-2026-80005"


PRODUCT = identity("acme", "mail_gateway")


STAMP = "2026-11-10T12:00:00Z"


def reference(identifier, *, severity="CRITICAL", product="mail_gateway", rejected=False):
    return {
        "id": identifier,
        "sourceIdentifier": "security@example.test",
        "published": "2026-10-01T12:00:00Z",
        "lastModified": STAMP,
        "vulnStatus": "Rejected" if rejected else "Analyzed",
        "descriptions": [{"lang": "en", "value": "Synthetic outreach reference " + identifier}],
        "metrics": {
            "cvssMetricV31": [
                {
                    "source": "security@example.test",
                    "type": "Primary",
                    "cvssData": {
                        "version": "3.1",
                        "baseScore": 9.8 if severity == "CRITICAL" else 7.5,
                        "baseSeverity": severity,
                        "vectorString": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
                        "attackVector": "NETWORK",
                        "privilegesRequired": "NONE",
                        "userInteraction": "NONE",
                    },
                }
            ]
        },
        "configurations": [
            {
                "nodes": [
                    {
                        "operator": "OR",
                        "cpeMatch": [
                            {
                                "vulnerable": True,
                                "criteria": f"cpe:2.3:a:acme:{product}:*:*:*:*:*:*:*:*",
                                "versionStartIncluding": "1.0",
                                "versionEndExcluding": "2.0",
                            }
                        ],
                    }
                ]
            }
        ],
        "references": [{"url": "https://example.test/advisory", "tags": ["Vendor Advisory"]}],
        "weaknesses": [
            {
                "source": "security@example.test",
                "type": "Primary",
                "description": [{"lang": "en", "value": "CWE-79"}],
            }
        ],
    }


def seed_catalog(root, temporary):
    catalog = Catalog(root)
    source = {"url": "https://example.test/synthetic-catalog", "retrieved_at": STAMP}
    with catalog.connection() as db:
        for value in (
            reference(CRITICAL),
            reference(HIGH_KEV, severity="HIGH"),
            reference(OTHER_CRITICAL_KEV, product="unrelated_server"),
            reference(CRITICAL_KEV),
            reference(REJECTED, rejected=True),
        ):
            catalog.upsert(db, value, source)
    catalog.build_index()
    entries = []
    for identifier in (HIGH_KEV, OTHER_CRITICAL_KEV, CRITICAL_KEV):
        entries.append(
            {
                "cveID": identifier,
                "vendorProject": "Acme",
                "product": "Synthetic product",
                "vulnerabilityName": "Synthetic known exploitation",
                "dateAdded": "2026-11-01",
                "shortDescription": "Synthetic KEV reference for local join acceptance.",
                "requiredAction": "Consult the synthetic advisory.",
                "dueDate": "2026-11-30",
                "knownRansomwareCampaignUse": "Unknown",
                "notes": "",
            }
        )
    raw = {
        "catalogVersion": "2026.11.10",
        "dateReleased": STAMP,
        "count": len(entries),
        "vulnerabilities": entries,
    }
    path = temporary / "synthetic-kev.json"
    path.write_text(json.dumps(raw))
    RiskStore(root, clock=lambda: datetime(2026, 11, 11, tzinfo=timezone.utc)).import_kev(
        path,
        {
            "source_url": KEV_FEED,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "last_success_at": STAMP,
        },
    )
    return catalog


def reported_rows():
    return [
        observation("first", tag=CRITICAL_KEV, product="Mail Gateway", version="1.0"),
        observation(
            "return",
            tag=CRITICAL_KEV,
            product="Mail Gateway",
            version="1.0",
            observed_day="2026-01-03",
        ),
        observation(
            "other-entity",
            tag=CRITICAL_KEV,
            hostname="mail.beta.example",
            entity_id="entity-beta",
            entity_name="Beta",
            product="Mail Gateway",
            version="1.1",
            observed_day="2026-01-04",
            delivered_at="2026-01-05",
        ),
        observation(
            "split-risk",
            tag=CRITICAL + ";" + HIGH_KEV,
            hostname="split.example",
            product="Mail Gateway",
        ),
        observation(
            "wrong-product",
            tag=HIGH_KEV + ";" + OTHER_CRITICAL_KEV,
            hostname="wrong.example",
            product="Mail Gateway",
        ),
        observation(
            "product-only",
            tag="eol-example",
            hostname="candidate.example",
            product="Mail Gateway",
            version="0.9",
        ),
        observation(
            "prefix", tag=CRITICAL_KEV + "0", hostname="prefix.example", product="Other product"
        ),
        observation("rejected", tag=REJECTED, hostname="rejected.example", product="Other product"),
    ]
