"""An interrupted catch-up resumes committed coverage without skipping seed gaps."""

from datetime import timedelta
import random
import string

import pytest

from test_cve_catalog_0983 import NOW, Pages, feed, record
from workbench.cve_catalog import Catalog, CatalogDeferred
from workbench.cve_catalog.storage import date, stamp
from workbench.cve_catalog.catalog import parse_meta
from workbench.cve_catalog.transport import CatalogTransient


def seeded_catalog(tmp_path, network):
    cache = tmp_path / "feeds"
    for year in range(2002, NOW.year + 1):
        feed(cache, year, [record(f"CVE-{year}-1234")], modified="2025-01-01T00:00:00Z")
    return Catalog(tmp_path / "data", feed_cache=cache, transport=network, clock=lambda: NOW)


def test_completed_catchup_window_is_not_replayed_after_later_failure(tmp_path):
    first = Pages([[], CatalogDeferred("Temporary upstream failure")])
    catalog = seeded_catalog(tmp_path, first)
    with pytest.raises(CatalogDeferred):
        catalog.sync()
    committed = catalog.metadata("sync_cursor")
    assert committed == first.calls[0][1]
    assert catalog.metadata("api_bootstrap_complete") is None

    resumed = Pages()
    catalog = Catalog(
        tmp_path / "data",
        feed_cache=tmp_path / "feeds",
        transport=resumed,
        clock=lambda: NOW,
    )
    catalog.sync()
    assert resumed.calls[0][0] == stamp(date(committed) - timedelta(minutes=5))
    assert catalog.metadata("sync_cursor") == stamp(NOW)
    assert catalog.status()["total"] == NOW.year - 2001


def test_changed_seed_cannot_reuse_another_seeds_coverage(tmp_path):
    network = Pages([[], CatalogDeferred("Temporary upstream failure")])
    catalog = seeded_catalog(tmp_path, network)
    with pytest.raises(CatalogDeferred):
        catalog.sync()
    with catalog.connection() as db:
        db.execute("UPDATE feeds SET sha256=? WHERE year=2002", ("f" * 64,))
    resumed = Pages()
    catalog.transport = resumed
    catalog.sync()
    assert resumed.calls[0][0] == network.calls[0][0]


def test_throttle_without_server_deadline_survives_restart_as_local_cooldown(tmp_path):
    catalog = Catalog(tmp_path / "data", transport=Pages(), clock=lambda: NOW)
    catalog._defer(CatalogDeferred("Throttled", 60, rate_limited=True))
    assert catalog.metadata("server_retry_at") is None
    assert catalog.metadata("rate_limit_retry_at") == stamp(NOW + timedelta(seconds=60))
    restored = Catalog(tmp_path / "data", transport=Pages(), clock=lambda: NOW)
    with pytest.raises(CatalogDeferred, match="paused until") as caught:
        restored.check_retry()
    assert not caught.value.server_requested
    restored.clock = lambda: NOW + timedelta(seconds=61)
    restored.check_retry()


def test_interrupted_annual_stream_restarts_file_without_duplicate_prefix(tmp_path, monkeypatch):
    from workbench.cve_catalog import transport

    monkeypatch.setattr(transport.time, "sleep", lambda delay: None)
    item = record()
    item["descriptions"][0]["value"] = "".join(
        random.Random(18).choices(string.ascii_letters + string.digits, k=200000)
    )
    cache = tmp_path / "feeds"
    feed(cache, NOW.year, [item])
    compressed = (cache / f"nvdcve-2.0-{NOW.year}.json.gz").read_bytes()
    assert len(compressed) > 80000
    meta = parse_meta((cache / f"nvdcve-2.0-{NOW.year}.meta").read_bytes())

    class Interrupted:
        attempts = 0

        def chunks(self, *args, **kwargs):
            self.attempts += 1
            if self.attempts == 1:
                yield compressed[:80000]
                raise CatalogTransient("Interrupted transfer")
            yield compressed

    network = Interrupted()
    catalog = Catalog(tmp_path / "data", transport=network)
    stage = tmp_path / "stage"
    stage.mkdir()
    unpacked = catalog._download(NOW.year, meta, stage, None)
    assert network.attempts == 2
    assert (stage / f"nvdcve-2.0-{NOW.year}.json.gz").read_bytes() == compressed
    assert unpacked.stat().st_size == meta["size"]


def test_failed_window_does_not_certify_seed_coverage(tmp_path):
    page = {
        "totalResults": 2,
        "startIndex": 0,
        "vulnerabilities": [{"cve": record()}],
    }
    network = Pages([page, CatalogDeferred("Interrupted")])
    catalog = Catalog(tmp_path / "data", transport=network, clock=lambda: NOW)
    with pytest.raises(CatalogDeferred):
        catalog._window(
            NOW - timedelta(days=2), NOW, lambda value: None, None, feed_seed="synthetic-seed"
        )
    assert catalog.metadata("sync_cursor") is None
    assert catalog.metadata("feed_catchup_seed") is None
    assert catalog.status()["total"] == 0
