"""Synthetic intake regressions; no user reports or external requests."""

import csv
import hashlib
import io
import json
from unittest.mock import Mock, patch

import pytest

from excel_intake import ExcelReader, LeadRuntime, UnvalidatedEntry, is_empty_entry
from workbench.intake_service import IntakeService
from workbench.store import Store


HEADERS = ("severity", "http_code", "tag", "hostname", "ip", "region", "version", "future_column")


def source_rows():
    base = dict(
        severity="critical",
        http_code="200",
        tag="eol-php",
        hostname="mail.example.com",
        ip="8.8.8.8",
        region="North Carolina",
        version="7.3.25",
        future_column="preserve",
    )
    empty = dict.fromkeys(HEADERS, "")
    return [
        base,
        empty,
        dict.fromkeys(HEADERS, " \t "),
        {**empty, "future_column": "incomplete observation"},
        {**base, "hostname": "mail2.example.com", "tag": "CVE-2024-12345", "version": ""},
        {**empty, "future_column": 0},
        {**empty, "future_column": False},
    ]


@pytest.mark.parametrize(
    "value, expected",
    [
        (None, True),
        ("", True),
        (" \t\n", True),
        (0, False),
        (False, False),
        ("data", False),
    ],
)
def test_empty_entry_checks_all_fields_without_discarding_zero_or_false(value, expected):
    entry = UnvalidatedEntry(
        "synthetic.xlsx", "Observations", 2, {**dict.fromkeys(HEADERS), "future_column": value}
    )
    assert is_empty_entry(entry) is expected


def test_runtime_counts_observations_and_retains_original_row_numbers(tmp_path):
    path = tmp_path / "synthetic.xlsx"
    path.write_bytes(b"synthetic loader fixture")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    sheet = Mock(title="Observations")
    sheet.iter_rows.return_value = iter(
        [HEADERS, *[tuple(row[name] for name in HEADERS) for row in source_rows()]]
    )
    workbook = Mock(worksheets=[sheet])
    lookup = Mock(return_value=None)
    runtime = LeadRuntime({"North Carolina"}, lookup)
    with patch("workbench.intake.files.load_workbook", return_value=workbook):
        runtime.run([path])
    assert runtime.run_log["rows_read"] == 5
    assert runtime.run_log["ignored_empty_rows"] == 2
    assert runtime.run_log["validated_entries"] == 2
    assert runtime.run_log["rejected_entries"] == 3
    assert runtime.run_log["rejection_reasons"] == {"missing_required_value": 3}
    assert runtime.run_log["hostname_groups"] == 1
    assert before == hashlib.sha256(path.read_bytes()).hexdigest()
    workbook.close.assert_called_once()

    # The reader preserves physical row provenance and every field; only the
    # intake pipeline distinguishes spreadsheet padding from observations.
    sheet.iter_rows.return_value = iter(
        [HEADERS, *[tuple(row[name] for name in HEADERS) for row in source_rows()]]
    )
    with patch("workbench.intake.files.load_workbook", return_value=workbook):
        entries = list(ExcelReader().read(path))
    assert [entry.row for entry in entries if not is_empty_entry(entry)] == [2, 5, 6, 7, 8]
    assert entries[4].fields["hostname"] == "mail2.example.com"
    assert entries[4].fields["version"] == ""
    assert entries[0].fields["future_column"] == "preserve"
    assert all(set(entry.fields) == set(HEADERS) for entry in entries)


def test_persistent_csv_intake_keeps_ignored_count_separate_and_preserves_input(tmp_path):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=HEADERS)
    writer.writeheader()
    writer.writerows(source_rows())
    original = buffer.getvalue().encode()
    store = Store(tmp_path / "data")
    registry = Mock()
    registry.lookup.return_value = None
    service = IntakeService(store, lookup_factory=lambda: registry)
    import_id = service.enqueue("synthetic-scan_http_vulnerable.csv", original)["id"]
    service.process(import_id)
    result = store.one("SELECT * FROM imports WHERE id=?", (import_id,))
    assert result["status"] == "done", result["error"]
    assert result["rows_read"] == 5
    assert result["valid_rows"] == 2
    assert json.loads(result["rejected"]) == {"missing_required_value": 3}
    assert json.loads(result["config"])["intake_stats"]["ignored_empty_rows"] == 2
    assert store.path(result["path"]).read_bytes() == original
    jobs = store.all("SELECT payload FROM jobs WHERE import_id=?", (import_id,))
    assert len(jobs) == 1
    entries = json.loads(jobs[0]["payload"])
    assert [entry["source"]["row"] for entry in entries] == [2, 6]
    assert entries[1]["source"]["fields"]["hostname"] == "mail2.example.com"
    assert entries[1]["source"]["fields"]["version"] == ""
    assert entries[0]["source"]["fields"]["future_column"] == "preserve"
