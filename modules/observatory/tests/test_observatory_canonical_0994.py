"""Canonical awareness, unique findings and honest event density in Observatory."""

from copy import deepcopy

from modules.observatory.components.eclipse import Eclipse, density_band
from modules.workspace.components.store import Store
from modules.observatory.tests.support.observations import base
from tests.support.workbench import app, client, import_rows, observations

from modules.observatory.tests.support.observations import (
    add,
)


def test_events_findings_and_days_have_independent_counts(tmp_path):
    store = Store(tmp_path / "workspace")
    fields = base(tag="CVE-2026-10001;CVE-2026-10002")
    first = add(store, fields)
    add(store, fields, filename="renamed.csv")
    add(store, {**fields, "timestamp": "2026-11-05T01:02:03Z"})
    view = Eclipse(store)
    snapshot = view.snapshot()
    assert snapshot["counts"]["observations"] == 2
    assert snapshot["counts"]["findings"] == 2
    assert snapshot["counts"]["assets"] == 1
    assert snapshot["counts"]["observation_days"] == 2
    assert len(snapshot["findings"]) == 2
    assert all(
        row["observation_count"] == 2 and row["sightings"] == 2 for row in snapshot["findings"]
    )
    assert all(row["density_count"] == 2 for row in snapshot["observations"])
    graph = view.intelligence(include_undated=True)
    assert graph["counts"]["assets"] == 1
    assert graph["counts"]["observations"] == 2
    assert graph["counts"]["findings"] == 2
    detail = view.observation(first["observation_id"])
    assert detail["fields"]["tag"] == fields["tag"]
    assert detail["source_available"] and detail["original_url"]


def test_snapshot_never_reparses_or_requalifies_originals(tmp_path, monkeypatch):
    store = Store(tmp_path / "workspace")
    add(store, base())
    originals = {
        r["path"]: store.path(r["path"]).read_bytes() for r in store.all("SELECT path FROM imports")
    }

    def forbidden(*args, **kwargs):
        raise AssertionError("A view must consume committed Accretion records")

    monkeypatch.setattr("modules.accretion.components.intake.read_entries", forbidden)
    monkeypatch.setattr(
        "modules.accretion.components.intake.EntryValidator.rejection_reason", forbidden
    )
    before = store.all("SELECT * FROM awareness_observations")
    view = Eclipse(store)
    result = view.snapshot()
    view.observation(result["findings"][0]["id"])
    assert store.all("SELECT * FROM awareness_observations") == before
    assert all(store.path(path).read_bytes() == body for path, body in originals.items())


def test_new_unadmitted_endpoint_does_not_replace_approved_representative(tmp_path):
    store = Store(tmp_path / "workspace")
    fields = base(tag="CVE-2026-10001")
    first = add(store, fields)
    add(
        store,
        {**fields, "ip": "1.1.1.1", "timestamp": "2026-11-05T01:02:03Z"},
        admitted=False,
        reason="endpoint_review",
    )
    snapshot = Eclipse(store).snapshot()
    assert snapshot["counts"]["findings"] == 1
    finding = snapshot["findings"][0]
    assert finding["admitted"] and finding["ip"] == "8.8.8.8"
    dark = next(row for row in snapshot["observations"] if row["ip"] == "1.1.1.1")
    assert dark["dark_matter"] and dark["status"] == "excluded"
    assert dark["intake_reason"] == "endpoint_review"
    assert dark["density_count"] == 2
    assert dark["admitted_density"] == dark["dark_matter_density"] == 1
    assert finding["observation_id"] == first["observation_id"]


def test_repeated_observation_does_not_freshen_finding(tmp_path, monkeypatch):
    store = Store(tmp_path / "workspace")
    fields = base(tag="CVE-2026-10001")
    monkeypatch.setattr(
        "modules.accretion.components.awareness.now", lambda: "2026-11-04T12:00:00+00:00"
    )
    add(store, fields)
    before = deepcopy(Eclipse(store).snapshot()["findings"][0])
    monkeypatch.setattr(
        "modules.accretion.components.awareness.now", lambda: "2026-11-06T12:00:00+00:00"
    )
    add(store, {**fields, "timestamp": "2026-11-05T01:02:03Z"})
    after = Eclipse(store).snapshot()["findings"][0]
    assert before["id"] == after["id"]
    assert before["fresh_at"] == after["fresh_at"]
    assert after["last_seen"] > before["last_seen"]
    assert after["observation_count"] == 2


def test_density_boundaries_do_not_depend_on_priority():
    assert [density_band(n) for n in (0, 50, 51, 200, 201, 1000, 1001)] == [
        "normal",
        "normal",
        "yellow",
        "yellow",
        "red",
        "red",
        "purple",
    ]


def test_local_risk_change_uses_known_baseline_not_daily_epss_noise():
    from modules.library.components.catalog_outreach import material_risk_changes

    baseline = {
        "CVE-2026-10001": {
            "status": "available",
            "severity": "HIGH",
            "kev": {"listed": False},
            "epss": {"score": 0.1},
        }
    }
    current = [
        {
            "id": "CVE-2026-10001",
            "severity": "CRITICAL",
            "kev": True,
            "modified": "2026-11-12T00:00:00Z",
            "risk": {"kev": {"source": {"retrieved_at": "2026-11-13T00:00:00Z"}}},
            "epss": {"score": 0.2},
        }
    ]
    result = material_risk_changes(baseline, current)
    assert result["risk_changed"] and len(result["risk_change_reasons"]) == 2
    assert result["risk_updated_at"] == "2026-11-13T00:00:00Z"
    assert not material_risk_changes({}, current)["risk_changed"]
    assert not material_risk_changes(baseline, [{**current[0], "severity": "HIGH", "kev": False}])[
        "risk_changed"
    ]
    assert baseline["CVE-2026-10001"]["kev"]["listed"] is False


def test_complementary_reports_share_event_but_source_details_remain_exact(tmp_path):
    store = Store(tmp_path / "workspace")
    first = base(tag="CVE-2026-10001", extra_source_field="first report")
    added = add(store, first, filename="first.csv")
    old_source = store.one(
        "SELECT source_key,source_sha256 FROM awareness_sources WHERE observation_id=?",
        (added["observation_id"],),
    )
    second = {**first, "tag": "CVE-2026-10002", "extra_source_field": "second report"}
    add(store, second, filename="second.csv")
    view = Eclipse(store)
    result = view.snapshot()
    assert result["counts"]["observations"] == 1
    assert result["counts"]["findings"] == 2
    assert "CVE-2026-10001" in result["observations"][0]["tag"]
    assert "CVE-2026-10002" in result["observations"][0]["tag"]
    current = view.observation(added["observation_id"])
    assert current["fields"]["extra_source_field"] == "second report"
    assert current["source"]["workbook"] == "second.csv"
    old = view.observation(old_source["source_key"])
    assert old["fields"]["extra_source_field"] == "first report"
    assert old["source"]["sha256"] == old_source["source_sha256"]
    assert old["fields"]["tag"] == "CVE-2026-10001"
    by_condition = {row["tag"]: row for row in result["findings"]}
    assert by_condition["CVE-2026-10001"]["source"]["workbook"] == "first.csv"
    assert by_condition["CVE-2026-10002"]["source"]["workbook"] == "second.csv"
    old_finding = view.observation(by_condition["CVE-2026-10001"]["id"])
    assert old_finding["fields"]["tag"] == "CVE-2026-10001"
    assert old_finding["fields"]["extra_source_field"] == "first report"
    assert old_finding["source"]["workbook"] == "first.csv"


def test_complementary_unapproved_condition_does_not_inherit_admission(tmp_path):
    store = Store(tmp_path / "workspace")
    first = base(tag="CVE-2026-10001")
    add(store, first, filename="approved.csv")
    add(
        store,
        {**first, "tag": "CVE-2026-10002"},
        filename="pending.csv",
        admitted=False,
        reason="pending",
    )
    view = Eclipse(store)
    snapshot = view.snapshot()
    assert snapshot["counts"]["observations"] == 1
    assert snapshot["counts"]["findings"] == 2
    conditions = {r["tag"]: r for r in snapshot["findings"]}
    assert conditions["CVE-2026-10001"]["admitted"]
    assert not conditions["CVE-2026-10002"]["admitted"]
    assert conditions["CVE-2026-10002"]["intake_reason"] == "pending"
    graph = view.intelligence(include_undated=True)
    nodes = {n["key"]: n for n in graph["graph"]["nodes"] if n["type"] == "cve"}
    assert nodes["CVE-2026-10001"]["admitted_observations"] == 1
    assert nodes["CVE-2026-10002"]["admitted_observations"] == 0
    assert nodes["CVE-2026-10002"]["dark_matter_observations"] == 1
    approved = view.intelligence(include_undated=True, intake="lead")
    assert {n["key"] for n in approved["graph"]["nodes"] if n["type"] == "cve"} == {
        "CVE-2026-10001"
    }
    dark = view.intelligence(include_undated=True, intake="dark_matter")
    assert {n["key"] for n in dark["graph"]["nodes"] if n["type"] == "cve"} == {"CVE-2026-10002"}
    assert dark["counts"]["findings"] == 1


def test_entity_and_observatory_share_local_risk_changes_without_rescoring(tmp_path):
    import json
    from modules.library.components.catalog_outreach import decorate_entity
    from modules.library.tests.support.catalog_outreach import CRITICAL_KEV, seed_catalog

    store = Store(tmp_path / "workspace")
    seed_catalog(store.root, tmp_path)
    result = add(store, base(tag=CRITICAL_KEV))
    pinned = {CRITICAL_KEV: {"status": "available", "severity": "HIGH", "kev": {"listed": False}}}
    with store.transaction() as db:
        db.execute(
            "UPDATE awareness_observations SET normalized=? WHERE id=?",
            (json.dumps({"accretion_cves": pinned}), result["observation_id"]),
        )
    before = store.one(
        "SELECT normalized FROM awareness_observations WHERE id=?", (result["observation_id"],)
    )["normalized"]
    entity = {
        "awareness": {},
        "awareness_findings": [
            {
                "id": result["finding_ids"][0],
                "condition": CRITICAL_KEV,
                "intake_cve_assessments": deepcopy(pinned),
            }
        ],
    }
    decorate_entity(store.root, entity)
    finding = entity["awareness_findings"][0]
    assert finding["risk_changed"]
    assert len(finding["risk_change_reasons"]) == 2
    assert finding["intake_cve_assessments"] == pinned
    assert entity["awareness"]["risk_changed_findings"] == 1
    assert Eclipse(store).snapshot()["findings"][0]["risk_changed"]
    assert (
        store.one(
            "SELECT normalized FROM awareness_observations WHERE id=?", (result["observation_id"],)
        )["normalized"]
        == before
    )


def test_entity_api_exposes_changed_risk_from_local_reference(client, app, tmp_path):
    import json
    from modules.library.tests.support.catalog_outreach import CRITICAL_KEV, seed_catalog

    store = app.state.store
    seed_catalog(store.root, tmp_path)
    record = {**observations()[0], "ip": "8.8.8.8", "tag": CRITICAL_KEV}
    import_rows(client, app, [record], start_notifications=False)
    entity = client.get("/api/entities").json()[0]
    with store.transaction() as db:
        for row in db.execute("SELECT id,normalized FROM awareness_observations").fetchall():
            normalized = json.loads(row["normalized"])
            normalized["accretion_cves"] = {
                CRITICAL_KEV: {"status": "available", "severity": "HIGH", "kev": {"listed": False}}
            }
            db.execute(
                "UPDATE awareness_observations SET normalized=? WHERE id=?",
                (json.dumps(normalized), row["id"]),
            )
    response = client.get("/api/entities/" + entity["id"])
    assert response.status_code == 200
    detail = response.json()
    assert detail["awareness"]["risk_changed_findings"] == 1
    finding = detail["awareness_findings"][0]
    assert finding["risk_changed"] and len(finding["risk_change_reasons"]) == 2
    assert finding["intake_cve_assessments"][CRITICAL_KEV]["severity"] == "HIGH"
