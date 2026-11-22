"""Reusable synthetic cve program fixtures and builders."""

ID = "CVE-2025-12345"


def ssvc(exploitation="active", timestamp="2026-11-01T12:00:00Z", identifier=ID):
    return {
        "id": identifier,
        "version": "2.0.3",
        "role": "CISA Coordinator",
        "timestamp": timestamp,
        "options": [
            {"Exploitation": exploitation},
            {"Automatable": "yes"},
            {"Technical Impact": "total"},
        ],
    }


def program(identifier=ID, exploitation="active"):
    return {
        "cveMetadata": {"cveId": identifier, "state": "PUBLISHED"},
        "containers": {
            "cna": {
                "providerMetadata": {"shortName": "Example CNA"},
                "descriptions": [{"lang": "en", "value": "Original CNA wording."}],
            },
            "adp": [
                {
                    "providerMetadata": {"shortName": "CISA-ADP"},
                    "metrics": [
                        {
                            "other": {
                                "type": "ssvc",
                                "content": ssvc(exploitation, identifier=identifier),
                            }
                        }
                    ],
                }
            ],
        },
    }


def kev(ids=(ID,), ransomware_value="Known"):
    return {
        "catalogVersion": "2026.11.06",
        "dateReleased": "2026-11-06T00:00:00Z",
        "count": len(ids),
        "vulnerabilities": [
            {
                "cveID": identifier,
                "vendorProject": "Example",
                "product": "Product",
                "vulnerabilityName": "Example issue",
                "dateAdded": "2026-11-01",
                "shortDescription": "Source text",
                "requiredAction": "Apply updates",
                "dueDate": "2026-11-20",
                "knownRansomwareCampaignUse": ransomware_value,
            }
            for identifier in ids
        ],
    }
