"""EOL snippets render as technical findings without altering historical cards."""

from copy import deepcopy

from workbench.vulnerability_layout import card_rows, layout_vulnerabilities, BOTTOM


def content(rows):
    return " ".join(element[3] for row in rows for element in row.elements if element[0] == "text")


def item():
    return {
        "label": "eol-php",
        "detail": "PHP/5.6.29",
        "finding_type": "eol",
        "exposure_count": 2,
        "observation_scope": "website.example.com; 192.0.2.4 and 192.0.2.5",
        "technical_explanation": {
            "id": "eol-php",
            "revision": "fixture",
            "title": "PHP outside normal support",
            "body": "The reported PHP branch has reached the end of normal vendor support. A functioning website does not establish that its software is maintained.",
            "limitations": "A lifecycle finding is not a CVE or evidence that every later vulnerability affects this installation.",
            "review": "Confirm the installed branch and any separately maintained vendor support, then assess an upgrade or replacement with the service owner.",
            "source_citations": [3, 8],
        },
    }


def test_eol_snippet_preserves_version_and_renders_meaning_limits_review_and_citations():
    finding = item()
    text = content(card_rows(finding, 480, justify=True))
    for value in (
        finding["detail"],
        "No CVSS score is assigned",
        "Reported on 2 IP addresses",
        finding["observation_scope"],
        "Reported condition",
        "Interpretation limits",
        "Technical review",
        "Sources: [3] [8]",
    ):
        assert value in text
    for key in ("body", "limitations", "review"):
        assert finding["technical_explanation"][key] in text
    assert "EPSS" not in text
    old = deepcopy(finding)
    old.pop("technical_explanation")
    assert (
        content(card_rows(old, 480))
        == "PHP/5.6.29 Reported end-of-life condition. No CVSS score is assigned. Original scan fields and observations: Appendix A."
    )


def test_eol_snippet_pagination_keeps_every_word_and_page_local_citations():
    finding = item()
    finding["technical_explanation"]["review"] = " ".join(
        f"ReviewWord{index:04}" for index in range(500)
    )
    model = {
        "id": "EX-VULNERABILITY",
        "title": "Reported Findings",
        "items": [finding],
        "severity": "High",
        "narrative": "Reported source observation.",
        "include_appendix": False,
        "paragraph_alignment": "justify",
    }
    pages = layout_vulnerabilities(model)
    text = " ".join(
        element[3] for page in pages for element in page.elements if element[0] == "text"
    )
    assert "Finding details" in text and "Vulnerability details" not in text
    for index in range(500):
        assert text.count(f"ReviewWord{index:04}") == 1
    assert any(
        segment["kind"] == "page_citations" and segment["values"] == [3, 8]
        for page in pages
        for segment in page.segments
    )
    assert all(
        segment["top"] + segment["height"] <= BOTTOM
        for page in pages
        for segment in page.segments
        if segment["kind"] == "finding"
    )


def test_source_aware_non_http_introduction_has_neutral_supporting_records_note():
    from tools.preview_introduction import specimen
    from workbench.introduction_model import build_introduction
    from workbench.introduction_layout import layout_introduction
    from workbench.notification_narrative_v4 import REVISION

    data = specimen(1, 1, 1)
    entry = data["qualified_lead"]["validated_leads"][0]["entries"][0]
    entry["normalized"] = {"profile": {"id": "scan_rdp"}}
    data["draft"]["narrative_revision"] = REVISION
    model = build_introduction(data, data["composition"]["exhibits"])
    model["include_appendix"] = False
    text = " ".join(
        element[3]
        for element in layout_introduction(model).summary.elements
        if element[0] == "text"
    )
    assert "Full observations and supporting records are available upon request." in text
    assert "Full asset, scan and vulnerability records" not in text
    data["draft"]["narrative_revision"] = "legacy"
    old = build_introduction(data, data["composition"]["exhibits"])
    assert "supporting_records_note" not in old


def test_current_eol_only_footer_describes_support_conditions_and_preserves_legacy():
    from workbench.finding_explainers import REVISION as FINDING_REVISION
    from workbench.notification_narrative_v4 import REVISION as NARRATIVE_REVISION
    from workbench.notification_narrative import REVISION as V3_REVISION
    from workbench.vulnerability_model import build_vulnerability_exhibit

    data = {
        "draft": {
            "narrative_revision": NARRATIVE_REVISION,
            "finding_explainer_revision": FINDING_REVISION,
            "narrative": "Reported lifecycle condition.",
            "severity": "High",
        },
        "entries": [
            {
                "ip": "192.0.2.4",
                "source": {
                    "fields": {
                        "report_type": "scan_http_vulnerable",
                        "hostname": "website.example.com",
                        "protocol": "tcp",
                        "port": "443",
                        "tag": "eol-php",
                        "version": "PHP/5.6.29",
                        "severity": "high",
                    }
                },
            }
        ],
    }
    exhibit = {"id": "EX-VULNERABILITY", "items": [item()]}
    current = build_vulnerability_exhibit(data, exhibit, [], [])
    text = " ".join(
        element[3]
        for page in layout_vulnerabilities(current)
        for element in page.elements
        if element[0] == "text"
    )
    assert "Source observations and reported support conditions require confirmation" in text
    assert "Scores and exploitation signals describe the published vulnerability" not in text

    # A retained CVE still gets the established score/assessment qualification.
    with_cve = deepcopy(exhibit)
    with_cve["items"].append({"label": "CVE-2099-10001", "finding_type": "cve"})
    assert "evidence_note" not in build_vulnerability_exhibit(data, with_cve, [], [])

    # Neither old narrative snapshots nor drafts without the new snippet
    # revision receive the new footer field or a changed model fingerprint.
    data["draft"]["narrative_revision"] = V3_REVISION
    assert "evidence_note" not in build_vulnerability_exhibit(data, exhibit, [], [])
    data["draft"]["narrative_revision"] = NARRATIVE_REVISION
    data["draft"].pop("finding_explainer_revision")
    assert "evidence_note" not in build_vulnerability_exhibit(data, exhibit, [], [])
