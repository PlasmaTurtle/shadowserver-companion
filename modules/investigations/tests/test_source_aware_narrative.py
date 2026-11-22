"""New report families never inherit HTTP-only evidentiary assertions."""

from copy import deepcopy

import pytest

from modules.investigations.components.notification_narrative import (
    REVISION as V3_REVISION,
    generate_narrative as generate_v3,
)
from modules.investigations.components.notification_narrative_v4 import (
    REVISION,
    generate_narrative,
    apply_copy,
    severity_summary,
)
from modules.investigations.components.outreach_template import (
    apply_outreach_template,
    narrative_scope_issue,
)

from modules.investigations.tests.support.notification_narrative import (
    case,
)


@pytest.mark.parametrize(
    "source_id,tag",
    [("scan_rdp", "rdp"), ("scan_msrpc", "msrpc"), ("scan_mongodb", "mongodb-noauth")],
)
def test_exposure_does_not_become_critical_vulnerability_or_compromise(source_id, tag):
    lead, draft = case(source_id, tag)
    before = deepcopy(lead)
    apply_outreach_template(lead, draft)
    text = draft["narrative"]
    assert text.startswith("On November 6, 2026,")
    assert "records an internet-reachable service" in text
    assert "identified vulnerability" not in text and "critical" not in text.lower()
    assert "does not establish unauthorized access" in text
    assert draft["severity"] == "High"
    assert "potential cybersecurity vulnerability" not in draft["intro"]
    assert draft["subject"] == "Shadowserver - Cybersecurity Notification"
    assert lead == before


@pytest.mark.parametrize(
    "source_id", ["scan_isakmp", "scan6_isakmp", "scan_msrpc", "scan6_msrpc", "scan_rdp"]
)
def test_protocol_version_is_never_used_as_installed_software(source_id):
    lead, draft = case(source_id, "protocol-condition", "5.0")
    text = generate_narrative(lead, draft)
    assert "reported protocol version" in text
    assert "software version" not in text and "affected range" not in text


@pytest.mark.parametrize(
    "source_id",
    ["compromised_website", "compromised_website6", "compromised_iot", "compromised_iot6"],
)
def test_incident_report_does_not_declare_confirmed_compromise(source_id):
    lead, draft = case(source_id, "reported-indicator", "10")
    text = generate_narrative(lead, draft)
    assert "indicators of possible compromise" in text
    assert "current status and scope" in text
    assert "confirmed compromise" not in text
    assert "software version" not in text


def test_unknown_source_does_not_get_http_label_from_port_or_cve():
    lead, draft = case("unrecognized-source", "CVE-2099-10001", "5.0")
    text = generate_narrative(lead, draft)
    assert "Reported observations" in text and "Vulnerable HTTP" not in text
    assert "software version" not in text


def test_profile_identity_wins_over_conflicting_row_label():
    lead, draft = case("scan_msrpc", "msrpc", "5.0")
    lead["entries"][0]["source"]["fields"]["report_type"] = "scan_http_vulnerable"
    text = generate_narrative(lead, draft)
    assert "Accessible MS-RPC" in text and "Vulnerable HTTP" not in text


def test_mixed_families_keep_findings_with_their_own_endpoints():
    lead, draft = case("scan_rdp", "rdp", "", "high")
    other, _ = case("scan_smtp_vulnerable", "cve-2099-20002", "ExampleMail/1.2", "critical")
    second = other["entries"][0]
    second["ip"] = "192.0.2.2"
    second["source"]["fields"].update(hostname="mail.example.com", port="25")
    lead["entries"].append(second)
    apply_outreach_template(lead, draft)
    text = draft["narrative"]
    assert (
        "Accessible RDP report records an internet-reachable service on vpn1.example.com (TCP 443; 192.0.2.1)"
        in text
    )
    assert (
        "Vulnerable SMTP report flags a potential security weakness on mail.example.com (TCP 25; 192.0.2.2)"
        in text
    )
    assert draft["severity"] == "Not specified"
    assert severity_summary({**lead, "draft": draft}) == "Critical; High"


def test_unknown_severity_never_uses_report_default():
    lead, draft = case("scan_mongodb", "mongodb-noauth", severity="")
    apply_copy(lead, draft)
    assert draft["severity"] == "Not specified"
    assert severity_summary({**lead, "draft": draft}) == "Not supplied"


def test_high_http_finding_does_not_claim_critical_before_template_selection():
    lead, draft = case("scan_http_vulnerable", "CVE-2099-10001", "7.0.1", "high")
    draft["outreach_template"] = "critical"
    assert "critical" not in generate_narrative(lead, draft).lower()
    assert "targeted-outreach" in narrative_scope_issue(lead, draft)


def test_older_vulnerability_narrative_cannot_certify_a_new_exposure_family():
    lead, draft = case("scan_rdp", "rdp")
    draft["narrative_revision"] = V3_REVISION
    assert "Adopt the current report presentation" in narrative_scope_issue(lead, draft)


@pytest.mark.parametrize(
    "source_id",
    ["compromised_website", "compromised_website6", "compromised_iot", "compromised_iot6"],
)
@pytest.mark.parametrize("mixed", [False, True])
def test_compromise_indicators_require_targeted_choice_even_when_critical_or_context(
    source_id, mixed
):
    lead, draft = case(source_id, "reported-indicator", severity="critical")
    lead["entries"][0]["normalized"]["eligibility"] = {
        "outreach_mode": "critical",
        "included_as_context": mixed,
    }
    if mixed:
        other, _ = case("scan_http_vulnerable", "CVE-2099-10001", "7.0.1", "critical")
        lead["entries"] = other["entries"] + lead["entries"]
    draft["outreach_template"] = "critical"
    assert "reported compromise indicators" in narrative_scope_issue(lead, draft)
    draft["outreach_template"] = "targeted-v1"
    assert narrative_scope_issue(lead, draft) is None


def test_excluding_mongodb_cve_does_not_erase_the_separate_noauth_observation():
    lead, draft = case("scan_mongodb", "mongodb-noauth;CVE-2099-10001", "7.0.1")
    draft["cve_dispositions"] = {
        "CVE-2099-10001": {"action": "exclude", "reason": "Reviewed patched build"}
    }
    text = generate_narrative(lead, draft)
    assert text.startswith("On November 6, 2026,")
    assert "mongodb-noauth" in text and "CVE-2099-10001" not in text


def test_legacy_api_receipt_copy_is_preserved_without_a_readiness_gate():
    lead, draft = case("scan_rdp", "rdp")
    lead["entries"][0]["normalized"]["acquisition"] = {
        "kind": "shadowserver_api_receipt",
        "narrative_date_basis": "unconfirmed",
    }
    text = generate_narrative(lead, draft)
    assert not text.startswith("On ") and "received" not in text
    assert narrative_scope_issue(lead, draft) is None
    lead["entries"][0]["normalized"]["acquisition"]["narrative_date_basis"] = "emailed_row_plus_one"
    assert generate_narrative(lead, draft).startswith("On November 6, 2026,")
    assert narrative_scope_issue(lead, draft) is None


def test_current_http_retains_v3_prose_and_saved_v3_is_still_dispatched():
    lead, draft = case("scan_http_vulnerable", "CVE-2099-10001", "7.0.1", "critical")
    assert generate_narrative(lead, draft) == generate_v3(lead, draft)
    draft.update(narrative_revision=V3_REVISION, outreach_template="critical")
    apply_outreach_template(lead, draft)
    assert draft["narrative"] == generate_v3(lead, draft)
    assert draft["narrative_revision"] == V3_REVISION


def test_non_cve_observation_is_visible_in_composed_findings_without_cvss():
    from modules.investigations.tools.preview_introduction import specimen
    from modules.investigations.components.report_composition import compose
    from modules.investigations.components.vulnerability_layout import layout_vulnerabilities
    from modules.investigations.components.vulnerability_model import REVISION as FINDINGS_REVISION

    data = specimen(1, 1, 1)
    entries = [
        entry for group in data["qualified_lead"]["validated_leads"] for entry in group["entries"]
    ]
    for entry in entries:
        entry["normalized"] = {"profile": {"id": "scan_msrpc"}}
        entry["source"]["fields"].update(
            report_type="scan_msrpc", tag="msrpc", version="5.0", severity="high"
        )
    lead = {
        "entries": entries,
        "company": "Example Company",
        "domain": "example.com",
        "entity_profile": {},
    }
    data["cves"] = []
    data["draft"].update(
        narrative_revision=REVISION,
        vulnerability_revision=FINDINGS_REVISION,
        outreach_template="targeted-v1",
        cve_records=[],
    )
    apply_outreach_template(lead, data["draft"])
    composition = compose(data)
    introduction = composition["sections"][0]["model"]
    assert introduction["intro"] == data["draft"]["intro"]
    assert introduction["subject"] == data["draft"]["subject"]
    findings = next(item for item in composition["exhibits"] if item["type"] == "vulnerability")
    assert findings["title"] == "Reported Findings"
    assert len(findings["items"]) == 1
    item = findings["items"][0]
    assert item["finding_type"] == "observation" and item["observation_ids"]
    assert item["version_detail"] == "Reported protocol version: 5.0"
    text = " ".join(
        element[3]
        for page in layout_vulnerabilities(findings)
        for element in page.elements
        if element[0] == "text"
    )
    assert "Reported Findings" in text
    assert "CVSS" not in text and "EPSS" not in text
