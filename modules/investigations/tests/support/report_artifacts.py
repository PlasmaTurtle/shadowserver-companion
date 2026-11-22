"""Reusable synthetic report artifacts fixtures and builders."""

import copy
import hashlib
import json
from html.parser import HTMLParser

from modules.investigations.components.report_composition import compose
from modules.investigations.components.report_layouts import CURRENT_LAYOUTS
from modules.investigations.components.reporting import default_draft
from modules.workspace.databases.workspace_defaults import DEFAULT_SETTINGS


class SourceWorkspace:
    def __init__(self, root):
        self.root = root

    def path(self, relative):
        return self.root / relative


def captured_snapshot(root):
    """A record with selected and supplementary evidence, including unknown fields."""
    data = specimen()
    data.update(
        case_id="case-fixture",
        report_revision=4,
        chronology=[],
        certification={
            "report_id": "report-fixture",
            "revision": 4,
            "certified_by": "Synthetic Analyst",
            "certified_at": "2026-11-07T12:00:00Z",
        },
    )
    root.mkdir()
    identifier = data["draft"]["cve_records"][0]["id"]
    raw = json.dumps(
        {
            "vulnerabilities": [
                {
                    "cve": {
                        "id": identifier,
                        "descriptions": [{"lang": "en", "value": "SYNTHETIC source"}],
                    }
                }
            ],
            "unknown_extension": {"values": [None, False, 0]},
        }
    ).encode()
    source = root / "source.json"
    source.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    record = data["draft"]["cve_records"][0]
    record.update(record_path="source.json", body_sha256=digest)
    record["sources"][0].update(record_path="source.json", sha256=digest)
    data["source_snapshots"] = [
        {
            "record_path": "source.json",
            "body_sha256": digest,
            "publisher": "NVD",
            "referenced_by": [identifier],
            "availability": "available",
            "record": json.loads(raw),
        }
    ]
    data["composition"]["citations"][0]["record_path"] = "source.json"
    return data, raw


def specimen(count=1, long=False, dns=False):
    lead = {"entries": [], "company": "Synthetic Example Company", "domain": "example.com"}
    draft = default_draft(lead, DEFAULT_SETTINGS)
    # Keep the historical export fixture on its original layout. Current-layout
    # adoption and end-to-end generation have their own integration coverage.
    draft.update({key: "legacy" for key in CURRENT_LAYOUTS})
    draft.update(
        sender_name="Test Analyst",
        company=lead["company"],
        narrative="Synthetic document test. No real business or exposure is represented.",
        website_verified=True,
        reviewed=True,
    )
    cves = [f"CVE-2099-{10000 + i}" for i in range(count)]
    records = []
    for ident in cves:
        body = "SYNTHETIC TEST DESCRIPTION. A fictional component is used solely to test document generation. The precise source wording, including qualifiers, must remain unchanged."
        if long:
            body += "\n\n" + (
                "This synthetic paragraph verifies that a long published description can flow across pages while preserving every word and qualifying condition. "
                * 40
            )
        records.append(
            {
                "id": ident,
                "source": "NVD",
                "verification_status": "published",
                "description": body,
                "description_contributor": "Fixture CNA",
                "public_url": "https://nvd.nist.gov/vuln/detail/" + ident,
                "retrieved_at": "2026-11-06T12:00:00Z",
                "revision_id": "test-" + ident,
                "cvss_assessments": [
                    {
                        "score": 9.8,
                        "severity": "CRITICAL",
                        "version": "3.1",
                        "source": "nvd@nist.gov",
                        "vector": "CVSS:3.1/test",
                    },
                    {
                        "score": 8.1,
                        "severity": "HIGH",
                        "version": "3.1",
                        "source": "Fixture CNA",
                        "vector": "CVSS:3.1/fixture",
                    },
                ],
                "epss": 0.1234,
                "epss_percentile": 0.8765,
                "epss_date": "2026-11-05",
                "epss_retrieved_at": "2026-11-06T12:00:00Z",
                "kev": False,
                "kev_date": "2026-11-06",
                "kev_retrieved_at": "2026-11-06T12:00:00Z",
                "sources": [
                    {
                        "publisher": "NVD",
                        "url": "https://services.nvd.nist.gov/rest/json/cves/2.0?cveId=" + ident,
                        "retrieved_at": "2026-11-06T12:00:00Z",
                    },
                    {
                        "publisher": "FIRST EPSS",
                        "public_url": "https://www.first.org/epss/",
                        "retrieved_at": "2026-11-06T12:00:00Z",
                    },
                    {
                        "publisher": "CISA KEV",
                        "public_url": "https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
                        "retrieved_at": "2026-11-06T12:00:00Z",
                    },
                ],
            }
        )
    draft["cve_records"] = records
    proof = {
        "ip": "192.0.2.1",
        "registry": "Fixture Registry",
        "source_url": "dns://192.0.2.53/example.com/A"
        if dns
        else "https://example.com/registration",
        "retrieved_at": "2026-11-06T12:00:00Z",
        "protocol": "DNS" if dns else "RDAP",
        "attribution": {"value": "contact@example.com"},
        "body_sha256": "f" * 64,
    }
    data = {
        "draft": draft,
        "profile": copy.deepcopy(DEFAULT_SETTINGS),
        "domain": "example.com",
        "demo": True,
        "cves": cves,
        "evidence": [],
        "explainers": [
            {
                "id": "context",
                "title": "General security context",
                "body": "Reusable advisory text for this synthetic test.",
                "sources": "https://www.cisa.gov/",
                "revision": 3,
            }
        ],
        "assets": [
            {
                "hostname": "example.com",
                "ip": "192.0.2.1",
                "asn": 64496,
                "location": "Example, NC, US",
                "private_ip": False,
                "protocol": "tcp",
                "port": 443,
                "version": "1.0",
                "tag": ";".join(cves) or "eol-example",
                "first_seen": "2026-11-05",
                "last_seen": "2026-11-05",
            }
        ],
        "qualified_lead": {
            "validated_leads": [
                {
                    "hostname": "example.com",
                    "entries": [
                        {"ip": "192.0.2.1", "source": {"fields": {"hostname": "example.com"}}}
                    ],
                }
            ],
            "whois": [proof],
        },
    }
    data["composition"] = compose(data)
    return data


class ReaderLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.ids = []
        self.scripts = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if tag == "a":
            self.links.append(attrs.get("href", ""))
        if tag == "script":
            self.scripts += 1
