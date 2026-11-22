"""Synthetic evidence for domain-product contract tests; no provider or store bypasses."""

from modules.accretion.components.intake.records import (
    CandidateGroup,
    CandidateObservation,
    SourceObservation,
    observation_payload,
)
from modules.accretion.components.report import Report, ReportCandidate
from modules.attribution.components.attribution_bridge import source_coverage


def qualification_values(*, demonstration=False):
    domain = "example.example" if demonstration else "example.com"
    fields = {
        "hostname": domain,
        "ip": "8.8.8.8",
        "tag": "eol-php",
        "version": "7.3.25",
        "report_type": "scan_http_vulnerable",
    }
    if demonstration:
        fields["source_note"] = "SYNTHETIC DEMONSTRATION — no source report"
    source = SourceObservation("report.csv", "CSV", 2, fields)
    normalized = {
        "source_sha256": "a" * 64,
        "profile": {"id": "scan_http_vulnerable", "observation_kind": "vulnerability"},
        "eligibility": {"eligible": True},
    }
    observation = CandidateObservation(source, fields["ip"], False, normalized)
    candidate = ReportCandidate(
        Report("report-id", "report.csv", "a" * 64, "imports/report.csv"),
        CandidateGroup(domain, (observation,)),
    )
    attribution = {
        "result_id": "attribution-result",
        "ip": fields["ip"],
        "attribution": {"root_domain": domain, "matched_domain": domain},
        "evaluated_at": "2026-11-21T10:00:00Z",
        "snapshot_id": "registry-snapshot",
        "body_sha256": "b" * 64,
    }
    if demonstration:
        attribution["synthetic"] = True
        attribution.pop("evaluated_at")
    coverage = source_coverage(domain, [observation_payload(observation)], attribution)
    capture = {
        "capture_status": "captured",
        "http_status": 200,
        "requested_url": "https://" + domain + "/",
        "final_url": "https://" + domain + "/",
        "captured_at": "2026-11-21T10:00:00Z",
    }
    if demonstration:
        capture["synthetic"] = True
    website = {
        **capture,
        "id": "website-capture",
        "root_domain": domain,
        "path": "evidence/original.png",
        "preview_path": "evidence/preview.jpg",
        "metadata_path": "evidence/metadata.json",
        "sha256": "c" * 64,
        "preview_sha256": "d" * 64,
        "metadata_sha256": "e" * 64,
        "capture": capture,
    }
    findings = (
        {
            "entry_index": 0,
            "finding_id": None,
            "condition": "eol-php:7.3",
            "kind": "eol",
            "report_type": "scan_http_vulnerable",
            "observation_kind": "vulnerability",
            "basis": "shadowserver_report",
            "source": {"workbook": "report.csv", "sheet": "CSV", "row": 2},
        },
    )
    return {
        "candidate": candidate,
        "attribution": attribution,
        "coverage": coverage,
        "website": website,
        "findings": findings,
        "ownership_token": "current-ownership",
    }
