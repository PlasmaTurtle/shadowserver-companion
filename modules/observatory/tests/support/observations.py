"""Reusable synthetic observations fixtures and builders."""

import csv
import io

from modules.accretion.components.awareness import associate
from tests.support.qualification import WhoisRecord
from modules.accretion.components.intake_service import IntakeService
from modules.workspace.components.primitives import now


class Registry:
    def lookup(self, ip):
        return WhoisRecord(
            ip, "TEST", "https://example.test/registration", now(), {"contact": "admin@example.com"}
        )

    def close(self):
        pass


def csv_data(rows):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode()


def base(**overrides):
    return {
        "report_type": "scan_http_vulnerable",
        "severity": "critical",
        "http_code": "200",
        "hostname": "mail.example.com",
        "ip": "8.8.8.8",
        "tag": "eol-php",
        "version": "7.3.25",
        "region": "North Carolina",
        "city": "",
        "geo": "US",
        "asn": "15169",
        "timestamp": "2026-11-04 01:02:03",
        "latitude": "35.2",
        "longitude": "-80.8",
        "extra_source_field": "preserved value",
        **overrides,
    }


def add(store, fields, *, admitted=True, filename="observations.csv", reason=""):
    job = IntakeService(store).enqueue(filename, csv_data([fields]))
    source = store.one("SELECT * FROM imports WHERE id=?", (job["id"],))
    entry = {
        "ip": fields["ip"],
        "source": {"workbook": filename, "sheet": "CSV", "row": 2, "fields": fields},
    }
    with store.transaction() as db:
        result = associate(
            db,
            entry,
            import_id=job["id"],
            source_sha256=source["sha256"],
            admitted=admitted,
            reason=reason,
        )
    return result


def observation(identity, **changes):
    row = {
        "id": identity,
        "ip": "8.8.8.8",
        "ip_valid": True,
        "hostname": "web.alpha.example",
        "domain": "alpha.example",
        "tag": "CVE-2026-10001",
        "version": "1.0",
        "product": "Example Web",
        "protocol": "tcp",
        "port": "443",
        "observed_at": "2026-01-01T12:00:00Z",
        "observed_day": "2026-01-01",
        "imported_at": "2026-11-11T12:00:00Z",
        "entity_id": "entity-alpha",
        "entity_name": "Alpha",
        "case_id": None,
        "lead_id": "lead-alpha",
        "job_id": None,
        "status": "qualified",
        "latitude": 35.2,
        "longitude": -80.8,
        "location_basis": "reported_coordinates",
        "source_available": True,
        "original_url": "/api/imports/import-one/original",
        "source": {
            "import_id": "import-one",
            "workbook": "observations.csv",
            "sheet": "",
            "row": 2,
            "sha256": "a" * 64,
        },
    }
    row.update(changes)
    return row


def snapshot(rows):
    return {
        "schema_version": 2,
        "generated_at": "2026-11-11T12:00:00Z",
        "observations": rows,
        "entities": [
            {"id": "entity-alpha", "name": "Alpha", "domain": "alpha.example", "case_ids": []},
            {"id": "entity-beta", "name": "Beta", "domain": "beta.example", "case_ids": []},
        ],
        "imports": [],
        "counts": {"rows": len(rows)},
        "coverage_complete": True,
        "warnings": [],
    }


DOMAINS = [
    "aster-fabrication.com",
    "meridian-care.com",
    "harbor-energy.com",
    "northline-logistics.com",
    "cedar-research.com",
    "summit-foundry.com",
]


class SyntheticRegistry:
    def lookup(self, address):
        index = min(5, max(0, int(address.split(".")[2]) - 1))
        return WhoisRecord(
            address,
            "TEST REGISTRY",
            "https://example.test/synthetic-registration",
            now(),
            {
                "contact": "security@" + DOMAINS[index],
                "startAddress": address,
                "endAddress": address,
                "notice": "Synthetic local fixture. No network lookup performed.",
            },
        )

    def close(self):
        pass
