"""Reusable synthetic catalog products fixtures and builders."""


def record(identifier="CVE-2026-1234", *, score=9.8, kev=False):
    return {
        "id": identifier,
        "published": "2026-01-01T00:00:00Z",
        "lastModified": "2026-11-10T00:00:00Z",
        "vulnStatus": "Analyzed",
        "descriptions": [{"lang": "en", "value": "Example product vulnerability"}],
        "metrics": {
            "cvssMetricV31": [
                {
                    "source": "nvd@nist.gov",
                    "type": "Primary",
                    "cvssData": {
                        "version": "3.1",
                        "baseScore": score,
                        "baseSeverity": "CRITICAL" if score >= 9 else "HIGH",
                        "attackVector": "NETWORK",
                        "privilegesRequired": "NONE",
                        "userInteraction": "NONE",
                    },
                }
            ]
        },
        "weaknesses": [
            {"description": [{"value": "CWE-79"}, {"value": "CWE-79"}, {"value": "NVD-CWE-noinfo"}]}
        ],
        "references": [
            {"url": "https://example.org/advisory", "tags": ["Vendor Advisory", "Patch"]}
        ],
        "affected": [
            {
                "source": "vendor@example.org",
                "affectedData": [
                    {
                        "vendor": "PHP",
                        "product": "PHP",
                        "versions": [
                            {
                                "version": "8.0.0",
                                "lessThan": "8.0.30",
                                "status": "affected",
                                "versionType": "custom",
                            }
                        ],
                    }
                ],
            }
        ],
        **({"cisaExploitAdd": "2026-11-01"} if kev else {}),
    }


def put(catalog, value):
    with catalog.connection() as db:
        catalog.upsert(
            db, value, {"url": "https://example.org/feed", "retrieved_at": "2026-11-10T00:00:00Z"}
        )
