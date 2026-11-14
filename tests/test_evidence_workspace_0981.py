"""Offline evidence workspace: bounded views, exact originals and safe enhancement."""

from base64 import b64encode
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from workbench.appendix import Appendix
from workbench.evidence_reader import _generic_overview, write_evidence_reader
from workbench.evidence_reader_assets import SCRIPT


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


def test_reader_has_only_hashed_bundled_script_and_preserves_raw_sources(tmp_path):
    data, files = evidence_package(tmp_path)
    before = deepcopy(data)
    html = (tmp_path / "Evidence_Record.html").read_text()
    expected = b64encode(hashlib.sha256(SCRIPT.encode()).digest()).decode()
    assert "sha256-" + expected in html
    assert "connect-src &#x27;none&#x27;" in html
    assert html.count("<script>") == 1
    assert '<img src="https://example.test/exfil"' not in html
    assert "&lt;img src=" in html
    assert "unknown%23source.json" in html
    assert 'id="evidence-search"' in html and 'id="verify-folder"' in html
    assert "Partial capture" in html and ">200</td>" in html
    assert "A concrete source finding." in html
    assert data == before
    assert all((tmp_path / name).read_bytes() == raw for name, raw in files.items())


def test_large_generic_feeds_are_bounded_but_show_record_count():
    payload = {"data": [{"unfamiliar": str(i)} for i in range(10000)]}
    overview, fields = _generic_overview(payload)
    assert len(fields) == 81
    assert any(field["value"] == 10000 and field["label"] == "Data count" for field in overview)
    assert len(payload["data"]) == 10000


def test_malformed_cve_description_shape_does_not_break_generic_reader():
    overview, fields = _generic_overview(
        {"cveMetadata": {"cveId": "CVE-2099-1"}, "containers": {"cna": {"descriptions": 4}}}
    )
    assert any(field["value"] == "CVE-2099-1" for field in overview)
    assert fields
