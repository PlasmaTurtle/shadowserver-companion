"""Local and online sources agree without rewriting retained case evidence."""

from copy import deepcopy
import json
from unittest.mock import patch

import pytest

from modules.accretion.components.scoring_evidence import _metric
from modules.library.components.cve_catalog import Catalog
from modules.library.components.cve_catalog.analytics import cvss_assessments
from modules.library.components.intelligence import acquisition, adapters, local, service
from modules.library.components.intelligence.metrics import select_nvd_metric
from modules.library.components.repositories.sources import SourceRepository
from modules.library.tests.support.catalog_products import put, record
from modules.library.tests.support.cve_program import kev, ssvc
from modules.library.tests.support.cve_sources import ID, nvd, response
from modules.library.tests.support.local_risk import risk
from modules.workspace.components.store import Store


def offline(*args, **kwargs):
    pytest.fail("Saved/local source lookup unexpectedly requested the network")


def multiple_metrics():
    raw = record(ID, score=7.5)
    primary = raw["metrics"]["cvssMetricV31"][0]
    secondary = deepcopy(primary)
    secondary.update(type="Secondary", source="secondary@example.org")
    secondary["cvssData"].update(baseScore=9.8, baseSeverity="CRITICAL")
    raw["metrics"]["cvssMetricV31"].insert(0, secondary)
    return raw


@pytest.mark.parametrize("reverse", [False, True])
def test_primary_selection_agrees_across_catalog_library_and_scoring(
    tmp_path, monkeypatch, reverse
):
    store = Store(tmp_path / "working")
    catalog = Catalog(store.root)
    raw = multiple_metrics()
    if reverse:
        raw["metrics"]["cvssMetricV31"].reverse()
    before = deepcopy(raw)
    put(catalog, raw)
    monkeypatch.setattr(acquisition, "_response_get", offline)
    selected = local.local_record(store, ID)
    with catalog.connection(readonly=True) as db:
        indexed = dict(
            db.execute("SELECT score,severity FROM records WHERE id=?", (ID,)).fetchone()
        )
    assert indexed == {"score": 7.5, "severity": "HIGH"}
    assert _metric(raw) == (7.5, "HIGH")
    assert selected["cvss"] == 7.5 and selected["cvss_source"] == "nvd@nist.gov"
    assert [(v["type"], v["score"]) for v in selected["cvss_assessments"]] == [
        (v["type"], v["cvssData"]["baseScore"]) for v in raw["metrics"]["cvssMetricV31"]
    ]
    assert len(cvss_assessments(raw)) == 2
    assert selected["record"]["vulnerabilities"][0]["cve"] == before == raw


def test_metric_selection_keeps_version_priority_and_ignores_unusable_scores():
    raw = multiple_metrics()
    newest = deepcopy(raw["metrics"]["cvssMetricV31"][0])
    newest["cvssData"].update(version="4.0", baseScore=6.9, baseSeverity="MEDIUM")
    raw["metrics"]["cvssMetricV40"] = [newest]
    assert select_nvd_metric(raw) is newest  # v4 Secondary precedes v3 Primary.
    invalid = deepcopy(newest)
    invalid.update(type="Primary")
    for value in (True, float("nan"), float("inf"), -1, 11, "9.8"):
        invalid["cvssData"]["baseScore"] = value
        raw["metrics"]["cvssMetricV40"] = [invalid, newest]
        assert select_nvd_metric(raw) is newest
    raw["metrics"]["cvssMetricV40"] = [None, {"cvssData": None}, invalid]
    assert select_nvd_metric(raw)["cvssData"]["baseScore"] == 7.5


def test_local_and_online_primary_fields_are_bound_once(tmp_path, monkeypatch):
    store = Store(tmp_path / "working")
    raw = record(ID)
    raw["metrics"]["ssvcV203"] = [{"source": "CISA", "ssvcData": ssvc(identifier=ID)}]
    put(Catalog(store.root), raw)
    monkeypatch.setattr(acquisition, "_response_get", offline)
    for selected in (local.local_record(store, ID), service.verify(store, ID)):
        assert len(selected["reference_records"]) == len(raw["references"]) == 1
        assert len(selected["ssvc_assessments"]) == 1
        for entry in selected["reference_records"] + selected["ssvc_assessments"]:
            assert entry["source_revision_id"] == selected["revision_id"]
        if selected.get("local_only"):
            assert selected["selected_ssvc_assessment_id"] == selected["ssvc_assessments"][0]["id"]


def test_failed_refresh_survives_reopen_and_clears_after_success(tmp_path, monkeypatch):
    store = Store(tmp_path / "working")
    monkeypatch.setattr(acquisition, "_wait_for_nvd", lambda *a, **k: None)
    monkeypatch.setattr(acquisition, "_response_get", lambda *a, **k: response(nvd()))
    first = service.verify(store, ID)
    body = store.path(first["record_path"]).read_bytes()
    historical = SourceRepository(store).get("cve-version:" + first["revision_id"])
    monkeypatch.setattr(acquisition, "_response_get", lambda *a, **k: response({}, 503))
    failed = service.verify(store, ID, refresh=True)
    monkeypatch.setattr(acquisition, "_response_get", offline)
    reopened = Store(store.root)
    cached = service.verify(reopened, ID)
    for key in (
        "checked_at",
        "refresh_status",
        "refresh_errors",
        "refresh_attempts",
        "refresh_acquisition",
    ):
        assert cached[key] == failed[key]
    assert cached["stale"] is True and cached["from_cache"] is True
    assert cached["revision_id"] == first["revision_id"]
    assert cached["retrieved_at"] == first["retrieved_at"]
    monkeypatch.setattr(
        acquisition, "_response_get", lambda *a, **k: response(nvd("Updated source"))
    )
    refreshed = service.verify(reopened, ID, refresh=True)
    assert refreshed["description"] == "Updated source"
    assert "refresh_status" not in refreshed and not refreshed.get("stale")
    assert SourceRepository(reopened).get("cve-refresh:" + ID) is None
    assert SourceRepository(reopened).get("cve-version:" + first["revision_id"]) == historical
    assert store.path(first["record_path"]).read_bytes() == body


def test_old_refresh_outcome_cannot_describe_a_new_reference(tmp_path, monkeypatch):
    store = Store(tmp_path / "working")
    monkeypatch.setattr(acquisition, "_wait_for_nvd", lambda *a, **k: None)
    monkeypatch.setattr(acquisition, "_response_get", lambda *a, **k: response(nvd()))
    first = service.verify(store, ID)
    with store.transaction() as db:
        SourceRepository.put(
            db,
            "cve-refresh:" + ID,
            {
                **first,
                "revision_id": "different-source",
                "stale": True,
                "checked_at": "2099-01-01T00:00:00Z",
                "refresh_status": "deferred",
            },
        )
    monkeypatch.setattr(acquisition, "_response_get", offline)
    cached = service.verify(store, ID)
    assert "refresh_status" not in cached and not cached.get("stale")
    assert cached["checked_at"] == first["checked_at"]


def test_legacy_reference_reprojects_without_network_or_historical_rewrite(tmp_path, monkeypatch):
    store = Store(tmp_path / "working")
    raw = multiple_metrics()
    put(Catalog(store.root), raw)
    body, source = acquisition._capture_catalog(store, ID, "https://nvd.nist.gov/vuln/detail/" + ID)
    source["adapter_version"] = "intelligence-0.7.0-v1"
    provider = json.loads(body)
    legacy = {
        **adapters.summarize_nvd(ID, provider, source),
        "id": ID,
        "record": provider,
        "record_path": source["record_path"],
        "body_sha256": source["sha256"],
        "revision_id": source["revision_id"],
        "retrieved_at": source["retrieved_at"],
        "sources": [source],
        "checked_at": "2026-11-10T00:00:00Z",
        "from_cache": False,
    }
    for item in legacy["cvss_assessments"]:
        item.pop("type")
    first = legacy["cvss_assessments"][0]
    legacy.update(
        cvss=first["score"],
        cvss_source=first["source"],
        cvss_version=first["version"],
        vector=first["vector"],
    )
    repository = SourceRepository(store)
    with store.transaction() as db:
        repository.save_reference(db, ID, legacy)
    cache_before = repository.get("cve-reference:" + ID)
    revision_before = repository.get("cve-version:" + source["revision_id"])
    monkeypatch.setattr(acquisition, "_response_get", offline)
    current = service.verify(store, ID)
    assert current["from_cache"] and current["cvss"] == 7.5
    assert current["revision_id"] == legacy["revision_id"]
    assert current["retrieved_at"] == legacy["retrieved_at"]
    assert repository.get("cve-reference:" + ID) == cache_before
    assert repository.get("cve-version:" + source["revision_id"]) == revision_before
    assert store.path(source["record_path"]).read_bytes() == body
    invalid = {**legacy, "cvss": 1.0}
    with pytest.raises(ValueError, match="differs"):
        acquisition.validate_reference_projection(store, ID, invalid)


def test_initial_records_interprets_one_complete_kev_snapshot_per_batch(tmp_path, monkeypatch):
    ids = ["CVE-2026-10000", "CVE-2026-10001", "CVE-2026-10002"]
    reference, feeds = risk(tmp_path)
    feeds.kev = json.dumps(kev(ids[:2])).encode()
    reference.sync("kev")
    store = Store(tmp_path / "working")
    catalog = Catalog(store.root)
    for identifier in ids:
        put(catalog, record(identifier))
    monkeypatch.setattr(acquisition, "_response_get", offline)
    with (
        patch.object(local, "parse_json", wraps=local.parse_json) as parsed,
        patch.object(local, "validate_kev_catalog", wraps=local.validate_kev_catalog) as validated,
        store.transaction() as db,
    ):
        results = local.initial_records(store, ids, [], db)
    assert parsed.call_count == len(ids) + 1  # each NVD record, one entire KEV feed
    assert validated.call_count == 1
    assert [row["kev"] for row in results] == [True, True, False]
    sources = [next(s for s in row["sources"] if s["publisher"] == "CISA KEV") for row in results]
    assert len({s["revision_id"] for s in sources}) == 1
    retained = store.path(sources[0]["record_path"]).read_bytes()
    assert json.loads(retained) == kev(ids[:2])
    assert all(row["kev_catalog_complete"] and row["kev_catalog_count"] == 2 for row in results)
    with store.transaction() as db:
        preserved = local.initial_records(store, ids, results, db, preserve_existing=True)
    assert preserved == results
    assert store.path(sources[0]["record_path"]).read_bytes() == retained
