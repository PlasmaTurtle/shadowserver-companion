"""Truthful, bounded discovery from preserved observations, without acquisition."""

from copy import deepcopy
import hashlib
import json
import random
import socket
import time

import pytest

from workbench.observatory_intelligence import project


def observation(identity, **changes):
    row = {
        "id": identity,
        "ip": "8.8.8.8",
        "ip_valid": True,
        "hostname": "web.alpha.example",
        "domain": "alpha.example",
        "tag": "CVE-2026-10001",
        "version": "1.0",
        "product": "Example Web",
        "protocol": "tcp",
        "port": "443",
        "observed_at": "2026-01-01T12:00:00Z",
        "observed_day": "2026-01-01",
        "imported_at": "2026-11-11T12:00:00Z",
        "entity_id": "entity-alpha",
        "entity_name": "Alpha",
        "case_id": None,
        "lead_id": "lead-alpha",
        "job_id": None,
        "status": "qualified",
        "latitude": 35.2,
        "longitude": -80.8,
        "location_basis": "reported_coordinates",
        "source_available": True,
        "original_url": "/api/imports/import-one/original",
        "source": {
            "import_id": "import-one",
            "workbook": "observations.csv",
            "sheet": "",
            "row": 2,
            "sha256": "a" * 64,
        },
    }
    row.update(changes)
    return row


def sample_rows():
    return [
        observation("a-first", tag="CVE-2026-10001; cve-2026-10001"),
        observation("a-return", observed_day="2026-01-03", observed_at="2026-01-03T12:00:00Z"),
        observation(
            "b-shared",
            hostname="web.beta.example",
            domain="beta.example",
            entity_id="entity-beta",
            entity_name="Beta",
            lead_id="lead-beta",
            observed_day="2026-01-02",
            observed_at="2026-01-02T12:00:00Z",
            version="2.0",
        ),
        observation(
            "b-dns",
            hostname="dns.beta.example",
            domain="beta.example",
            ip="1.1.1.1",
            entity_id="entity-beta",
            entity_name="Beta",
            lead_id="lead-beta",
            observed_day="2026-01-03",
            observed_at="2026-01-03T12:00:00Z",
            product="Example DNS",
            protocol="udp",
            port="53",
            tag="CVE-2026-10002",
        ),
        observation(
            "unknown",
            hostname="unknown.example",
            domain="unknown.example",
            ip="",
            ip_valid=False,
            entity_id=None,
            entity_name="",
            lead_id=None,
            tag="eol-example",
            product="",
            protocol="",
            port="",
            version="",
            observed_day="",
            observed_at="",
            latitude=None,
            longitude=None,
            location_basis="unplaced",
            status="excluded",
        ),
    ]


def snapshot(rows):
    return {
        "schema_version": 2,
        "generated_at": "2026-11-11T12:00:00Z",
        "observations": rows,
        "entities": [
            {"id": "entity-alpha", "name": "Alpha", "domain": "alpha.example", "case_ids": []},
            {"id": "entity-beta", "name": "Beta", "domain": "beta.example", "case_ids": []},
        ],
        "imports": [],
        "counts": {"rows": len(rows)},
        "coverage_complete": True,
        "warnings": [],
    }


def typed_nodes(result, kind):
    return [n for n in result["graph"]["nodes"] if n["type"] == kind]


def node_for(result, kind, value):
    return next(n for n in typed_nodes(result, kind) if value in str(n["key"]))


def assert_bounded_support(value):
    if isinstance(value, dict):
        if "observation_ids" in value:
            assert len(value["observation_ids"]) <= 5
            assert len(set(value["observation_ids"])) == len(value["observation_ids"])
        if "examples" in value:
            assert len(value["examples"]) <= 3
        for child in value.values():
            assert_bounded_support(child)
    elif isinstance(value, list):
        for child in value:
            assert_bounded_support(child)


def test_shared_cve_counts_source_rows_once_and_does_not_assert_shared_ownership():
    data = project(snapshot(sample_rows()))
    shared = node_for(data, "cve", "CVE-2026-10001")
    assert shared["observation_count"] == 3
    assert shared["asset_count"] == 2
    assert shared["entity_count"] == 2
    assert set(shared["entity_ids"]) == {"entity-alpha", "entity-beta"}
    assert set(shared["observation_ids"]) == {"a-first", "a-return", "b-shared"}
    assert shared["first_seen"] == "2026-01-01" and shared["last_seen"] == "2026-01-03"
    ids = {n["id"]: n for n in data["graph"]["nodes"]}
    edges = [e for e in data["graph"]["edges"] if e["target"] == shared["id"]]
    assert len(edges) == 2
    assert sorted(e["observation_count"] for e in edges) == [1, 2]
    assert all(ids[e["source"]]["type"] == "asset" for e in edges)
    assert all(e["basis"] for e in edges)
    assert not any(
        ids[e["source"]]["type"] == ids[e["target"]]["type"] == "entity"
        for e in data["graph"]["edges"]
    )


def test_missing_geography_and_dates_remain_in_denominator_and_temporal_claims_are_observed_only():
    data = project(snapshot(sample_rows()))
    assert data["counts"]["total_rows"] == data["counts"]["selected_rows"] == 5
    assert data["counts"]["mapped_rows"] == 4
    assert data["counts"]["unplaced_rows"] == 1
    assert data["counts"]["dated_rows"] == 4
    assert data["counts"]["undated_rows"] == 1
    bins = {item["day"]: item for item in data["timeline"]}
    assert set(bins) == {"2026-01-01", "2026-01-02", "2026-01-03"}
    assert bins["2026-01-01"]["new_assets"] == 1
    assert bins["2026-01-03"]["new_assets"] == 1
    assert bins["2026-01-03"]["returning_assets"] == 1
    assert all("remediated" not in item and "resolved" not in item for item in bins.values())
    assert "2026-11-11" not in bins  # Import time never becomes scan time.


def test_shared_ip_is_a_reported_relationship_without_entity_assignment():
    rows = sample_rows()
    before = deepcopy(rows)
    data = project(snapshot(rows), lens="ip")
    shared = node_for(data, "ip", "8.8.8.8")
    assert shared["entity_count"] == 2 and shared["asset_count"] == 2
    assert shared["observation_count"] == 3
    assert not any(n["type"] == "ip" and n["key"] == "" for n in data["graph"]["nodes"])
    assert rows == before
    assert {r["entity_id"] for r in rows if r["ip"] == "8.8.8.8"} == {"entity-alpha", "entity-beta"}


def test_version_relationships_retain_product_or_service_context():
    rows = [
        observation("web-v1"),
        observation(
            "dns-v1", hostname="dns.alpha.example", protocol="udp", port="53", product="Example DNS"
        ),
        observation("web-v2", hostname="web2.alpha.example", version="2.0"),
    ]
    data = project(snapshot(rows), lens="version")
    versions = typed_nodes(data, "version")
    assert len(versions) == 3
    assert len({n["key"] for n in versions}) == 3
    assert all(n["asset_count"] == 1 for n in versions)


def test_filters_select_actual_observations_without_rewriting_totals():
    original = snapshot(sample_rows())
    data = project(original, entity_id="entity-beta", cve="CVE-2026-10001")
    assert data["counts"]["total_rows"] == 5
    assert data["counts"]["selected_rows"] == 1
    assert typed_nodes(data, "cve")[0]["observation_ids"] == ["b-shared"]
    dates = project(original, date_from="2026-01-02", date_to="2026-01-03")
    assert dates["counts"]["selected_rows"] == 3
    assert dates["counts"]["undated_rows"] == 0
    unplaced = project(original, unplaced=True)
    assert unplaced["counts"]["selected_rows"] == 1
    assert unplaced["counts"]["unplaced_rows"] == 1
    missing = project(original, q="a needle that does not occur")
    assert missing["counts"]["selected_rows"] == 0
    assert missing["graph"]["nodes"] == [] and missing["graph"]["edges"] == []


def test_stable_ids_and_selection_ignore_input_iteration_order():
    rows = sample_rows()
    first = project(snapshot(rows), max_nodes=4, max_edges=3)
    shuffled = deepcopy(rows)
    random.Random(98).shuffle(shuffled)
    second = project(snapshot(shuffled), max_nodes=4, max_edges=3)
    assert first["graph"] == second["graph"]
    assert first["timeline"] == second["timeline"]
    assert len(first["graph"]["nodes"]) <= 4 and len(first["graph"]["edges"]) <= 3
    assert first["graph"]["limits"]["nodes_truncated"]
    assert all(
        e["source"] in {n["id"] for n in first["graph"]["nodes"]}
        and e["target"] in {n["id"] for n in first["graph"]["nodes"]}
        for e in first["graph"]["edges"]
    )


def test_more_than_ten_thousand_rows_have_full_counts_and_bounded_graph():
    rows = [
        observation(
            hashlib.sha256(str(i).encode()).hexdigest(),
            hostname=f"asset{i % 2000}.example",
            ip=f"10.{i // 65536}.{(i // 256) % 256}.{i % 256}",
            entity_id=f"entity-{i % 80}",
            entity_name=f"Entity {i % 80}",
            tag=f"CVE-2026-{10000 + i % 30}",
            version=str(i % 12),
            observed_day=f"2026-01-{1 + i % 28:02d}",
            latitude=None if i % 3 == 0 else 35.2,
            longitude=None if i % 3 == 0 else -80.8,
        )
        for i in range(12000)
    ]
    began = time.monotonic()
    data = project(snapshot(rows), max_nodes=75, max_edges=90)
    elapsed = time.monotonic() - began
    assert data["counts"]["total_rows"] == data["counts"]["selected_rows"] == 12000
    assert data["counts"]["unplaced_rows"] == 4000
    assert data["counts"]["mapped_rows"] == 8000
    assert sum(b["observation_count"] for b in data["timeline"]) == 12000
    assert len(data["graph"]["nodes"]) <= 75 and len(data["graph"]["edges"]) <= 90
    assert data["graph"]["limits"]["total_nodes"] > 75
    assert data["graph"]["limits"]["nodes_truncated"]
    assert_bounded_support(data)
    assert len(json.dumps(data, allow_nan=False)) < 2_000_000
    # Generous regression guard against accidental quadratic cross-entity cliques.
    assert elapsed < 20


def test_projection_never_uses_network_and_does_not_mutate_saved_input(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Observatory projections must remain offline")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    original = snapshot(sample_rows())
    original["coverage_complete"] = False
    original["warnings"] = ["Original source unavailable; retained observations shown."]
    before = deepcopy(original)
    data = project(original)
    assert original == before
    assert not data["coverage"]["complete"]
    assert data["coverage"]["warnings"] == original["warnings"]
    assert data["coverage"]["indexed_rows"] == 5
    json.dumps(data, allow_nan=False)


def test_large_untrusted_source_labels_cannot_expand_graph_payload_without_bound():
    attack = '<img src="https://invalid.example/x" onerror="alert(1)">' + "Z" * 200000
    original = snapshot([observation("oversized", hostname=attack, tag=attack, version=attack)])
    before = deepcopy(original)
    data = project(original, lens="version")
    assert original == before
    assert all(len(n["label"]) <= 180 for n in data["graph"]["nodes"])
    assert all(len(n["id"]) < 100 for n in data["graph"]["nodes"])
    assert len(json.dumps(data, allow_nan=False)) < 100000


def test_focus_drills_into_complete_support_even_when_graph_is_visually_bounded():
    original = snapshot(sample_rows())
    whole = project(original)
    target = node_for(whole, "cve", "CVE-2026-10001")
    focused = project(original, focus=target["id"], lens="ip", max_nodes=3, max_edges=2)
    assert focused["counts"]["total_rows"] == 5
    assert focused["counts"]["selected_rows"] == 3
    assert node_for(focused, "ip", "8.8.8.8")["observation_count"] == 3
    asset = next(
        n
        for n in typed_nodes(whole, "asset")
        if set(n["observation_ids"]) == {"a-first", "a-return"}
    )
    exact = project(original, focus=asset["id"])
    assert exact["counts"]["selected_rows"] == 2
    assert {i for n in exact["graph"]["nodes"] for i in n["observation_ids"]} == {
        "a-first",
        "a-return",
    }
    assert project(original, focus="unknown-node")["counts"]["selected_rows"] == 0


def test_presentation_limits_never_hide_searchable_source_observations(monkeypatch):
    monkeypatch.setattr("workbench.observatory_intelligence.MAX_ROWS", 3)
    rows = sample_rows()
    data = project(snapshot(rows))
    assert data["counts"]["total_rows"] == 5
    assert data["counts"]["selected_rows"] == data["coverage"]["indexed_rows"] == 5
    assert data["coverage"]["omitted_rows"] == 0
    assert data["coverage"]["complete"]
    assert project(snapshot(list(reversed(rows))))["graph"] == data["graph"]
    omitted_under_old_cap = sorted(rows, key=lambda row: row["id"])[-1]
    result = project(snapshot(rows), q=omitted_under_old_cap["hostname"])
    assert result["counts"]["selected_rows"] >= 1


def test_timeline_window_discloses_omitted_days_without_reducing_selected_totals(monkeypatch):
    monkeypatch.setattr("workbench.observatory_intelligence.MAX_TIMELINE", 2)
    data = project(snapshot(sample_rows()))
    assert [b["day"] for b in data["timeline"]] == ["2026-01-02", "2026-01-03"]
    assert data["coverage"]["timeline_omitted_days"] == 1
    assert data["counts"]["dated_rows"] == 4 and data["counts"]["selected_rows"] == 5
    assert sum(b["observation_count"] for b in data["timeline"]) == 3
    assert any("Timeline" in message for message in data["coverage"]["warnings"])


def test_provenance_links_are_local_generated_routes_and_unavailable_sources_are_explicit():
    row = observation(
        "unsafe/id?query=<script>",
        original_url="javascript:alert(1)",
        detail_url="https://untrusted.example/collect",
        source={
            "import_id": "../source?escape=1",
            "workbook": "<script>alert(1)</script>",
            "sheet": "",
            "row": 7,
            "sha256": "b" * 64,
        },
    )
    data = project(snapshot([row]))
    examples = [example for node in data["graph"]["nodes"] for example in node["examples"]]
    assert examples
    for example in examples:
        assert (
            example["detail_url"] == "/api/eclipse/observations/unsafe%2Fid%3Fquery%3D%3Cscript%3E"
        )
        assert example["original_url"] == "/api/imports/..%2Fsource%3Fescape%3D1/original"
        assert example["source"]["row"] == 7 and example["source"]["sha256"] == "b" * 64
    unavailable = project(snapshot([{**row, "source_available": False}]))
    assert all(
        example["original_url"] is None and not example["source_available"]
        for node in unavailable["graph"]["nodes"]
        for example in node["examples"]
    )


def test_identifier_cap_discloses_omissions_but_never_invents_a_shorter_cve():
    tags = ";".join(f"CVE-2026-{10000 + i}" for i in range(9))
    capped = project(snapshot([observation("many-identifiers", tag=tags)]))
    assert len(typed_nodes(capped, "cve")) == 8
    assert capped["coverage"]["identifier_limited_rows"] == 1
    assert not capped["coverage"]["complete"]
    # Cut exactly after an otherwise valid shorter ID, inside the actual ID.
    from workbench.observatory_intelligence import MAX_FIELD

    prefix = "x" * (MAX_FIELD - len(";CVE-2026-1000")) + ";"
    cut = project(snapshot([observation("split-identifier", tag=prefix + "CVE-2026-100000001")]))
    assert not typed_nodes(cut, "cve")
    assert cut["coverage"]["identifier_limited_rows"] == 1
    assert not cut["coverage"]["complete"]


def test_reported_cve_array_limit_is_also_visible_in_coverage():
    row = observation(
        "cve-array", tag="", reported_cves=[f"CVE-2026-{10000 + i}" for i in range(9)]
    )
    data = project(snapshot([row]))
    assert len(typed_nodes(data, "cve")) == 8
    assert data["coverage"]["identifier_limited_rows"] == 1
    assert not data["coverage"]["complete"]


def test_service_values_without_hostname_or_ip_do_not_merge_unknown_endpoints():
    rows = [
        observation("anonymous-a", hostname="", ip="", ip_valid=False),
        observation("anonymous-b", hostname="", ip="bad address", ip_valid=False),
    ]
    data = project(snapshot(rows), lens="service")
    assert data["counts"]["assets"] == 2
    assert len(typed_nodes(data, "asset")) == 2
    assert typed_nodes(data, "service")[0]["asset_count"] == 2


def test_discovery_patterns_expose_shared_support_and_recurrence_without_negative_scan_claims():
    data = project(snapshot(sample_rows()))
    shared = next(
        p for p in data["patterns"] if p["type"] == "shared_cve" and "CVE-2026-10001" in p["key"]
    )
    assert shared["entity_count"] == shared["asset_count"] == 2
    assert shared["observation_count"] == 3
    assert set(shared["observation_ids"]) == {"a-first", "a-return", "b-shared"}
    recurrent = next(p for p in data["patterns"] if p["type"] == "recurrent_asset")
    assert recurrent["day_count"] == 2 and recurrent["observation_count"] == 2
    assert recurrent["first_seen"] == "2026-01-01" and recurrent["last_seen"] == "2026-01-03"
    assert "do not establish" in recurrent["basis"].lower()
    assert all(p["examples"] and p["basis"] and p["node_id"] for p in data["patterns"])
    assert_bounded_support(data["patterns"])


def test_saved_intelligence_and_reported_network_filters_do_not_treat_unknown_as_false_or_known():
    rows = [
        observation("known", asn="15169", kev=True, ransomware_known=True),
        observation("unknown", asn="", kev=None, ransomware_known=None),
        observation("false", asn="13335", kev=False, ransomware_known=False),
        observation("truthy", asn="0", kev=1, ransomware_known="known"),
    ]
    original = snapshot(rows)
    for keyword in ("kev", "ransomware"):
        filtered = project(original, intelligence=keyword)
        assert filtered["counts"]["selected_rows"] == 1
        assert {i for n in filtered["graph"]["nodes"] for i in n["observation_ids"]} == {"known"}
    missing = project(original, network="__unknown")
    assert missing["counts"]["selected_rows"] == 1
    assert {i for n in missing["graph"]["nodes"] for i in n["observation_ids"]} == {"unknown"}
    assert project(original, network="0015169")["counts"]["selected_rows"] == 1
    assert project(original, network="0")["counts"]["selected_rows"] == 1
    assert project(original, network="13335", intelligence="kev")["counts"]["selected_rows"] == 0


def test_undated_inclusion_is_explicit_and_keeps_other_filters_active():
    rows = sample_rows()
    dated = project(snapshot(rows), date_from="2026-01-02", date_to="2026-01-03")
    included = project(
        snapshot(rows), date_from="2026-01-02", date_to="2026-01-03", include_undated=True
    )
    assert dated["counts"]["selected_rows"] == 3 and dated["counts"]["undated_rows"] == 0
    assert included["counts"]["selected_rows"] == 4 and included["counts"]["undated_rows"] == 1
    assert included["timeline"] == dated["timeline"]
    qualified = project(
        snapshot(rows), date_from="2026-01-02", include_undated=True, status="qualified"
    )
    assert qualified["counts"]["selected_rows"] == 3
    assert qualified["counts"]["undated_rows"] == 0


def test_geography_requires_a_finite_complete_coordinate_pair():
    rows = [
        observation("valid"),
        observation("only-lat", longitude=None),
        observation("only-lon", latitude=None),
        observation("nan", latitude=float("nan")),
        observation("infinite", longitude=float("inf")),
        observation("boolean", latitude=True),
        observation("range", latitude=91),
        observation("numeric-text", latitude="35.2", longitude="-80.8"),
    ]
    data = project(snapshot(rows))
    assert data["counts"]["mapped_rows"] == 1
    assert data["counts"]["unplaced_rows"] == 7
    missing = project(snapshot(rows), unplaced=True)
    assert missing["counts"]["selected_rows"] == missing["counts"]["unplaced_rows"] == 7
    assert missing["counts"]["mapped_rows"] == 0
    json.dumps(data, allow_nan=False)


def test_first_seen_findings_use_full_indexed_history_before_date_filters():
    original = snapshot(sample_rows())
    current = project(original, date_from="2026-01-03")
    newly_observed = [p for p in current["patterns"] if p["type"] == "first_seen_finding"]
    assert {p["key"] for p in newly_observed} == {"CVE-2026-10002"}
    assert newly_observed[0]["first_seen"] == "2026-01-03"
    assert "not a verified onset date" in newly_observed[0]["basis"]
    prior_finding = project(original, date_from="2026-01-03", cve="CVE-2026-10001")
    assert prior_finding["counts"]["selected_rows"] == 1
    assert not any(p["type"] == "first_seen_finding" for p in prior_finding["patterns"])
    earlier_window = project(original, date_to="2026-01-02")
    assert not any(p["type"] == "first_seen_finding" for p in earlier_window["patterns"])
    first_import = project(snapshot([observation("first-import")]))
    assert not any(p["type"] == "first_seen_finding" for p in first_import["patterns"])
