"""Repeated unparsed dark observations do not masquerade as new discoveries."""

from modules.observatory.tests.support.observations import base
from modules.observatory.tests.support.observations import add
from modules.observatory.components import observatory_field
from modules.observatory.components.eclipse import Eclipse
from modules.workspace.components.store import Store


def dark_add(store, monkeypatch, hostname, day, *, filename=None, port="443"):
    monkeypatch.setattr(
        "modules.accretion.components.awareness.now", lambda: f"2026-11-{day:02d}T12:00:00+00:00"
    )
    return add(
        store,
        base(hostname=hostname, tag="", timestamp=f"2026-11-{day:02d}T01:00:00Z", port=port),
        admitted=False,
        reason="unsupported_finding",
        filename=filename or f"{hostname}-{day}.csv",
    )


def objects(eclipse, *, lens="organization", **filters):
    response = eclipse.view(
        field_only=True, lens=lens, intake="dark_matter", field_limit=24, **filters
    )
    return [node for node in response["intelligence"]["graph"]["nodes"] if node["field_object"]]


def test_daily_dark_repeat_increases_density_without_changing_freshness_or_order(
    tmp_path, monkeypatch
):
    store = Store(tmp_path / "workspace")
    first = dark_add(store, monkeypatch, "old.example.com", 1)
    dark_add(store, monkeypatch, "new.example.com", 5)
    eclipse = Eclipse(store)
    before = objects(eclipse)
    old_before = next(node for node in before if node["asset_id"] == first["asset_id"])
    assert before[0]["asset_id"] != first["asset_id"]

    dark_add(store, monkeypatch, "old.example.com", 10)
    dark_add(store, monkeypatch, "old.example.com", 10, filename="renamed-repeat.csv")
    after = objects(eclipse)
    old_after = next(node for node in after if node["asset_id"] == first["asset_id"])

    assert [node["id"] for node in after] == [node["id"] for node in before]
    assert old_after["fresh_at"] == old_before["fresh_at"]
    assert old_after["fresh_at"].startswith("2026-11-01")
    assert old_after["last_seen"] > old_before["last_seen"]
    assert old_before["density_count"] == 1 and old_after["density_count"] == 2
    assert old_after["dark_matter_density"] == 2
    assert old_after["admitted_density"] == 0
    assert old_after["finding_count"] == 0
    assert "discovery" in old_after["recency_basis"].casefold()

    # A date-range filter changes visible history, not local discovery time.
    scoped = objects(eclipse, date_from="2026-11-05")
    scoped_old = next(node for node in scoped if node["asset_id"] == first["asset_id"])
    assert scoped_old["fresh_at"] == old_before["fresh_at"]


def test_grouped_dark_discovery_advances_for_a_new_asset_but_not_a_repeat(tmp_path, monkeypatch):
    store = Store(tmp_path / "workspace")
    dark_add(store, monkeypatch, "one.example.com", 1)
    dark_add(store, monkeypatch, "two.example.com", 5)
    eclipse = Eclipse(store)
    before = objects(eclipse, lens="service")[0]
    assert before["asset_count"] == 2
    assert before["fresh_at"].startswith("2026-11-05")

    dark_add(store, monkeypatch, "one.example.com", 10)
    repeated = objects(eclipse, lens="service")[0]
    assert repeated["id"] == before["id"]
    assert repeated["fresh_at"] == before["fresh_at"]
    assert repeated["density_count"] == 3

    dark_add(store, monkeypatch, "three.example.com", 12)
    expanded = objects(eclipse, lens="service")[0]
    assert expanded["id"] == before["id"]
    assert expanded["fresh_at"].startswith("2026-11-12")
    assert expanded["asset_count"] == 3 and expanded["density_count"] == 4
    assert expanded["finding_count"] == 0


def test_raw_condition_discovery_is_distinct_and_normalized():
    original = {
        "id": "old-source",
        "asset_id": "one-asset",
        "finding_ids": [],
        "reported_tag": "!unparsed-condition",
        "protocol": "tcp",
        "port": "443",
        "product": "Acme",
        "first_indexed_at": "2026-11-01T12:00:00Z",
        "imported_at": "2026-11-01T12:01:00Z",
        "observed_at": "2026-11-01T01:00:00Z",
        "admitted": False,
    }
    repeat = {
        **original,
        "id": "repeat-source",
        "reported_tag": "  !UNPARSED-CONDITION  ",
        "protocol": "TCP",
        "port": "00443",
        "product": "acme",
        "first_indexed_at": "2026-11-10T12:00:00Z",
        "imported_at": "2026-11-10T12:01:00Z",
        "observed_at": "2026-11-10T01:00:00Z",
    }
    changed = {
        **repeat,
        "id": "different-raw-condition",
        "reported_tag": "!another-condition",
        "first_indexed_at": "2026-11-12T12:00:00Z",
    }
    discoveries = observatory_field._dark_discoveries([original, repeat, changed])
    repeated = observatory_field._recency(
        [repeat], {}, historical=False, dark_discoveries=discoveries
    )
    expanded = observatory_field._recency(
        [repeat, changed], {}, historical=False, dark_discoveries=discoveries
    )
    assert repeated["fresh_at"] == original["first_indexed_at"]
    assert expanded["fresh_at"] == changed["first_indexed_at"]


def test_new_dark_service_on_an_existing_asset_changes_discovery_once(tmp_path, monkeypatch):
    store = Store(tmp_path / "workspace")
    dark_add(store, monkeypatch, "one.example.com", 1, port="443")
    eclipse = Eclipse(store)
    first = objects(eclipse)[0]

    dark_add(store, monkeypatch, "one.example.com", 5, port="8443")
    expanded = objects(eclipse)[0]
    assert expanded["id"] == first["id"]
    assert expanded["fresh_at"].startswith("2026-11-05")
    assert expanded["fresh_at"] > first["fresh_at"]

    dark_add(store, monkeypatch, "one.example.com", 10, port="00443")
    repeated = objects(eclipse)[0]
    assert repeated["fresh_at"] == expanded["fresh_at"]
    assert repeated["density_count"] == 3
    assert repeated["finding_count"] == 0


def test_missing_local_discovery_time_stays_explicitly_unknown():
    row = {
        "id": "undated-local-discovery",
        "asset_id": "one-asset",
        "finding_ids": [],
        "reported_tag": "",
        "first_indexed_at": "",
        "imported_at": "",
        "observed_at": "2026-11-12T01:00:00Z",
        "admitted": False,
    }
    discoveries = observatory_field._dark_discoveries([row])
    result = observatory_field._recency([row], {}, historical=False, dark_discoveries=discoveries)
    assert not result["fresh_at"] and not result["local_changed_at"]
    assert not result["first_indexed_at"]
    assert any(
        word in result["recency_basis"].casefold()
        for word in ("unknown", "not recorded", "unavailable")
    )
