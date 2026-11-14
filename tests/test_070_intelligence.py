"""Independent exploitation facts and immutable source provenance."""

import copy
import json
import threading
from unittest.mock import Mock

import pytest
import requests

from workbench.intelligence import service as sources
from workbench.intelligence import acquisition
from workbench.cve_intelligence import (
    extract_ssvc,
    select_ssvc,
    ransomware,
    validate_kev_catalog,
    signal_labels,
    reviewed_impact,
    structured_impacts,
)
from workbench.store import Store

ID = "CVE-2025-12345"
OTHER = "CVE-2025-98765"


def response(data, status=200):
    value = Mock(status_code=status, headers={"Content-Type": "application/json"})
    value.__enter__ = Mock(return_value=value)
    value.__exit__ = Mock(return_value=False)
    value.iter_content.return_value = [json.dumps(data).encode()]
    return value


def nvd(identifier=ID):
    return {
        "vulnerabilities": [
            {
                "cve": {
                    "id": identifier,
                    "vulnStatus": "Analyzed",
                    "descriptions": [
                        {
                            "lang": "en",
                            "value": "A Windows-only flaw requires feature X to permit arbitrary code execution.",
                        }
                    ],
                    "references": [
                        {
                            "url": "https://vendor.example/advisory",
                            "tags": ["Exploit", "Vendor Advisory"],
                        }
                    ],
                    "metrics": {
                        "ssvcV203": [
                            {
                                "source": "CISA",
                                "ssvcData": ssvc("none", "2025-01-01T00:00:00Z", identifier),
                            }
                        ]
                    },
                }
            }
        ]
    }


def ssvc(exploitation="active", timestamp="2026-11-01T12:00:00Z", identifier=ID):
    return {
        "id": identifier,
        "version": "2.0.3",
        "role": "CISA Coordinator",
        "timestamp": timestamp,
        "options": [
            {"Exploitation": exploitation},
            {"Automatable": "yes"},
            {"Technical Impact": "total"},
        ],
    }


def program(identifier=ID, exploitation="active"):
    return {
        "cveMetadata": {"cveId": identifier, "state": "PUBLISHED"},
        "containers": {
            "cna": {
                "providerMetadata": {"shortName": "Example CNA"},
                "descriptions": [{"lang": "en", "value": "Original CNA wording."}],
            },
            "adp": [
                {
                    "providerMetadata": {"shortName": "CISA-ADP"},
                    "metrics": [
                        {
                            "other": {
                                "type": "ssvc",
                                "content": ssvc(exploitation, identifier=identifier),
                            }
                        }
                    ],
                }
            ],
        },
    }


def kev(ids=(ID,), ransomware_value="Known"):
    return {
        "catalogVersion": "2026.11.06",
        "dateReleased": "2026-11-06T00:00:00Z",
        "count": len(ids),
        "vulnerabilities": [
            {
                "cveID": identifier,
                "vendorProject": "Example",
                "product": "Product",
                "vulnerabilityName": "Example issue",
                "dateAdded": "2026-11-01",
                "shortDescription": "Source text",
                "requiredAction": "Apply updates",
                "dueDate": "2026-11-20",
                "knownRansomwareCampaignUse": ransomware_value,
            }
            for identifier in ids
        ],
    }


@pytest.fixture(autouse=True)
def no_pacing(monkeypatch):
    monkeypatch.setattr(acquisition, "_wait_for_nvd", lambda store, cancel_event=None: None)


def routed(monkeypatch, calls, *, ransomware_value="Known"):
    def fetch(url, **kwargs):
        calls.append(url)
        identifier = OTHER if OTHER in url else ID
        if "nist.gov" in url:
            return response(nvd(identifier))
        if "mitre.org" in url:
            return response(program(identifier))
        if "first.org" in url:
            return response(
                {
                    "status": "OK",
                    "data": [
                        {"cve": identifier, "epss": "0", "percentile": "0", "date": "2026-11-05"}
                    ],
                }
            )
        return response(kev((ID, OTHER), ransomware_value))

    monkeypatch.setattr("workbench.intelligence.acquisition._response_get", fetch)


def test_supplementary_adp_despite_nvd_success_and_independent_signals(tmp_path, monkeypatch):
    calls = []
    routed(monkeypatch, calls)
    result = sources.enrich(Store(tmp_path), ID)
    assert len(calls) == 4
    assert result["source"] == "NVD"
    assert result["description"].startswith("A Windows-only")
    assert len(result["ssvc_assessments"]) == 2
    chosen = select_ssvc(result["ssvc_assessments"])
    assert chosen["exploitation"] == "active" and chosen["assessed_at"] == "2026-11-01T12:00:00Z"
    assert result["ransomware"]["status"] == "known" and result["kev"] is True
    assert result["epss"] == result["epss_percentile"] == 0.0
    assert result["epss_date"] == "2026-11-05"
    assert result["impacts"] == []  # no inference from SSVC total or description
    assert any("Exploit" in record.get("tags", []) for record in result["reference_records"])
    assert all(a["source_revision_id"] for a in result["ssvc_assessments"])
    assert result["intelligence_revision_id"]


def test_batch_shares_complete_catalog_even_when_refresh_requested(tmp_path, monkeypatch):
    calls = []
    routed(monkeypatch, calls)
    store = Store(tmp_path)
    first = sources.enrich(store, ID, refresh=True)
    second = sources.enrich(store, OTHER, refresh=True)
    assert calls.count(acquisition.KEV_URL) == 1
    assert first["ransomware"]["source_revision_id"] == second["ransomware"]["source_revision_id"]


@pytest.mark.parametrize(
    "edit",
    [
        lambda raw: raw.pop("count"),
        lambda raw: raw.update(count=99),
        lambda raw: raw.update(count=True),
        lambda raw: raw.update(catalogVersion=""),
        lambda raw: raw.update(dateReleased="bad"),
        lambda raw: raw["vulnerabilities"][0].pop("product"),
        lambda raw: raw.update(count=2, vulnerabilities=raw["vulnerabilities"] * 2),
    ],
)
def test_incomplete_or_ambiguous_catalog_rejected(edit):
    raw = kev()
    edit(raw)
    with pytest.raises(ValueError):
        validate_kev_catalog(raw)


def test_only_complete_negative_catalog_establishes_nonmembership(tmp_path, monkeypatch):
    calls = []
    routed(monkeypatch, calls)
    original = acquisition._response_get
    monkeypatch.setattr(
        "workbench.intelligence.acquisition._response_get",
        lambda url, **kw: (
            response(kev((OTHER,))) if url == acquisition.KEV_URL else original(url, **kw)
        ),
    )
    result = sources.enrich(Store(tmp_path), ID)
    assert result["kev"] is False and result["kev_catalog_complete"]
    assert result["ransomware"]["status"] == "not_supplied"
    assert result["ransomware"]["availability"] == "not_in_catalog"


@pytest.mark.parametrize(
    "value,status,label",
    [
        ("Known", "known", "Known ransomware use"),
        ("Unknown", "unknown", "Ransomware use unconfirmed by CISA"),
        (None, "not_supplied", "Ransomware use not supplied"),
        ("Possibly", "unrecognized", "Ransomware assessment requires adapter review"),
    ],
)
def test_ransomware_semantics_not_boolean(value, status, label):
    got = ransomware({"knownRansomwareCampaignUse": value})
    assert got["status"] == status and got["label"] == label and got["raw"] == value


def test_ssvc_explicit_case_choice_and_actual_date_preference():
    a = extract_ssvc(ID, program(), {"revision_id": "program-source"})
    b = extract_ssvc(ID, nvd(), {"revision_id": "nvd-source"})
    records = a + b
    saved = copy.deepcopy(records)
    assert select_ssvc(records)["id"] == a[0]["id"]
    assert select_ssvc(records, b[0]["id"])["exploitation"] == "none"
    assert records == saved
    with pytest.raises(ValueError, match="not in this source revision"):
        select_ssvc(records, "another-case-assessment")


def test_unknown_ssvc_scheme_and_value_preserved_for_review():
    raw = program()
    content = raw["containers"]["adp"][0]["metrics"][0]["other"]["content"]
    content["version"] = "3.0.0"
    content["options"][0]["Exploitation"] = "future-state"
    record = extract_ssvc(ID, raw, {"revision_id": "x"})[0]
    assert record["exploitation"] is None and record["raw_exploitation"] == "future-state"
    assert record["raw"]["version"] == "3.0.0"
    assert record["availability"] == "unrecognized"


def test_ssvc_wrong_identifier_rejected():
    raw = program()
    raw["containers"]["adp"][0]["metrics"][0]["other"]["content"]["id"] = OTHER
    with pytest.raises(ValueError, match="does not match"):
        extract_ssvc(ID, raw)


def test_missing_assessment_date_is_not_retrieval_date():
    raw = program()
    raw["containers"]["adp"][0]["metrics"][0]["other"]["content"].pop("timestamp")
    got = extract_ssvc(ID, raw, {"revision_id": "x", "retrieved_at": "2026-11-07T00:00:00Z"})[0]
    assert got["assessed_at"] is None and not got["assessment_date_valid"]


def test_failed_refresh_preserves_usable_response_and_records_no_response_attempt(
    tmp_path, monkeypatch
):
    store = Store(tmp_path)
    calls = []
    routed(monkeypatch, calls)
    first = sources.enrich(store, ID)
    old_body = store.path(first["record_path"]).read_bytes()

    def fail(*a, **k):
        raise requests.Timeout("connection timed out")

    monkeypatch.setattr("workbench.intelligence.acquisition._response_get", fail)
    second = sources.enrich(store, ID, refresh=True)
    assert second["description"] == first["description"]
    assert second["retrieved_at"] == first["retrieved_at"]
    assert second["epss_retrieved_at"] == first["epss_retrieved_at"]
    assert store.path(first["record_path"]).read_bytes() == old_body
    attempts = second["refresh_acquisition"]
    assert attempts and all(
        a["source_snapshot_id"] is None and "response" not in a for a in attempts
    )
    assert all("retrieved_at" not in a and "sha256" not in a for a in attempts)
    saved = json.loads(
        store.one(
            "SELECT payload FROM evidence_revisions WHERE key=?",
            ("intelligence-version:" + first["intelligence_revision_id"],),
        )["payload"]
    )
    assert saved["retrieved_at"] == first["retrieved_at"]


def test_no_response_attempt_is_saved_even_without_prior_record(tmp_path, monkeypatch):
    def fail(*a, **k):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr("workbench.intelligence.acquisition._response_get", fail)
    store = Store(tmp_path)
    result = sources.enrich(store, ID)
    assert result["retrieved_at"] is None
    assert result["kev"] is None
    assert result["acquisition"] and all(
        a["source_snapshot_id"] is None for a in result["acquisition"]
    )
    assert store.all("SELECT * FROM evidence_revisions WHERE key LIKE 'acquisition-version:%'")


def test_cancellation_between_providers_keeps_captured_evidence(tmp_path, monkeypatch):
    event = threading.Event()

    def fetch(url, **kw):
        event.set()
        return response(nvd())

    monkeypatch.setattr("workbench.intelligence.acquisition._response_get", fetch)
    store = Store(tmp_path)
    with pytest.raises(sources.SourceCancelled):
        sources.enrich(store, ID, cancel_event=event)
    assert store.one("SELECT * FROM cache WHERE key=?", ("cve-reference:" + ID,))


def test_rejected_primary_not_promoted_by_published_supplement(tmp_path, monkeypatch):
    def fetch(url, **kw):
        if "nist.gov" in url:
            raw = nvd()
            raw["vulnerabilities"][0]["cve"]["vulnStatus"] = "Rejected"
            return response(raw)
        if "mitre.org" in url:
            return response(program())
        if "first.org" in url:
            return response({"data": []})
        return response(kev())

    monkeypatch.setattr("workbench.intelligence.acquisition._response_get", fetch)
    result = sources.enrich(Store(tmp_path), ID)
    assert result["state"] == "REJECTED" and result["verification_status"] == "rejected"
    assert result["description"] == ""


def test_supplementary_rejection_blocks_primary_published_record(tmp_path, monkeypatch):
    calls = []
    routed(monkeypatch, calls)
    previous = acquisition._response_get

    def fetch(url, **kw):
        if "mitre.org" in url:
            return response({"cveMetadata": {"cveId": ID, "state": "REJECTED"}})
        return previous(url, **kw)

    monkeypatch.setattr("workbench.intelligence.acquisition._response_get", fetch)
    result = sources.enrich(Store(tmp_path), ID)
    assert result["verification_status"] == "rejected" and result["state_conflict"]
    assert result["description"] == ""


def test_impact_structured_or_reviewed_preserves_conditions():
    raw = program()
    raw["containers"]["cna"]["impacts"] = [
        {
            "descriptions": [
                {"lang": "en", "value": "Authentication bypass when optional SSO is enabled."}
            ]
        }
    ]
    raw["containers"]["cna"]["affected"] = [{"platforms": ["Windows"], "product": "Example"}]
    impact = structured_impacts(raw, {"revision_id": "source-1"})[0]
    assert impact["label"].endswith("SSO is enabled.") and impact["conditions"][0]["platforms"] == [
        "Windows"
    ]
    assert impact["basis"] == "explicit_structured_data"
    reviewed = reviewed_impact(
        "Authentication bypass",
        impact["source_text"],
        {"revision_id": "source-1"},
        actor="Example analyst",
        reviewed_at="2026-11-07T12:00:00Z",
        reason="Matches source description",
        conditions="SSO enabled",
    )
    assert (
        reviewed["conditions"] == "SSO enabled" and reviewed["review"]["actor"] == "Example analyst"
    )
    with pytest.raises(ValueError):
        reviewed_impact("RCE", "", {}, actor="", reviewed_at="", reason="")


def test_epss_wrong_id_does_not_enter_bank(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "workbench.intelligence.acquisition._response_get",
        lambda *a, **kw: response({"data": [{"cve": OTHER, "epss": ".8", "date": "2026-11-06"}]}),
    )
    store = Store(tmp_path)
    with pytest.raises(ValueError, match="does not match"):
        sources.cached_json(store, "epss:" + ID, acquisition.EPSS_URL + ID)
    assert store.one("SELECT * FROM cache WHERE key=?", ("risk:epss:" + ID,)) is None
