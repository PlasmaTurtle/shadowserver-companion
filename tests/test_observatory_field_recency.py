"""The Field puts material changes first without rewriting historical density."""

from copy import deepcopy
import json

from test_eclipse import base
from test_observatory_canonical_0994 import add
from workbench.eclipse import Eclipse
from workbench.store import Store


OLD_CVE = "CVE-2026-10001"
NEW_CVE = "CVE-2026-10002"


def field(eclipse, **filters):
    return eclipse.view(field_only=True, lens="vulnerability", field_limit=24, **filters)


def conditions(response):
    return [node for node in response["intelligence"]["graph"]["nodes"] if node["type"] == "cve"]


def condition(response, cve):
    return next(node for node in conditions(response) if node["label"] == cve)


def test_material_change_ranks_before_a_denser_more_recent_repeat(tmp_path, monkeypatch):
    store = Store(tmp_path / "workspace")
    monkeypatch.setattr("workbench.awareness.now", lambda: "2026-11-01T12:00:00+00:00")
    original = base(tag=OLD_CVE, timestamp="2026-11-01T01:00:00Z")
    add(store, original, filename="initial.csv")
    for day in range(2, 11):
        monkeypatch.setattr(
            "workbench.awareness.now", lambda day=day: f"2026-11-{day:02d}T12:00:00+00:00"
        )
        add(
            store,
            {**original, "timestamp": f"2026-11-{day:02d}T01:00:00Z"},
            filename=f"repeat-{day}.csv",
        )
    monkeypatch.setattr("workbench.awareness.now", lambda: "2026-11-09T12:00:00+00:00")
    add(
        store,
        base(hostname="new.example.com", tag=NEW_CVE, timestamp="2026-11-09T01:00:00Z"),
        filename="new-finding.csv",
    )

    response = field(Eclipse(store))
    first, second = conditions(response)
    assert first["label"] == NEW_CVE and second["label"] == OLD_CVE
    assert first["fresh_at"] > second["fresh_at"]
    assert first["last_seen"] < second["last_seen"]
    assert first["density_count"] == 1 and second["density_count"] == 10
    assert first["recency_basis"] and second["recency_basis"]


def test_repeat_adds_density_without_refreshing_the_material_change_time(tmp_path, monkeypatch):
    store = Store(tmp_path / "workspace")
    monkeypatch.setattr("workbench.awareness.now", lambda: "2026-11-01T12:00:00+00:00")
    original = base(tag=OLD_CVE, timestamp="2026-11-01T01:00:00Z")
    add(store, original, filename="initial.csv")
    eclipse = Eclipse(store)
    before = deepcopy(condition(field(eclipse), OLD_CVE))

    monkeypatch.setattr("workbench.awareness.now", lambda: "2026-11-12T12:00:00+00:00")
    repeated = {**original, "timestamp": "2026-11-12T01:00:00Z"}
    add(store, repeated, filename="repeat.csv")
    add(store, repeated, filename="renamed-repeat.csv")
    after = condition(field(eclipse), OLD_CVE)

    assert after["id"] == before["id"]
    assert after["fresh_at"] == before["fresh_at"]
    assert after["last_seen"] > before["last_seen"]
    assert before["density_count"] == 1 and after["density_count"] == 2
    assert after["finding_count"] == before["finding_count"] == 1
    assert after["admitted_density"] == 2 and after["dark_matter_density"] == 0


def test_new_co_observed_cve_does_not_refresh_an_unchanged_condition(tmp_path, monkeypatch):
    store = Store(tmp_path / "workspace")
    monkeypatch.setattr("workbench.awareness.now", lambda: "2026-11-01T12:00:00+00:00")
    original = base(tag=OLD_CVE, timestamp="2026-11-01T01:00:00Z")
    add(store, original, filename="first-condition.csv")
    eclipse = Eclipse(store)
    before = condition(field(eclipse), OLD_CVE)

    # Complementary reports can add a finding to the same canonical source
    # event. Its admission time must not become the old condition's recency.
    monkeypatch.setattr("workbench.awareness.now", lambda: "2026-11-12T12:00:00+00:00")
    add(store, {**original, "tag": NEW_CVE}, filename="second-condition.csv")
    response = field(eclipse)
    old, new = condition(response, OLD_CVE), condition(response, NEW_CVE)

    assert old["fresh_at"] == before["fresh_at"]
    assert new["fresh_at"] > old["fresh_at"]
    assert old["density_count"] == new["density_count"] == 1
    assert conditions(response)[0]["id"] == new["id"]
    assert response["snapshot"]["counts"]["observations"] == 1
    assert response["snapshot"]["counts"]["findings"] == 2


def test_historical_field_does_not_use_future_material_change_timestamps(tmp_path, monkeypatch):
    store = Store(tmp_path / "workspace")
    monkeypatch.setattr("workbench.awareness.now", lambda: "2026-11-01T12:00:00+00:00")
    original = base(tag=OLD_CVE, timestamp="2026-11-01T01:00:00Z")
    add(store, original, filename="old.csv")
    monkeypatch.setattr("workbench.awareness.now", lambda: "2026-11-12T12:00:00+00:00")
    add(store, {**original, "tag": NEW_CVE}, filename="late-complementary.csv")
    eclipse = Eclipse(store)
    current = field(eclipse)
    assert condition(current, NEW_CVE)["fresh_at"].startswith("2026-11-12")

    historical = field(eclipse, date_to="2026-11-05")
    for node in conditions(historical):
        assert node["fresh_at"][:10] <= "2026-11-05"
        assert node["last_seen"][:10] <= "2026-11-05"
        assert node["recency_basis"]
    assert historical["snapshot"]["counts"]["observations"] == 1
    assert condition(historical, NEW_CVE)["fresh_at"] != condition(current, NEW_CVE)["fresh_at"]


def test_unadmitted_endpoint_density_stays_dark_for_an_approved_finding(tmp_path, monkeypatch):
    store = Store(tmp_path / "workspace")
    monkeypatch.setattr("workbench.awareness.now", lambda: "2026-11-01T12:00:00+00:00")
    original = base(tag=OLD_CVE, timestamp="2026-11-01T01:00:00Z")
    add(store, original, filename="approved.csv")
    eclipse = Eclipse(store)
    before = condition(field(eclipse), OLD_CVE)

    monkeypatch.setattr("workbench.awareness.now", lambda: "2026-11-12T12:00:00+00:00")
    add(
        store,
        {**original, "ip": "1.1.1.1", "timestamp": "2026-11-12T01:00:00Z"},
        admitted=False,
        reason="endpoint_review",
        filename="unadmitted-endpoint.csv",
    )
    after = condition(field(eclipse), OLD_CVE)

    assert after["finding_count"] == 1
    assert after["density_count"] == 2
    assert after["admitted_density"] == 1
    assert after["dark_matter_density"] == 1
    assert after["admitted"] is True and after["dark_matter"] is False
    assert after["admitted_observations"] == 1
    assert after["dark_matter_observations"] == 1
    assert after["fresh_at"] == before["fresh_at"]


def test_material_catalog_change_freshens_only_its_own_cve(tmp_path, monkeypatch):
    from test_catalog_outreach_0984 import CRITICAL, CRITICAL_KEV, seed_catalog

    store = Store(tmp_path / "workspace")
    seed_catalog(store.root, tmp_path)
    monkeypatch.setattr("workbench.awareness.now", lambda: "2026-11-01T12:00:00+00:00")
    added = add(
        store,
        base(tag=CRITICAL + ";" + CRITICAL_KEV, timestamp="2026-11-01T01:00:00Z"),
        filename="original-assessment.csv",
    )
    pinned = {
        CRITICAL: {"status": "available", "severity": "CRITICAL", "kev": {"listed": False}},
        CRITICAL_KEV: {"status": "available", "severity": "HIGH", "kev": {"listed": False}},
    }
    with store.transaction() as db:
        db.execute(
            "UPDATE awareness_observations SET normalized=? WHERE id=?",
            (json.dumps({"accretion_cves": pinned}), added["observation_id"]),
        )

    response = field(Eclipse(store))
    changed, unchanged = condition(response, CRITICAL_KEV), condition(response, CRITICAL)
    assert changed["fresh_at"][:10] >= "2026-11-10"
    assert unchanged["fresh_at"].startswith("2026-11-01")
    assert conditions(response)[0]["id"] == changed["id"]
    assert changed["density_count"] == unchanged["density_count"] == 1
    assert (
        json.loads(
            store.one(
                "SELECT normalized FROM awareness_observations WHERE id=?",
                (added["observation_id"],),
            )["normalized"]
        )["accretion_cves"]
        == pinned
    )
