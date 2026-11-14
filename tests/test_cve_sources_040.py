"""Source bank acceptance: exact published text, versions, failures and metrics."""

import hashlib
import json
from unittest.mock import Mock

import pytest
import requests

from workbench.intelligence import service as sources
from workbench.intelligence import acquisition
from workbench.store import Store

ID = "CVE-2025-12345"


def nvd(description="Exact official wording.\nSecond paragraph.", metrics=True):
    cve = {
        "id": ID,
        "sourceIdentifier": "vendor@example.com",
        "vulnStatus": "Awaiting Analysis",
        "published": "2025-05-01T00:00:00.000",
        "lastModified": "2026-01-02T01:00:00.000",
        "descriptions": [{"lang": "es", "value": "Otro"}, {"lang": "en", "value": description}],
        "references": [{"url": "https://example.com/advisory"}],
    }
    if metrics:
        cve["metrics"] = {
            "cvssMetricV31": [
                {
                    "source": "nvd@nist.gov",
                    "cvssData": {
                        "version": "3.1",
                        "baseScore": 9.8,
                        "baseSeverity": "CRITICAL",
                        "vectorString": "NVD-VECTOR",
                    },
                },
                {
                    "source": "vendor@example.com",
                    "cvssData": {
                        "version": "3.1",
                        "baseScore": 8.1,
                        "baseSeverity": "HIGH",
                        "vectorString": "VENDOR-VECTOR",
                    },
                },
            ]
        }
    return {"totalResults": 1, "vulnerabilities": [{"cve": cve}]}


def program():
    return {
        "cveMetadata": {"cveId": ID, "state": "PUBLISHED"},
        "containers": {
            "cna": {
                "providerMetadata": {"shortName": "Example CNA"},
                "descriptions": [{"lang": "en", "value": "CNA exact description"}],
            }
        },
    }


def response(data, status=200, headers=None):
    value = Mock()
    value.status_code = status
    value.headers = {"Content-Type": "application/json", **(headers or {})}
    value.__enter__ = Mock(return_value=value)
    value.__exit__ = Mock(return_value=False)
    value.iter_content.return_value = [json.dumps(data).encode()]
    return value


@pytest.fixture(autouse=True)
def no_test_pacing(monkeypatch):
    monkeypatch.setattr(acquisition, "_wait_for_nvd", lambda store, cancel_event=None: None)


def test_nvd_preserves_words_and_multiple_assessments_without_configuration():
    raw = nvd()
    got = sources.summarize_nvd(ID, raw)
    assert got["description"] == raw["vulnerabilities"][0]["cve"]["descriptions"][1]["value"]
    assert got["description_contributor"] == "vendor@example.com"
    assert got["source"] == "NVD" and got["verification_status"] == "published"
    assert [(v["source"], v["score"]) for v in got["cvss_assessments"]] == [
        ("nvd@nist.gov", 9.8),
        ("vendor@example.com", 8.1),
    ]
    assert got["epss"] is None and got["kev"] is None


def test_description_usable_without_scores_or_affected_products():
    assert sources.summarize_nvd(ID, nvd(metrics=False))["cvss"] is None
    assert sources.summarize(ID, program())["description"] == "CNA exact description"


def test_default_nvd_and_hash_checked_cache(tmp_path, monkeypatch):
    calls = []

    def fetch(url, **kwargs):
        calls.append(url)
        return response(nvd())

    monkeypatch.setattr("workbench.intelligence.acquisition._response_get", fetch)
    store = Store(tmp_path)
    result = sources.verify(store, ID)
    assert calls == [acquisition.NVD_URL + ID]
    assert (
        hashlib.sha256(store.path(result["record_path"]).read_bytes()).hexdigest()
        == result["body_sha256"]
    )
    cached = sources.verify(store, ID)
    assert len(calls) == 1 and cached["from_cache"]
    assert cached["revision_id"] == result["revision_id"]
    assert store.one(
        "SELECT * FROM evidence_revisions WHERE key=?", ("cve-version:" + result["revision_id"],)
    )


def test_refresh_keeps_old_revision_and_new_record_independent(tmp_path, monkeypatch):
    store = Store(tmp_path)
    monkeypatch.setattr(
        "workbench.intelligence.acquisition._response_get",
        lambda *a, **k: response(nvd("First wording")),
    )
    first = sources.verify(store, ID)
    first_file = store.path(first["record_path"]).read_bytes()
    monkeypatch.setattr(
        "workbench.intelligence.acquisition._response_get",
        lambda *a, **k: response(nvd("Revised wording")),
    )
    second = sources.verify(store, ID, refresh=True)
    assert first["revision_id"] != second["revision_id"]
    assert first["description"] == "First wording" and second["description"] == "Revised wording"
    assert store.path(first["record_path"]).read_bytes() == first_file
    old = json.loads(
        store.one(
            "SELECT payload FROM evidence_revisions WHERE key=?",
            ("cve-version:" + first["revision_id"],),
        )["payload"]
    )
    assert old["description"] == "First wording"


def test_failed_refresh_retains_actual_date_and_does_not_overwrite_bank(tmp_path, monkeypatch):
    store = Store(tmp_path)
    monkeypatch.setattr(
        "workbench.intelligence.acquisition._response_get", lambda *a, **k: response(nvd())
    )
    first = sources.verify(store, ID)
    monkeypatch.setattr(
        "workbench.intelligence.acquisition._response_get",
        lambda *a, **k: response({}, 429, {"Retry-After": "60"}),
    )
    later = sources.verify(store, ID, refresh=True)
    assert later["description"] == first["description"]
    assert later["retrieved_at"] == first["retrieved_at"]
    assert later["revision_id"] == first["revision_id"]
    assert later["stale"] and later["refresh_status"] == "deferred"
    assert sources.verify(store, ID)["revision_id"] == first["revision_id"]


def test_fallback_is_explicit_and_cited(tmp_path, monkeypatch):
    def fetch(url, **kwargs):
        return response({"vulnerabilities": []}) if "nist.gov" in url else response(program())

    monkeypatch.setattr("workbench.intelligence.acquisition._response_get", fetch)
    result = sources.verify(Store(tmp_path), ID)
    assert result["fallback"] and result["fallback_reason"]
    assert result["source"] == "CVE Program"
    assert result["sources"][0]["publisher"] == "CVE Program"
    assert result["sources"][0]["public_url"] == f"https://www.cve.org/CVERecord?id={ID}"


@pytest.mark.parametrize("status", ["Rejected", "Reserved"])
def test_unpublished_nvd_state_not_normal_vulnerability(tmp_path, monkeypatch, status):
    raw = nvd()
    raw["vulnerabilities"][0]["cve"]["vulnStatus"] = status
    monkeypatch.setattr(
        "workbench.intelligence.acquisition._response_get", lambda *a, **k: response(raw)
    )
    result = sources.verify(Store(tmp_path), ID)
    assert result["verification_status"] == status.lower()
    assert result["description"] == "" and result["cvss"] is None


def test_wrong_nvd_identifier_rejected():
    raw = nvd()
    raw["vulnerabilities"][0]["cve"]["id"] = "CVE-2025-99999"
    with pytest.raises(ValueError, match="does not match"):
        sources.summarize_nvd(ID, raw)


def test_risk_metrics_dates_percentile_and_kev_entry(tmp_path, monkeypatch):
    def fetch(url, **kwargs):
        if "services.nvd" in url:
            return response(nvd())
        if "first.org" in url:
            return response(
                {"data": [{"cve": ID, "epss": "0.30", "percentile": "0.95", "date": "2026-11-01"}]}
            )
        return response(
            {
                "dateReleased": "2026-11-02",
                "catalogVersion": "2026.11.02",
                "count": 1,
                "vulnerabilities": [
                    {
                        "cveID": ID,
                        "vendorProject": "Example",
                        "product": "Example",
                        "vulnerabilityName": "Example issue",
                        "shortDescription": "Synthetic source description",
                        "dueDate": "2026-11-15",
                        "dateAdded": "2026-10-01",
                        "requiredAction": "Apply vendor updates",
                        "knownRansomwareCampaignUse": "Unknown",
                    }
                ],
            }
        )

    monkeypatch.setattr("workbench.intelligence.acquisition._response_get", fetch)
    result = sources.enrich(Store(tmp_path), ID)
    assert result["epss"] == 0.3 and result["epss_percentile"] == 0.95
    assert result["epss_date"] == "2026-11-01" and result["epss_retrieved_at"]
    assert result["kev"] is True and result["kev_date"] == "2026-11-02"
    assert result["kev_details"]["dateAdded"] == "2026-10-01"
    assert len(result["sources"]) == 3
    assert all(s["revision_id"] and s["public_url"] for s in result["sources"])


def test_risk_failed_refresh_retains_good_data_and_original_dates(tmp_path, monkeypatch):
    store = Store(tmp_path)
    monkeypatch.setattr(
        "workbench.intelligence.acquisition._response_get",
        lambda *a, **k: response({"data": [{"cve": ID, "epss": ".4", "date": "2026-10-31"}]}),
    )
    original, stamp = sources.cached_json(store, "epss:" + ID, acquisition.EPSS_URL + ID)
    monkeypatch.setattr(
        "workbench.intelligence.acquisition._response_get", lambda *a, **k: response({}, 503)
    )
    old, old_stamp = sources.cached_json(
        store, "epss:" + ID, acquisition.EPSS_URL + ID, refresh=True
    )
    assert old == original and old_stamp == stamp
    assert store.one("SELECT * FROM cache WHERE key=?", ("risk-refresh:epss:" + ID,))


def test_incomplete_catalog_never_establishes_negative_membership(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "workbench.intelligence.acquisition._response_get",
        lambda url, **k: (
            response(nvd()) if "services.nvd" in url else response({"vulnerabilities": []})
        ),
    )
    result = sources.enrich(Store(tmp_path), ID)
    assert result["kev"] is None and result["epss"] is None


def test_nvd_empty_cisa_fields_do_not_imply_unlisted():
    assert sources.summarize_nvd(ID, nvd())["kev"] is None


def test_corrupt_old_record_is_not_used_when_refresh_fails(tmp_path, monkeypatch):
    store = Store(tmp_path)
    monkeypatch.setattr(
        "workbench.intelligence.acquisition._response_get", lambda *a, **k: response(nvd())
    )
    first = sources.verify(store, ID)
    store.path(first["record_path"]).write_text("changed")
    monkeypatch.setattr(
        "workbench.intelligence.acquisition._response_get", lambda *a, **k: response({}, 503)
    )
    result = sources.verify(store, ID, refresh=True)
    assert result["verification_status"] == "unavailable" and not result["description"]


def test_nonfinite_metrics_rejected():
    raw = nvd()
    raw["vulnerabilities"][0]["cve"]["metrics"]["cvssMetricV31"][0]["cvssData"]["baseScore"] = (
        float("nan")
    )
    with pytest.raises(ValueError):
        sources.summarize_nvd(ID, raw)


def test_retry_after_prevents_immediate_requests(tmp_path, monkeypatch):
    calls = []

    def limited(url, **kwargs):
        calls.append(url)
        return response({}, 429, {"Retry-After": "60"})

    monkeypatch.setattr("workbench.intelligence.acquisition._response_get", limited)
    store = Store(tmp_path)
    first = sources.verify(store, ID)
    second = sources.verify(store, ID, refresh=True)
    assert first["verification_status"] == second["verification_status"] == "deferred"
    assert len(calls) == 2  # one NVD and one Program request, zero immediate retries
