"""Production import references compare DNS identity without rewriting source rows."""

import io
import json
import socket
from types import SimpleNamespace

import pytest
from openpyxl import Workbook

from attribution import DnsProvider, RdapProvider
from modules.attribution.components.attribution_bridge import checked_result
from modules.accretion.components.intake_service import IntakeService
from modules.workspace.components.store import Store
from modules.workspace.components.workspace_data_attribution import validate_attribution_data
from modules.accretion.tests.support.intake import row


@pytest.mark.parametrize(
    ("saved", "expected"),
    [
        ("example.com", "EXAMPLE.COM"),
        ("EXAMPLE.COM", "example.com."),
        ("xn--bcher-kva.de", "BÜCHER.DE"),
        ("bücher.de", "XN--BCHER-KVA.DE"),
        ("example.xn--p1ai", "EXAMPLE.РФ"),
    ],
)
def test_attribution_reference_compares_exact_case_and_idna_identity(saved, expected):
    record = {"result_id": "result", "root_domain": saved}
    store = SimpleNamespace(result=lambda identifier: record)
    assert checked_result(store, "result", expected) is record
    assert record["root_domain"] == saved


@pytest.mark.parametrize(
    ("saved", "expected", "saved_id"),
    [
        ("example.com", "unrelated.com", "result"),
        ("example.com", "sub.example.com", "result"),
        ("example.com", "example.com.evil.org", "result"),
        ("example.com", "notexample.com", "result"),
        ("example.com", "https://example.com", "result"),
        (None, None, "result"),
        ("", "", "result"),
        ("example.com", "EXAMPLE.COM", "wrong-result"),
    ],
)
def test_reference_rejects_unrelated_invalid_and_wrong_result_ids(saved, expected, saved_id):
    store = SimpleNamespace(result=lambda identifier: {"result_id": saved_id, "root_domain": saved})
    with pytest.raises(ValueError, match="does not belong"):
        checked_result(store, "result", expected)


def test_normal_xlsx_import_and_restore_validation_with_production_attribution(
    tmp_path, monkeypatch
):
    def no_network(*args, **kwargs):
        raise AssertionError("Nonpublic observations must not invoke any network/provider lookup")

    monkeypatch.setattr(RdapProvider, "collect", no_network)
    monkeypatch.setattr(DnsProvider, "collect", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    store = Store(tmp_path / "workspace")
    rows = [
        row(
            hostname=host,
            ip="192.168.1.10",
            tag="eol-php",
            version="PHP/5.6.40",
            severity="critical",
        )
        for host in (
            "WWW.EXAMPLE.COM",
            "MAIL2.BUSINESS123.ORG",
            "WWW.XN--BCHER-KVA.DE",
            "WWW.EXAMPLE.XN--P1AI",
        )
    ]
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(list(rows[0]))
    for fields in rows:
        sheet.append(list(fields.values()))
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    original = buffer.getvalue()
    intake = IntakeService(store)  # Exercise the default production attribution adapter.
    identifier = intake.enqueue("scan_http_vulnerable.xlsx", original)["id"]
    intake.process(identifier)
    saved = store.one("SELECT * FROM imports WHERE id=?", (identifier,))
    assert saved["status"] == "done", saved["error"]
    assert saved["valid_rows"] == 4 and saved["groups_total"] == 4
    assert store.path(saved["path"]).read_bytes() == original
    jobs = store.all("SELECT * FROM jobs WHERE import_id=? ORDER BY rowid", (identifier,))
    assert all(job["status"] == "no_public_ip" for job in jobs)
    for job, fields in zip(jobs, rows, strict=True):
        assert job["domain"] == job["domain"].upper()
        assert job["attribution_result_id"] is None, "Local exclusion must not open Attribution"
        assert json.loads(job["attempts"])[0]["status"] == "no_public_ip"
        payload = json.loads(job["payload"])
        assert payload[0]["source"]["fields"]["hostname"] == fields["hostname"]
    validate_attribution_data(store)
