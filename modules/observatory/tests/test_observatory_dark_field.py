"""Dark clouds count retained source events and provide a complete Records route."""

from modules.observatory.tests.support.observations import base
from modules.observatory.tests.support.observations import add
from modules.observatory.components.eclipse import Eclipse
from modules.observatory.components.observatory_field import _dark_history
from modules.workspace.components.store import Store


def test_mixed_cloud_reasons_count_unique_unadmitted_events_not_retired_work(tmp_path):
    store = Store(tmp_path / "workspace")
    original = base(tag="CVE-2026-20000", timestamp="2026-11-01T10:00:00Z")
    approved = add(store, original)
    first = {**original, "ip": "1.1.1.1", "timestamp": "2026-11-02T10:00:00Z"}
    add(store, first, admitted=False, reason="endpoint_review", filename="dark.csv")
    add(store, first, admitted=False, reason="endpoint_review", filename="renamed.csv")
    add(
        store,
        {**first, "timestamp": "2026-11-03T10:00:00Z"},
        admitted=False,
        reason="endpoint_review",
    )
    add(store, {**first, "timestamp": "2026-11-04T10:00:00Z"}, admitted=False)
    with store.transaction() as db:
        db.execute(
            "UPDATE awareness_findings SET workflow='ignored' WHERE id=?",
            (approved["finding_ids"][0],),
        )
    eclipse = Eclipse(store)
    result = eclipse.view(field_only=True, lens="vulnerability")
    node = next(node for node in result["intelligence"]["graph"]["nodes"] if node["field_object"])
    assert node["admitted"] and not node["dark_matter"]
    assert node["density_count"] == 4
    assert node["admitted_density"] == 1 and node["dark_matter_density"] == 3
    assert {item["reason"]: item["count"] for item in node["dark_matter_reasons"]} == {
        "endpoint_review": 2,
        "Not admitted": 1,
    }
    assert node["dark_matter_counted_observations"] == 3
    assert node["dark_matter_first_seen"].startswith("2026-11-02")
    assert node["dark_matter_last_seen"].startswith("2026-11-04")
    assert node["dark_matter_reasons_omitted"] == 0
    assert (
        store.one(
            "SELECT admitted FROM awareness_observations WHERE id=?", (approved["observation_id"],)
        )["admitted"]
        == 1
    )


def test_dark_reason_groups_are_bounded_without_losing_the_denominator():
    rows = [
        {
            "id": str(index),
            "admitted": False,
            "dark_matter": True,
            "intake_reason": f"reason_{index}",
            "observed_at": "",
        }
        for index in range(20)
    ]
    result = _dark_history(
        [*rows, *rows, {"id": "approved", "admitted": True, "workflow": "ignored"}]
    )
    assert len(result["dark_matter_reasons"]) == 8
    assert sum(item["count"] for item in result["dark_matter_reasons"]) == 20
    assert result["dark_matter_reason_groups"] == 20
    assert (
        result["dark_matter_counted_observations"]
        == result["dark_matter_undated_observations"]
        == 20
    )


def test_dark_records_include_sources_without_parsed_findings(tmp_path):
    store = Store(tmp_path / "workspace")
    added = add(
        store,
        base(tag="", timestamp="2026-11-01T10:00:00Z"),
        admitted=False,
        reason="unsupported_finding",
    )
    eclipse = Eclipse(store)
    result = eclipse.view(intake="dark_matter")
    assert result["records"]["kind"] == "observations"
    assert result["records"]["total"] == 1
    assert result["snapshot"]["counts"]["findings"] == 0
    item = result["records"]["items"][0]
    assert item["record_kind"] == "observation"
    assert item["id"] == added["observation_id"]
    assert item["admitted"] is False and item["dark_matter"] is True
    assert item["intake_reason"] == "unsupported_finding"
    detail = eclipse.observation(item["id"])
    assert detail["source_available"] and detail["fields"]["tag"] == ""


def test_dark_records_for_approved_cve_retain_only_its_unadmitted_endpoint(tmp_path):
    store = Store(tmp_path / "workspace")
    fields = base(tag="CVE-2026-20000", timestamp="2026-11-01T10:00:00Z")
    approved = add(store, fields)
    rejected = add(
        store,
        {**fields, "ip": "1.1.1.1", "timestamp": "2026-11-02T10:00:00Z"},
        admitted=False,
        reason="endpoint_review",
    )
    eclipse = Eclipse(store)
    for filters in (
        {"intake": "dark_matter"},
        {"intake": "dark_matter", "cve": "CVE-2026-20000"},
        {"status": "excluded", "cve": "CVE-2026-20000"},
    ):
        result = eclipse.view(**filters)
        assert result["records"]["kind"] == "observations"
        assert result["records"]["total"] == 1
        row = result["records"]["items"][0]
        assert row["id"] == rejected["observation_id"]
        assert row["id"] != approved["observation_id"]
        assert row["ip"] == "1.1.1.1" and row["admitted"] is False
        assert result["snapshot"]["counts"]["admitted_observations"] == 0
        cve = next(
            node for node in result["intelligence"]["graph"]["nodes"] if node["type"] == "cve"
        )
        assert cve["admitted_density"] == 0 and cve["dark_matter_density"] == 1
    unfiltered = eclipse.view()
    assert unfiltered["records"]["kind"] == "findings"
    assert unfiltered["records"]["total"] == 1
    assert unfiltered["records"]["items"][0]["ip"] == fields["ip"]


def test_dark_condition_of_mixed_source_keeps_reason_and_detail_context(tmp_path):
    from urllib.parse import parse_qs, urlsplit

    store = Store(tmp_path / "workspace")
    fields = base(tag="CVE-2026-20000", timestamp="2026-11-01T10:00:00Z")
    first = add(store, fields)
    dark = add(
        store, {**fields, "tag": "CVE-2026-20001"}, admitted=False, reason="attribution_review"
    )
    assert first["observation_id"] == dark["observation_id"]
    eclipse = Eclipse(store)
    for filters in ({"intake": "dark_matter"}, {"intake": "dark_matter", "cve": "CVE-2026-20001"}):
        result = eclipse.view(**filters)
        row = result["records"]["items"][0]
        assert row["admitted"] is False and row["intake_reason"] == "attribution_review"
        assert row["observation_admitted"] is True
        url = urlsplit(row["detail_url"])
        detail = eclipse.observation(
            url.path.rsplit("/", 1)[-1], finding_id=parse_qs(url.query)["finding_id"][0]
        )
        assert detail["admitted"] is False and detail["dark_matter"] is True
        assert detail["observation_admitted"] is True
        assert detail["tag"] == detail["fields"]["tag"] == "CVE-2026-20001"
        assert detail["intake_reason"] == "attribution_review"
    field = eclipse.view(field_only=True, lens="vulnerability")
    node = next(
        node
        for node in field["intelligence"]["graph"]["nodes"]
        if node["label"] == "CVE-2026-20001"
    )
    assert node["dark_matter_reasons"] == [
        {"reason": "attribution_review", "label": "Attribution review", "count": 1}
    ]
