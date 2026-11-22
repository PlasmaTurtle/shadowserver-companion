"""Report identity stays attached to candidates through saved-job restoration."""

from dataclasses import FrozenInstanceError, replace
import json

import pytest

from modules.accretion.components.intake import (
    CandidateGroup,
    CandidateObservation,
    SourceObservation,
)
from modules.accretion.components.report import Report, ReportCandidate


def source_report(**changes):
    record = {
        "id": "report-a",
        "name": "scan_http_vulnerable.csv",
        "sha256": "a1" * 32,
        "path": "imports/report-a.csv",
        "status": "processing",
    }
    record.update(changes)
    return Report.from_record(record)


def observation(report, *, row=2, workbook=None, normalized=None):
    return CandidateObservation(
        SourceObservation(
            report.name if workbook is None else workbook,
            "CSV",
            row,
            {
                "hostname": "mail.example.com",
                "ip": "8.8.8.8",
                "tag": "CVE-2026-12345",
                "provider_extension": "unchanged",
            },
        ),
        "8.8.8.8",
        False,
        {"source_sha256": report.sha256} if normalized is None else normalized,
    )


def test_report_snapshots_identity_without_loading_the_retained_file():
    report = source_report(sha256="A1" * 32)
    assert report == Report(
        "report-a", "scan_http_vulnerable.csv", "a1" * 32, "imports/report-a.csv"
    )
    with pytest.raises(FrozenInstanceError):
        report.id = "report-b"


@pytest.mark.parametrize("field", ["id", "name", "path"])
@pytest.mark.parametrize("value", ["", " \t", None, 1])
def test_report_requires_a_complete_source_identity(field, value):
    with pytest.raises((TypeError, ValueError)):
        source_report(**{field: value})


@pytest.mark.parametrize("digest", ["", "a" * 63, "a" * 65, "g" * 64, None, 123])
def test_report_rejects_invalid_content_digest(digest):
    with pytest.raises((TypeError, ValueError)):
        source_report(sha256=digest)


def test_candidate_rejects_another_report_with_the_same_display_name():
    report = source_report()
    group = CandidateGroup("example.com", (observation(report),))
    other = replace(report, id="report-b", sha256="b2" * 32)
    with pytest.raises(ValueError, match="digest"):
        ReportCandidate(other, group)


def test_candidate_rejects_mixed_workbooks_even_when_the_digest_matches():
    report = source_report()
    group = CandidateGroup(
        "example.com",
        (observation(report), observation(report, row=3, workbook="another-report.csv")),
    )
    with pytest.raises(ValueError, match="workbook"):
        ReportCandidate(report, group)


def test_candidate_requires_typed_report_and_group():
    report = source_report()
    group = CandidateGroup("example.com", (observation(report),))
    with pytest.raises(TypeError, match="Report"):
        ReportCandidate({"id": report.id}, group)
    with pytest.raises(TypeError, match="CandidateGroup"):
        ReportCandidate(report, {"root_domain": group.root_domain})


def test_candidate_restoration_checks_identity_without_changing_saved_payload_shape():
    report = source_report()
    original = ReportCandidate(report, CandidateGroup("example.com", (observation(report),)))
    payload = json.loads(json.dumps(original.payload()))
    assert set(payload[0]) == {"source", "ip", "private_ip", "normalized"}
    assert set(payload[0]["source"]) == {"workbook", "sheet", "row", "fields"}
    restored = ReportCandidate.restore(report, "example.com", payload)
    assert restored == original
    assert restored.payload() == payload
    payload[0]["normalized"]["source_sha256"] = "b2" * 32
    with pytest.raises(ValueError, match="digest"):
        ReportCandidate.restore(report, "example.com", payload)
    assert restored.payload() == original.payload()


@pytest.mark.parametrize("normalized", [{}, {"source_sha256": None}])
def test_in_memory_observations_remain_bound_by_their_source_name(normalized):
    report = source_report()
    group = CandidateGroup("example.com", (observation(report, normalized=normalized),))
    assert ReportCandidate(report, group).group is group
    with pytest.raises(ValueError, match="workbook"):
        ReportCandidate(replace(report, name="another-report.csv"), group)
