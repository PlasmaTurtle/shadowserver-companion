"""Dark Records preserve condition scope through the source detail endpoint."""

from urllib.parse import parse_qs, urlsplit

from test_eclipse import base
from test_observatory_canonical_0994 import add
from test_workbench import app, client
from workbench.eclipse import Eclipse
from workbench.store import Store


def mixed_event(store):
    fields_by_source = {}
    members = {}
    for name, condition, admitted, reason in (
        ("approved.csv", "CVE-2026-21000", True, ""),
        ("dark-b.csv", "CVE-2026-21001", False, "attribution_review"),
        ("dark-c.csv", "CVE-2026-21002", False, "unsupported_finding"),
    ):
        fields = base(
            tag=condition,
            timestamp="2026-11-01T10:00:00Z",
            protocol="tcp",
            port="443",
            extra_source_field=f"Original source: {name}",
        )
        fields_by_source[name] = fields
        result = add(store, fields, admitted=admitted, reason=reason, filename=name)
        members[condition] = {**result, "reason": reason, "admitted": admitted}
    assert len({member["observation_id"] for member in members.values()}) == 1
    return next(iter(members.values()))["observation_id"], members, fields_by_source


def assert_dark_members(detail, members):
    excluded = {
        condition: member for condition, member in members.items() if not member["admitted"]
    }
    assert detail["admitted"] is False and detail["dark_matter"] is True
    assert detail["observation_admitted"] is True
    assert detail["selection_context"] == "dark_matter"
    assert detail["status"] == "excluded"
    assert {part.strip() for part in detail["tag"].split(";")} == set(excluded)
    assert set(detail["finding_ids"]) == {member["finding_ids"][0] for member in excluded.values()}
    assert detail["selected_finding_count"] == 2
    assert detail["selected_findings_omitted"] == 0
    assert set(detail["intake_reasons"]) == {member["reason"] for member in excluded.values()}
    selected = {item["condition"]: item for item in detail["selected_findings"]}
    assert set(selected) == set(excluded)
    for condition, member in excluded.items():
        item = selected[condition]
        assert item["id"] == member["finding_ids"][0]
        assert item["admitted"] is False
        assert item["reason"] == member["reason"]
        url = urlsplit(item["detail_url"])
        assert url.path == f"/api/eclipse/observations/{detail['id']}"
        assert parse_qs(url.query) == {
            "finding_id": member["finding_ids"],
            "intake": ["dark_matter"],
        }


def test_multi_condition_dark_record_links_to_scoped_detail_without_changing_raw_source(tmp_path):
    store = Store(tmp_path / "workspace")
    observation_id, members, originals = mixed_event(store)
    eclipse = Eclipse(store)
    result = eclipse.view(intake="dark_matter")
    records = result["records"]
    assert records["kind"] == "observations" and records["total"] == 1
    assert len(records["items"]) == 1
    row = records["items"][0]
    assert row["id"] == observation_id
    assert row["admitted"] is False and row["observation_admitted"] is True
    url = urlsplit(row["detail_url"])
    assert url.path == f"/api/eclipse/observations/{observation_id}"
    assert parse_qs(url.query) == {"intake": ["dark_matter"]}

    detail = eclipse.observation(observation_id, intake="dark_matter")
    assert_dark_members(detail, members)
    assert detail["fields"] == originals[detail["source"]["workbook"]]
    assert detail["source_available"] and detail["original_url"]

    # The projection must not withdraw the approved membership or rewrite any source.
    ordinary = eclipse.observation(observation_id)
    assert ordinary["admitted"] is True
    assert set(ordinary["finding_ids"]) == {member["finding_ids"][0] for member in members.values()}
    assert ordinary["fields"] == originals[ordinary["source"]["workbook"]]


def test_dark_detail_api_keeps_multi_condition_context_and_condition_links(app, client):
    observation_id, members, originals = mixed_event(app.state.store)
    response = client.get(f"/api/eclipse/observations/{observation_id}?intake=dark_matter")
    assert response.status_code == 200, response.text
    detail = response.json()
    assert_dark_members(detail, members)
    assert detail["fields"] == originals[detail["source"]["workbook"]]
    for selected in detail["selected_findings"]:
        response = client.get(selected["detail_url"])
        assert response.status_code == 200, response.text
        scoped = response.json()
        assert scoped["admitted"] is False and scoped["observation_admitted"] is True
        assert scoped["finding_ids"] == [selected["id"]]
        assert scoped["tag"] == selected["condition"]
        assert scoped["intake_reason"] == selected["reason"]
        assert scoped["fields"] == originals[scoped["source"]["workbook"]]


def test_unknown_observation_intake_context_is_rejected(app, client):
    added = add(app.state.store, base(tag="CVE-2026-21000"))
    response = client.get(
        f"/api/eclipse/observations/{added['observation_id']}?intake=not-a-context"
    )
    assert response.status_code == 422


def test_dark_context_does_not_present_pure_approved_observation(app, client):
    added = add(app.state.store, base(tag="CVE-2026-21000"))
    response = client.get(f"/api/eclipse/observations/{added['observation_id']}?intake=dark_matter")
    assert response.status_code == 404


def test_dark_context_keeps_unparsed_source_and_original_exclusion_reason(app, client):
    fields = base(tag="", extra_source_field="Unparsed original source retained")
    added = add(app.state.store, fields, admitted=False, reason="unsupported_finding")
    response = client.get(f"/api/eclipse/observations/{added['observation_id']}?intake=dark_matter")
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["admitted"] is False and detail["dark_matter"] is True
    assert detail["observation_admitted"] is False
    assert detail["finding_ids"] == detail["selected_findings"] == []
    assert detail["selected_finding_count"] == detail["selected_findings_omitted"] == 0
    assert detail["intake_reason"] == "unsupported_finding"
    assert detail["fields"] == fields and detail["tag"] == ""
    assert detail["source_available"] and detail["original_url"]


def test_explicit_approved_finding_cannot_borrow_sibling_dark_context(app, client):
    observation_id, members, _ = mixed_event(app.state.store)
    approved_id = members["CVE-2026-21000"]["finding_ids"][0]
    assert (
        Eclipse(app.state.store).observation(
            observation_id, finding_id=approved_id, intake="dark_matter"
        )
        is None
    )
    response = client.get(
        f"/api/eclipse/observations/{observation_id}",
        params={"finding_id": approved_id, "intake": "dark_matter"},
    )
    assert response.status_code == 404
    assert (
        client.get(f"/api/eclipse/observations/{approved_id}?intake=dark_matter").status_code == 404
    )


def test_unrelated_finding_cannot_be_selected_from_a_mixed_event(app, client):
    observation_id, _, _ = mixed_event(app.state.store)
    unrelated = add(
        app.state.store,
        base(hostname="other.example.net", tag="CVE-2026-21099"),
        admitted=False,
        reason="attribution_review",
        filename="unrelated.csv",
    )
    unrelated_id = unrelated["finding_ids"][0]
    assert (
        Eclipse(app.state.store).observation(
            observation_id, finding_id=unrelated_id, intake="dark_matter"
        )
        is None
    )
    response = client.get(
        f"/api/eclipse/observations/{observation_id}",
        params={"finding_id": unrelated_id, "intake": "dark_matter"},
    )
    assert response.status_code == 404


def test_direct_dark_finding_path_preserves_actual_source_observation_admission(app, client):
    _, members, originals = mixed_event(app.state.store)
    selected_id = members["CVE-2026-21001"]["finding_ids"][0]
    response = client.get(f"/api/eclipse/observations/{selected_id}?intake=dark_matter")
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["admitted"] is False and detail["observation_admitted"] is True
    assert detail["finding_ids"] == [selected_id]
    assert detail["tag"] == "CVE-2026-21001"
    assert detail["intake_reason"] == "attribution_review"
    assert detail["fields"] == originals[detail["source"]["workbook"]]
    assert [item["id"] for item in detail["selected_findings"]] == [selected_id]
