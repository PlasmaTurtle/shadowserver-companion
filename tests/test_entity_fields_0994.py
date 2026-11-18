"""Entity edits validate independently of intake and preserve case snapshots."""

import pytest

from workbench.entity_validation import locations, validate_profile
from test_workbench import app, client, import_rows, observations


@pytest.mark.parametrize(
    "values",
    [
        {"city": "Asheville", "state": "SC"},
        {"city": "Definitely Not A City", "state": "NC"},
        {"state": "XY"},
        {"contact_email": "someone@@example.com"},
        {"contact_email": "someone@example..com"},
        {"contact_email": "Name <someone@example.com>"},
        {"contact_email": "a@example.com\nb@example.com"},
        {"contact_phone": "+1 123 nope"},
        {"contact_phone": "1234"},
        {"contact_phone": "0000000"},
        {"contact_phone": "+01234567"},
        {"contact_phone": "123-555-0100"},
        {"contact_phone": "+1 704 123 0100"},
        {"contact_phone": "+1234567"},
    ],
)
def test_invalid_fields_rejected(values):
    with pytest.raises(ValueError):
        validate_profile(values)


def test_nationwide_location_and_international_contact_formats():
    values = validate_profile(
        {
            "city": "San Francisco",
            "state": "California",
            "contact_email": "team+security@bücher.de",
            "contact_phone": "+44 20 7946 0958 ext. 42",
            "address": "Any free-text mailing address",
        }
    )
    assert values["city"] == "San Francisco" and values["state"] == "CA"
    assert values["address"] == "Any free-text mailing address"
    assert {r["city"] for r in locations("NC", "ashev")} == {"Asheville"}
    assert locations("SC", "ashev") == []


def test_contact_change_keeps_unchanged_legacy_location():
    previous = {"city": "Legacy postal locality", "state": "Out of catalog"}
    assert (
        validate_profile({**previous, "contact_email": "contact@example.com"}, previous=previous)[
            "city"
        ]
        == previous["city"]
    )


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ({"state": "SC"}, {"city": "", "state": "SC"}),
        ({"state": "NC"}, {"city": "Asheville", "state": "NC"}),
        ({"city": "Charlotte"}, {"city": "Charlotte", "state": ""}),
        ({"city": "Asheville"}, {"city": "Asheville", "state": "NC"}),
        ({}, {"city": "Asheville", "state": "NC"}),
    ],
)
def test_merge_fills_only_compatible_city_state_pairs(target, expected):
    from workbench.entity_validation import merge_profiles

    assert merge_profiles({"city": "Asheville", "state": "NC"}, target) == expected


def test_historical_attribution_reuse_keeps_original_times(tmp_path):
    from test_attribution_display_050 import saved_record, case_lead, RETRIEVED, EVALUATED
    from workbench.attribution_display import attribution_summaries

    store, proof = saved_record(tmp_path)
    lead = case_lead(proof)
    proof["reuse"] = {
        "fresh_lookup": False,
        "recognized_at": "2026-11-13T00:00:00Z",
        "source_evaluated_at": EVALUATED,
    }
    summary = attribution_summaries(store, lead)[0]
    assert summary["reuse"]["fresh_lookup"] is False
    assert summary["retrieved_at"] == RETRIEVED and summary["validated_at"] == EVALUATED


def test_entity_merge_preserves_target_location_and_pinned_case_content(client, app):
    import json
    from test_workbench import FakeRegistry

    import_rows(client, app)
    source = client.get("/api/entities").json()[0]
    source = client.put(
        f"/api/entities/{source['id']}/profile",
        json={"expected_revision": source["entity_revision"], "city": "Asheville", "state": "NC"},
    ).json()

    class Other(FakeRegistry):
        def lookup(self, ip):
            record = super().lookup(ip)
            return type(record)(
                record.ip,
                record.registry,
                record.source_url,
                record.retrieved_at,
                {"contact": "support@another.com"},
            )

    app.state.intake.lookup_factory = Other
    import_rows(
        client,
        app,
        [{**observations()[0], "hostname": "mail.another.com", "ip": "8.8.4.4"}],
        "other.csv",
    )
    target = next(item for item in client.get("/api/entities").json() if item["id"] != source["id"])
    target = client.put(
        f"/api/entities/{target['id']}/profile",
        json={"expected_revision": target["entity_revision"], "state": "SC"},
    ).json()
    store = app.state.store
    before = store.all("SELECT id,draft,entity_snapshot FROM cases ORDER BY id")
    response = client.post(
        f"/api/entities/{source['id']}/merge",
        json={
            "target_id": target["id"],
            "source_revision": source["entity_revision"],
            "target_revision": target["entity_revision"],
        },
    )
    assert response.status_code == 200, response.text
    profile = json.loads(
        store.one("SELECT payload FROM entity_profiles WHERE entity_id=?", (target["id"],))[
            "payload"
        ]
    )
    assert profile["state"] == "SC" and not profile["city"]
    assert store.all("SELECT id,draft,entity_snapshot FROM cases ORDER BY id") == before


def test_cloudflare_report_evidence_uses_its_exact_source_not_google_label():
    from attribution.cloudflare_dns import query_url
    from test_attribution_exhibit_model import google_dns_inputs, build

    parts = google_dns_inputs()
    proof = parts[2][0]["source"]
    proof["registry"] = proof["evidence"]["source_name"] = "Cloudflare DNS"
    proof["source_url"] = proof["evidence"]["source_url"] = query_url("remote.example.com.", "A")
    assert build(parts)["items"][0]["supported"]
    proof["evidence"]["source_name"] = "Google Public DNS"
    assert not build(parts)["items"][0]["supported"]


def test_manual_rebrand_asset_has_no_new_observations_or_case_edits(client, app):
    import_rows(client, app)
    store = app.state.store
    entity = client.get("/api/entities").json()[0]
    before = store.all("SELECT * FROM cases")
    count = store.one("SELECT count(*) n FROM awareness_observations")["n"]
    response = client.post(
        f"/api/entities/{entity['id']}/assets",
        json={"hostname": "example.org", "expected_revision": entity["entity_revision"]},
    )
    assert response.status_code == 200, response.text
    detail = response.json()
    assert any(
        a["hostname"] == "example.org" and a["association_basis"] == "manual"
        for a in detail["associated_assets"]
    )
    assert any(h["name"] == "example.org" for h in detail["hostnames"])
    assert client.get("/api/entities?q=example.org").json()[0]["id"] == entity["id"]
    assert store.all("SELECT * FROM cases") == before
    assert store.one("SELECT count(*) n FROM awareness_observations")["n"] == count
    stale = client.post(
        f"/api/entities/{entity['id']}/assets",
        json={"hostname": "example.net", "expected_revision": entity["entity_revision"]},
    )
    assert stale.status_code == 422


def test_location_api_and_rejected_write_leave_record_unchanged(client, app):
    import_rows(client, app)
    entity = client.get("/api/entities").json()[0]
    result = client.get("/api/entity-locations?state=California&q=San%20Francisco").json()
    assert result["cities"] == [{"city": "San Francisco", "state": "CA"}]
    response = client.put(
        f"/api/entities/{entity['id']}/profile",
        json={"expected_revision": entity["entity_revision"], "city": "Asheville", "state": "SC"},
    )
    assert response.status_code == 422
    current = client.get(f"/api/entities/{entity['id']}").json()
    assert current["entity_revision"] == entity["entity_revision"]


def test_directory_and_dossier_use_same_canonical_counts_on_reordered_delivery(client, app):
    rows = observations()
    import_rows(client, app, rows, start_notifications=False)
    first = client.get("/api/entities").json()[0]
    assert first["finding_count"] > 0
    import_rows(client, app, list(reversed(rows)), name="reordered.csv", start_notifications=False)
    latest = client.get("/api/entities").json()[0]
    for key in (
        "finding_count",
        "observations",
        "approved_observations",
        "dark_matter_observations",
    ):
        assert latest[key] == first[key]
    detail = client.get(f"/api/entities/{first['id']}").json()
    assert detail["awareness"]["observations"] == latest["observations"]
    assert detail["awareness"]["findings"] == latest["finding_count"]
    assert len({f["id"] for f in detail["awareness_findings"]}) == len(detail["awareness_findings"])
