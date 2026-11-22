"""Actual catalog coverage, read snapshots, and public-feed acquisition outcomes."""

from contextlib import contextmanager
import json
import sqlite3
from urllib.parse import urlsplit

import pytest

from modules.library.components.cve_catalog import Catalog, CatalogManager
from modules.library.components.cve_catalog.products import version_candidate
from modules.library.components.cve_catalog.transport import NVDTransport, API_URL
from modules.library.tests.support.cve_catalog import NOW, feed, record


def test_search_page_and_count_share_one_committed_snapshot(tmp_path, monkeypatch):
    catalog = Catalog(tmp_path / "work")
    original = catalog.connection
    with original() as db:
        catalog.upsert(db, record("CVE-2026-10001"), {})
    inserted = False

    class Count:
        def __init__(self, cursor):
            self.cursor = cursor

        def fetchone(self):
            nonlocal inserted
            value = self.cursor.fetchone()
            if not inserted:
                inserted = True
                with original() as writer:
                    catalog.upsert(writer, record("CVE-2026-10002"), {})
            return value

    class Connection:
        def __init__(self, db):
            self.db = db

        def execute(self, sql, args=()):
            result = self.db.execute(sql, args)
            return Count(result) if sql.startswith("SELECT count(*) FROM records r") else result

    @contextmanager
    def interleaved(**kwargs):
        with original(**kwargs) as db:
            yield Connection(db)

    monkeypatch.setattr(catalog, "connection", interleaved)
    page = catalog.search()
    assert inserted
    assert page["total"] == len(page["items"]) == 1
    assert [r["id"] for r in page["items"]] == ["CVE-2026-10001"]
    assert catalog.search()["total"] == 2


def test_queries_do_not_initialize_or_write_catalog(tmp_path, monkeypatch):
    catalog = Catalog(tmp_path / "work")
    with catalog.connection() as db:
        catalog.upsert(db, record(), {})
    monkeypatch.setattr(catalog, "_initialize", lambda: pytest.fail("Read initialized catalog"))
    assert catalog.status()["total"] == 1
    assert catalog.search()["total"] == 1
    assert catalog.get("CVE-2026-1234")["cve"]["id"] == "CVE-2026-1234"
    assert catalog.index_status()["ready"]
    assert catalog.fields(scope="all")["population"] == 1
    assert catalog.changes()["items"] == []
    with catalog.connection(readonly=True) as db:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            db.execute("UPDATE records SET description='unwanted'")


def test_index_reports_partial_coverage_then_recovers(tmp_path):
    catalog = Catalog(tmp_path / "work")
    good, damaged = record("CVE-2026-10001"), record("CVE-2026-10002")
    with catalog.connection() as db:
        catalog.upsert(db, good, {})
        catalog.upsert(db, damaged, {})
        db.execute("UPDATE records SET raw_json='{}' WHERE id=?", (damaged["id"],))
    manager = CatalogManager(catalog)
    manager._index()
    assert manager.index_job["status"] == "partial"
    assert manager.index_job["coverage"]["errors"] == 1
    assert manager.index_job["coverage"]["indexed"] == 1
    with catalog.connection() as db:
        catalog.upsert(db, damaged, {})
    manager._index()
    assert manager.index_job["status"] == "complete"
    assert manager.index_job["coverage"]["ready"] is True


def test_public_feed_bootstrap_then_incremental_sync_needs_no_key(tmp_path):
    files = tmp_path / "provider"
    for year in range(2002, NOW.year + 1):
        feed(files, year, [record(f"CVE-{year}-10001")])

    class PublicFeeds(NVDTransport):
        def __init__(self):
            super().__init__(lambda: "")
            self.requests = []

        def bytes(self, url, **kwargs):
            self.requests.append(url)
            if url.startswith(API_URL):
                return json.dumps(
                    {"totalResults": 0, "startIndex": 0, "resultsPerPage": 0, "vulnerabilities": []}
                ).encode()
            return (files / urlsplit(url).path.rsplit("/", 1)[-1]).read_bytes()

        def chunks(self, url, **kwargs):
            yield self.bytes(url, **kwargs)

    provider = PublicFeeds()
    catalog = Catalog(tmp_path / "work", transport=provider, clock=lambda: NOW)
    result = catalog.sync()
    assert result["bootstrap_complete"] and result["total"] == NOW.year - 2001
    provider.requests.clear()
    catalog.sync()
    assert provider.requests and all(url.startswith(API_URL) for url in provider.requests)
    assert catalog.get("CVE-2026-10001")["cve"]["id"] == "CVE-2026-10001"


@pytest.mark.parametrize(
    "observed,state",
    [
        ("1.2.3-rc.1", "candidate"),
        ("1.2.3+build.8", "candidate"),
        ("1.2.3.4", "unresolved"),
        ("01.2.3", "unresolved"),
        ("2.0.0", "not_matched"),
    ],
)
def test_declared_semver_uses_native_scheme_precedence(observed, state):
    rule = {
        "kind": "CNA",
        "version": "1.2.3-rc.0",
        "lessThan": "2.0.0",
        "versionType": "semver",
        "status": "affected",
    }
    assert version_candidate("Example", "Example", observed, rule)["state"] == state


def test_semver_status_changes_are_sorted_and_build_metadata_is_not_precedence():
    rule = {
        "kind": "CNA",
        "version": "0",
        "lessThan": "*",
        "versionType": "semver",
        "status": "affected",
        "changes": [{"at": "2.0.0", "status": "affected"}, {"at": "1.5.0", "status": "unaffected"}],
    }
    assert version_candidate("Example", "Example", "1.6.0", rule)["state"] == "not_matched"
    assert version_candidate("Example", "Example", "2.1.0", rule)["state"] == "candidate"
    exact = {"kind": "CNA", "versionType": "semver", "version": "1.2.3", "status": "affected"}
    assert version_candidate("Example", "Example", "1.2.3+build.4", exact)["state"] == "candidate"


@pytest.mark.parametrize(
    "initial,changed,before,after",
    [
        ("unaffected", "affected", "not_matched", "candidate"),
        ("affected", "unaffected", "candidate", "not_matched"),
        ("unaffected", "unknown", "not_matched", "unresolved"),
    ],
)
def test_indexed_product_compares_semver_status_transitions(
    tmp_path, initial, changed, before, after
):
    catalog = Catalog(tmp_path / "work")
    cve = record()
    cve["affected"] = [
        {
            "vendor": "Example",
            "product": "Example Server",
            "versions": [
                {
                    "version": "1.0.0",
                    "lessThan": "3.0.0",
                    "versionType": "semver",
                    "status": initial,
                    "changes": [{"at": "2.0.0", "status": changed}],
                }
            ],
        }
    ]
    with catalog.connection() as db:
        catalog.upsert(db, cve, {})
    found = catalog.products("Example Server", scope="all")
    assert found["total"] == 1
    identity = found["items"][0]["id"]
    for version, expected in (("1.5.0", before), ("2.1.0", after)):
        detail = catalog.product(identity, scope="all", version=version)
        assert detail["total"] == 1
        assert detail["items"][0]["id"] == cve["id"]
        assert detail["items"][0]["versions"][0]["match"]["state"] == expected


def test_old_complete_index_rebuilds_changed_product_membership_without_changing_source(tmp_path):
    catalog = Catalog(tmp_path / "work")
    cve = record()
    cve["affected"] = [
        {
            "vendor": "Example",
            "product": "Example Server",
            "versions": [
                {
                    "version": "1.0.0",
                    "lessThan": "3.0.0",
                    "versionType": "semver",
                    "status": "unaffected",
                    "changes": [{"at": "2.0.0", "status": "affected"}],
                }
            ],
        },
        {
            "vendor": "Example",
            "product": "Unaffected Client",
            "versions": [
                {
                    "version": "1.0.0",
                    "lessThan": "3.0.0",
                    "versionType": "semver",
                    "status": "unaffected",
                    "changes": [{"at": "2.0.0", "status": "unaffected"}],
                }
            ],
        },
    ]
    with catalog.connection() as db:
        catalog.upsert(db, cve, {})
        raw = tuple(db.execute("SELECT raw_json,raw_sha256 FROM records").fetchone())
        # Version2 marked this raw record indexed but omitted its affected product.
        db.execute("DELETE FROM catalog_product_cves")
        db.execute("DELETE FROM catalog_product_aliases")
        db.execute("DELETE FROM catalog_products")
        catalog.put_metadata("analytics_schema", 2, db=db)
        catalog.put_metadata("analytics_cursor", 1, db=db)
        catalog.put_metadata("analytics_analyzed", 2, db=db)
    assert catalog.index_status()["ready"]
    assert catalog.products("Example", scope="all")["total"] == 0

    reopened = Catalog(catalog.workspace_root)
    assert reopened.build_index(batch_size=1)["ready"]
    products = reopened.products("Example", scope="all")
    assert products["total"] == 1
    assert products["items"][0]["product"] == "Example Server"
    detail = reopened.product(products["items"][0]["id"], scope="all", version="2.1.0")
    assert detail["items"][0]["versions"][0]["match"]["state"] == "candidate"
    with reopened.connection(readonly=True) as db:
        assert tuple(db.execute("SELECT raw_json,raw_sha256 FROM records").fetchone()) == raw
        assert reopened.metadata("analytics_schema", db=db) == 3
        assert db.execute("SELECT count(*) FROM catalog_changes").fetchone()[0] == 0
    assert reopened.build_index(batch_size=1)["ready"]
    assert reopened.products("Example", scope="all")["total"] == 1
