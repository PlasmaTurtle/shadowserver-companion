"""Reusable synthetic evidence workspace fixtures and builders."""

import json
from pathlib import Path

from modules.investigations.components.appendix import Appendix
from modules.investigations.components.evidence_reader import write_evidence_reader


def evidence_package(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    evidence = root / "evidence"
    evidence.mkdir(exist_ok=True)
    appendix = Appendix()
    first = appendix.add(
        "A",
        "observation",
        "Mail exposure",
        {
            "hostname": "mail.example.test",
            "ip": "192.0.2.1",
            "tag": "CVE-2099-10001",
            "observed_at": "2026-11-10T12:00:00Z",
            "source": {"filename": "report.csv", "row": 2},
        },
    )
    repeated = appendix.add(
        "A",
        "observation",
        "Mail exposure observed again",
        {
            "hostname": "mail.example.test",
            "ip": "192.0.2.1",
            "tag": "CVE-2099-10001",
            "observed_at": "2026-11-11T12:00:00Z",
            "source": {"filename": "report-next.csv", "row": 3},
        },
    )
    appendix.add(
        "B",
        "accepted_attribution",
        "Registration",
        {
            "source": "Example registry",
            "retrieved_at": "2026-11-10T12:30:00Z",
            "review": {"decision": "accepted", "reason": "Recorded registration match"},
        },
        referenced_by=[first["id"], repeated["id"]],
    )
    data = {
        "entity_name": "Example Company",
        "domain": "example.test",
        "report_revision": 1,
        "composition": {"appendix": appendix.model()},
        "contact_research": {
            "packaged_at": "2026-11-10T13:00:00Z",
            "contacts": [
                {"value": "security@example.test", "purpose": "security", "known": False},
            ],
            "runs": [
                {
                    "id": "run-one",
                    "snapshots": [
                        {
                            "url": "https://example.test/security",
                            "status_code": 200,
                            "truncated": True,
                            "path": "evidence/contact.txt",
                            "captured_at": "2026-11-10T12:40:00Z",
                        }
                    ],
                }
            ],
        },
    }
    files = {
        "notification.pdf": b"Synthetic notification",
        "snapshot.json": json.dumps(data).encode(),
        "evidence/contact.txt": b"Security contact: security@example.test",
        "evidence/contact-research.json": json.dumps(data["contact_research"]).encode(),
        "evidence/unknown#source.json": json.dumps(
            {
                "message": '<img src="https://example.test/exfil" onerror="alert(1)">',
                "value": False,
                "count": 0,
                "null": None,
            }
        ).encode(),
        "evidence/cve.json": json.dumps(
            {
                "cveMetadata": {
                    "cveId": "CVE-2099-10001",
                    "state": "PUBLISHED",
                    "datePublished": "2026-11-01T00:00:00Z",
                },
                "containers": {
                    "cna": {"descriptions": [{"lang": "en", "value": "A concrete source finding."}]}
                },
            }
        ).encode(),
    }
    for name, raw in files.items():
        (root / name).write_bytes(raw)
    write_evidence_reader(data, root)
    return data, files
