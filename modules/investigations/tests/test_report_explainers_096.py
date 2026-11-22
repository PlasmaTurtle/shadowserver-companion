"""Exact report family selection, preserved wording, and production page geometry."""

from copy import deepcopy

import pytest

from modules.investigations.components.information_layout import layout_information
from modules.investigations.components.information_model import REVISION
from modules.investigations.components.information_pages import build_information_pages
from modules.investigations.components.report_composition import Citations
from modules.library.resources.report_explainer_data import BANK, DEFERRED
from modules.investigations.components.report_explainers import (
    canonical_source_types,
    select_report_explainers,
    selection_is_current,
)
from modules.investigations.components.report_drafts import hydrated_draft
from modules.ui.components.exhibit_rendering import svg_pages
from tests.support.workbench import app, client, import_rows
from modules.investigations.tests.support.section_reviews import save


def lead_for(*types):
    return {
        "entries": [
            {"source": {"fields": {}}, "normalized": {"profile": {"id": key}}} for key in types
        ]
    }


def model_for(*types):
    pages = select_report_explainers(lead_for(*types))
    refs = Citations()
    model = build_information_pages(
        {"draft": {"report_explainer_snapshots": pages}, "explainers": []}, refs
    )
    return model, refs


@pytest.mark.parametrize("key,page", BANK.items())
def test_exact_ids_and_ipv6_variants_share_one_page(key, page):
    selected = select_report_explainers(lead_for(*page["report_types"], *page["report_types"]))
    assert len(selected) == 1 and selected[0]["id"] == key
    assert selected[0]["source_report_types"] == page["report_types"]
    assert selected[0]["format"] == "one_pager"
    selected[0]["intro"] = "A case-local mutation"
    assert BANK[key]["intro"] != "A case-local mutation"


@pytest.mark.parametrize("key", DEFERRED)
def test_deferred_reports_never_receive_a_vulnerability_explainer(key):
    assert select_report_explainers(lead_for(key)) == []
    model, _ = model_for(key)
    assert [p["id"] for p in model["pages"]] == ["business-information"]


def test_explicit_unknown_identity_is_not_replaced_by_filename_or_http_columns():
    lead = lead_for("new_unrecognized_type")
    lead["entries"][0]["source"] = {
        "workbook": "scan_http_vulnerable.csv",
        "fields": {"http": "OK", "tag": "CVE-2024-12345"},
    }
    assert canonical_source_types(lead) == ["new_unrecognized_type"]
    assert select_report_explainers(lead) == []
    assert (
        select_report_explainers(
            {"entries": [{"source": {"fields": {"http": "OK", "ip": "192.0.2.1"}}}]}
        )
        == []
    )


def test_old_source_filename_fallback_is_exact_and_bounded():
    for name, expected in (
        ("2026-11-10-scan6_http_vulnerable.csv", ["scan6_http_vulnerable"]),
        ("2026-11-10-scan-http_vulnerable.csv", ["scan_http_vulnerable"]),
        ("not_scan_http_vulnerable_extra.csv", ["unclassified"]),
        ("scan_http_vulnerabletypo.csv", ["unclassified"]),
    ):
        lead = {"entries": [{"source": {"workbook": name, "fields": {}}}]}
        assert canonical_source_types(lead) == expected


def test_mixed_families_keep_business_page_once_and_preserve_evidence_distinctions():
    model, refs = model_for(
        "scan_http_vulnerable", "scan6_http_vulnerable", "scan_rdp", "compromised_website"
    )
    assert len(model["pages"]) == 4
    assert sum(p["id"] == "business-information" for p in model["pages"]) == 1
    assert model["layout_revision"] == REVISION
    assert "full scope or impact" in model["pages"][0]["blocks"][-1]["body"]
    assert all(c in {item["number"] for item in refs.items} for c in model["source_citations"])


@pytest.mark.parametrize("key,page", BANK.items())
def test_each_family_fits_one_page_with_justified_paragraphs_and_clickable_sources(key, page):
    model, _ = model_for(page["report_types"][0])
    pages = layout_information(model)
    assert len(pages) == 2
    for page in pages:
        assert any(s["kind"] == "justified_line" for s in page.segments)
        links = [s for s in page.segments if s["kind"] == "link"]
        assert links and all(s["url"].startswith("https://") for s in links)
        assert all(0 <= s["left"] < s["left"] + s["width"] <= page.width + 0.01 for s in links)
        assert all(0 <= s["top"] < s["top"] + s["height"] <= page.height for s in links)
        assert "DRAFT FOR REVIEW" not in page.alt_text
    svgs = svg_pages(model)
    assert all("<a href=" in svg for svg in svgs)


def test_changed_report_types_require_deliberate_adoption():
    lead = lead_for("scan_http_vulnerable")
    draft = {"report_explainer_snapshots": select_report_explainers(lead)}
    assert selection_is_current(lead, draft)
    lead["entries"].extend(lead_for("scan6_http_vulnerable")["entries"])
    assert not selection_is_current(lead, draft)


def test_information_pages_preserve_older_role_wording_and_cite_new_role_source_once():
    page = deepcopy(BANK["compromised_iot"])
    assert "eleven11bot" in str(page["examples"]) and "suspended" in str(page["examples"])
    assert all(s["public_url"].startswith("https://") for s in page["sources"])
    old = deepcopy(page)
    old.pop("roles_heading")
    old["sources"] = [
        s
        for s in old["sources"]
        if s["publisher"] != "National Institute of Standards and Technology"
    ]
    old["revision"] = "report-explainers-2026-11-10-v1"
    old["routes"][0][1] = "Historical case wording"
    for record, title in (
        (page, "Who may hold service records"),
        (old, "Where to Start in Your Business"),
    ):
        model = build_information_pages(
            {"draft": {"report_explainer_snapshots": [record]}}, Citations()
        )
        rendered = model["pages"][-1]
        assert rendered["blocks"][-2]["title"] == title
        assert rendered["blocks"][-1]["items"] == record["routes"]
        assert (
            sum(
                r["publisher"] == "National Institute of Standards and Technology"
                for r in rendered["references"]
            )
            == 1
        )


def test_case_pins_bank_and_rejects_forged_report_pages(client, app, monkeypatch):
    import_rows(client, app)
    entity_id = client.get("/api/leads").json()[0]["id"]
    lead = client.get("/api/leads/" + entity_id).json()
    assert lead["draft_revision"] == 0
    pinned = deepcopy(lead["draft"]["report_explainer_snapshots"])
    assert pinned and pinned[0]["id"] == "vulnerable_http"
    page = BANK["vulnerable_http"]
    monkeypatch.setitem(BANK, "vulnerable_http", {**page, "intro": "A later bank revision."})
    current = client.get("/api/leads/" + lead["id"]).json()
    assert current["draft"]["report_explainer_snapshots"] == pinned
    forged = deepcopy(pinned)
    forged[0]["intro"] = "Unsupported claim."
    response = save(client, current, report_explainer_snapshots=forged)
    assert response.status_code == 422
    assert "read-only" in response.text
    assert (
        client.get("/api/leads/" + lead["id"]).json()["draft"]["report_explainer_snapshots"]
        == pinned
    )
