"""One notification narrative, with accurate scope and preserved review history."""

from copy import deepcopy
from datetime import date, datetime, timezone
import json

import pytest
from tests.support.workbench import app, client, validate_sections, reopen_sections
from modules.investigations.tests.support.template import open_lead, save
from modules.investigations.tests.support.section_reviews import prepared, status
from modules.investigations.components import approved_template as approved
from modules.investigations.components import outreach_template
from modules.investigations.components.notification_narrative import (
    generate_narrative,
    presentation_groups,
    REVISION,
)
from modules.investigations.components.notification_narrative_v1 import (
    generate_narrative as generate_v1,
    REVISION as V1_REVISION,
)
from modules.investigations.components.notification_narrative_v2 import (
    generate_narrative as generate_v2,
    REVISION as V2_REVISION,
)
from modules.investigations.components.report_drafts import default_draft, hydrated_draft
from modules.investigations.components.notification_narrative_v5 import REVISION as CURRENT_REVISION

from modules.investigations.tests.support.notification_narrative import (
    inputs,
)


def assert_single(text):
    assert "\n" not in text
    assert (
        text.count("received a Shadowserver Notification")
        + text.count("began reviewing Shadowserver observations")
        == 1
    )
    assert text.count("Open source searches indicate") == 1
    assert text.count("If confirmed,") == 1


def test_shared_finding_combines_assets_and_duplicate_observations_without_repetition():
    lead, draft = inputs()
    lead["entries"].append(deepcopy(lead["entries"][0]))
    before = deepcopy((lead, draft))
    text = generate_narrative(lead, draft)
    assert_single(text)
    assert "detected on 192.0.2.1 and 192.0.2.2." in text
    assert "the domains vpn1.example.com and vpn2.example.com." in text
    assert text.count("The identified vulnerability is CVE-2099-10001") == 1
    assert text.count("The reported software version is 7.0.1") == 1
    assert "CVE-2099-10001 — Example VPN 7.0.0 to before 7.0.2" in text
    assert "8.9.9" not in text
    assert "the reported assets are associated with Example Company in Asheville, NC." in text
    assert (lead, draft) == before


def test_mixed_products_versions_and_services_keep_their_own_asset_scope():
    lead, draft = inputs()
    fields = lead["entries"][1]["source"]["fields"]
    fields.update(
        hostname="mail.example.com",
        protocol="UDP",
        port="8443",
        tag="CVE-2099-20002;example-mail",
        product="Example Mail",
        version="4.2.0",
    )
    text = generate_narrative(lead, draft)
    assert_single(text)
    assert "TCP 443 (vpn1.example.com: 192.0.2.1)" in text
    assert "UDP 8443 (mail.example.com: 192.0.2.2)" in text
    vpn = "vpn1.example.com (TCP 443; 192.0.2.1)"
    mail = "mail.example.com (UDP 8443; 192.0.2.2)"
    assert "CVE-2099-10001 (associated with Example VPN on " + vpn + ")" in text
    assert "CVE-2099-20002 (associated with Example Mail on " + mail + ")" in text
    assert "Example VPN 7.0.1 (" + vpn + ")" in text
    assert "Example Mail 4.2.0 (" + mail + ")" in text
    assert "not supplied in the selected source for " + mail in text
    assert "critical security findings" in text


def test_overrides_are_scoped_and_bracketed_values_are_data_not_template_tokens():
    lead, draft = inputs()
    groups = approved.narrative_groups(lead, draft)
    draft["narrative_values"] = {
        groups[1]["key"]: {
            "software": "Reviewed [VPN]\nSuite",
            "affected_versions": "Review [R1]\n7.0.0 through 7.0.1",
        }
    }
    before = deepcopy(draft)
    text = generate_narrative(lead, draft)
    assert_single(text)
    assert "associated with Reviewed [VPN] Suite on vpn2.example.com" in text
    assert "Review [R1] 7.0.0 through 7.0.1 (vpn2.example.com)" in text
    assert "CVE-2099-10001 — Example VPN 7.0.0 to before 7.0.2 (vpn1.example.com)" in text
    assert draft == before


def test_one_hostname_on_different_ips_keeps_versions_and_findings_paired():
    lead, draft = inputs()
    lead["entries"][1]["source"]["fields"].update(
        hostname="vpn1.example.com", tag="CVE-2099-20002", version="8.0.1"
    )
    text = generate_narrative(lead, draft)
    assert_single(text)
    assert (
        "CVE-2099-10001 (associated with Example VPN on vpn1.example.com (TCP 443; 192.0.2.1))"
        in text
    )
    assert (
        "CVE-2099-20002 (associated with Example VPN on vpn1.example.com (TCP 443; 192.0.2.2))"
        in text
    )
    assert "Example VPN 7.0.1 (vpn1.example.com (TCP 443; 192.0.2.1))" in text
    assert "Example VPN 8.0.1 (vpn1.example.com (TCP 443; 192.0.2.2))" in text


def test_excluded_findings_drop_from_prose_and_eol_does_not_gain_cve_claims():
    lead, draft = inputs()
    draft["cve_dispositions"] = {"CVE-2099-10001": {"action": "exclude"}}
    assert generate_narrative(lead, draft) == ""
    lead["entries"][1]["source"]["fields"]["tag"] = "eol-example-vpn"
    text = generate_narrative(lead, draft)
    assert_single(text)
    assert "CVE-2099-10001" not in text and "192.0.2.1" not in text
    assert "192.0.2.2" in text and "eol-example-vpn" in text
    assert "No CVE was reported" in text


def test_unpublished_ranges_remain_unsupplied():
    lead, draft = inputs()
    draft["cve_records"][0]["verification_status"] = "unresolved"
    text = generate_narrative(lead, draft)
    assert "not supplied in the selected source" in text
    assert "7.0.0 to before 7.0.2" not in text


def test_receipt_date_is_scan_calendar_date_plus_one_not_document_date():
    lead, draft = inputs()
    first = generate_narrative(lead, draft)
    assert first.startswith("On November 6, 2026, the United States Secret Service,")
    assert "November 7" not in first and "On November 5" not in first
    draft["report_date"] = "2027-01-15"
    assert generate_narrative(lead, draft) == first


@pytest.mark.parametrize(
    "timestamp,receipt_date",
    [
        ("11/5/2026 13:32", "November 6, 2026"),
        ("11/5/2026 13:32:01.123", "November 6, 2026"),
        ("2026-11-05", "November 6, 2026"),
        ("2026-11-05T00:15:00+14:00", "November 6, 2026"),
        ("2026-11-05T23:59:00-10:00", "November 6, 2026"),
        ("2026-11-06T18:00:00Z", "November 7, 2026"),  # Friday to Saturday.
        ("2026-11-30T13:32:00Z", "December 1, 2026"),
        ("2026-12-31T13:32:00Z", "January 1, 2027"),
        ("2028-02-28T13:32:00Z", "February 29, 2028"),
        ("2028-02-29T13:32:00Z", "March 1, 2028"),
        ("2027-02-28T13:32:00Z", "March 1, 2027"),
        (date(2026, 11, 5), "November 6, 2026"),
        (datetime(2026, 11, 5, 13, 32, tzinfo=timezone.utc), "November 6, 2026"),
    ],
)
def test_receipt_date_handles_source_formats_calendar_rollovers_and_preserves_source(
    timestamp, receipt_date
):
    lead, draft = inputs()
    for entry in lead["entries"]:
        entry["source"]["fields"]["timestamp"] = timestamp
    before = deepcopy((lead, draft))
    text = generate_narrative(lead, draft)
    assert text.startswith("On " + receipt_date + ", the United States Secret Service,")
    assert_single(text)
    assert (lead, draft) == before


def test_multiple_scan_dates_are_sorted_deduplicated_and_not_filled_into_a_range():
    lead, draft = inputs()
    lead["entries"][0]["source"]["fields"]["timestamp"] = "2026-11-08T13:32:00Z"
    lead["entries"].append(deepcopy(lead["entries"][0]))
    text = generate_narrative(lead, draft)
    assert text.startswith("On November 6, 2026 and November 9, 2026,")
    assert "November 7" not in text and "November 8" not in text
    assert text.count("November 9, 2026") == 1


def test_excluded_findings_cannot_supply_a_receipt_date_but_partial_exclusions_keep_row_date():
    lead, draft = inputs()
    fields = lead["entries"][1]["source"]["fields"]
    fields.update(timestamp="2026-12-31", tag="CVE-2099-20002")
    draft["cve_dispositions"] = {"CVE-2099-20002": {"action": "exclude"}}
    text = generate_narrative(lead, draft)
    assert text.startswith("On November 6, 2026,")
    assert "January 1, 2027" not in text and "192.0.2.2" not in text
    fields["tag"] = "CVE-2099-10001;CVE-2099-20002"
    text = generate_narrative(lead, draft)
    assert text.startswith("On November 6, 2026 and January 1, 2027,")
    assert "CVE-2099-20002" not in text


@pytest.mark.parametrize("timestamp", [None, "", "unknown", "2026-02-30", "9999-12-31", 46331])
def test_unusable_scan_dates_do_not_fall_back_to_document_or_retrieval_dates(timestamp):
    lead, draft = inputs()
    for entry in lead["entries"]:
        entry["source"]["fields"]["timestamp"] = timestamp
        entry["source"]["retrieved_at"] = "2026-11-20T12:00:00Z"
    text = generate_narrative(lead, draft)
    assert not text.startswith("On ")
    assert "The supplied observations do not include a valid scan date." in text
    assert "November" not in text


def test_mixed_dated_and_undated_rows_do_not_assign_known_date_to_undated_ip():
    lead, draft = inputs()
    # Same grouped finding/hostname; each row still owns its own timestamp.
    fields = lead["entries"][1]["source"]["fields"]
    fields.update(hostname="vpn1.example.com", timestamp="")
    text = generate_narrative(lead, draft)
    opening = text.split(" A valid scan date was not supplied")[0]
    assert opening.startswith("On November 6, 2026,")
    assert "192.0.2.1" in opening and "192.0.2.2" not in opening
    assert (
        "A valid scan date was not supplied for CVE-2099-10001 on "
        "vpn1.example.com (TCP 443; 192.0.2.2)" in text
    )


def test_v2_keeps_its_original_opening_and_v3_changes_only_opening():
    lead, draft = inputs()
    previous = generate_v2(lead, draft)
    current = generate_narrative(lead, draft)
    marker = " The reported services were accessible over "
    assert previous.startswith("The United States Secret Service,")
    assert current.startswith("On November 6, 2026,")
    assert previous.split(marker, 1)[1] == current.split(marker, 1)[1]
    draft["narrative_revision"] = V2_REVISION
    outreach_template.apply_outreach_template(lead, draft)
    assert draft["narrative"] == previous


@pytest.mark.parametrize("missing_value", [None, ""])
def test_missing_version_is_not_treated_as_within_the_published_range(missing_value):
    lead, draft = inputs()
    lead["entries"] = lead["entries"][:1]
    fields = lead["entries"][0]["source"]["fields"]
    fields["version"] = missing_value
    fields["tag"] = "CVE-2099-10001"
    fields.pop("product")
    before = deepcopy((lead, draft))
    text = generate_narrative(lead, draft)
    assert_single(text)
    assert "which is associated with Example VPN" in text
    assert "The supplied observation does not include a software version" in text
    assert (
        "The published affected range is CVE-2099-10001 — Example VPN 7.0.0 to before 7.0.2" in text
    )
    assert "Applicability requires confirmation against the installed product and version" in text
    assert "may fall within" not in text
    assert "software version is not supplied" not in text
    assert (lead, draft) == before


def test_mixed_known_and_missing_versions_preserve_endpoint_scope():
    lead, draft = inputs()
    lead["entries"][1]["source"]["fields"].update(hostname="vpn1.example.com", version="")
    text = generate_narrative(lead, draft)
    assert_single(text)
    assert "version is 7.0.1 (vpn1.example.com (TCP 443; 192.0.2.1))" in text
    assert "A software version was not supplied for vpn1.example.com (TCP 443; 192.0.2.2)" in text
    assert "may fall within" not in text


@pytest.mark.parametrize("status", ["published", "unresolved"])
def test_product_inference_never_chooses_one_product_from_ambiguous_advisory(status):
    lead, draft = inputs()
    for entry in lead["entries"]:
        entry["source"]["fields"].update(tag="CVE-2099-10001", version="")
        entry["source"]["fields"].pop("product")
    draft["cve_records"][0]["verification_status"] = status
    draft["cve_records"][0]["affected"].append(
        {"product": "Example Mail", "versions": [{"version": "4.0", "status": "affected"}]}
    )
    text = generate_narrative(lead, draft)
    assert "associated with software not identified in the source record" in text
    assert "associated with Example VPN" not in text
    assert "associated with Example Mail" not in text


def test_product_inference_requires_evidence_for_every_included_cve():
    lead, draft = inputs()
    lead["entries"] = lead["entries"][:1]
    fields = lead["entries"][0]["source"]["fields"]
    fields.update(tag="CVE-2099-10001;CVE-2099-20002", version="")
    fields.pop("product")
    assert "associated with software not identified in the source record" in generate_narrative(
        lead, draft
    )
    draft["cve_dispositions"] = {"CVE-2099-20002": {"action": "exclude"}}
    text = generate_narrative(lead, draft)
    assert "associated with Example VPN" in text
    assert "CVE-2099-20002" not in text


def test_selected_software_override_wins_over_cna_product_inference():
    lead, draft = inputs()
    lead["entries"] = lead["entries"][:1]
    fields = lead["entries"][0]["source"]["fields"]
    fields.update(tag="CVE-2099-10001", version="")
    fields.pop("product")
    key = approved.narrative_groups(lead, draft)[0]["key"]
    draft["narrative_values"] = {key: {"software": "Reviewed Product"}}
    assert "associated with Reviewed Product" in generate_narrative(lead, draft)


def test_cna_version_text_with_product_name_is_not_prefixed_twice():
    lead, draft = inputs()
    version = draft["cve_records"][0]["affected"][0]["versions"][0]
    version.clear()
    version.update(version="Example VPN Build 1234 and earlier", status="affected")
    before = deepcopy(draft)
    text = generate_narrative(lead, draft)
    assert "CVE-2099-10001 — Example VPN Build 1234 and earlier" in text
    assert "Example VPN Example VPN" not in text
    assert draft == before


def test_builder_groups_share_inferred_values_and_preserve_excluded_groups():
    lead, draft = inputs()
    for entry in lead["entries"]:
        entry["source"]["fields"].update(tag="CVE-2099-10001", version="")
        entry["source"]["fields"].pop("product")
    lead["entries"][1]["source"]["fields"]["tag"] = "CVE-2099-20002"
    draft["cve_dispositions"] = {"CVE-2099-20002": {"action": "exclude"}}
    before = deepcopy((lead, draft))
    groups = presentation_groups(lead, draft)
    assert len(groups) == 2
    assert groups[0]["software"] == "Example VPN"
    assert groups[0]["version"] == ""
    assert groups[1]["excluded"] is True
    assert [g["key"] for g in groups] == [g["key"] for g in approved.narrative_groups(lead, draft)]
    assert (lead, draft) == before


def test_missing_version_and_ranges_have_grammatical_evidence_limits():
    lead, draft = inputs()
    for entry in lead["entries"]:
        entry["source"]["fields"].pop("version")
    draft["cve_records"] = []
    text = generate_narrative(lead, draft)
    assert "do not include a software version" in text
    assert "Affected version ranges were not supplied in the selected source." in text
    assert "may fall within" not in text


@pytest.mark.parametrize(
    "profile,location",
    [({}, ""), ({"state": "NC"}, " in NC"), ({"city": "Asheville"}, " in Asheville")],
)
def test_missing_business_location_omits_unavailable_fields(profile, location):
    lead, draft = inputs()
    lead["entity_profile"] = profile
    text = generate_narrative(lead, draft)
    assert "associated with Example Company" + location + "." in text
    assert "not recorded" not in text


def test_generation_is_repeatable_without_network_or_ai_service(monkeypatch):
    import socket
    import requests

    def forbidden(*args, **kwargs):
        pytest.fail("Narrative generation attempted a network request")

    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    lead, draft = inputs()
    before = deepcopy((lead, draft))
    assert generate_narrative(lead, draft) == generate_narrative(lead, draft)
    assert (lead, draft) == before


@pytest.mark.parametrize("multiple", [False, True])
def test_targeted_scope_handles_singular_and_plural_findings(multiple):
    lead, draft = inputs()
    if multiple:
        lead["entries"][1]["source"]["fields"]["tag"] = "CVE-2099-20002"
    draft["outreach_template"] = "targeted-v1"
    outreach_template.apply_outreach_template(lead, draft)
    assert_single(draft["narrative"])
    assert "critical" not in draft["narrative"]
    assert "reported security finding" in draft["narrative"]
    assert draft["narrative_revision"] == REVISION


def test_default_preview_save_and_hydration_use_the_same_generator(client, app):
    lead = open_lead(client, app)
    assert_single(lead["draft"]["narrative"])
    response = client.post("/api/leads/" + lead["id"] + "/narrative", json=lead["draft"])
    assert response.status_code == 200, response.text
    expected = response.json()["narrative"]
    assert len(response.json()["groups"]) == len(lead["narrative_groups"])
    lead = save(client, lead, narrative="Repeated prose", narrative_revision="client-forgery")
    assert lead["draft"]["narrative"] == expected
    assert lead["draft"]["narrative_revision"] == CURRENT_REVISION
    from modules.investigations.components.notification_narrative_v5 import (
        generate_narrative as generate_current,
    )

    assert generate_current(lead, lead["draft"]) == expected
    default = default_draft(lead, app.state.store.settings())
    assert_single(default["narrative"])
    assert default["narrative_revision"] == CURRENT_REVISION


@pytest.mark.parametrize("stage", ["pending_notification", "notification_completed", "closed"])
def test_completed_drafts_preserve_historical_narrative(stage):
    lead, draft = inputs()
    draft["narrative"] = approved.generate_narrative(lead, draft)
    lead.update(draft=draft, case={"stage": stage})
    settings = {"analyst_name": "Example Analyst", "analyst_title": "Special Agent"}
    hydrated = hydrated_draft(lead, settings)
    assert hydrated["narrative"] == draft["narrative"]
    assert "\n\n" in hydrated["narrative"]
    assert hydrated["narrative_revision"] == "legacy"


@pytest.mark.parametrize("revision", ["legacy", V1_REVISION, V2_REVISION])
def test_saved_legacy_generation_pins_entity_until_explicit_adoption(client, app, revision):
    lead = prepared(client, app, validate=False)
    prior = deepcopy(lead["draft"])
    prior["narrative_revision"] = revision
    outreach_template.apply_outreach_template(lead, prior)
    # Model an existing active draft from a prior release. The public save
    # endpoint intentionally cannot choose a historical generator revision.
    with app.state.store.transaction() as db:
        db.execute("UPDATE cases SET draft=? WHERE id=?", (json.dumps(prior), lead["case_id"]))
    lead = validate_sections(client, client.get("/api/leads/" + lead["id"]).json())
    old = status(lead, "vulnerabilities")
    assert old["status"] == "validated"
    refreshed = client.get("/api/leads/" + lead["id"]).json()
    current = status(refreshed, "vulnerabilities")
    assert current["status"] == "validated"
    assert refreshed["draft"]["narrative_revision"] == revision
    assert current["validation_id"] == old["validation_id"]
    assert current["frozen_fields"]["narrative"] == old["frozen_fields"]["narrative"]
    changed = client.put(
        "/api/entities/" + lead["id"] + "/name",
        json={"name": "Renamed Example Company", "expected_revision": refreshed["entity_revision"]},
    )
    assert changed.status_code == 200, changed.text
    assert "section_reviews" not in changed.json()
    unchanged = client.get("/api/cases/" + lead["case_id"]).json()
    assert unchanged["company"] == refreshed["company"]
    assert unchanged["current_entity"]["company"] == "Renamed Example Company"
    current = status(unchanged, "vulnerabilities")
    assert current["status"] == "validated"
    assert current["validation_id"] == old["validation_id"]
    assert current["frozen_fields"]["narrative"] == old["frozen_fields"]["narrative"]
    assert current["validated_by"] == old["validated_by"]
    assert current["validated_at"] == old["validated_at"]
    adopt_url = "/api/cases/" + lead["case_id"] + "/entity-details"
    assert (
        client.post(adopt_url, json={"expected_version": unchanged["case"]["version"]}).status_code
        == 422
    )
    reopened = reopen_sections(
        client,
        unchanged,
        "Use the current entity name.",
        keys=["introduction", "vulnerabilities", "attribution"],
    )
    adopted = client.post(adopt_url, json={"expected_version": reopened["case"]["version"]})
    assert adopted.status_code == 200, adopted.text
    assert adopted.json()["company"] == "Renamed Example Company"
    assert adopted.json()["draft"]["narrative_revision"] == revision
    assert "Renamed Example Company" in adopted.json()["draft"]["narrative"]
    assert status(adopted.json(), "vulnerabilities")["status"] == "draft"
    assert status(adopted.json(), "attribution")["status"] == "draft"
    assert status(adopted.json(), "information")["status"] == "validated"
    assert status(adopted.json(), "closing")["status"] == "validated"
    assert client.post("/api/leads/" + lead["id"] + "/finalize").status_code == 422


@pytest.mark.parametrize(
    "revision,generator",
    [
        ("legacy", approved.generate_narrative),
        (V1_REVISION, generate_v1),
        (V2_REVISION, generate_v2),
        (REVISION, generate_narrative),
    ],
)
def test_dispatch_preserves_selected_generator_and_still_regenerates_dependencies(
    revision, generator
):
    lead, draft = inputs()
    draft["narrative_revision"] = revision
    outreach_template.apply_outreach_template(lead, draft)
    assert draft["narrative"] == generator(lead, draft)
    assert draft["narrative_revision"] == revision
    original = draft["narrative"]
    lead["entries"][0]["source"]["fields"]["version"] = "99.0.0"
    outreach_template.apply_outreach_template(lead, draft)
    assert draft["narrative"] != original
    assert "99.0.0" in draft["narrative"]
    assert draft["narrative_revision"] == revision


def test_unknown_saved_generator_fails_closed_instead_of_silently_rewriting():
    lead, draft = inputs()
    draft.update(narrative="Preserved unsupported-version text", narrative_revision="future-v99")
    before = deepcopy(draft)
    with pytest.raises(ValueError, match="Unsupported saved narrative revision"):
        outreach_template.apply_outreach_template(lead, draft)
    assert draft == before
