"""Production feed bootstrap preserves raw fields and switches to API catchup."""

from datetime import datetime, timezone
import threading
import pytest

from modules.library.tests.support.cve_catalog import feed, record, Pages, NOW
from modules.library.components.cve_catalog import Catalog, CatalogCancelled


def test_feed_seed_completes_all_years_then_only_incremental(tmp_path):
    folder = tmp_path / "feeds"
    for year in range(2002, datetime.now(timezone.utc).year + 1):
        feed(folder, year, [record(f"CVE-{year}-1234")])
    transport = Pages()
    catalog = Catalog(tmp_path / "data", feed_cache=folder, transport=transport, clock=lambda: NOW)
    result = catalog.sync()
    assert result["bootstrap_complete"]
    assert result["download_method"] == "feeds"
    assert catalog.get("CVE-2002-1234")["cve"]["additiveFutureField"] == {"kept": True}
    assert {"download_seconds", "decompress_seconds", "parse_seconds", "index_seconds"} <= set(
        result["timings"]
    )
    # The full seed stays complete across calendar rollovers and does not need feeds again.
    for path in folder.iterdir():
        path.unlink()
    assert catalog.sync()["bootstrap_complete"]
    assert len(transport.calls) == 2


def test_interrupted_seed_keeps_completed_year_and_resumes(tmp_path):
    folder = tmp_path / "feeds"
    feed(folder, 2025, [record("CVE-2025-1234")])
    feed(folder, 2026, [record()])
    cancel = threading.Event()
    catalog = Catalog(
        tmp_path / "data",
        feed_cache=folder,
        transport=Pages(),
        years=[2025, 2026],
        clock=lambda: NOW,
    )

    def progress(value):
        if value.get("year") == 2025 and value.get("changed") == 1:
            cancel.set()

    with pytest.raises(CatalogCancelled):
        catalog.sync(cancel_event=cancel, progress=progress)
    assert catalog.status()["years_complete"] == [2025]
    (folder / "nvdcve-2.0-2025.json.gz").unlink()
    cancel.clear()
    catalog.sync(cancel_event=cancel)
    assert catalog.status()["years_complete"] == [2025, 2026]
    assert catalog.status()["total"] == 2


def test_partial_seed_cursor_cannot_skip_annual_snapshot_catchup(tmp_path):
    folder = tmp_path / "feeds"
    for year in range(2002, datetime.now(timezone.utc).year + 1):
        feed(folder, year, [record(f"CVE-{year}-1234")])
    missing = record("CVE-2026-4321", modified="2026-11-10T01:00:00.000")
    network = Pages([[missing]])
    catalog = Catalog(tmp_path / "data", feed_cache=folder, transport=network, clock=lambda: NOW)
    catalog._initialize()
    catalog.put_metadata("sync_cursor", NOW.isoformat())
    catalog.sync()
    assert network.calls[0][0] == "2026-11-09T02:55:00.000Z"
    assert catalog.get("CVE-2026-4321")
