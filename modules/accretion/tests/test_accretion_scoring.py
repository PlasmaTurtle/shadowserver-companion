"""Intake ranking keeps provenance, coherent findings and bounded policy signals."""

import hashlib
import json
import sqlite3

import pytest

from modules.accretion.components import accretion
from modules.accretion.components.intake.versions import project_conditions
from modules.library.components.cve_catalog.storage import CatalogStorage
from modules.library.components.cve_catalog.risk import RiskStore, digest

from modules.accretion.tests.support.scoring import (
    ID,
    entry,
    vetted,
)

NOW = "2026-11-12T12:00:00Z"
OTHER = "CVE-2026-5678"


def seed_catalog(path, records):
    store = CatalogStorage(path)
    with store.connection() as db:
        for identifier, score, status, corrupt in records:
            raw = json.dumps(
                {
                    "id": identifier,
                    "vulnStatus": status,
                    "metrics": {
                        "cvssMetricV31": [{"type": "Primary", "cvssData": {"baseScore": score}}]
                    },
                }
            )
            checksum = "0" * 64 if corrupt else hashlib.sha256(raw.encode()).hexdigest()
            db.execute(
                "INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    identifier,
                    "Synthetic",
                    status,
                    NOW,
                    NOW,
                    "CRITICAL",
                    score,
                    raw,
                    checksum,
                    json.dumps({"publisher": "NVD"}),
                ),
            )
        store.put_metadata("last_success_at", NOW, db=db)
    return store


def test_defaults_are_detached_bounded_and_versioned():
    policy = accretion.policy_defaults()
    policy["quality_weights"]["data"] = 99
    assert accretion.policy_defaults()["quality_weights"]["data"] == 40
    for bad in (
        {"oops": 1},
        {"quality_weights": {"data": -1}},
        {"version": True},
        {"temperature_thresholds": [60, 40, 80]},
        {"urgency_weights": {"epss": float("nan")}},
        {"priority_cities": [""]},
        {"report_bases": {"custom_report": {"value": 1.1, "reason": "Out of bounds"}}},
        {"report_bases": {"custom_report": {"value": 0.2}}},
        {"report_bases": []},
    ):
        with pytest.raises(ValueError):
            accretion.normalize_policy(bad)
    a = accretion.normalize_policy({"priority_cities": [" Burnsville ", "burnsville"]})
    assert a["priority_cities"] == ["burnsville"]
    assert accretion.policy_hash(a) == accretion.policy_hash({"priority_cities": ["burnsville"]})


def test_coherent_urgency_never_combines_different_cves():
    rows = [entry(ID + ";" + OTHER)]
    records = {
        ID: vetted(score=10, kev=False, epss=0),
        OTHER: vetted(OTHER, score=4, kev=True, epss=0),
    }
    score = accretion.score_lead(rows, cve_records=records, as_of=NOW)
    assert score["urgency"] == 51
    assert score["strongest_finding"]["id"] == OTHER
    assert score["factors"]["urgency"][0]["points"] == 16


def test_probabilities_not_percentiles_and_missing_remains_unknown():
    score = accretion.score_lead([entry()], cve_records={ID: vetted(epss=0.001)})
    assert score["factors"]["urgency"][2]["points"] == 0.015
    unknown = accretion.score_lead([entry()])
    assert unknown["cves"][0]["kev"] is None
    assert unknown["cves"][0]["epss"] is None
    assert unknown["urgency"] == 38


def test_snapshot_is_detached_stable_and_duplicates_do_not_inflate():
    records = {ID: vetted(kev=True, epss=0.9)}
    observations = [entry()]
    first = accretion.score_lead(observations, cve_records=records, as_of=NOW)
    repeated = accretion.score_lead(observations * 100, cve_records=records, as_of=NOW)
    assert first == repeated
    records[ID]["epss"]["score"] = 0
    observations[0]["normalized"]["products"][0]["version"] = "changed"
    assert first["cves"][0]["epss"]["score"] == 0.9
    json.dumps(first, allow_nan=False)


def test_entity_association_uses_explicit_owner_not_shared_ip():
    known = accretion.score_lead(
        [entry()], association=("id", "known", "Stored hostname association", ["id"])
    )
    overlap = accretion.score_lead(
        [entry()],
        association=(None, "review", "Reported IP also appears for another entity", ["id"]),
    )
    new = accretion.score_lead([entry()])
    assert known["quality"] == 100
    assert new["quality"] == 90
    assert overlap["quality"] == 80


def test_supported_service_profile_keeps_non_cve_evidence():
    observation = entry("rdp", severity="high", version=None)
    observation["normalized"]["products"] = []
    observation["normalized"]["profile"].update(
        version_requirement="eol_only", version_semantics="protocol"
    )
    score = accretion.score_lead([observation])
    assert score["quality"] == 84
    assert score["cves"] == []
    assert score["urgency"] == 32


def test_priorities_exact_match_and_ransomware_never_stack():
    policy = {"priority_cities": ["Burnsville"], "priority_products": ["Acme"]}
    records = {ID: vetted(kev=True, ransomware="Known")}
    score = accretion.score_lead(
        [entry(city="BURNSVILLE")],
        cve_records=records,
        policy=policy,
        priority={"score": 1, "reason": "Campaign"},
    )
    assert score["factors"]["urgency"][3]["points"] == 10
    partial = entry(city="Greater Burnsville")
    partial["normalized"]["products"][0]["product"] = "AcmeOther"
    score = accretion.score_lead([partial], cve_records={ID: vetted()}, policy=policy)
    assert score["factors"]["urgency"][3]["points"] == 0
    assert (
        "known ransomware"
        in accretion.score_lead([entry()], cve_records=records)["factors"]["urgency"][3]["reason"]
    )


def test_missing_catalog_is_read_only_and_unknown(tmp_path):
    workspace = tmp_path / "work"
    result = accretion.vet_cves(workspace, [ID, ID.lower(), "garbage"], as_of=NOW)
    assert list(result) == [ID]
    assert result[ID]["status"] == "unavailable"
    assert result[ID]["kev"] is None
    assert list(tmp_path.iterdir()) == []


def test_catalog_corruption_isolated_and_rejected_not_scored(tmp_path):
    workspace = tmp_path / "work"
    rejected = "CVE-2026-9999"
    seed_catalog(
        workspace,
        [
            (ID, 9.8, "Analyzed", False),
            (OTHER, 9.9, "Analyzed", True),
            (rejected, 10, "Rejected", False),
        ],
    )
    records = accretion.vet_cves(workspace, [ID, OTHER, rejected], as_of=NOW)
    assert records[ID]["status"] == "available"
    assert records[ID]["cvss"] == 9.8
    assert records[OTHER]["status"] == "invalid"
    assert records[rejected]["status"] == "rejected"
    assert records[rejected]["cvss"] is None
    assert records[ID]["source"]["record_sha256"]


@pytest.mark.parametrize("damaged", [False, True])
def test_catalog_connection_closes_after_read_or_schema_failure(tmp_path, monkeypatch, damaged):
    workspace = tmp_path / "data"
    catalog = seed_catalog(workspace, [(ID, 9.8, "Analyzed", False)])
    if damaged:
        with catalog.connection() as db:
            db.execute("DROP TABLE metadata")
    opened = []
    connect = sqlite3.connect

    def tracked_connect(*args, **kwargs):
        db = connect(*args, **kwargs)
        opened.append(db)
        return db

    monkeypatch.setattr(sqlite3, "connect", tracked_connect)
    result = accretion.vet_cves(workspace, [ID], as_of=NOW)
    assert result[ID]["status"] == ("unavailable" if damaged else "available")
    assert len(opened) == 1
    for db in opened:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            db.execute("SELECT 1")


def test_risk_record_corruption_isolated_stale_positives_retained(tmp_path):
    workspace = tmp_path / "work"
    risk = RiskStore(workspace)
    old = "2026-11-01T00:00:00Z"
    with risk.connection(write=True) as db:
        risk.put_metadata("kev", {"last_success_at": old, "count": 2}, db=db)
        risk.put_metadata("epss", {"last_success_at": old, "score_date": "2026-11-01"}, db=db)
        for identifier in (ID, OTHER):
            raw = json.dumps({"cveID": identifier, "knownRansomwareCampaignUse": "Known"})
            checksum = hashlib.sha256(raw.encode()).hexdigest() if identifier == ID else "bad"
            db.execute("INSERT INTO kev VALUES (?,?,?)", (identifier, raw, checksum))
            row = {
                "cve": identifier,
                "epss": 0.9,
                "percentile": 0.99,
                "date": "2026-11-01",
                "model_version": "v1",
            }
            db.execute(
                "INSERT INTO epss VALUES (?,?,?,?,?,?)",
                (
                    identifier,
                    0.9,
                    0.99,
                    "2026-11-01",
                    "v1",
                    digest(row) if identifier == ID else "bad",
                ),
            )
    result = accretion.vet_cves(workspace, [ID, OTHER], as_of=NOW)
    assert result[ID]["kev"]["listed"] is True
    assert result[ID]["kev"]["stale"] is True
    assert result[ID]["epss"]["score"] == 0.9
    assert result[OTHER]["kev"] is None
    assert result[OTHER]["epss"] is None
    assert "Local KEV snapshot is stale" in result[ID]["warnings"]


def test_batch_vets_unique_ids_once_and_embedded_records_need_no_reads(monkeypatch):
    calls = []

    def vet(root, ids, **kwargs):
        calls.append((root, set(ids)))
        return {ID: vetted()}

    monkeypatch.setattr(accretion, "vet_cves", vet)
    groups = {"one.com": [entry()] * 3, "two.com": [entry()]}
    assert len(accretion.score_leads(groups, workspace_root="/unused")) == 2
    assert calls == [("/unused", {ID})]
    observation = entry()
    observation["normalized"]["accretion_cves"] = {ID: vetted()}
    assert accretion.score_lead([observation])["cves"][0]["cvss"] == 9.8
    assert len(calls) == 1


def test_empty_and_invalid_numbers_cannot_generate_score():
    result = accretion.score_lead([])
    assert (result["quality"], result["urgency"], result["aggregate"], result["temperature"]) == (
        0,
        0,
        0,
        "cool",
    )
    record = vetted(score=float("inf"), epss=float("nan"))
    score = accretion.score_lead([entry()], cve_records={ID: record})
    assert score["urgency"] == 38
    json.dumps(score, allow_nan=False)
    assert accretion.TEMPERATURES == ("cool", "warm", "hot", "blazing")


def test_vetted_local_severity_overrides_reported_label_without_claiming_applicability():
    score = accretion.score_lead(
        [entry(severity="critical")], cve_records={ID: vetted(score=2, epss=0)}
    )
    assert score["urgency"] == 8
    assert score["strongest_finding"]["id"] == ID
    assert "applicability" in score["factors"]["quality"][1]["reason"]


def test_withdrawn_context_does_not_supply_severity_or_finding_quality():
    withdrawn = entry(ID, severity="critical")
    withdrawn["normalized"]["eligibility"] = {"eligible": False, "reason": "withdrawn_cve_only"}
    current = entry("service", severity="low")
    current["normalized"]["products"] = []
    current["normalized"]["profile"]["version_requirement"] = "eol_only"
    records = {ID: vetted(status="rejected", kev=True, ransomware="Known")}
    score = accretion.score_lead([withdrawn, current], cve_records=records)
    assert score["quality"] == 84
    assert score["urgency"] == 8
    assert score["cves"][0]["status"] == "rejected"


def test_cached_record_identifier_cannot_swap_findings():
    score = accretion.score_lead([entry()], cve_records={ID: vetted(OTHER, kev=True)})
    assert score["cves"][0]["id"] == ID
    assert score["cves"][0]["status"] == "invalid"
    assert score["urgency"] == 38


def test_only_active_conditions_contribute_to_evaluation():
    from copy import deepcopy

    observation = entry(ID + ";" + OTHER)
    observation["normalized"]["findings"] = [{"id": ID}, {"id": OTHER}]
    observation["normalized"]["accretion_cves"] = {
        ID: vetted(score=10, kev=True, epss=1),
        OTHER: vetted(OTHER, score=4, epss=0),
    }
    scoped = project_conditions(observation, [OTHER])
    before = deepcopy(scoped)
    result = accretion.score_lead([scoped], as_of=NOW)
    assert result["urgency"] == 16
    assert result["strongest_finding"]["id"] == OTHER
    assert [item["id"] for item in result["cves"]] == [OTHER]
    assert scoped == before
    assert accretion.score_lead([project_conditions(observation, [])], as_of=NOW) == (
        accretion.score_lead([], as_of=NOW)
    )


@pytest.mark.parametrize("latest_status,latest_score", [("available", 2), ("rejected", None)])
def test_embedded_snapshots_use_latest_whole_capture_in_any_row_order(latest_status, latest_score):
    old = vetted(score=10, kev=True, epss=1)
    latest = vetted(score=latest_score, kev=False, epss=0, status=latest_status)
    # NVD has not refreshed, but the captured risk-feed facts have changed.
    for record in (old, latest):
        record["catalog_checked_at"] = "2026-11-01T00:00:00Z"
    old["captured_at"] = "2026-11-10T00:00:00Z"
    latest["captured_at"] = NOW
    first, second = entry(), entry(hostname="other.example.com")
    first["normalized"]["accretion_cves"] = {ID: old}
    second["normalized"]["accretion_cves"] = {ID: latest}
    expected = accretion.score_lead([first, second], cve_records={ID: latest}, as_of=NOW)
    assert accretion.score_lead([first, second], as_of=NOW) == expected
    assert accretion.score_lead([second, first], as_of=NOW) == expected
    assert expected["cves"][0]["captured_at"] == NOW
    assert expected["urgency"] == (8 if latest_status == "available" else 0)
    # An explicit caller-selected snapshot still overrides embedded history.
    explicit = accretion.score_lead([second, first], cve_records={ID: old}, as_of=NOW)
    assert explicit["cves"][0]["captured_at"] == old["captured_at"]


@pytest.mark.parametrize("captured_at", [None, "invalid date", NOW])
def test_untimed_or_tied_embedded_snapshots_have_stable_selection(captured_at):
    rows = [entry(), entry(hostname="other.example.com")]
    for row, severity in zip(rows, (2, 10)):
        record = vetted(score=severity)
        if captured_at is not None:
            record["captured_at"] = captured_at
        row["normalized"]["accretion_cves"] = {ID: record}
    assert accretion.score_lead(rows, as_of=NOW) == accretion.score_lead(rows[::-1], as_of=NOW)


def test_local_cve_bundle_records_its_capture_time_even_when_unavailable(tmp_path):
    result = accretion.vet_cves(tmp_path / "absent", [ID], as_of=NOW)
    assert result[ID]["captured_at"] == "2026-11-12T12:00:00.000Z"
    assert result[ID]["status"] == "unavailable"


@pytest.mark.parametrize(
    "severity,urgency,basis", [("", 10, "report_type"), ("high", 32, "reported_severity")]
)
def test_compromise_has_modest_priority_without_overriding_stronger_evidence(
    severity, urgency, basis
):
    observation = entry("compromised-website", severity=severity)
    observation["normalized"]["products"] = []
    observation["normalized"]["profile"].update(
        id="compromised_website",
        observation_kind="compromise_indicator",
        version_requirement="none",
    )
    result = accretion.score_lead([observation], as_of=NOW)
    assert result["urgency"] == urgency
    assert result["strongest_finding"]["basis"] == basis
    assert result["cves"] == []
    assert [f["points"] for f in result["factors"]["urgency"]][1:] == [0, 0, 0]
    assert accretion.score_lead([observation] * 20, as_of=NOW) == result
    assert accretion.score_lead([project_conditions(observation, [])], as_of=NOW)["urgency"] == 0
    observation["normalized"]["profile"]["capability"] = "unsupported"
    observation["source"]["fields"]["severity"] = ""
    assert accretion.score_lead([observation], as_of=NOW)["urgency"] == 0


def test_report_matrix_can_add_a_profile_rule_without_changing_other_scores():
    observation = entry("custom-incident", severity="")
    observation["normalized"]["profile"].update(
        id="custom_incident", observation_kind="compromise_indicator"
    )
    policy = {"report_bases": {"custom_incident": {"value": 0.5, "reason": "Targeted review"}}}
    base = accretion.score_lead([observation], as_of=NOW)
    targeted = accretion.score_lead([observation], policy=policy, as_of=NOW)
    assert base["urgency"] == 10
    assert targeted["urgency"] == 20
    assert targeted["quality"] == base["quality"]
    assert targeted["factors"]["urgency"][0]["reason"] == "Targeted review"
    assert targeted["policy_hash"] != base["policy_hash"]
    # A profile override must not change other profiles of the same kind.
    observation["normalized"]["profile"]["id"] = "other_incident"
    assert accretion.score_lead([observation], policy=policy)["urgency"] == 10
    # The new rule also leaves CVE-backed scores intact, even on a matching profile.
    observation = entry()
    observation["normalized"]["profile"].update(
        id="custom_incident", observation_kind="compromise_indicator"
    )
    before = accretion.score_lead([observation], cve_records={ID: vetted(kev=True)})
    after = accretion.score_lead([observation], cve_records={ID: vetted(kev=True)}, policy=policy)
    assert after["strongest_finding"] == before["strongest_finding"]
    assert after["factors"] == before["factors"]
    policy["report_bases"]["custom_incident"]["value"] = 0
    assert targeted["policy"]["report_bases"]["custom_incident"]["value"] == 0.5


@pytest.mark.parametrize(
    "condition,kind",
    [("eol-php:7.3", "vulnerability"), ("", "exposure"), ("", "compromise_indicator")],
)
def test_rejected_cve_does_not_discard_independent_finding(condition, kind):
    observation = entry(ID + ";eol-php", severity="high")
    observation["normalized"]["profile"]["observation_kind"] = kind
    scoped = project_conditions(observation, [ID, condition] if condition else [ID])
    score = accretion.score_lead([scoped], cve_records={ID: vetted(status="rejected")})
    assert score["urgency"] == 32
    assert score["cves"][0]["status"] == "rejected"
    if condition:
        # A settled EOL finding cannot rescue the now-withdrawn CVE-only scope.
        scoped = project_conditions(observation, [ID])
        score = accretion.score_lead([scoped], cve_records={ID: vetted(status="rejected")})
        assert score["quality"] == score["urgency"] == 0
