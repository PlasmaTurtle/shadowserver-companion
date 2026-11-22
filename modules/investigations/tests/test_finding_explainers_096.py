"""Source-scoped lifecycle snippets, immutable case selection, and real exports."""

from copy import deepcopy
import json
import re

import pytest

from modules.workspace.components import compact_json
from modules.investigations.components.exhibit_models import build_exhibits
from modules.library.resources.finding_explainer_data import BANK
from modules.investigations.components.finding_explainers import REVISION, select_finding_explainers
from modules.investigations.components.notification_narrative_v4 import REVISION as V4
from modules.investigations.components.report_composition import Citations
from modules.ui.components.exhibit_rendering import prepared_pages
from modules.investigations.components.vulnerability_model import build_vulnerability_exhibit
from tests.support.workbench import app, client, import_rows, observations, ready
from modules.investigations.tests.support.section_reviews import save


def entry(source, tag, ip="192.0.2.1", version="5.6.29"):
    fields = {
        "report_type": source,
        "tag": tag,
        "ip": ip,
        "hostname": "mail.example.com",
        "version": version,
        "protocol": "tcp",
        "port": 443,
        "timestamp": "2026-11-05T01:00:00Z",
    }
    return {"ip": ip, "source": {"fields": fields}, "normalized": {"profile": {"id": source}}}


def findings(entries, *, revision=REVISION, cves=(), excluded=()):
    draft = {
        "finding_explainer_revision": revision,
        "finding_explainer_snapshots": select_finding_explainers({"entries": entries}),
        "narrative_revision": V4,
    }
    data = {
        "draft": draft,
        "cves": list(cves),
        "qualified_lead": {"validated_leads": [{"hostname": "example.com", "entries": entries}]},
    }
    refs = Citations()
    exhibits, appendix = build_exhibits(data, refs, [], excluded=excluded)
    model = next(item for item in exhibits if item["type"] == "vulnerability")
    return data, model, refs, appendix


@pytest.mark.parametrize(
    "source,tag,expected",
    [
        ("scan_http_vulnerable", "eol-php", "http_eol_php"),
        ("scan6_http_vulnerable", "EOL-PHP", "http_eol_php"),
        ("scan_http_vulnerable", "eol-iis", "http_iis_support"),
        ("scan_http_vulnerable", "eos-iis", "http_iis_support"),
        ("scan_http_vulnerable", "eol-zimbra", "http_eol_component"),
        ("scan_http_vulnerable", "eol", "http_eol_component"),
        ("scan_http_vulnerable", "eol-exchange", "exchange-eol"),
        ("scan_exchange", "eol", "exchange-eol"),
        ("scan6_exchange", "eol", "exchange-eol"),
        ("scan_exchange", "eol-php", None),
        ("scan_http", "eol-php", None),
        ("scan_smtp_vulnerable", "eol", None),
        ("scan_http_vulnerable", "not-eol-php", None),
        ("scan_http_vulnerable", "eos-unknown", None),
        ("scan_http_vulnerable", "CVE-2099-10001", None),
    ],
)
def test_matching_uses_exact_report_family_and_documented_tag(source, tag, expected):
    def selected(value):
        return [s["id"] for s in select_finding_explainers({"entries": [value]})]

    assert selected(entry(source, tag)) == ([expected] if expected else [])


def test_generic_http_condition_never_guesses_the_product_from_version():
    _, model, _, _ = findings(
        [entry("scan_http_vulnerable", "eol-custom-appliance", version="PHP/1.0")]
    )
    item = model["items"][0]
    assert item["technical_explanation"]["id"] == "http_eol_component"
    assert "PHP" not in item["technical_explanation"]["body"]


def test_exchange_condition_deduplicates_http_and_exchange_reports_without_losing_assets():
    rows = [
        entry("scan_exchange", "eol", "192.0.2.1", "14.2"),
        entry("scan_http_vulnerable", "eol-exchange", "192.0.2.2", "15.0"),
        entry("scan6_exchange", "eol", "192.0.2.1", "14.2"),
    ]
    _, model, refs, appendix = findings(rows)
    assert len(model["items"]) == 1
    item = model["items"][0]
    assert item["exposure_count"] == 2 and len(item["observation_ids"]) == 3
    assert set(item["reported_versions"]) == {"14.2", "15.0"}
    assert set(item["reported_tags"]) == {"eol", "eol-exchange"}
    assert model["counts"][1]["value"] == 1
    assert item["technical_explanation"]["source_citations"] == item["citations"]
    assert set(item["citations"]) <= {source["number"] for source in refs.items}
    assert any(row["partition"] == "C" for row in appendix["entries"])


def test_eos_iis_has_one_lifecycle_card_not_a_duplicate_observation():
    _, model, _, _ = findings([entry("scan_http_vulnerable", "eos-iis")])
    assert [item["finding_type"] for item in model["items"]] == ["eol"]
    assert model["items"][0]["technical_explanation"]["id"] == "http_iis_support"


def test_excluded_cve_never_returns_as_a_generic_explanation_but_independent_eol_remains():
    cve = "CVE-2099-10001"
    exclusion = [{"id": cve, "reason": "Not applicable to the installed product."}]
    _, only_cve, _, _ = findings(
        [entry("scan_http_vulnerable", cve)], cves=[cve], excluded=exclusion
    )
    assert only_cve["items"] == []
    _, mixed, _, _ = findings(
        [entry("scan_http_vulnerable", cve + ";eol-php")], cves=[cve], excluded=exclusion
    )
    assert [item["finding_type"] for item in mixed["items"]] == ["eol"]
    assert mixed["items"][0]["technical_explanation"]["id"] == "http_eol_php"


def test_historical_revision_does_not_gain_content_or_citations():
    _, old, refs, _ = findings([entry("scan_http_vulnerable", "eol-php")], revision="legacy")
    assert "technical_explanation" not in old["items"][0]
    assert old["items"][0]["citations"] == []
    assert refs.items == []


@pytest.mark.parametrize(
    "source,tag", [("scan_http_vulnerable", "eol-php"), ("scan_exchange", "eol")]
)
def test_eol_only_case_freezes_and_exports_source_backed_technical_text(client, app, source, tag):
    rows = observations()
    for row in rows:
        row.update(report_type=source, tag=tag)
    import_rows(client, app, rows)
    lead_id = client.get("/api/leads").json()[0]["id"]
    lead = ready(client, lead_id)
    response = client.post(
        "/api/leads/" + lead_id + "/finalize", params={"case_id": lead["case_id"]}
    )
    assert response.status_code == 200, response.text
    folder = app.state.store.path(response.json()["path"])
    assert (folder / "notification.pdf").read_bytes().startswith(b"%PDF")
    data = compact_json.loads((folder / "snapshot.json").read_bytes())
    model = next(
        item for item in data["composition"]["exhibits"] if item["type"] == "vulnerability"
    )
    snippets = [
        item["technical_explanation"]
        for item in model["items"]
        if item.get("technical_explanation")
    ]
    assert len(snippets) == 1 and snippets[0]["source_citations"]
    assert not data["composition"]["citation_integrity_issues"]
    pages = prepared_pages(model)
    text = " ".join(page.page.alt_text for page in pages)
    assert all(
        snippets[0][key] in " ".join(text.split()) for key in ("body", "limitations", "review")
    )
    for page in pages:
        assert all(
            segment.get("top", 0) + segment.get("height", 0) <= page.page.height
            for segment in page.page.segments
            if segment.get("kind") == "finding"
        )


def test_first_open_pins_technical_bank_and_rejects_forged_case_content(client, app, monkeypatch):
    import_rows(client, app)
    lead_id = client.get("/api/leads").json()[0]["id"]
    lead = client.get("/api/leads/" + lead_id).json()
    pinned = deepcopy(lead["draft"]["finding_explainer_snapshots"])
    assert pinned and pinned[0]["id"] == "http_eol_php"
    monkeypatch.setitem(
        BANK, "http_eol_php", {**BANK["http_eol_php"], "body": "A later technical revision."}
    )
    current = client.get("/api/leads/" + lead_id).json()
    assert current["draft"]["finding_explainer_snapshots"] == pinned
    forged = deepcopy(pinned)
    forged[0]["body"] = "Unsupported assertion."
    response = save(client, current, finding_explainer_snapshots=forged)
    assert response.status_code == 422 and "read-only" in response.text
