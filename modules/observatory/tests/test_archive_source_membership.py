"""Canonical rejected findings and archive copies describe one source event."""

from copy import deepcopy

from modules.accretion.components.dark_matter_store import DarkMatterStore
from modules.observatory.components.observatory_dark_matter import append_records, project_record


def locate(_fields):
    return 35.2, -80.8, "reported_coordinates", "", ""


def archived(tmp_path):
    archive = DarkMatterStore(tmp_path)
    source = {
        "import_id": "scan",
        "sha256": "a" * 64,
        "name": "scan.csv",
        "report_type": "scan_http_vulnerable",
    }
    fields = {
        "ip": "8.8.8.8",
        "hostname": "example.com",
        "tag": "CVE-2026-1234",
        "timestamp": "2026-11-21 12:00:00",
    }
    ids = archive.record_batch(
        source,
        [{"sheet": "CSV", "row": row, "fields": fields} for row in (2, 3, 4)],
        stage="qualification",
        reason="unsupported_finding",
    )["record_ids"]
    return archive, ids


def snapshot_for(record):
    canonical = project_record(record, locate)
    canonical.update(
        id="canonical-event", observation_id="canonical-event", finding_ids=["rejected-finding"]
    )
    return {
        "observations": [canonical],
        "findings": [{"id": "rejected-finding", "admitted": False}],
        "counts": {
            "rows": 1,
            "observations": 1,
            "dark_matter_rows": 1,
            "dark_matter_observations": 1,
            "mapped_rows": 1,
            "unplaced_rows": 0,
        },
        "warnings": [],
        "coverage_complete": True,
    }


def test_same_source_is_not_counted_twice_but_distinct_source_rows_remain(tmp_path):
    archive, ids = archived(tmp_path)
    before = {key: archive.get(key) for key in ids}
    snapshot = snapshot_for(before[ids[0]])
    finding = deepcopy(snapshot["findings"])
    appended = append_records(snapshot, archive, locate, limit=100)
    assert len(appended) == 2
    assert snapshot["counts"]["observations"] == 3
    assert snapshot["counts"]["dark_matter_observations"] == 3
    assert {row["source"]["source_key"] for row in snapshot["observations"]} == set(ids)
    assert snapshot["findings"] == finding
    assert snapshot["observations"][0]["finding_ids"] == ["rejected-finding"]
    assert {key: archive.get(key) for key in ids} == before
    assert not any(value["promoted"] for value in before.values())


def test_scan_limit_stays_visible_when_the_first_archive_row_is_already_represented(tmp_path):
    archive, ids = archived(tmp_path)
    snapshot = snapshot_for(archive.get(min(ids)))
    assert append_records(snapshot, archive, locate, limit=1) == []
    assert snapshot["counts"]["observations"] == 1
    assert snapshot["coverage_complete"] is False
    assert snapshot["warnings"]
