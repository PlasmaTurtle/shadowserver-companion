"""Contracts for user-approved wording, entity details and generated narratives."""

import json
from xml.etree import ElementTree as ET
from tests.support.workbench import app, client, ready, reopen_sections
from modules.investigations.components import approved_template as approved
from modules.investigations.components.introduction_model import INTRO as CURRENT_INTRO
from modules.investigations.components.report_composition import compose
from modules.investigations.components.report_layouts import CURRENT_LAYOUTS
from modules.ui.components.exhibit_rendering import prepared_pages
from modules.investigations.components.reporting import snapshot
from modules.workspace.databases.migrations import SCHEMA_VERSION
from modules.workspace.components.store import Store

from modules.investigations.tests.support.template import (
    open_lead,
    save,
)


def test_report_fields_are_authoritative_and_entity_contacts_stay_separate(client, app):
    lead = open_lead(client, app)
    profile = {
        "expected_revision": lead["entity_revision"],
        "contact_name": "Actual recipient",
        "contact_title": "CTO",
        "contact_email": "private@example.com",
        "address": "24 Main Street\nAsheville, NC",
        "city": "Asheville",
        "state": "North Carolina",
    }
    response = client.put("/api/entities/" + lead["id"] + "/profile", json=profile)
    assert response.status_code == 200, response.text
    entity = response.json()
    assert entity["entity_profile"]["contact_email"] == "private@example.com"
    assert "case_id" not in entity
    unchanged = client.get("/api/cases/" + lead["case_id"]).json()
    assert unchanged["draft_revision"] == lead["draft_revision"]
    assert unchanged["entity_profile"] == lead["entity_profile"]
    adopted = client.post(
        "/api/cases/" + lead["case_id"] + "/entity-details",
        json={"expected_version": lead["case"]["version"]},
    )
    assert adopted.status_code == 200, adopted.text
    lead = save(
        client,
        adopted.json(),
        contact_name="Wrong addressee",
        contact_email="wrong@example.com",
        sender_name="Wrong sender",
        intro="Rewritten text",
        narrative="Invented prose",
        closing="Changed closing",
    )
    d = lead["draft"]
    assert (
        d["contact_name"] == "Principal Executive / IT Director"
        and not d["contact_email"]
        and not d["contact_title"]
    )
    assert (
        d["sender_name"] == "Test Analyst"
        and d["intro"] == CURRENT_INTRO
        and d["closing"] == approved.CLOSING
    )
    assert lead["entity_profile"]["state"] == "NC"
    assert "Asheville, NC" in d["narrative"] and "Invented prose" not in d["narrative"]
    assert lead["entity_profile"]["contact_name"] == "Actual recipient"
    model = snapshot(app.state.store, lead["id"])["composition"]
    to = next(n["model"]["to"] for n in model["sections"] if n["kind"] == "introduction")
    assert to.startswith(approved.ADDRESSEE) and "24 Main Street" in to
    assert "Actual recipient" not in to and "private@example.com" not in to
    assert (
        client.get("/api/leads/" + lead["id"] + "/json").json()["entity_profile"]["contact_email"]
        == "private@example.com"
    )
    assert client.put("/api/entities/" + lead["id"] + "/profile", json=profile).status_code == 422


def test_historical_narrative_contract_and_distinct_service_grouping():
    lead = {
        "company": "Example Company",
        "domain": "example.com",
        "entity_profile": {"city": "Asheville", "state": "NC"},
        "entries": [],
    }
    for ip, host, port, ver in [
        ("192.0.2.1", "mail.example.com", 443, "7.3.25"),
        ("192.0.2.2", "mail.example.com", 443, "7.3.25"),
        ("192.0.2.3", "vpn.example.com", 8443, "8.0.0"),
    ]:
        lead["entries"].append(
            {
                "ip": ip,
                "source": {
                    "fields": {
                        "hostname": host,
                        "protocol": "TCP",
                        "port": port,
                        "version": ver,
                        "tag": "eol-php",
                    }
                },
            }
        )
    draft = {"report_date": "2026-11-06", "company": "Example Company", "cve_records": []}
    text = approved.generate_narrative(lead, draft)
    first = text.split("\n\n")[0]
    expected = (
        "On November 6, 2026, the United States Secret service, Charlotte Cyber Fraud Task Force, received a Shadowserver Notification related to a critical security finding detected on 192.0.2.1, 192.0.2.2. "
        "The reported services were accessible over TCP 443 and are associated with the domain mail.example.com. "
        "The identified vulnerability is eol-php, which are associated with php. The reported software version is 7.3.25, which may fall within the affected ranges of not applicable; no CVE reported. "
        "Open source searches indicate the reported asset is associated with Example Company in Asheville, NC. If confirmed, remediation should be prioritized in accordance with critical vulnerability handling procedures."
    )
    assert first == expected
    second = text.split("\n\n")[1]
    assert "192.0.2.3" not in first and "8443" not in first
    assert "192.0.2.1" not in second and "TCP 8443" in second and "8.0.0" in second


def test_only_explicit_cna_ranges_are_inserted_and_overrides_are_scoped(client, app):
    lead = open_lead(client, app)
    key = lead["narrative_groups"][0]["key"]
    lead = save(
        client,
        lead,
        narrative_values={key: {"software": "PHP", "affected_versions": "vendor-confirmed range"}},
        reviewed=True,
    )
    assert not lead["draft"]["reviewed"]
    assert (
        "associated with PHP." in lead["draft"]["narrative"]
        and "vendor-confirmed range" in lead["draft"]["narrative"]
    )
    result = client.put(
        "/api/leads/" + lead["id"] + "/draft",
        json={
            "expected_revision": lead["draft_revision"],
            "fields": {**lead["draft"], "narrative_values": {"wrong": {"software": "Wrong"}}},
        },
    )
    assert result.status_code == 422
    assert (
        approved.affected_text(
            [
                {
                    "id": "CVE-2026-1234",
                    "verification_status": "published",
                    "affected": [
                        {
                            "product": "Example",
                            "versions": [
                                {"version": "1", "lessThan": "2", "status": "affected"},
                                {"version": "2", "status": "unaffected"},
                            ],
                        }
                    ],
                }
            ],
            ["CVE-2026-1234"],
        )
        == "CVE-2026-1234 — Example 1 to before 2"
    )


def test_entity_city_is_not_inferred_from_ip_geolocation(client, app):
    lead = open_lead(client, app)
    narrative = lead["draft"]["narrative"]
    association = narrative.split("Open source searches indicate ")[1].split(". If confirmed")[0]
    assert lead["draft"]["company"] in association
    assert " in " not in association
    assert "city not recorded" not in narrative and "state not recorded" not in narrative


def test_current_sections_preserve_reviewed_intro_and_unchanged_approved_copy(client, app):
    lead = open_lead(client, app)
    model = snapshot(app.state.store, lead["id"])["composition"]
    assert [n["section_key"] for n in model["sections"] if "section_key" in n] == [
        "introduction",
        "vulnerabilities",
        "attribution",
        "information",
        "closing",
    ]
    intro = next(n["model"] for n in model["sections"] if n["kind"] == "introduction")
    assert intro["intro"] == CURRENT_INTRO
    text = " ".join(
        "".join(element.itertext())
        for exhibit in model["exhibits"]
        if exhibit["type"] in {"attribution", "information", "closing"}
        for page in prepared_pages(exhibit)
        for element in ET.fromstring(page.svg).iter("{http://www.w3.org/2000/svg}text")
    )
    for paragraph in [
        approved.ATTRIBUTION,
        # The 0.9.6 Information revision adopts the agreed plain-English page;
        # the legacy test below still requires the original exact wording.
        "As part of our mission to protect local businesses and the financial infrastructure of the United States, the Secret Service provides this voluntary advisory. We recommend prompt review with the person or company responsible for the technology identified in this notice.",
        approved.RESPONSIBILITY,
        approved.CLOSING,
    ]:
        assert text.count(paragraph) == 1


def test_legacy_five_sections_and_exact_approved_paragraphs_remain_available(client, app):
    lead = open_lead(client, app)
    data = snapshot(app.state.store, lead["id"])
    data["draft"].update({key: "legacy" for key in CURRENT_LAYOUTS})
    data["draft"]["intro"] = approved.INTRO
    model = compose(data)
    assert model["template"]["section_order"] == [
        "Introduction",
        "Vulnerabilities",
        "Attribution",
        "Information",
        "Closing",
    ]
    labels = [n["text"] for n in model["sections"] if n["kind"] == "heading"]
    assert [x for x in labels if x in model["template"]["section_order"]] == model["template"][
        "section_order"
    ]
    texts = [n.get("text", "") for n in model["sections"]]
    for text in [
        approved.INTRO,
        approved.ATTRIBUTION,
        approved.SECURITY_INTRO,
        approved.FRAUD_INTRO,
        approved.FRAUD_STATS_INTRO,
        approved.PARTNERSHIP,
        approved.RESPONSIBILITY,
        approved.CLOSING,
    ]:
        assert texts.count(text) == 1
    assert "We are contacting your organization" not in "\n".join(texts)


def test_schema_four_contact_upgrade_is_lossless_and_backed_up(client, app):
    from tests.schema_helpers import restore_schema

    lead = open_lead(client, app)
    store = app.state.store
    old = {
        **lead["draft"],
        "contact_name": "Original contact",
        "contact_title": "Director",
        "contact_email": "old@example.com",
        "address": "Old mailing address",
    }
    old.pop("template_revision")
    with store.transaction() as db:
        restore_schema(db, 4)
        db.execute("UPDATE cases SET draft=? WHERE id=?", (json.dumps(old), lead["case_id"]))
        db.execute("PRAGMA user_version=4")
    upgraded = Store(store.root)
    profile = upgraded.lead(lead["id"])["entity_profile"]
    for key in ("contact_name", "contact_title", "contact_email", "address"):
        assert profile[key] == old[key]
    assert list((store.root / "backups").glob(f"before-schema-{SCHEMA_VERSION}-*.sqlite3"))
    lead = client.get("/api/leads/" + lead["id"]).json()
    save(client, lead)
    assert client.get("/api/leads/" + lead["id"] + "/previous-template.json").json() == old
    assert Store(store.root).lead(lead["id"])["entity_profile"] == profile


def test_settings_changes_require_review_but_do_not_rewrite_certified_package(client, app):
    lead = open_lead(client, app)
    lead = ready(client, lead["id"])
    response = client.post("/api/leads/" + lead["id"] + "/finalize")
    assert response.status_code == 200, response.text
    report = response.json()
    pdf = client.get("/api/reports/" + report["id"] + "/pdf").content
    settings = client.get("/api/bootstrap").json()["settings"]
    settings.update(analyst_name="Another Analyst", analyst_title="Supervisor")
    assert client.put("/api/settings", json=settings).status_code == 200
    fixed = client.get("/api/cases/" + lead["case_id"]).json()
    assert fixed["draft"]["sender_name"] == "Test Analyst"
    assert client.get("/api/reports/" + report["id"] + "/pdf").content == pdf
    response = client.post(
        "/api/cases/" + lead["case_id"] + "/revise",
        json={
            "expected_version": fixed["case"]["version"],
            "reason": "Apply the updated sender profile.",
        },
    )
    assert response.status_code == 200, response.text
    frozen = next(
        section
        for section in response.json()["section_reviews"]
        if section["key"] == "introduction"
    )
    # Revising a certified report retains its pinned sender. Updating identity
    # is a second explicit action, with affected content reopened for review.
    assert frozen["status"] == "validated" and frozen["validated_by"] == "Test Analyst"
    revised = reopen_sections(
        client,
        response.json(),
        "Review the updated sender profile.",
        keys=["introduction", "closing"],
    )
    adopted = client.post(
        "/api/cases/" + lead["case_id"] + "/presentation/adopt",
        json={
            "expected_revision": revised["draft_revision"],
            "reason": "Adopt the reviewed sender profile.",
        },
    )
    assert adopted.status_code == 200, adopted.text
    revised = client.get("/api/cases/" + lead["case_id"]).json()
    assert revised["draft"]["sender_name"] == "Another Analyst" and not revised["draft"]["reviewed"]
    assert client.get("/api/reports/" + report["id"] + "/pdf").content == pdf
