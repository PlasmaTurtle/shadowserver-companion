"""Condition-specific state, historical endpoints and reusable scoped views."""

from copy import deepcopy

from test_eclipse import base
from test_observatory_canonical_0994 import add
from test_observatory_intelligence_0981 import observation
from test_workbench import app, client, import_rows, observations
from workbench.eclipse import Eclipse
from workbench.observatory_intelligence import project
from workbench.store import Store


def test_new_cve_does_not_inherit_an_older_delivered_notification(client, app):
    import_rows(client, app)
    store = app.state.store
    case = store.one("SELECT id FROM cases")
    with store.transaction() as db:
        db.execute(
            "UPDATE cases SET delivered_at='2026-11-05T12:00:00Z',stage='notification_completed' WHERE id=?",
            (case["id"],),
        )
    add(
        store,
        {**observations()[2], "tag": "eol-php;CVE-2026-10001", "timestamp": "2026-11-06T01:02:03Z"},
        filename="new.csv",
    )
    view = Eclipse(store)
    finding = next(row for row in view.snapshot()["findings"] if row["tag"] == "CVE-2026-10001")
    assert finding["workflow"] == "unworked"
    assert finding["status"] == "qualified"
    assert finding["case_id"] is None and finding["delivered_at"] is None
    assert not any(
        row["tag"] == finding["tag"] for row in view.view(status="delivered")["records"]["items"]
    )
    selected = view.view(cve="CVE-2026-10001", status="qualified")
    assert selected["records"]["total"] == 1
    assert selected["records"]["items"][0]["case_id"] is None


def test_historical_view_keeps_the_endpoint_observed_at_that_time(tmp_path):
    store = Store(tmp_path / "workspace")
    first = base(tag="CVE-2026-10001", timestamp="2026-11-01T00:00:00Z")
    add(store, first)
    add(store, {**first, "timestamp": "2026-11-10T00:00:00Z", "ip": "1.1.1.1", "version": "8.2"})
    view = Eclipse(store)
    current = view.view()
    old = view.view(date_to="2026-11-05")
    assert old["records"]["total"] == 1
    row = old["records"]["items"][0]
    assert row["ip"] == "8.8.8.8" and row["version"] == first["version"]
    assert row["observed_day"] == "2026-11-01"
    assert row["observation_count"] == row["sightings"] == 1
    assert row["fresh_at"] <= "2026-11-05" and row["changed_at"] is None
    assert row["current_changed_at"] == current["records"]["items"][0]["changed_at"]
    assert [bin["day"] for bin in old["snapshot"]["timeline"]["bins"]] == [
        "2026-11-01",
        "2026-11-10",
    ]
    assert [bin["day"] for bin in old["intelligence"]["timeline"]] == ["2026-11-01"]


def test_selected_intake_version_and_products_survive_projection(tmp_path):
    store = Store(tmp_path / "workspace")
    add(
        store,
        base(
            tag="CVE-2026-10001",
            report_type="scan_exchange",
            version="",
            device_version="15.2.1118.30",
        ),
    )
    row = Eclipse(store).view()["records"]["items"][0]
    assert row["version"] == "15.2.1118.30"


def test_explicit_cve_cannot_borrow_another_conditions_risk():
    mixed = observation(
        "mixed",
        tag="CVE-2026-10001;CVE-2026-10002",
        kev=True,
        catalog_findings=[
            {"id": "CVE-2026-10001", "severity": "HIGH", "kev": False},
            {"id": "CVE-2026-10002", "severity": "CRITICAL", "kev": True},
        ],
    )
    for key in ("cve", "q"):
        selected = project(
            {"observations": [mixed]}, **{key: "CVE-2026-10001"}, intelligence="critical_kev"
        )
        assert selected["counts"]["observations"] == 0


def test_unidentified_version_and_changed_endpoint_have_honest_meaning():
    rows = [
        observation("a", version="1.0", product="", entity_id="one"),
        observation("b", version="1.0", product="", hostname="other.example", entity_id="two"),
    ]
    result = project({"observations": rows}, lens="version")
    assert not any(pattern["type"] == "shared_version" for pattern in result["patterns"])
    rows = [
        observation("old", asset_id="asset", ip="8.8.8.8", observed_day="2026-11-01"),
        observation("new", asset_id="asset", ip="1.1.1.1", observed_day="2026-11-02"),
    ]
    recurrent = next(
        pattern
        for pattern in project({"observations": rows})["patterns"]
        if pattern["type"] == "recurrent_asset"
    )
    assert (
        "canonical asset" in recurrent["basis"]
        and "exact endpoint tuple recurs" not in recurrent["basis"]
    )


def test_pagination_reuses_scoped_projection_without_resending_graph(tmp_path, monkeypatch):
    store = Store(tmp_path / "workspace")
    for index in range(3):
        add(
            store,
            base(hostname=f"host{index}.example.com", tag="CVE-2026-10001"),
            filename=f"{index}.csv",
        )
    eclipse = Eclipse(store)
    first = eclipse.view(limit=1)
    original = deepcopy(first)
    first["snapshot"]["counts"]["findings"] = -999

    def forbidden(*args, **kwargs):
        raise AssertionError("Pagination rebuilt a scoped graph")

    monkeypatch.setattr("workbench.observatory_view.project", forbidden)
    page = eclipse.view(limit=1, offset=1, records_only=True)
    assert page["records"]["total"] == 3 and len(page["records"]["items"]) == 1
    assert "snapshot" not in page and "intelligence" not in page
    assert page["revision"] == original["revision"]
    assert page["counts"]["findings"] == 3
    assert page["records"]["items"][0]["id"] != original["records"]["items"][0]["id"]


def test_old_complementary_source_resolves_inside_historical_scope(tmp_path):
    from urllib.parse import urlsplit, parse_qs

    store = Store(tmp_path / "workspace")
    fields = base(
        tag="CVE-2026-10001",
        timestamp="2026-11-01T00:00:00Z",
        extra_source_field="first condition evidence",
    )
    add(store, fields, filename="old-first.csv")
    add(
        store,
        {**fields, "tag": "CVE-2026-10002", "extra_source_field": "second condition evidence"},
        filename="old-second.csv",
    )
    add(
        store,
        {
            **fields,
            "tag": "CVE-2026-10001;CVE-2026-10002",
            "timestamp": "2026-11-10T00:00:00Z",
            "ip": "1.1.1.1",
        },
        filename="new.csv",
    )
    eclipse = Eclipse(store)
    row = eclipse.view(cve="CVE-2026-10001", date_to="2026-11-05")["records"]["items"][0]
    url = urlsplit(row["detail_url"])
    detail = eclipse.observation(
        url.path.rsplit("/", 1)[-1], finding_id=parse_qs(url.query)["finding_id"][0]
    )
    assert detail["ip"] == "8.8.8.8"
    assert detail["observed_day"] == "2026-11-01"
    assert detail["source"]["workbook"] == "old-first.csv"
    assert detail["fields"]["extra_source_field"] == "first condition evidence"
    assert detail["fields"]["tag"] == "CVE-2026-10001"


def test_non_cve_field_object_drills_by_exact_condition_without_other_findings(client, app):
    store = app.state.store
    add(
        store,
        base(tag="eol-php;CVE-2026-10001", version="7.3.25", city="Asheville"),
        filename="php73.csv",
    )
    add(
        store,
        base(hostname="other.example.com", tag="eol-php", version="7.4.33", city="Charlotte"),
        filename="php74.csv",
    )
    initial = client.get("/api/eclipse/view", params={"lens": "vulnerability"}).json()
    node = next(
        item
        for item in initial["intelligence"]["graph"]["nodes"]
        if item["type"] == "finding" and item["key"] == "eol-php:7.3"
    )
    assert node["scope"] == {"condition": "eol-php:7.3"}
    scoped = client.get(
        "/api/eclipse/view", params={**node["scope"], "lens": "vulnerability"}
    ).json()
    assert scoped["snapshot"]["counts"]["observations"] == 1
    assert scoped["records"]["total"] == 1
    assert scoped["records"]["items"][0]["tag"] == "eol-php:7.3"
    assert [item["city"] for item in scoped["intelligence"]["locations"]] == ["Asheville"]
    assert not any(item["type"] == "cve" for item in scoped["intelligence"]["graph"]["nodes"])
    prefix = client.get("/api/eclipse/view", params={"condition": "eol-php:7"}).json()
    assert prefix["records"]["total"] == 0
    assert client.get("/api/eclipse/view", params={"condition": "x" * 301}).status_code == 422


def test_non_cve_condition_drill_preserves_independent_admission(tmp_path):
    store = Store(tmp_path / "workspace")
    fields = base(tag="CVE-2026-10001", version="7.3.25")
    add(store, fields, filename="approved.csv")
    add(
        store,
        {**fields, "tag": "eol-php"},
        filename="unapproved.csv",
        admitted=False,
        reason="missing_version",
    )
    view = Eclipse(store)
    selected = view.view(condition="eol-php:7.3", intake="dark_matter")
    assert selected["records"]["total"] == 1
    assert selected["records"]["items"][0]["admitted"] is False
    assert selected["records"]["items"][0]["status"] == "excluded"
    assert view.view(condition="eol-php:7.3", intake="lead")["records"]["total"] == 0
