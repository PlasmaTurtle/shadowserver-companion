"""Reusable synthetic notification narrative fixtures and builders."""

from modules.investigations.components.notification_narrative_v4 import REVISION


def inputs():
    lead = {
        "company": "Example Company",
        "domain": "example.com",
        "entity_profile": {"city": "Asheville", "state": "NC"},
        "entries": [],
    }
    for n in (1, 2):
        lead["entries"].append(
            {
                "ip": f"192.0.2.{n}",
                "source": {
                    "fields": {
                        "hostname": f"vpn{n}.example.com",
                        "timestamp": "2026-11-05T13:32:00Z",
                        "protocol": "TCP",
                        "port": "443",
                        "tag": "CVE-2099-10001;example-vpn",
                        "product": "Example VPN",
                        "version": "7.0.1",
                    }
                },
            }
        )
    draft = {
        "company": "Example Company",
        "report_date": "2026-11-07",
        "cve_records": [
            {
                "id": "CVE-2099-10001",
                "verification_status": "published",
                "affected": [
                    {
                        "product": "Example VPN",
                        "versions": [
                            {"version": "7.0.0", "lessThan": "7.0.2", "status": "affected"},
                            {"version": "8.9.9", "status": "unaffected"},
                        ],
                    }
                ],
            }
        ],
    }
    return lead, draft


def case(source_id, tag, version="", severity="high"):
    lead, draft = inputs()
    lead["entries"] = lead["entries"][:1]
    entry = lead["entries"][0]
    entry["source"]["fields"].update(
        report_type=source_id, tag=tag, version=version, severity=severity
    )
    entry["source"]["fields"].pop("product")
    entry["normalized"] = {
        "profile": {"id": source_id},
        "eligibility": {"outreach_mode": "targeted"},
    }
    draft.update(narrative_revision=REVISION, outreach_template="targeted-v1")
    return lead, draft
