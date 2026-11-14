"""Catalog completeness, failure checkpoints and daily cache behavior."""

from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
from pathlib import Path
import threading
import time

import pytest

from workbench.cve_catalog import Catalog, CatalogManager, CatalogCancelled, CatalogDeferred
from workbench.cve_catalog.catalog import parse_meta, sync_lock
from workbench.cve_catalog.streaming import records
from workbench.cve_catalog.transport import NVDTransport, retry_seconds

NOW = datetime(2026, 11, 11, 4, 0, tzinfo=timezone.utc)


def record(identifier="CVE-2026-1234", modified="2026-11-10T01:00:00.000", status="Analyzed"):
    return {
        "id": identifier,
        "published": "2026-01-01T00:00:00.000",
        "lastModified": modified,
        "vulnStatus": status,
        "descriptions": [{"lang": "en", "value": "Apache synthetic vulnerability"}],
        "metrics": {
            "cvssMetricV31": [
                {"type": "Primary", "cvssData": {"baseScore": 9.1, "baseSeverity": "CRITICAL"}}
            ]
        },
        "additiveFutureField": {"kept": True},
    }


def feed(folder, year, entries, *, modified="2026-11-09T03:00:00Z", corrupt=False):
    folder.mkdir(exist_ok=True)
    raw = json.dumps(
        {"format": "NVD_CVE", "version": "2.0", "vulnerabilities": [{"cve": r} for r in entries]}
    ).encode()
    zipped = gzip.compress(raw)
    (folder / f"nvdcve-2.0-{year}.json.gz").write_bytes(zipped)
    digest = "0" * 64 if corrupt else hashlib.sha256(raw).hexdigest().upper()
    (folder / f"nvdcve-2.0-{year}.meta").write_text(
        f"lastModifiedDate:{modified}\nsize:{len(raw)}\ngzSize:{len(zipped)}\nsha256:{digest}\n"
    )


class Pages:
    def __init__(self, pages=None):
        self.pages = list(pages or [])
        self.calls = []

    def api_page(self, start, end, index, *, cancel_event=None):
        self.calls.append((start, end, index))
        value = self.pages.pop(0) if self.pages else []
        if isinstance(value, BaseException):
            raise value
        if isinstance(value, dict):
            body = value
        else:
            body = {
                "totalResults": len(value),
                "startIndex": index,
                "resultsPerPage": len(value),
                "vulnerabilities": [{"cve": r} for r in value],
            }
        return json.dumps(
            body
        ).encode(), "https://services.nvd.nist.gov/rest/json/cves/2.0?fixture=1"


def catalog(tmp_path, pages=None):
    transport = Pages(pages)
    return Catalog(
        tmp_path / "data",
        feed_cache=tmp_path / "feeds",
        transport=transport,
        years=[2026],
        clock=lambda: NOW,
    ), transport


def test_absent_catalog_is_lazy_and_does_not_touch_workspace(tmp_path):
    c, _ = catalog(tmp_path)
    assert c.status()["total"] == 0
    assert c.search("Apache")["items"] == []
    assert c.get("CVE-2026-1234") is None
    assert not c.folder.exists()
    assert c.folder == Path(str(tmp_path / "data") + "-reference") / "nvd"


def test_bootstrap_preserves_fields_and_catches_updates_before_download_start(tmp_path):
    c, transport = catalog(
        tmp_path, [[record(modified="2026-11-10T20:00:00.000", status="Rejected")]]
    )
    feed(tmp_path / "feeds", 2026, [record()])
    result = c.sync()
    found = c.get("CVE-2026-1234")
    assert result["total"] == 1
    assert found["cve"]["vulnStatus"] == "Rejected"
    assert found["cve"]["additiveFutureField"] == {"kept": True}
    assert found["catalog_checked_at"] == "2026-11-11T04:00:00.000Z"
    assert transport.calls[0][0] == "2026-11-09T02:55:00.000Z"
    assert c.metadata("sync_cursor") == "2026-11-11T04:00:00.000Z"
    assert c.search("Apache", severity="CRITICAL")["total"] == 1
    assert c.search("CVE-2026-")["items"][0]["status"] == "Rejected"


def test_feed_hash_failure_preserves_prior_records_and_resume_years(tmp_path):
    c, _ = catalog(tmp_path)
    feed(tmp_path / "feeds", 2026, [record()], corrupt=True)
    with c.connection() as db:
        c.upsert(db, record("CVE-2025-9999"), {"url": "old", "retrieved_at": "old"})
    with pytest.raises(ValueError, match="checksum"):
        c.sync()
    assert c.status()["years_complete"] == []
    assert c.status()["total"] == 1
    assert c.metadata("sync_cursor") is None


def test_invalid_record_rolls_back_entire_feed_and_fts(tmp_path):
    c, _ = catalog(tmp_path)
    feed(tmp_path / "feeds", 2026, [record(), {"id": "invalid"}])
    with pytest.raises(ValueError, match="invalid CVE"):
        c.sync()
    assert c.status()["total"] == 0
    assert c.search("Apache")["total"] == 0
    assert c.status()["years_complete"] == []


def test_page_failure_does_not_advance_cursor_or_partially_update(tmp_path):
    first = {
        "totalResults": 2,
        "startIndex": 0,
        "vulnerabilities": [{"cve": record(status="Rejected")}],
        "resultsPerPage": 1,
    }
    c, _ = catalog(tmp_path, [first, CatalogDeferred("NVD unavailable")])
    feed(tmp_path / "feeds", 2026, [record(modified="2026-11-09T04:00:00.000")])
    with pytest.raises(CatalogDeferred):
        c.sync()
    assert c.get("CVE-2026-1234")["cve"]["vulnStatus"] == "Analyzed"
    assert c.metadata("sync_cursor") is None
    assert c.status()["years_complete"] == [2026]


def test_pagination_overlapping_sync_and_older_records_do_not_overwrite(tmp_path):
    first = {
        "totalResults": 2,
        "startIndex": 0,
        "vulnerabilities": [{"cve": record()}],
        "resultsPerPage": 1,
    }
    second = {
        "totalResults": 2,
        "startIndex": 1,
        "vulnerabilities": [{"cve": record("CVE-2026-1235")}],
        "resultsPerPage": 1,
    }
    c, transport = catalog(tmp_path, [first, second])
    feed(tmp_path / "feeds", 2026, [record(modified="2026-11-10T22:00:00.000", status="Rejected")])
    c.sync()
    assert [p[2] for p in transport.calls] == [0, 1]
    assert c.status()["total"] == 2
    assert c.get("CVE-2026-1234")["cve"]["vulnStatus"] == "Rejected"
    c.sync()
    assert transport.calls[-1][0] == "2026-11-11T03:55:00.000Z"
    assert c.status()["total"] == 2


def test_long_gap_split_into_bounded_windows(tmp_path):
    c, transport = catalog(tmp_path)
    c.years = []
    c.put_metadata("sync_cursor", "2025-01-01T00:00:00Z")
    c.sync()
    assert len(transport.calls) > 2
    for start, end, _ in transport.calls:
        assert datetime.fromisoformat(end) - datetime.fromisoformat(start) < timedelta(days=120)
    assert c.metadata("sync_cursor") == "2026-11-11T04:00:00.000Z"


def test_changed_page_total_does_not_skip_results(tmp_path):
    c, _ = catalog(
        tmp_path,
        [
            {"totalResults": 2, "startIndex": 0, "vulnerabilities": [{"cve": record()}]},
            {
                "totalResults": 3,
                "startIndex": 1,
                "vulnerabilities": [{"cve": record("CVE-2026-1235")}],
            },
        ],
    )
    c.years = []
    c.put_metadata("sync_cursor", "2026-11-09T00:00:00Z")
    with pytest.raises(CatalogDeferred, match="count changed"):
        c.sync()
    assert c.status()["total"] == 0
    assert c.metadata("sync_cursor") == "2026-11-09T00:00:00Z"


def test_cancellation_retains_completed_year_and_stops_before_api(tmp_path):
    c, transport = catalog(tmp_path)
    feed(tmp_path / "feeds", 2026, [record()])
    event = threading.Event()

    def progress(value):
        if value.get("message") == "CVE-2026 imported":
            event.set()

    with pytest.raises(CatalogCancelled):
        c.sync(progress=progress, cancel_event=event)
    assert c.status()["years_complete"] == [2026]
    assert c.status()["total"] == 1
    assert transport.calls == []


def test_sync_lock_prevents_overlap(tmp_path):
    c, _ = catalog(tmp_path)
    c._initialize()
    with sync_lock(c.folder), pytest.raises(ValueError, match="already running"):
        c.sync()


def test_streaming_handles_chunk_boundary_and_rejects_truncation(tmp_path, monkeypatch):
    from workbench.cve_catalog import streaming

    monkeypatch.setattr(streaming, "CHUNK", 37)
    path = tmp_path / "stream.json"
    path.write_text(json.dumps({"vulnerabilities": [{"cve": record()} for _ in range(3)]}))
    assert len(list(records(path))) == 3
    path.write_text(path.read_text()[:-5])
    with pytest.raises(ValueError):
        list(records(path))


def test_missing_score_is_unknown_and_query_is_escaped(tmp_path):
    c, _ = catalog(tmp_path)
    item = record()
    item.pop("metrics")
    with c.connection() as db:
        c.upsert(db, item, {})
    assert c.search("Apache")["items"][0]["severity"] == "UNKNOWN"
    assert c.search("CVE-%")["total"] == 0
    assert c.search('Apache " OR *')["total"] == 0
    with pytest.raises(ValueError):
        c.search("x", limit=101)


def test_manager_no_opt_in_means_no_network_and_manual_failure_backoff(tmp_path):
    c, _ = catalog(tmp_path)
    attempted = []

    def fail(**kwargs):
        attempted.append(True)
        raise CatalogDeferred("Please retry", 7200)

    c.sync = fail
    manager = CatalogManager(c)
    manager.start()
    assert not attempted
    assert not c.db.exists()
    manager.sync()
    manager.worker.join(timeout=3)
    assert attempted == [True]
    assert manager.status()["job"]["status"] == "error"
    assert c.metadata("enabled") is True
    assert c.metadata("next_check_at") == "2026-11-11T06:00:00.000Z"
    manager.close()


def test_manager_due_schedule_catches_up_and_close_is_bounded(tmp_path):
    c, _ = catalog(tmp_path)
    c.set_enabled(True)
    c.put_metadata("next_check_at", "2026-11-10T00:00:00Z")
    called = threading.Event()
    c.sync = lambda **kwargs: called.set()
    manager = CatalogManager(c)
    manager.start()
    assert called.wait(2)
    manager.close()
    assert not manager.scheduler.is_alive()


def test_retry_after_and_metadata_limits():
    assert retry_seconds("7200") == 7200
    with pytest.raises(ValueError):
        parse_meta(
            b"size:999999999999\ngzSize:1\nsha256:"
            + b"a" * 64
            + b"\nlastModifiedDate:2026-11-10T00:00:00Z"
        )


def test_unavailable_catalog_does_not_break_manager_status(tmp_path):
    c, _ = catalog(tmp_path)
    c.folder.mkdir(parents=True)
    c.db.write_bytes(b"corrupt cache")
    manager = CatalogManager(c)
    assert "unavailable" in manager.status()["last_error"]
    manager.start()
    manager.close()


def test_api_uses_same_millisecond_boundaries_for_query_and_validation(tmp_path):
    item = record(modified="2026-11-10T01:00:00.123")
    c, transport = catalog(tmp_path, [[item]])
    c._initialize()
    c._window(
        datetime(2026, 11, 10, 1, 0, 0, 123999, tzinfo=timezone.utc), NOW, lambda value: None, None
    )
    assert transport.calls[0][0] == "2026-11-10T01:00:00.123Z"
    assert c.get(item["id"]) is not None


def test_orphan_staging_cleanup_only_removes_marked_owned_directories(tmp_path):
    c, _ = catalog(tmp_path)
    c.years = []
    c._initialize()
    owned = c.folder / "import-owned"
    owned.mkdir()
    (owned / ".catalog-import-owned").write_text("NVD catalog staging v1\n")
    (owned / "old.json").write_text("old partial download")
    unrelated = c.folder / "import-user"
    unrelated.mkdir()
    (unrelated / "notes.txt").write_text("keep")
    c.sync()
    assert not owned.exists()
    assert (unrelated / "notes.txt").read_text() == "keep"


def test_global_api_budget_spaces_requests_without_real_sleep(monkeypatch):
    from workbench.cve_catalog import transport

    current = [100.0]
    waited = []
    monkeypatch.setattr(transport, "_next_api", 0.0)
    monkeypatch.setattr(transport.time, "monotonic", lambda: current[0])

    def sleep(seconds):
        waited.append(seconds)
        current[0] += seconds

    monkeypatch.setattr(transport.time, "sleep", sleep)
    transport.pace_nvd()
    transport.pace_nvd()
    assert current[0] == pytest.approx(106.1)
    assert sum(waited) == pytest.approx(6.1)
    event = threading.Event()
    event.set()
    with pytest.raises(CatalogCancelled):
        transport.pace_nvd(event)


def test_transport_honors_retry_after_without_following_redirects(monkeypatch):
    from workbench.cve_catalog import transport

    captured = {}

    class Response:
        status_code = 429
        headers = {"Retry-After": "7200"}

        def close(self):
            captured["closed"] = True

    def get(url, **kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(transport.requests, "get", get)
    with pytest.raises(CatalogDeferred) as error:
        transport.NVDTransport().open(transport.FEED_BASE + "nvdcve-2.0-2026.meta")
    assert error.value.retry_after == 7200
    assert captured["allow_redirects"] is False
    assert captured["closed"] is True


def test_search_fallback_without_fts_and_future_schema_is_not_downgraded(tmp_path):
    c, _ = catalog(tmp_path)
    with c.connection() as db:
        c.put_metadata("fts_enabled", False, db=db)
        c.upsert(db, record(), {})
    assert c.search("Apache")["total"] == 1
    with c.connection() as db:
        db.execute("PRAGMA user_version=100")
    with pytest.raises(ValueError, match="newer application"):
        c.status()


def test_get_rejects_valid_json_corruption_and_wrong_identifier(tmp_path):
    c, _ = catalog(tmp_path)
    item = record()
    with c.connection() as db:
        c.upsert(db, item, {})
        item["descriptions"][0]["value"] = "tampered but valid JSON"
        raw = json.dumps(item)
        db.execute("UPDATE records SET raw_json=?", (raw,))
    with pytest.raises(ValueError, match="integrity"):
        c.get("CVE-2026-1234")
    with c.connection() as db:
        item["id"] = "CVE-2026-9999"
        raw = json.dumps(item)
        db.execute(
            "UPDATE records SET raw_json=?,raw_sha256=?",
            (raw, hashlib.sha256(raw.encode()).hexdigest()),
        )
    with pytest.raises(ValueError, match="identifier"):
        c.get("CVE-2026-1234")


def test_server_retry_after_cannot_be_bypassed_by_manual_sync_or_restart(tmp_path):
    c, transport = catalog(
        tmp_path, [CatalogDeferred("Rate limited", 172800, server_requested=True)]
    )
    c.years = []
    manager = CatalogManager(c)
    manager.sync()
    manager.worker.join(timeout=3)
    assert c.metadata("server_retry_at") == "2026-11-13T04:00:00.000Z"
    with pytest.raises(CatalogDeferred, match="paused until"):
        manager.sync()
    assert len(transport.calls) == 1
    restored, new_transport = catalog(tmp_path)
    with pytest.raises(CatalogDeferred, match="paused until"):
        restored.sync()
    assert new_transport.calls == []
    manager.close()


def test_duplicate_cve_across_pages_rolls_back_without_advancing_checkpoint(tmp_path):
    first = {"totalResults": 2, "startIndex": 0, "vulnerabilities": [{"cve": record()}]}
    duplicate = {"totalResults": 2, "startIndex": 1, "vulnerabilities": [{"cve": record()}]}
    c, _ = catalog(tmp_path, [first, duplicate])
    c.years = []
    c.put_metadata("sync_cursor", "2026-11-09T00:00:00Z")
    with pytest.raises(CatalogDeferred, match="repeated a CVE"):
        c.sync()
    assert c.metadata("sync_cursor") == "2026-11-09T00:00:00Z"
    assert c.status()["total"] == 0
