"""The map represents saved entities, with supporting evidence kept secondary."""

import json

import pytest

from test_eclipse import base
from test_observatory_canonical_0994 import add
from workbench.eclipse import Eclipse
from workbench.observatory_view import ATLAS_LIMIT, _entity_atlas
from workbench.services.entities import EntityService
from workbench.store import Store


def entity(store, identity, *, city="Charlotte", state="NC"):
    domain, entry_id = identity + ".example", "attribution-" + identity
    with store.transaction() as db:
        db.execute(
            """INSERT INTO leads(id,domain,company,created_at,updated_at,attribution,attribution_entry_id)
            VALUES(?,?,?,?,?,?,?)""",
            (identity, domain, "Business " + identity, "2026-11-01", "2026-11-01", "{}", entry_id),
        )
        db.execute("INSERT INTO domain_groups VALUES(?,?,?,?)", (domain, identity, entry_id, "{}"))
        db.execute("INSERT INTO hostnames VALUES(?,?)", (domain, domain))
        db.execute(
            "INSERT INTO entries(id,lead_id,payload,ip,hostname,tag,version,root_domain) VALUES(?,?,?,?,?,?,?,?)",
            (entry_id, identity, "{}", "8.8.8.8", domain, "", "", domain),
        )
        db.execute(
            "INSERT INTO entity_profiles VALUES(?,?)",
            (identity, json.dumps({"city": city, "state": state})),
        )


def observation(store, entity_id=None, **changes):
    result = add(store, base(**changes))
    if entity_id:
        with store.transaction() as db:
            db.execute(
                "UPDATE awareness_assets SET entity_id=? WHERE id=?",
                (entity_id, result["asset_id"]),
            )
    return result


def atlas(eclipse, **filters):
    return eclipse.view(include_undated=True, **filters)["intelligence"]["atlas"]


def test_one_entity_marker_unions_findings_and_assets_without_repeat_inflation(tmp_path):
    store = Store(tmp_path / "workspace")
    entity(store, "one")
    first = observation(store, "one", hostname="first.example", tag="CVE-2026-10001")
    observation(
        store,
        "one",
        hostname="first.example",
        tag="CVE-2026-10001",
        timestamp="2026-11-05T01:02:03Z",
    )
    observation(
        store,
        "one",
        hostname="second.example",
        ip="1.1.1.1",
        tag="CVE-2026-10002",
        latitude="40.7",
        longitude="-74.0",
    )
    repeated = add(
        store, base(hostname="first.example", tag="CVE-2026-10001"), filename="renamed.csv"
    )
    assert first["observation_id"] == repeated["observation_id"]
    result = atlas(Eclipse(store))
    assert result["unit"] == "entities"
    assert result["total_entities"] == result["mapped_entities"] == len(result["nodes"]) == 1
    node = result["nodes"][0]
    assert node["id"] == "entity-location:one" and node["type"] == "entity-location"
    assert node["entity_ids"] == ["one"] and node["scope"] == {"entity_id": "one"}
    assert node["entity_count"] == 1 and node["asset_count"] == 2
    assert node["finding_count"] == 2 and node["observation_count"] == 3
    assert node["workflow_summary"]["findings_by_status"] == {"qualified": 2}
    assert node["reported_location_count"] == 2
    assert node["location_basis"] == "entity_city_area" and node["approximate"]
    assert node["latitude"] == pytest.approx(35.209045)
    assert node["longitude"] == pytest.approx(-80.83099)
    assert node["rows"][0]["observed_day"] == "2026-11-05"


@pytest.mark.parametrize("city,state", [("", ""), ("Fairview", "NC"), ("Unknown City", "GA")])
def test_missing_ambiguous_or_unsupported_entity_location_stays_unplaced_despite_scan_coordinates(
    tmp_path, city, state
):
    store = Store(tmp_path / "workspace")
    entity(store, "one", city=city, state=state)
    observation(store, "one")
    result = atlas(Eclipse(store))
    assert result["nodes"] == [] and result["mapped_entities"] == 0
    assert result["unplaced_entities"] == result["unplaced_count"] == 1
    node = result["unplaced_entities_list"][0]
    assert node["entity_id"] == "one" and node["scope"] == {"entity_id": "one"}
    assert node["latitude"] is None and node["longitude"] is None
    assert node["unplaced_reason"] and node["reported_location_count"] == 1


def test_unassociated_assets_are_counted_without_manufacturing_entities(tmp_path):
    store = Store(tmp_path / "workspace")
    observation(store, hostname="unresolved.example")
    observation(store, hostname="unresolved.example", timestamp="2026-11-05T01:02:03Z")
    result = atlas(Eclipse(store))
    assert result["total_entities"] == result["mapped_entities"] == result["unplaced_entities"] == 0
    assert result["unresolved_asset_count"] == 1 and result["nodes"] == []


@pytest.mark.parametrize("city,state", [("", ""), ("", "SC"), ("Charlotte", "")])
def test_incomplete_profile_uses_latest_report_city_state_together_not_ip_coordinates(
    tmp_path, city, state
):
    store = Store(tmp_path / "workspace")
    entity(store, "one", city=city, state=state)
    source = observation(
        store,
        "one",
        hostname="network.example",
        ip="1.1.1.1",
        city="Raleigh",
        region="NC",
        latitude="40.7",
        longitude="-74.0",
    )
    eclipse = Eclipse(store)
    node = atlas(eclipse)["nodes"][0]
    expected = eclipse._location({"city": "Raleigh", "region": "NC", "country": "US"})
    assert (node["latitude"], node["longitude"]) == expected[:2]
    assert node["latitude"] != 40.7 and node["city"] == "Raleigh" and node["region"] == "NC"
    assert node["location_basis"] == "reported_asset_city_area" and node["approximate"]
    assert node["location_temporal_basis"] == "latest_selected_report"
    assert node["location_hostname"] == "network.example" and node["location_ip"] == "1.1.1.1"
    assert node["location_observation_id"] == source["observation_id"]
    assert node["location_observed_at"] == node["rows"][0]["observed_at"]
    assert (
        node["location_source_locator"]["id"] == node["rows"][0]["id"] == source["observation_id"]
    )
    assert node["location_source_locator"]["source"]["sha256"]
    assert "not a verified business address" in node["basis"]


@pytest.mark.parametrize("city,state", [("Fairview", "NC"), ("Unknown City", "GA")])
def test_complete_unsupported_saved_location_does_not_get_overridden_by_network_report(
    tmp_path, city, state
):
    store = Store(tmp_path / "workspace")
    entity(store, "one", city=city, state=state)
    observation(store, "one", city="Raleigh", region="NC")
    result = atlas(Eclipse(store))
    assert result["nodes"] == [] and result["unplaced_entities"] == 1
    node = result["unplaced_entities_list"][0]
    assert node["city"] == city and node["region"] == state
    assert node["location_temporal_basis"] == "current_saved_profile"
    assert "location_observation_id" not in node


@pytest.mark.parametrize(
    "city,state",
    [
        ("Atlanta", "Georgia"),
        ("Austin", "TX"),
        ("Anchorage", "Alaska"),
        ("Hilo", "HI"),
        ("San Juan", "PR"),
    ],
)
def test_national_saved_entity_cities_are_placed_without_using_scan_coordinates(
    tmp_path, city, state
):
    store = Store(tmp_path / "workspace")
    entity(store, "one", city=city, state=state)
    observation(store, "one", city="Raleigh", region="NC", latitude="0", longitude="0")
    node = atlas(Eclipse(store))["nodes"][0]
    assert node["city"] == city and node["region"] == state
    assert node["location_basis"] == "entity_city_area"
    assert node["latitude"] and node["longitude"]
    assert "location_observation_id" not in node


def test_latest_report_fallback_works_outside_carolinas_without_using_older_supported_city(
    tmp_path,
):
    store = Store(tmp_path / "workspace")
    entity(store, "one", city="", state="")
    observation(store, "one", city="Raleigh", region="NC", timestamp="2026-11-01T12:00:00Z")
    latest = observation(
        store, "one", city="Austin", region="Texas", timestamp="2026-11-05T12:00:00Z"
    )
    node = atlas(Eclipse(store))["nodes"][0]
    assert node["city"] == "Austin" and node["region"] == "Texas"
    assert node["location_observation_id"] == latest["observation_id"]
    assert node["location_basis"] == "reported_asset_city_area"
    assert node["latitude"] == pytest.approx(30.2985, abs=0.1)


def test_puerto_rico_country_code_does_not_allow_foreign_state_matches(tmp_path):
    eclipse = Eclipse(Store(tmp_path / "workspace"))
    assert (
        eclipse._location({"city": "San Juan", "region": "PR", "country": "PR"})[2] == "city_area"
    )
    assert eclipse._location({"city": "Austin", "region": "TX", "country": "PR"})[2] == "unplaced"


def test_jurisdiction_changes_refresh_cached_context_without_hiding_historical_entities(tmp_path):
    store = Store(tmp_path / "workspace")
    entity(store, "north-carolina")
    entity(store, "texas", city="Austin", state="TX")
    observation(store, "north-carolina", hostname="nc.example")
    observation(store, "texas", hostname="tx.example", ip="1.1.1.1")
    eclipse = Eclipse(store)
    before = eclipse.view(include_undated=True)
    settings = store.settings()
    settings["regions"] = ["Texas"]
    with store.transaction() as db:
        db.execute("UPDATE settings SET value=? WHERE key='profile'", (json.dumps(settings),))
    after = eclipse.view(include_undated=True)
    assert after["revision"] != before["revision"]
    assert after["snapshot"]["jurisdiction"]["states"] == ["TX"]
    assert after["snapshot"]["jurisdiction"]["label"] == "Texas"
    assert {node["entity_id"] for node in after["intelligence"]["atlas"]["nodes"]} == {
        "north-carolina",
        "texas",
    }
    assert after["intelligence"]["atlas"]["total_entities"] == 2
    assert eclipse.view(include_undated=True)["revision"] == after["revision"]


@pytest.mark.parametrize(
    "region,code",
    [
        ("Guam", "GU"),
        ("American Samoa", "AS"),
        ("Northern Mariana Islands", "MP"),
        ("US Virgin Islands", "VI"),
    ],
)
def test_configured_territories_fit_without_inventing_unavailable_city_points(
    tmp_path, region, code
):
    store = Store(tmp_path / "workspace")
    settings = store.settings()
    settings["regions"] = [region]
    with store.transaction() as db:
        db.execute("UPDATE settings SET value=? WHERE key='profile'", (json.dumps(settings),))
    eclipse = Eclipse(store)
    assert eclipse.snapshot()["jurisdiction"]["states"] == [code]
    assert (
        eclipse._location({"city": "Unknown City", "region": region, "country": "US"})[2]
        == "unplaced"
    )


def test_latest_associated_hostname_selects_fallback_city_and_cutoff_then_missing_latest_is_unplaced(
    tmp_path,
):
    store = Store(tmp_path / "workspace")
    entity(store, "one", city="", state="")
    old = observation(
        store,
        "one",
        hostname="first.example",
        city="Charlotte",
        region="NC",
        timestamp="2026-11-01T12:00:00Z",
    )
    newer = observation(
        store,
        "one",
        hostname="second.example",
        ip="1.1.1.1",
        city="Raleigh",
        region="NC",
        latitude="37.77",
        longitude="-122.42",
        timestamp="2026-11-05T12:00:00Z",
    )
    eclipse = Eclipse(store)
    current = atlas(eclipse)["nodes"][0]
    historical = atlas(eclipse, date_to="2026-11-02")["nodes"][0]
    assert (
        current["city"] == "Raleigh"
        and current["location_observation_id"] == newer["observation_id"]
    )
    assert (
        historical["city"] == "Charlotte"
        and historical["location_observation_id"] == old["observation_id"]
    )
    assert historical["location_temporal_basis"] == "latest_selected_report"
    newest = observation(
        store,
        "one",
        hostname="third.example",
        ip="8.8.4.4",
        city="",
        region="",
        timestamp="2026-11-06T12:00:00Z",
    )
    result = atlas(eclipse)
    assert result["nodes"] == [] and result["unplaced_entities"] == 1
    missing = result["unplaced_entities_list"][0]
    assert missing["location_observation_id"] == newest["observation_id"]
    assert "latest selected hostname/IP report" in missing["unplaced_reason"]


def test_saving_profile_replaces_report_fallback_and_invalidates_location_provenance(tmp_path):
    store = Store(tmp_path / "workspace")
    entity(store, "one", city="", state="")
    observation(store, "one", city="Raleigh", region="NC")
    eclipse = Eclipse(store)
    assert atlas(eclipse)["nodes"][0]["location_basis"] == "reported_asset_city_area"
    EntityService(store).update_entity_profile(
        "one", {"city": "Charlotte", "state": "NC"}, expected_revision=0
    )
    node = atlas(eclipse)["nodes"][0]
    assert node["city"] == "Charlotte" and node["location_basis"] == "entity_city_area"
    assert node["location_temporal_basis"] == "current_saved_profile"
    assert "location_observation_id" not in node


def test_profile_change_invalidates_cache_and_cutoff_does_not_backdate_current_location(tmp_path):
    store = Store(tmp_path / "workspace")
    entity(store, "one")
    observation(store, "one", timestamp="2026-11-01T01:02:03Z")
    observation(store, "one", timestamp="2026-11-05T01:02:03Z")
    eclipse = Eclipse(store)
    before = eclipse.view(include_undated=True)
    EntityService(store).update_entity_profile(
        "one", {"city": "Raleigh", "state": "NC"}, expected_revision=0
    )
    after = eclipse.view(include_undated=True, date_to="2026-11-02")
    assert after["revision"] != before["revision"]
    current = after["intelligence"]["atlas"]["nodes"][0]
    assert current["city"] == "Raleigh" and current["observation_count"] == 1
    assert current["location_temporal_basis"] == "current_saved_profile"
    assert "saved entity location is current" in current["basis"]
    assert current["latitude"] != before["intelligence"]["atlas"]["nodes"][0]["latitude"]
    assert atlas(eclipse)["nodes"][0]["city"] == "Raleigh", (
        "The previous same-filter cache must also invalidate"
    )


def test_merged_entity_has_one_target_marker_with_combined_support(tmp_path):
    store = Store(tmp_path / "workspace")
    entity(store, "source", city="Raleigh")
    entity(store, "target", city="Charlotte")
    observation(store, "source", hostname="source.example")
    observation(store, "target", hostname="target.example", ip="1.1.1.1")
    eclipse = Eclipse(store)
    assert atlas(eclipse)["total_entities"] == 2
    EntityService(store).merge_entities("source", "target", source_revision=0, target_revision=0)
    result = atlas(eclipse)
    assert result["total_entities"] == 1 and len(result["nodes"]) == 1
    assert result["nodes"][0]["entity_id"] == "target"
    assert result["nodes"][0]["asset_count"] == 2
    assert result["nodes"][0]["city"] == "Charlotte"


def aggregate_row(identity, **changes):
    result = {
        "id": identity,
        "entity_id": identity,
        "asset_id": "asset-" + identity,
        "observed_at": "2026-11-01T00:00:00Z",
        "observed_day": "2026-11-01",
        "finding_ids": ["finding-" + identity],
        "admitted": True,
        "dark_matter": False,
        "status": "qualified",
        "latitude": 35.2,
        "longitude": -80.8,
    }
    result.update(changes)
    return result


def test_equal_time_fallback_uses_stable_observation_id_not_input_order():
    rows = [
        aggregate_row("z", entity_id="one", city="Raleigh", region="NC", country="US"),
        aggregate_row("a", entity_id="one", city="Charlotte", region="NC", country="US"),
    ]
    result = _entity_atlas(
        rows, {"one": {"name": "One"}}, location_resolver=Eclipse(None)._location
    )
    node = result["nodes"][0]
    assert node["city"] == "Raleigh" and node["location_observation_id"] == "z"
    assert node["rows"][0]["id"] == "z"


def test_entity_cap_and_unplaced_directory_preserve_exact_counts():
    rows = [aggregate_row(str(index)) for index in range(ATLAS_LIMIT + 2)]
    entities = {
        row["entity_id"]: {
            "name": row["entity_id"],
            "map_location": {
                "city": "Charlotte",
                "region": "NC",
                "latitude": 35.2,
                "longitude": -80.8,
                "location_basis": "entity_city_area",
                "approximate": True,
            },
        }
        for row in rows
    }
    result = _entity_atlas(rows, entities)
    assert result["total_entities"] == result["mapped_entities"] == ATLAS_LIMIT + 2
    assert len(result["nodes"]) == ATLAS_LIMIT and result["omitted_nodes"] == 2
    unplaced = _entity_atlas(rows, {identity: {"name": identity} for identity in entities})
    assert unplaced["unplaced_entities"] == ATLAS_LIMIT + 2
    assert len(unplaced["unplaced_entities_list"]) == ATLAS_LIMIT
    assert unplaced["omitted_unplaced_entities"] == 2


def test_workflow_counts_findings_and_cases_once_and_no_findings_entity_is_retained():
    rows = [
        aggregate_row("a", entity_id="one", case_id="case-one", case_stage="in_progress"),
        aggregate_row(
            "b",
            entity_id="one",
            finding_ids=["finding-a"],
            case_id="case-one",
            case_stage="in_progress",
        ),
        aggregate_row(
            "c",
            entity_id="two",
            finding_ids=[],
            status="excluded",
            admitted=False,
            dark_matter=True,
        ),
    ]
    result = _entity_atlas(rows, {"one": {"name": "One"}, "two": {"name": "Two"}})
    summaries = {node["entity_id"]: node for node in result["unplaced_entities_list"]}
    assert summaries["one"]["workflow_summary"] == {
        "findings_by_status": {"qualified": 1},
        "cases_by_stage": {"in_progress": 1},
        "case_count": 1,
    }
    assert summaries["two"]["finding_count"] == 0 and summaries["two"]["entity_count"] == 1
