"""Product applicability, local indexing, distinct facets and immutable revision boundaries."""

from contextlib import closing

import hashlib
import json
import sqlite3
import threading

import pytest

from modules.library.components.cve_catalog import Catalog, CatalogCancelled, CatalogManager
from modules.library.components.cve_catalog.products import (
    identity,
    product_statements,
    version_candidate,
)

from modules.library.tests.support.catalog_products import (
    put,
    record,
)


def test_unused_queries_do_not_create_catalog(tmp_path):
    c = Catalog(tmp_path / "data")
    assert c.products()["items"] == []
    assert c.fields()["population"] == 0
    assert c.changes()["items"] == []
    assert c.assessments("CVE-2026-1234") == []
    assert c.build_index()["total"] == 0
    assert not c.folder.exists()


def test_cna_without_cpe_is_indexed_and_facets_deduplicate(tmp_path):
    c = Catalog(tmp_path / "data")
    put(c, record())
    assert c.index_status()["ready"]
    found = c.products(query="PHP")["items"]
    assert len(found) == 1 and found[0]["cve_count"] == 1
    assert found[0]["sources"] == ["CNA"]
    fields = c.fields()
    assert fields["covered"] == 1 and fields["items"] == [{"value": "CWE-79", "count": 1}]
    rows = c.field_records("weakness", "CWE-79")
    assert rows["total"] == 1
    assert c.field_records("weakness", "' OR 1=1 --")["total"] == 0
    assert c.product_cve_ids(found[0]["id"]) == {"CVE-2026-1234"}
    dossier = c.product(found[0]["id"], version="8.0.29")
    assert dossier["items"][0]["versions"][0]["match"]["state"] == "candidate"
    assert c.assessments("CVE-2026-1234")[0]["source"] == "nvd@nist.gov"


def test_unaffected_products_and_environment_cpes_do_not_become_targets(tmp_path):
    c = Catalog(tmp_path / "data")
    value = record()
    value["affected"][0]["affectedData"].append(
        {
            "vendor": "PHP",
            "product": "Not affected",
            "versions": [{"version": "*", "status": "unaffected"}],
        }
    )
    value["configurations"] = [
        {
            "operator": "AND",
            "nodes": [
                {
                    "operator": "OR",
                    "cpeMatch": [
                        {"criteria": "cpe:2.3:a:php:php:8.0.1:*:*:*:*:*:*:*", "vulnerable": True},
                        {
                            "criteria": "cpe:2.3:o:example:platform:*:*:*:*:*:*:*:*",
                            "vulnerable": False,
                        },
                    ],
                }
            ],
        }
    ]
    put(c, value)
    found = c.products(scope="all")["items"]
    assert len(found) == 1
    assert found[0]["sources"] == ["CNA", "CPE"]
    rules = list(product_statements(value))
    cpe_rule = next(rule for _, _, _, rule in rules if rule["kind"] == "CPE")
    assert version_candidate("php", "php", "8.0.1", cpe_rule)["state"] == "unresolved"


def test_version_ranges_are_conservative_and_boundaries_are_exact():
    rule = {
        "kind": "CNA",
        "status": "affected",
        "version": "8.0.0",
        "lessThan": "8.0.30",
        "versionType": "custom",
    }
    assert version_candidate("php", "php", "8.0.29", rule)["state"] == "candidate"
    assert version_candidate("php", "php", "8.0.30", rule)["state"] == "not_matched"
    assert version_candidate("php", "php", "8.0.9-custom", rule)["state"] == "unresolved"
    assert version_candidate("other", "custom product", "8.0.9", rule)["state"] == "unresolved"
    assert (
        version_candidate(
            "php", "php", "8.0.9", {**rule, "changes": [{"at": "8.0.8", "status": "unaffected"}]}
        )["state"]
        == "unresolved"
    )
    assert (
        version_candidate(
            "Microsoft",
            "Exchange Server",
            "15.00.1395.011",
            {**rule, "version": "15.00.0", "lessThan": "15.00.1395.012"},
        )["state"]
        == "candidate"
    )


def test_changes_ignore_timestamp_only_and_update_indexes_atomically(tmp_path):
    c = Catalog(tmp_path / "data")
    value = record()
    put(c, value)
    value["lastModified"] = "2026-11-11T00:00:00Z"
    put(c, value)
    assert c.changes()["total"] == 0
    value["lastModified"] = "2026-11-12T00:00:00Z"
    value["affected"][0]["affectedData"][0]["versions"][0]["lessThan"] = "8.0.31"
    put(c, value)
    change = c.changes()["items"][0]
    assert [field["field"] for field in change["fields"]] == ["affected"]
    assert change["previous_sha256"] != change["current_sha256"]
    value["lastModified"] = "2026-11-13T00:00:00Z"
    value["vulnStatus"] = "Rejected"
    put(c, value)
    assert c.products(scope="all")["items"] == []
    assert c.fields(scope="all")["population"] == 0
    assert c.get(value["id"])["cve"]["vulnStatus"] == "Rejected"


def test_index_migrates_existing_records_in_resumable_batches(tmp_path):
    c = Catalog(tmp_path / "data")
    for i in range(4):
        put(c, record(f"CVE-2026-{1000 + i}"))
    with c.connection() as db:
        for table in ("catalog_indexed", "catalog_product_cves", "catalog_facets", "catalog_cvss"):
            db.execute(f"DELETE FROM {table}")
    stopped = threading.Event()

    def progress(_):
        stopped.set()

    with pytest.raises(CatalogCancelled):
        c.build_index(cancel_event=stopped, progress=progress, batch_size=2)
    assert c.index_status()["indexed"] == 2
    assert c.build_index(batch_size=2)["ready"]
    assert c.products()["items"][0]["cve_count"] == 4
    with c.connection() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1


def test_same_cve_must_be_critical_and_kev(tmp_path):
    c = Catalog(tmp_path / "data")
    put(c, record("CVE-2026-1000", score=9.8, kev=False))
    put(c, record("CVE-2026-1001", score=8.0, kev=True))
    assert c.products(scope="critical_kev")["total"] == 0
    assert c.products(scope="kev")["items"][0]["cve_count"] == 1
    assert c.products(scope="critical")["items"][0]["kev_count"] == 0


def test_cisa_feed_join_overrides_embedded_kev_and_exposes_local_epss(tmp_path):
    c = Catalog(tmp_path / "data")
    put(c, record("CVE-2026-1000", kev=True))
    risk = sqlite3.connect(c.folder / "risk.sqlite3")
    risk.executescript(
        "CREATE TABLE kev(id TEXT PRIMARY KEY,raw_json TEXT,raw_sha256 TEXT);CREATE TABLE epss(id TEXT PRIMARY KEY,score REAL,percentile REAL,score_date TEXT,model_version TEXT,raw_sha256 TEXT);CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT)"
    )
    risk.execute(
        "INSERT INTO metadata VALUES('kev',?)",
        (json.dumps({"last_success_at": "2026-11-11T00:00:00Z", "count": 0}),),
    )
    from modules.library.components.cve_catalog.risk import digest

    checksum = digest(
        {
            "cve": "CVE-2026-1000",
            "epss": 0.9,
            "percentile": 0.99,
            "date": "2026-11-11",
            "model_version": "v4",
        }
    )
    risk.execute(
        "INSERT INTO epss VALUES('CVE-2026-1000',0.9,0.99,'2026-11-11','v4',?)", (checksum,)
    )
    risk.commit()
    risk.close()
    assert c.products(scope="critical_kev")["total"] == 0
    item = c.product(identity("php", "php"))["items"][0]
    assert item["epss"]["score"] == 0.9 and item["kev"] is False
    assert item["kev_source"] == "CISA KEV"


def test_candidate_subset_applies_before_limit(tmp_path):
    c = Catalog(tmp_path / "data")
    for i in range(5):
        put(c, record(f"CVE-2026-{1000 + i}"))
    result = c.candidate_matches(
        identity("php", "php"), "8.0.9", cve_ids=["CVE-2026-1004"], limit=1
    )
    assert result["total"] == 1 and result["items"][0]["cve_id"] == "CVE-2026-1004"
    assert result["items"][0]["state"] == "candidate"


def test_corrupt_record_does_not_supply_version_evidence(tmp_path):
    c = Catalog(tmp_path / "data")
    put(c, record())
    with c.connection() as db:
        db.execute("UPDATE records SET raw_json='{}'")
    assert c.product(identity("php", "php"))["items"] == []
    assert c.index_status()["ready"] is False


def test_unknown_vendors_are_not_merged_across_publishers():
    first, second = record(), record("CVE-2026-1235")
    for value in (first, second):
        value["affected"][0]["affectedData"][0].pop("vendor")
    second["affected"][0]["source"] = "different@example.org"
    assert list(product_statements(first))[0][0] != list(product_statements(second))[0][0]


def test_risk_refresh_cannot_change_a_selected_query_generation(tmp_path, monkeypatch):
    from modules.library.components.cve_catalog.risk import encoded, digest

    c = Catalog(tmp_path / "data")
    put(c, record("CVE-2026-1000", kev=True))
    path = c.folder / "risk.sqlite3"
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(
            "CREATE TABLE kev(id TEXT PRIMARY KEY,raw_json TEXT,raw_sha256 TEXT);CREATE TABLE epss(id TEXT PRIMARY KEY,score REAL,percentile REAL,score_date TEXT,model_version TEXT,raw_sha256 TEXT);CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT)"
        )
        entry = {"cveID": "CVE-2026-1000", "vendorProject": "PHP", "product": "PHP"}
        db.execute("INSERT INTO kev VALUES(?,?,?)", (entry["cveID"], encoded(entry), digest(entry)))
        db.execute(
            "INSERT INTO metadata VALUES('kev',?)",
            (encoded({"last_success_at": "2026-11-11T00:00:00Z", "count": 1}),),
        )
    original = c._risk_sql

    def refresh_after_snapshot(db):
        context = original(db)
        with closing(sqlite3.connect(path)) as writer, writer:
            writer.execute("DELETE FROM kev")
            writer.execute(
                "UPDATE metadata SET value=? WHERE key='kev'",
                (encoded({"last_success_at": "2026-11-12T00:00:00Z", "count": 0}),),
            )
        return context

    monkeypatch.setattr(c, "_risk_sql", refresh_after_snapshot)
    result = c.product(identity("php", "php"), scope="critical_kev")
    assert result["total"] == 1
    assert result["items"][0]["kev"] is True
    assert result["items"][0]["kev_detail"]["source"]["count"] == 1
    assert result["items"][0]["kev_detail"]["entry"]["cveID"] == "CVE-2026-1000"


def test_identical_feed_repairs_a_tampered_raw_record(tmp_path):
    c = Catalog(tmp_path / "data")
    value = record()
    put(c, value)
    with c.connection() as db:
        db.execute("UPDATE records SET raw_json='{}'")
    put(c, value)
    assert c.get(value["id"])["cve"] == value
    assert c.changes()["total"] == 0


def test_seed_copy_restores_wal_before_background_indexing(tmp_path):
    c = Catalog(tmp_path / "data")
    put(c, record())
    with closing(sqlite3.connect(c.db)) as db, db:
        assert db.execute("PRAGMA journal_mode=DELETE").fetchone()[0] == "delete"
    assert c.index_status()["ready"]
    with closing(sqlite3.connect(c.db)) as db:
        assert db.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    # Manager composition initializes/migrates; passive readers leave storage alone.
    CatalogManager(c)
    with closing(sqlite3.connect(c.db)) as db, db:
        assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_older_release_updates_invalidate_and_rebuild_derived_data(tmp_path):
    import hashlib

    c = Catalog(tmp_path / "data")
    value = record()
    put(c, value)
    c.build_index()
    value["affected"][0]["affectedData"][0]["product"] = "Changed product"
    value["lastModified"] = "2026-11-12T00:00:00Z"
    raw = json.dumps(value, sort_keys=True)
    with closing(sqlite3.connect(c.db)) as old_release, old_release:
        old_release.execute(
            "UPDATE records SET raw_json=?,raw_sha256=?,modified=? WHERE id=?",
            (raw, hashlib.sha256(raw.encode()).hexdigest(), value["lastModified"], value["id"]),
        )
    assert c.index_status()["ready"] is False
    assert c.products()["total"] == 0
    assert c.build_index()["ready"] is True
    assert c.products()["items"][0]["product"] == "Changed product"


def test_older_delete_and_reused_rowid_insert_are_reindexed(tmp_path):
    import hashlib

    c = Catalog(tmp_path / "data")
    old, new = record(), record("CVE-2026-5678")
    put(c, old)
    c.build_index()
    raw = json.dumps(new, sort_keys=True)
    with closing(sqlite3.connect(c.db)) as previous, previous:
        previous.execute("DELETE FROM records WHERE id=?", (old["id"],))
        previous.execute(
            "INSERT INTO records VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                new["id"],
                "New record",
                "Analyzed",
                new["published"],
                new["lastModified"],
                "CRITICAL",
                9.8,
                raw,
                hashlib.sha256(raw.encode()).hexdigest(),
                "{}",
            ),
        )
    assert c.index_status()["ready"] is False
    assert c.build_index()["ready"] is True
    assert c.product_cve_ids(identity("php", "php")) == {new["id"]}
