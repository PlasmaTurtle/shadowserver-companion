"""Bounded FIELD pages cover the full canonical selection without rich graph rebuilds."""

from copy import deepcopy

import pytest

from modules.observatory.tests.support.observations import base, csv_data
from tests.support.workbench import app, client
from modules.accretion.components.awareness import associate
from modules.observatory.components.eclipse import Eclipse
from modules.accretion.components.intake_service import IntakeService
from modules.observatory.components.observatory_field import FieldRevisionChanged
from modules.workspace.components.store import Store


def seed_field(store, count, *, shared=False):
    rows = [
        base(
            hostname=f"mail.organization{index}.com",
            ip=f"8.8.{index // 250}.{index % 250 + 1}",
            tag="CVE-2026-20000" if shared else f"CVE-2026-{20000 + index}",
            timestamp="2026-11-04T12:00:00+00:00",
        )
        for index in range(count)
    ]
    imported = IntakeService(store).enqueue("scan_http_vulnerable.csv", csv_data(rows))
    source = store.one("SELECT sha256 FROM imports WHERE id=?", (imported["id"],))
    with store.transaction() as db:
        for number, fields in enumerate(rows, 2):
            associate(
                db,
                {
                    "ip": fields["ip"],
                    "source": {
                        "workbook": "scan_http_vulnerable.csv",
                        "sheet": "CSV",
                        "row": number,
                        "fields": fields,
                    },
                },
                import_id=imported["id"],
                source_sha256=source["sha256"],
                admitted=True,
            )


@pytest.fixture
def field(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "modules.accretion.components.awareness.now", lambda: "2026-11-04T13:00:00+00:00"
    )
    store = Store(tmp_path / "workspace")
    seed_field(store, 137)
    return Eclipse(store)


def bodies(response):
    return [node for node in response["intelligence"]["graph"]["nodes"] if node["field_object"]]


def test_every_object_is_reachable_beyond_sixty_with_stable_ties(field):
    result = field.view(field_only=True, lens="vulnerability", field_limit=24)
    revision = result["revision"]
    expected_counts = deepcopy(result["intelligence"]["counts"])
    expected_range = result["intelligence"]["graph"]["recency_range"]
    all_ids = []
    while True:
        page = result["intelligence"]["field"]
        assert page["total_objects"] == 137 and page["counts_exact"]
        assert result["intelligence"]["counts"] == expected_counts
        assert result["intelligence"]["graph"]["recency_range"] == expected_range
        assert len(bodies(result)) <= 24
        assert len(result["snapshot"]["observations"]) <= 24 * 5
        assert result["records"]["total"] == 137
        all_ids.extend(node["id"] for node in bodies(result))
        if not page["has_more"]:
            assert page["next_offset"] is None
            break
        result = field.view(
            field_only=True,
            lens="vulnerability",
            field_limit=24,
            field_offset=page["next_offset"],
            field_revision=revision,
        )
    assert len(all_ids) == len(set(all_ids)) == 137
    assert all_ids == sorted(all_ids), "Equal recency uses stable identifier order"
    assert expected_counts["findings"] == expected_counts["observations"] == 137


def test_following_pages_reuse_counts_selection_and_bounded_public_nodes(field, monkeypatch):
    from modules.observatory.components import (
        observatory_field,
        observatory_intelligence,
        observatory_view,
    )

    public = observatory_intelligence.Support.public
    calls = []

    def counted(support):
        calls.append(support.id)
        return public(support)

    def forbidden(*args, **kwargs):
        raise AssertionError("FIELD pages must reuse their selection and exact-count index")

    monkeypatch.setattr(observatory_intelligence.Support, "public", counted)
    monkeypatch.setattr(observatory_view, "_aggregates", forbidden)
    first = field.view(field_only=True, lens="vulnerability", field_limit=12)
    assert len(calls) == 24, "Materialize only12objects and12visibleassets"
    calls.clear()
    monkeypatch.setattr(field, "_build", forbidden)
    monkeypatch.setattr(observatory_view, "project", forbidden)
    monkeypatch.setattr(observatory_field, "build_index", forbidden)
    second = field.view(
        field_only=True,
        lens="vulnerability",
        field_limit=12,
        field_offset=12,
        field_revision=first["revision"],
    )
    assert len(calls) == 24
    assert second["intelligence"]["counts"] == first["intelligence"]["counts"]
    assert set(node["id"] for node in bodies(first)).isdisjoint(
        node["id"] for node in bodies(second)
    )


def test_focus_pages_all_assets_and_reports_omitted_satellites(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "modules.accretion.components.awareness.now", lambda: "2026-11-04T13:00:00+00:00"
    )
    store = Store(tmp_path / "workspace")
    seed_field(store, 151, shared=True)
    field = Eclipse(store)
    overview = field.view(field_only=True, lens="vulnerability")
    body = bodies(overview)[0]
    assert body["total_assets"] == 151
    assert body["loaded_assets"] == 6 and body["omitted_assets"] == 145
    found = set()
    offset = 0
    while True:
        focused = field.view(
            field_only=True,
            lens="vulnerability",
            focus=body["id"],
            field_revision=overview["revision"],
            field_asset_limit=60,
            field_asset_offset=offset,
        )
        graph = focused["intelligence"]["graph"]
        page = focused["intelligence"]["field"]["asset_page"]
        assert page["total_assets"] == 151
        assert focused["intelligence"]["counts"]["findings"] == 151
        satellites = {node["id"] for node in graph["nodes"] if node["type"] == "asset"}
        assert len(satellites) <= 60 and found.isdisjoint(satellites)
        assert len(graph["edges"]) == len(satellites) <= graph["limits"]["max_edges"]
        assert all(edge["observation_count"] == 1 for edge in graph["edges"])
        found.update(satellites)
        if not page["has_more"]:
            break
        offset = page["next_offset"]
    assert len(found) == 151


def test_revision_change_rejects_page_before_rebuilding(field, monkeypatch):
    first = field.view(field_only=True, lens="vulnerability")
    with field.store.transaction() as db:
        db.execute("UPDATE awareness_findings SET changed_at='2026-11-05T00:00:00+00:00'")

    def forbidden(*args, **kwargs):
        raise AssertionError("Stale page should fail before expensive rebuilding")

    monkeypatch.setattr(field, "_build", forbidden)
    with pytest.raises(FieldRevisionChanged):
        field.view(
            field_only=True, lens="vulnerability", field_offset=24, field_revision=first["revision"]
        )


def test_field_api_bounds_and_revision_conflict(client, app):
    seed_field(app.state.store, 3)
    response = client.get("/api/eclipse/view?field_only=true&lens=vulnerability&field_limit=1")
    assert response.status_code == 200, response.text
    first = response.json()
    assert len(bodies(first)) == 1
    assert first["intelligence"]["field"]["total_objects"] == 3
    assert client.get("/api/eclipse/view?field_only=true&field_limit=61").status_code == 422
    assert client.get("/api/eclipse/view?field_only=true&field_asset_offset=-1").status_code == 422
    stale = client.get("/api/eclipse/view?field_only=true&field_revision=" + "0" * 24)
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "field_revision_changed"


def test_unknown_focus_returns_empty_scoped_field(field):
    result = field.view(field_only=True, lens="vulnerability", focus="missing-object")
    assert result["intelligence"]["field"]["total_objects"] == 0
    assert result["intelligence"]["graph"]["nodes"] == []
    assert result["intelligence"]["counts"]["findings"] == 0


def test_unresolved_assets_are_pageable_field_objects_without_entity_hubs(field):
    result = field.view(field_only=True, lens="organization", field_limit=24)
    page = result["intelligence"]["field"]
    assert page["total_objects"] == 137 and page["has_more"]
    assert len(bodies(result)) == 24
    assert all(node["type"] == "asset" and node["omitted_assets"] == 0 for node in bodies(result))
    assert result["intelligence"]["graph"]["edges"] == []


def test_focused_condition_does_not_create_orbits_for_co_observed_conditions(tmp_path):
    from modules.observatory.tests.support.observations import add

    store = Store(tmp_path / "workspace")
    add(store, base(tag="CVE-2026-20000;CVE-2026-20001"))
    field = Eclipse(store)
    overview = field.view(field_only=True, lens="vulnerability")
    selected = bodies(overview)[0]
    focused = field.view(field_only=True, lens="vulnerability", focus=selected["id"])
    assert [node["id"] for node in bodies(focused)] == [selected["id"]]
    assert focused["intelligence"]["field"]["total_objects"] == 1
    assert focused["intelligence"]["field"]["asset_page"]["total_assets"] == 1
    assert focused["intelligence"]["graph"]["limits"]["total_edges"] == 1


def test_unchanged_kev_refresh_does_not_retimestamp_material_risk():
    from modules.library.components.catalog_outreach import material_risk_changes

    identifier = "CVE-2026-20000"
    baseline = {identifier: {"status": "available", "severity": "HIGH", "kev": False}}
    finding = {
        "id": identifier,
        "severity": "HIGH",
        "kev": True,
        "risk": {
            "kev": {
                "entry": {"dateAdded": "2026-11-10"},
                "source": {"retrieved_at": "2026-11-11T12:00:00Z"},
            }
        },
    }
    first = material_risk_changes(baseline, [finding])
    finding["risk"]["kev"]["source"]["retrieved_at"] = "2026-11-13T12:00:00Z"
    repeated = material_risk_changes(baseline, [finding])
    assert first["risk_changed"] and repeated["risk_changed"]
    assert first["risk_updated_at"] == repeated["risk_updated_at"] == "2026-11-10"


def test_old_backlog_keeps_report_date_separate_from_local_discovery(tmp_path, monkeypatch):
    from modules.observatory.tests.support.observations import add

    store = Store(tmp_path / "workspace")
    monkeypatch.setattr(
        "modules.accretion.components.awareness.now", lambda: "2026-11-13T12:00:00+00:00"
    )
    add(store, base(tag="CVE-2026-20000", timestamp="2026-10-01T10:00:00Z"))
    result = Eclipse(store).view(field_only=True, lens="vulnerability")
    body = bodies(result)[0]
    assert body["fresh_at"] == body["local_changed_at"] == "2026-11-13T12:00:00+00:00"
    assert body["first_indexed_at"] == body["latest_indexed_at"] == body["local_changed_at"]
    assert body["last_seen"] == "2026-10-01T10:00:00+00:00"
    assert body["recency_basis"] == "Latest local finding change"


def test_equal_local_change_dates_do_not_reorder_when_a_repeat_advances_last_seen(
    tmp_path, monkeypatch
):
    from modules.observatory.tests.support.observations import add

    store = Store(tmp_path / "workspace")
    monkeypatch.setattr(
        "modules.accretion.components.awareness.now", lambda: "2026-11-13T12:00:00+00:00"
    )
    first = base(
        hostname="first.example.com", tag="CVE-2026-20000", timestamp="2026-11-01T10:00:00Z"
    )
    second = base(
        hostname="second.example.com", tag="CVE-2026-20001", timestamp="2026-11-02T10:00:00Z"
    )
    add(store, first)
    add(store, second)
    eclipse = Eclipse(store)
    before = bodies(eclipse.view(field_only=True, lens="vulnerability"))
    assert [body["id"] for body in before] == sorted(body["id"] for body in before)
    monkeypatch.setattr(
        "modules.accretion.components.awareness.now", lambda: "2026-11-14T12:00:00+00:00"
    )
    add(store, {**first, "timestamp": "2026-11-14T10:00:00Z"})
    after = bodies(eclipse.view(field_only=True, lens="vulnerability"))
    assert [body["id"] for body in before] == [body["id"] for body in after]
    repeated = next(body for body in after if body["label"] == "CVE-2026-20000")
    assert repeated["last_seen"].startswith("2026-11-14")
    assert repeated["density_count"] == 2
    assert repeated["fresh_at"] == "2026-11-13T12:00:00+00:00"
