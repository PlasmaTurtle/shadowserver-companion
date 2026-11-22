"""Filter spends preparation work only on candidates and preserves rejected sources."""

from tests.support.qualification import registry_factory, capture_website

import gzip
import io
import json
from zipfile import ZipFile

import pytest

from modules.accretion.components import intake_filter as filtering
from modules.accretion.components.intake.files import SourceFormatError, read_entries
from modules.accretion.components.intake_progress import overview
from modules.accretion.components.intake_service import IntakeService
from modules.accretion.components.shadowserver_reports.download import iter_rows
from modules.accretion.components.shadowserver_reports.errors import DownloadError
from modules.accretion.tests.support.intake import Registry, report, row
from modules.workspace.components.store import Store


def observation(**changes):
    return row(tag="eol-php", version="PHP/7.3.25", **changes)


def assert_no_qualification():
    raise AssertionError("No candidate group should initialize attribution")


def normalized_rows(monkeypatch):
    original = filtering.observation_envelope
    prepared = []

    def normalize(source, *args, **kwargs):
        prepared.append(source.row)
        return original(source, *args, **kwargs)

    monkeypatch.setattr(filtering, "observation_envelope", normalize)
    return prepared


def process(store, intake, rows):
    original = report(rows)
    identifier = intake.enqueue("scan_http_vulnerable.csv", original)["id"]
    intake.process(identifier)
    saved = store.one("SELECT * FROM imports WHERE id=?", (identifier,))
    assert saved["status"] == "done", saved["error"]
    assert store.path(saved["path"]).read_bytes() == original
    return saved


def test_all_rejected_groups_create_no_full_candidate_envelopes(tmp_path, monkeypatch):
    store = Store(tmp_path / "workspace")
    prepared = normalized_rows(monkeypatch)
    intake = IntakeService(
        store,
        attribution_factory=registry_factory(assert_no_qualification),
        capture=capture_website,
    )
    rows = [observation(hostname=f"host{index}.example.com") for index in range(32)]
    saved = process(store, intake, rows)
    assert prepared == []
    assert not store.all("SELECT * FROM jobs")
    assert store.dark_matter.query()["total"] == len(rows)
    assert json.loads(saved["rejected"]) == {"below_critical": len(rows)}
    assert json.loads(saved["config"])["intake_progress"]["filter_complete"]


def test_only_selected_groups_and_their_context_receive_full_envelopes(tmp_path, monkeypatch):
    store = Store(tmp_path / "workspace")
    prepared = normalized_rows(monkeypatch)
    registry = Registry()
    intake = IntakeService(
        store, attribution_factory=registry_factory(lambda: registry), capture=capture_website
    )
    rows = [
        observation(severity="critical"),
        observation(hostname="context.example.com", ip="1.1.1.1"),
        observation(hostname="rejected.another.com", ip="9.9.9.9"),
        observation(hostname="", severity="critical"),
    ]
    process(store, intake, rows)
    jobs = store.all("SELECT * FROM jobs")
    assert len(jobs) == 1 and jobs[0]["domain"] == "example.com"
    entries = json.loads(jobs[0]["payload"])
    assert [entry["source"]["row"] for entry in entries] == [2, 3]
    assert [entry["normalized"]["eligibility"]["included_as_context"] for entry in entries] == [
        False,
        True,
    ]
    assert prepared == [2, 3]
    current = overview(store)["current"]
    stats = current["stats"]
    assert current["rows_read"] == 4
    assert stats["admitted_rows"] == current["valid_rows"] == 2
    assert stats["context_rows"] == 1 and stats["filtered_rows"] == 2
    assert current["progress"]["filtered_rows"] == stats["filtered_rows"]
    with store.transaction() as db:
        db.execute(
            "UPDATE imports SET config=json_set(config, '$.intake_progress.filtered_rows', 1)"
        )
    assert overview(store)["current"]["progress"]["filtered_rows"] == 2
    assert current["groups_done"] == current["groups_total"] == 1
    assert registry.calls == ["8.8.8.8", "1.1.1.1"]
    assert store.dark_matter.query()["total"] == 4
    assert not store.all("SELECT * FROM awareness_findings")


def test_invalid_and_out_of_region_rows_keep_complete_queryable_fields(tmp_path, monkeypatch):
    store = Store(tmp_path / "workspace")
    prepared = normalized_rows(monkeypatch)
    intake = IntakeService(
        store,
        attribution_factory=registry_factory(assert_no_qualification),
        capture=capture_website,
    )
    common = observation(
        severity="critical", http_code="403", future_provider_field="complete field " * 400
    )
    rows = [
        {**common, "hostname": ""},
        {**common, "ip": "malformed-address"},
        {**common, "region": "Virginia"},
        {**common, "tag": ""},
        {**common, "region": ""},
    ]
    saved = process(store, intake, rows)
    archived = sorted(store.dark_matter.query()["items"], key=lambda item: item["source"]["row"])
    assert [item["raw_fields"] for item in archived] == rows
    assert all(item["outcome"] == "rejected" for item in archived)
    assert prepared == [] and not store.all("SELECT * FROM jobs")
    assert (
        store.dark_matter.query(filters=[{"field": "http_code", "op": "eq", "value": 403}])["total"]
        == 5
    )
    assert json.loads(saved["config"])["intake_stats"]["accretion"]["discarded_rows"] == 0


@pytest.mark.parametrize("action", ["pause", "stop"])
@pytest.mark.parametrize("eligible", [False, True])
def test_interruption_during_read_publishes_no_jobs_or_filter_completion(
    tmp_path, monkeypatch, action, eligible
):
    store = Store(tmp_path / "workspace")
    intake = IntakeService(
        store,
        attribution_factory=registry_factory(assert_no_qualification),
        capture=capture_website,
    )
    original = report([observation(severity="critical" if eligible else "high")] * 300)
    identifier = intake.enqueue("scan_http_vulnerable.csv", original)["id"]
    reader = filtering.read_entries
    consumed = []

    def interrupting_reader(*args, **kwargs):
        for entry in reader(*args, **kwargs):
            consumed.append(entry.row)
            if len(consumed) == 1:
                if action == "pause":
                    with store.transaction() as db:
                        db.execute("UPDATE imports SET status='paused' WHERE id=?", (identifier,))
                else:
                    intake.stop_event.set()
            yield entry

    monkeypatch.setattr(filtering, "read_entries", interrupting_reader)
    intake.process(identifier)
    saved = store.one("SELECT * FROM imports WHERE id=?", (identifier,))
    assert saved["status"] == ("paused" if action == "pause" else "running")
    assert 0 < len(consumed) < 300
    assert not json.loads(saved["config"])["intake_progress"].get("filter_complete")
    assert not store.all("SELECT * FROM jobs")
    assert store.dark_matter.query()["total"] == 0
    assert not store.all("SELECT * FROM dark_matter_outbox")
    assert store.path(saved["path"]).read_bytes() == original


def test_malformed_csv_stops_both_readers_and_archives_source_failure(tmp_path):
    malformed = (
        b"hostname,ip,tag,version,region,severity\n"
        b'mail.example.com,8.8.8.8,eol-php,PHP/7.3.25,"North Carolina,critical\n'
    )
    api_source = tmp_path / "source.csv"
    api_source.write_bytes(malformed)
    with pytest.raises(DownloadError):
        list(iter_rows(api_source))
    with pytest.raises(SourceFormatError):
        list(read_entries(api_source, ""))
    store = Store(tmp_path / "workspace")
    intake = IntakeService(
        store,
        attribution_factory=registry_factory(assert_no_qualification),
        capture=capture_website,
    )
    identifier = intake.enqueue("scan_http_vulnerable.csv", malformed)["id"]
    intake.process(identifier)
    saved = store.one("SELECT * FROM imports WHERE id=?", (identifier,))
    assert saved["status"] == "error"
    assert not store.all("SELECT * FROM jobs")
    assert not json.loads(saved["config"])["intake_progress"].get("filter_complete")
    archived = store.dark_matter.query()["items"]
    assert len(archived) == 1
    assert archived[0]["source"]["row"] == 0
    assert archived[0]["reason"] == "invalid_report_format"
    assert archived[0]["raw_fields"]["source_error"]
    assert store.path(saved["path"]).read_bytes() == malformed


def malformed_workbook(member):
    stream = io.BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr(member, "<unfinished")
    return stream.getvalue()


@pytest.mark.parametrize(
    "name,content",
    [
        ("report.xlsx", b"this is not a workbook container"),
        ("report.xlsx", malformed_workbook("wrong-member.xml")),
        ("report.xlsx", malformed_workbook("[Content_Types].xml")),
        ("report.csv", b"hostname,ip\ninvalid-utf8,\xff\n"),
        ("report.csv.gz", gzip.compress(b"hostname,ip\nexample.com,8.8.8.8\n")[:-4]),
    ],
    ids=["invalid-zip", "missing-ooxml", "invalid-xml", "invalid-utf8", "truncated-gzip"],
)
def test_malformed_sources_use_one_archive_failure_contract(tmp_path, name, content):
    original = tmp_path / name
    original.write_bytes(content)
    with pytest.raises(SourceFormatError):
        list(read_entries(original, ""))
    # On Windows this also detects an unclosed parser/source handle.
    renamed = original.with_name("released-" + name)
    original.rename(renamed)
    assert renamed.read_bytes() == content
    store = Store(tmp_path / "workspace")
    intake = IntakeService(
        store,
        attribution_factory=registry_factory(assert_no_qualification),
        capture=capture_website,
    )
    identifier = intake.enqueue(name, content)["id"]
    intake.process(identifier)
    saved = store.one("SELECT * FROM imports WHERE id=?", (identifier,))
    assert saved["status"] == "error"
    assert not json.loads(saved["config"])["intake_progress"].get("filter_complete")
    assert not store.all("SELECT * FROM jobs")
    records = store.dark_matter.query()["items"]
    assert len(records) == 1
    assert records[0]["source"]["row"] == 0
    assert records[0]["reason"] == "invalid_report_format"
    assert records[0]["raw_fields"]["source_error"]
    assert store.path(saved["path"]).read_bytes() == content


def test_unavailable_source_remains_an_io_failure(tmp_path):
    with pytest.raises(FileNotFoundError):
        list(read_entries(tmp_path / "missing.csv", ""))
