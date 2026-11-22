"""Reference changes locate exact retained case selections without adopting them."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from modules.entities.tests.support.contacts import entity_only
from modules.library.components.cve_catalog import Catalog
from modules.library.components.cve_catalog.risk import RiskStore
from modules.library.components.intelligence.adapters import summarize_nvd
from modules.library.components.reference_changes import ReferenceChanges
from modules.library.components.routes.reference_changes import register
from modules.library.tests.support.catalog_products import put, record
from modules.library.tests.support.local_risk import Feeds, kev_raw
from modules.workspace.components.store import Store

ID = "CVE-2026-1234"


def pinned(raw):
    data = {"vulnerabilities": [{"cve": raw}]}
    return {
        **summarize_nvd(raw["id"], data),
        "id": raw["id"],
        "record": data,
        "revision_id": "source-" + raw["id"],
        "intelligence_revision_id": "selection-" + raw["id"],
    }


def case(store, identity, records, *, stage="in_progress", certified=False):
    with store.transaction() as db:
        db.execute(
            "INSERT INTO cases(id,entity_id,title,stage,created_at,updated_at,draft) VALUES(?,?,?,?,?,?,?)",
            (
                identity,
                "entity",
                "Case " + identity,
                stage,
                "2026-01-01",
                "2026-11-20",
                json.dumps({"cve_records": records}),
            ),
        )
        if certified:
            revision = db.execute(
                "SELECT COALESCE(MAX(revision),0)+1 FROM reports WHERE lead_id='entity'"
            ).fetchone()[0]
            db.execute(
                "INSERT INTO reports(id,lead_id,entity_id,case_id,revision,created_at,path) VALUES(?,?,?,?,?,?,?)",
                (
                    "report-" + identity,
                    "entity",
                    "entity",
                    identity,
                    revision,
                    "2026-11-20",
                    "reports/" + identity,
                ),
            )
            db.execute(
                "UPDATE cases SET certified_report_id=? WHERE id=?",
                ("report-" + identity, identity),
            )
    if certified:
        folder = store.root / "reports" / identity
        folder.mkdir(parents=True)
        (folder / "snapshot.json").write_text(
            json.dumps({"cve_records": records}), encoding="utf-8"
        )


@pytest.fixture
def data(tmp_path):
    store = Store(tmp_path / "working")
    entity_only(store, "entity", "example.com")
    catalog = Catalog(store.root)
    return store, catalog


def database_dump(store):
    with store.read_snapshot() as db:
        return "\n".join(db.iterdump())


def test_changed_current_record_locates_exact_active_and_certified_cases_without_writes(data):
    store, catalog = data
    old = record(ID, score=7.5)
    current = deepcopy(old)
    current.update(vulnStatus="Rejected", lastModified="2026-11-21T00:00:00Z")
    current["metrics"]["cvssMetricV31"][0]["cvssData"]["baseScore"] = 9.8
    current["affected"][0]["affectedData"][0]["versions"][0]["lessThan"] = "8.0.40"
    current["references"].append({"url": "https://example.com/new-remediation"})
    put(catalog, current)
    case(store, "active", [pinned(old)])
    case(store, "certified", [pinned(old)], stage="pending_notification", certified=True)
    case(store, "unchanged", [pinned(current)])
    case(store, "prefix-only", [pinned(record(ID + "0"))])
    case(store, "shared", [pinned(old), pinned(record("CVE-2026-9999"))])
    case(store, "completed", [pinned(old)], stage="notification_completed", certified=True)
    case(store, "closed", [pinned(old)], stage="closed", certified=True)
    before = database_dump(store)
    catalog_before = hashlib.sha256(catalog.db.read_bytes()).hexdigest()
    snapshots = {p: p.read_bytes() for p in store.root.glob("reports/*/snapshot.json")}
    changes = ReferenceChanges(store, SimpleNamespace(catalog=catalog))
    first = changes.impact(ID, limit=2)
    second = changes.impact(ID, limit=2, offset=2)
    assert first["cases"]["total"] == second["cases"]["total"] == 4
    items = {row["id"]: row for row in first["cases"]["items"] + second["cases"]["items"]}
    assert set(items) == {"active", "certified", "unchanged", "shared"}
    assert items["unchanged"]["nvd_changed"] is False
    assert items["unchanged"]["changed"] is None  # KEV was never selected or imported.
    assert items["certified"]["certified"] and items["certified"]["stage"] == "pending_notification"
    assert {c["field"] for c in items["active"]["changes"]} == {
        "status",
        "assessments",
        "versions",
        "references",
    }
    assert items["active"]["pinned_source_revision_id"] == "source-" + ID
    assert first["current"]["status"] == "Rejected"
    assert first["observations_url"] == "#eclipse?cve=" + ID
    assert changes.impact(ID, include_completed=True)["cases"]["total"] == 6
    assert database_dump(store) == before
    assert hashlib.sha256(catalog.db.read_bytes()).hexdigest() == catalog_before
    assert all(path.read_bytes() == body for path, body in snapshots.items())


def test_missing_reference_and_uncomparable_source_are_explicit(data):
    store, catalog = data
    case(store, "unknown", [{"id": ID, "source": "CVE Program", "revision_id": "old-program"}])
    missing = ReferenceChanges(store, SimpleNamespace(catalog=catalog)).impact(ID)
    assert missing["current"]["available"] is False
    assert missing["cases"]["items"][0]["changed"] is None
    assert not catalog.db.exists()  # A read of missing reference data never initializes it.
    put(catalog, record(ID))
    current = ReferenceChanges(store, SimpleNamespace(catalog=catalog)).impact(ID)
    assert current["current"]["available"] is True
    assert current["cases"]["items"][0]["changed"] is None
    assert "no comparable" in current["cases"]["items"][0]["reason"]


def test_route_is_bounded_and_reports_case_coverage(data):
    store, catalog = data
    put(catalog, record(ID))
    case(store, "normal", [pinned(record(ID))])
    case(store, "without-selected-source", [])
    app = FastAPI()
    register(app, store=store, catalog=SimpleNamespace(catalog=catalog))
    with TestClient(app) as client:
        got = client.get("/api/library/changes/" + ID + "/impact?limit=1").json()
        assert got["cases"]["total"] == 1 and len(got["cases"]["items"]) == 1
        assert got["cases"]["coverage_complete"] is True
        assert got["cases"]["unreadable_cases"] == 0
        assert client.get("/api/library/changes/" + ID + "/impact?limit=101").status_code == 422
        assert client.get("/api/library/changes/" + ID + "/impact?offset=-1").status_code == 422
    with pytest.raises(ValueError, match="identifier"):
        ReferenceChanges(store, SimpleNamespace(catalog=catalog)).impact(
            "CVE-2026-1234 trailing text"
        )


def test_impact_route_is_wired_behind_the_workspace_session(tmp_path):
    from modules.workspace.components.api import create_app
    from tests.session_helpers import TestClient as AuthenticatedClient

    app = create_app(tmp_path / "working", worker=False)
    route = "/api/library/changes/" + ID + "/impact"
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get(route).status_code == 401
    with AuthenticatedClient(app) as client:
        result = client.get(route)
        assert result.status_code == 200
        assert result.json()["cases"]["total"] == 0
        assert result.json()["current"]["available"] is False


def install_kev(store, *, listed, stale=False):
    release = datetime.now(timezone.utc) - timedelta(days=10 if stale else 0, minutes=1)
    raw = kev_raw()
    raw.update(catalogVersion=release.strftime("%Y.%m.%d"), dateReleased=release.isoformat())
    raw["vulnerabilities"][0].update(
        cveID=ID if listed else "CVE-2026-9999", dateAdded=release.date().isoformat()
    )
    feeds = Feeds()
    feeds.kev = json.dumps(raw).encode()
    risk = RiskStore(store.root, transport=feeds, clock=lambda: release + timedelta(minutes=1))
    risk.sync("kev")
    return risk, feeds


def file_hashes(root):
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_automatic_open_kev_changes_exclude_minor_unknown_stale_and_closed(data):
    store, catalog = data
    old = {"id": ID, "kev": False, "kev_catalog_complete": True}
    current = {"id": ID, "kev": True}
    case(store, "a", [old, old])
    case(store, "b", [{"id": ID, "kev": False}])
    case(store, "c", [old], stage="closed")
    case(store, "d", [current])
    case(store, "e", [current, old])
    case(store, "f", [dict(old, kev_retrieved_at="2099-01-01T00:00:00Z")])
    case(store, "g", [old], stage="pending_notification")
    case(store, "h", [dict(old, kev_date="2099-01-01")])
    case(store, "i", {"unexpected-object": old})
    service = ReferenceChanges(store, SimpleNamespace(catalog=catalog))
    assert service.open_kev_changes()["notice"]
    install_kev(store, listed=True, stale=True)
    assert service.open_kev_changes()["items"] == []
    install_kev(store, listed=True)
    before = database_dump(store)
    app = FastAPI()
    register(app, store=store, catalog=SimpleNamespace(catalog=catalog))
    with TestClient(app) as client:
        route = "/api/library/changes/open-kev"
        first = client.get(route, params={"limit": 1}).json()
        assert first["total"] == 2 and first["unknown"] == 4 and first["comparable"] == 3
        assert first["unreadable_cases"] == 1
        assert first["items"][0]["case_id"] == "a"
        assert first["items"][0]["previous"] is False and first["items"][0]["listed"] is True
        assert client.get(route, params={"limit": 1}).json() == first
        assert [
            row["case_id"] for row in client.get(route, params={"offset": 1}).json()["items"]
        ] == ["g"]
        assert client.get(route, params={"limit": 0}).status_code == 422
    assert database_dump(store) == before


@pytest.mark.parametrize(
    "previous,current", [(False, True), (True, False), (False, False), (True, True)]
)
def test_local_kev_membership_compares_retained_selection_without_adoption_or_fetch(
    data, previous, current
):
    store, catalog = data
    raw = record(ID)
    put(catalog, raw)
    selection = {**pinned(raw), "kev": previous, "kev_catalog_complete": True}
    case(store, "certified", [selection], stage="pending_notification", certified=True)
    risk, feeds = install_kev(store, listed=current)
    before = file_hashes(store.root)
    result = ReferenceChanges(store, SimpleNamespace(catalog=catalog)).impact(ID)
    item = result["cases"]["items"][0]
    current_kev = result["current"]["kev"]
    assert current_kev["available"] is True and current_kev["listed"] is current
    assert current_kev["stale"] is False
    assert current_kev["source"] == risk.get(ID)["kev"]["source"]
    assert current_kev["source"]["catalog_version"] and current_kev["source"]["sha256"]
    assert item["pinned_kev"] is previous
    assert item["nvd_changed"] is False
    assert item["kev_changed"] is (previous != current)
    assert item["changed"] is (previous != current)
    assert {value["field"] for value in item["changes"]} == (
        {"kev_membership"} if previous != current else set()
    )
    assert item["certified"] and item["pinned_source_revision_id"] == selection["revision_id"]
    assert feeds.calls == ["kev"]
    assert file_hashes(store.root) == before


@pytest.mark.parametrize("previous", [None, False])
def test_missing_or_legacy_default_negative_kev_is_unknown(data, previous):
    store, catalog = data
    raw = record(ID)
    put(catalog, raw)
    case(store, "legacy", [{**pinned(raw), "kev": previous}])
    install_kev(store, listed=False)
    before = file_hashes(store.root)
    item = ReferenceChanges(store, SimpleNamespace(catalog=catalog)).impact(ID)["cases"]["items"][0]
    assert item["pinned_kev"] is None
    assert item["kev_changed"] is None and item["changed"] is None
    assert "Retained KEV membership is unknown" in item["reason"]
    assert file_hashes(store.root) == before


def test_stale_local_kev_change_keeps_warning_and_source_provenance(data):
    store, catalog = data
    raw = record(ID)
    put(catalog, raw)
    case(store, "active", [{**pinned(raw), "kev": False, "kev_catalog_complete": True}])
    install_kev(store, listed=True, stale=True)
    before = file_hashes(store.root)
    result = ReferenceChanges(store, SimpleNamespace(catalog=catalog)).impact(ID)
    assert result["current"]["kev"]["stale"] is True
    assert result["current"]["kev"]["source"]["date_released"]
    item = result["cases"]["items"][0]
    assert item["kev_changed"] is True and item["changed"] is True
    assert "KEV catalog is stale" in item["reason"]
    assert "KEV catalog is stale" in result["current"]["reason"]
    assert file_hashes(store.root) == before


@pytest.mark.parametrize("corrupt", [False, True])
def test_missing_or_corrupt_local_kev_never_becomes_negative_membership(data, corrupt):
    store, catalog = data
    raw = record(ID)
    put(catalog, raw)
    case(store, "active", [{**pinned(raw), "kev": True}])
    if corrupt:
        risk, _ = install_kev(store, listed=True)
        with risk.connection(write=True) as db:
            db.execute("UPDATE kev SET raw_json='{}' WHERE id=?", (ID,))
    before = file_hashes(store.root)
    result = ReferenceChanges(store, SimpleNamespace(catalog=catalog)).impact(ID)
    item = result["cases"]["items"][0]
    assert result["current"]["kev"]["available"] is False
    assert result["current"]["kev"]["listed"] is None
    assert item["pinned_kev"] is True
    assert item["kev_changed"] is None and item["changed"] is None
    assert item["changes"] == []
    assert "integrity" in item["reason"] if corrupt else "unavailable" in item["reason"]
    assert file_hashes(store.root) == before
