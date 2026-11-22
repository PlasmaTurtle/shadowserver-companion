"""Reusable synthetic cve sources fixtures and builders."""

import json
from unittest.mock import Mock

ID = "CVE-2025-12345"


def nvd(description="Exact official wording.\nSecond paragraph.", metrics=True):
    cve = {
        "id": ID,
        "sourceIdentifier": "vendor@example.com",
        "vulnStatus": "Awaiting Analysis",
        "published": "2025-05-01T00:00:00.000",
        "lastModified": "2026-01-02T01:00:00.000",
        "descriptions": [{"lang": "es", "value": "Otro"}, {"lang": "en", "value": description}],
        "references": [{"url": "https://example.com/advisory"}],
    }
    if metrics:
        cve["metrics"] = {
            "cvssMetricV31": [
                {
                    "source": "nvd@nist.gov",
                    "cvssData": {
                        "version": "3.1",
                        "baseScore": 9.8,
                        "baseSeverity": "CRITICAL",
                        "vectorString": "NVD-VECTOR",
                    },
                },
                {
                    "source": "vendor@example.com",
                    "cvssData": {
                        "version": "3.1",
                        "baseScore": 8.1,
                        "baseSeverity": "HIGH",
                        "vectorString": "VENDOR-VECTOR",
                    },
                },
            ]
        }
    return {"totalResults": 1, "vulnerabilities": [{"cve": cve}]}


def program():
    return {
        "cveMetadata": {"cveId": ID, "state": "PUBLISHED"},
        "containers": {
            "cna": {
                "providerMetadata": {"shortName": "Example CNA"},
                "descriptions": [{"lang": "en", "value": "CNA exact description"}],
            }
        },
    }


def response(data, status=200, headers=None):
    value = Mock()
    value.status_code = status
    value.headers = {"Content-Type": "application/json", **(headers or {})}
    value.__enter__ = Mock(return_value=value)
    value.__exit__ = Mock(return_value=False)
    value.iter_content.return_value = [json.dumps(data).encode()]
    return value
