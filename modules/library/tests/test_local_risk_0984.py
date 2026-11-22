"""Local risk feeds are complete, atomic, and honest evidence sources."""

from datetime import timedelta
import gzip
import hashlib
import json
import threading

import pytest

from modules.library.components.cve_catalog.risk import RiskStore, RiskTransport
from modules.library.components.cve_catalog.risk_manager import RiskManager
from modules.library.components.cve_catalog.transport import CatalogCancelled, CatalogDeferred
from modules.library.components.intelligence import acquisition, service
from modules.workspace.components.store import Store
from modules.library.tests.support.cve_sources import ID, response
from modules.library.tests.support.cve_catalog import catalog_record

from modules.library.tests.support.local_risk import NOW, epss_bytes, kev_raw, risk

OTHER = "CVE-2026-9999"


def test_lazy_reads_do_not_create_any_database(tmp_path):
    r, _ = risk(tmp_path)
    assert r.status()["epss"]["count"] == 0
    assert r.get(ID) == {"epss": None, "kev": None}
    assert r.batch([ID, OTHER])[OTHER]["kev"] is None
    assert r.extract("kev") is None
    assert not r.folder.exists()


def test_complete_feeds_preserve_dates_models_and_negative_membership(tmp_path):
    r, transport = risk(tmp_path)
    r.sync("epss")
    r.sync("kev")
    row = r.get(ID)
    assert row["epss"]["score"] == 0.7
    assert row["epss"]["score_date"] == "2026-11-10"
    assert row["epss"]["model_version"] == "v2026.06.15"
    assert row["epss"]["source"]["sha256"] == hashlib.sha256(transport.epss).hexdigest()
    assert row["kev"]["listed"] is True
    assert r.get(OTHER)["kev"]["listed"] is False
    assert r.get(OTHER)["epss"] is None
    assert r.extract("kev")["data"] == kev_raw()
    assert r.status()["epss"]["count"] == 1


@pytest.mark.parametrize(
    "bad",
    [
        epss_bytes("NaN"),
        epss_bytes("1.1"),
        epss_bytes(extra=f"{ID},0.2,0.8\n"),
        epss_bytes()[:-4],
        gzip.compress(b"cve,epss,percentile\n"),
    ],
)
def test_bad_epss_never_replaces_good_scores(tmp_path, bad):
    r, feeds = risk(tmp_path)
    r.sync("epss")
    before = r.status()["epss"]
    feeds.epss = bad
    with pytest.raises((ValueError, EOFError)):
        r.sync("epss")
    assert r.status()["epss"] == before
    assert r.get(ID)["epss"]["score"] == 0.7


def test_invalid_kev_count_and_rollback_preserve_complete_catalog(tmp_path):
    r, feeds = risk(tmp_path)
    r.sync("kev")
    old = r.extract("kev")
    raw = kev_raw()
    raw["count"] = 2
    feeds.kev = json.dumps(raw).encode()
    with pytest.raises(ValueError, match="count"):
        r.sync("kev")
    assert r.extract("kev") == old


def test_old_feed_and_cancel_cannot_move_checkpoint(tmp_path):
    r, feeds = risk(tmp_path)
    r.sync("epss")
    feeds.epss = epss_bytes(day="2026-11-09")
    with pytest.raises(ValueError, match="older"):
        r.sync("epss")
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(CatalogCancelled):
        r.sync("epss", cancel_event=cancel)
    assert r.get(ID)["epss"]["score_date"] == "2026-11-10"


def test_failed_provider_does_not_block_other_and_retry_survives_restart(tmp_path):
    r, feeds = risk(tmp_path)
    feeds.failure["epss"] = CatalogDeferred("Try tomorrow", 172800, server_requested=True)
    manager = RiskManager(r)
    manager.sync()
    manager.worker.join(3)
    assert r.get(ID)["kev"]["listed"]
    assert r.status()["epss"]["retry_at"] == "2026-11-13T04:00:00.000Z"
    manager.close()
    restored = RiskStore(tmp_path / "working", transport=feeds, clock=lambda: NOW)
    with pytest.raises(CatalogDeferred):
        restored.sync("epss")
    assert feeds.calls.count("epss") == 1


def test_schedule_only_runs_after_opt_in_and_catches_up(tmp_path):
    r, feeds = risk(tmp_path)
    manager = RiskManager(r)
    manager.start()
    assert feeds.calls == [] and not r.db.exists()
    manager.close()
    manager = RiskManager(r, enabled=lambda: True)
    manager.start()
    manager.scheduler.join(0.03)
    if manager.worker:
        manager.worker.join(3)
    assert set(feeds.calls) == {"epss", "kev"}
    manager.close()


def test_local_sources_are_immutable_and_update_bypasses_evidence_cache(tmp_path, monkeypatch):
    r, feeds = risk(tmp_path)
    r.sync("epss")
    r.sync("kev")
    working = Store(tmp_path / "working")
    monkeypatch.setattr(
        acquisition, "_response_get", lambda *a, **kw: pytest.fail("Local score triggered network")
    )
    capture = acquisition.capture_json(working, "epss:" + ID, acquisition.EPSS_URL + ID)
    assert capture.source["http_status"] is None
    assert capture.source["network_request"] is False
    assert capture.source["retrieved_at"] == "2026-11-11T04:00:00.000Z"
    old = working.path(capture.source["record_path"]).read_bytes()
    feeds.epss = epss_bytes("0.8")
    r.sync("epss")
    updated = acquisition.capture_json(working, "epss:" + ID, acquisition.EPSS_URL + ID)
    assert updated.data["data"][0]["epss"] == 0.8
    assert updated.source["revision_id"] != capture.source["revision_id"]
    assert working.path(capture.source["record_path"]).read_bytes() == old
    kev = acquisition.capture_json(working, "kev", acquisition.KEV_URL)
    assert kev.source["catalog_complete"] is True and kev.source["http_status"] is None
    assert kev.data["count"] == 1


def test_tampered_local_score_falls_back_to_existing_api(tmp_path, monkeypatch):
    r, _ = risk(tmp_path)
    r.sync("epss")
    with r.connection(write=True) as db:
        db.execute("UPDATE epss SET score=0.1")
    calls = []

    def remote(url, **kwargs):
        calls.append(url)
        return response(
            {
                "status": "OK",
                "data": [{"cve": ID, "epss": "0.4", "percentile": "0.8", "date": "2026-11-10"}],
            }
        )

    monkeypatch.setattr(acquisition, "_response_get", remote)
    value = acquisition.capture_json(
        Store(tmp_path / "working"), "epss:" + ID, acquisition.EPSS_URL + ID
    )
    assert calls == [acquisition.EPSS_URL + ID]
    assert value.source["http_status"] == 200


def test_normal_builder_enrichment_can_be_entirely_local(tmp_path, monkeypatch):
    r, _ = risk(tmp_path)
    r.sync("epss")
    r.sync("kev")
    monkeypatch.setattr(acquisition, "catalog_record", lambda *_: catalog_record())
    monkeypatch.setattr(
        acquisition, "_response_get", lambda *a, **kw: pytest.fail("Unexpected network request")
    )
    result = service.enrich(Store(tmp_path / "working"), ID)
    assert result["from_catalog"] and result["kev"] and result["epss"] == 0.7
    assert result["epss_model_version"] == "v2026.06.15"
    assert {s["publisher"] for s in result["sources"]} == {"NVD", "FIRST EPSS", "CISA KEV"}
    assert all(s["http_status"] is None for s in result["sources"])


def test_risk_redirect_cannot_leave_publisher_or_use_non_https(tmp_path, monkeypatch):
    from modules.library.components.cve_catalog import risk

    calls = []

    class Redirect:
        status_code = 302
        headers = {"Location": "http://127.0.0.1/private"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def redirect(url, **kwargs):
        calls.append(url)
        return Redirect()

    monkeypatch.setattr(risk, "_response_get", redirect)
    with pytest.raises(ValueError, match="outside"):
        RiskTransport().download("epss", tmp_path / "download")
    assert len(calls) == 1
    assert not (tmp_path / "download").exists()


def test_incomplete_local_kev_index_cannot_claim_negative_membership(tmp_path):
    r, _ = risk(tmp_path)
    r.sync("kev")
    with r.connection(write=True) as db:
        db.execute("DELETE FROM kev")
    with pytest.raises(ValueError, match="incomplete"):
        r.get(ID)
    # Captured full feed remains intact and can still answer the provider lookup.
    assert r.extract("kev")["data"]["vulnerabilities"][0]["cveID"] == ID


def test_rechecked_unchanged_kev_keeps_evidence_but_refreshes_current_status(tmp_path, monkeypatch):
    from modules.library.components.cve_catalog import risk as risk_module

    # Enrichment reopens the reference store. Its freshness clock must match
    # the writer's fixed clock, rather than aging this fixture against today.
    current = [NOW]
    monkeypatch.setattr(
        risk_module,
        "RiskStore",
        lambda root: RiskStore(root, clock=lambda: current[0]),
    )
    r, _ = risk(tmp_path)
    r.sync("epss")
    r.sync("kev")
    state = r.metadata("kev")
    state["last_success_at"] = "2026-11-01T04:00:00Z"
    r.put_metadata("kev", state)
    working = Store(tmp_path / "working")
    monkeypatch.setattr(acquisition, "catalog_record", lambda *_: catalog_record())
    monkeypatch.setattr(
        acquisition, "_response_get", lambda *a, **kw: pytest.fail("Unexpected HTTP")
    )
    first = service.enrich(working, ID)
    assert first["kev_stale"] is True
    old_source = next(s for s in first["sources"] if s["publisher"] == "CISA KEV")
    old_bytes = working.path(old_source["record_path"]).read_bytes()
    r.sync("kev")
    second = service.enrich(working, ID)
    assert second["kev_stale"] is False
    assert second["kev_checked_at"] == "2026-11-11T04:00:00.000Z"
    same_source = next(s for s in second["sources"] if s["publisher"] == "CISA KEV")
    assert same_source["revision_id"] == old_source["revision_id"]
    assert same_source["retrieved_at"] == old_source["retrieved_at"]
    assert working.path(old_source["record_path"]).read_bytes() == old_bytes
    current[0] += timedelta(days=2, seconds=1)
    aged = service.enrich(working, ID)
    assert aged["kev_stale"] is True
    assert aged["kev_checked_at"] == second["kev_checked_at"]
    aged_source = next(s for s in aged["sources"] if s["publisher"] == "CISA KEV")
    assert aged_source["revision_id"] == same_source["revision_id"]
    assert working.path(old_source["record_path"]).read_bytes() == old_bytes
