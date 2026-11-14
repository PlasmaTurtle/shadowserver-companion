"""Attribution review integration: source scope, export parity and frozen history."""

from copy import deepcopy
import json
import socket
import subprocess
from zipfile import ZipFile

import pytest

from test_attribution_review import review_app, accept_payload
from test_section_validation_050 import prepared, save, status
from test_workbench import app, client, ready
from tools.preview_attribution import specimen, SCENARIOS
from workbench import approved_template as approved
from workbench.appendix import flatten_fields
from workbench.attribution_model import REVISION
from workbench.exhibit_rendering import (
    capture_exhibit_masters,
    export_exhibits,
    prepared_pages,
    svg_pages,
)
from workbench.report_composition import compose
from workbench.report_renderers import render_pdf, render_docx


def exhibit(data):
    return next(e for e in data["composition"]["exhibits"] if e["type"] == "attribution")


def rendered_text(model):
    return " ".join(
        e[3] for item in prepared_pages(model) for e in item.page.elements if e[0] == "text"
    )


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_scenarios_preserve_one_approved_paragraph_and_exact_saved_evidence(scenario):
    data = specimen(scenario)
    model = exhibit(data)
    assert len(prepared_pages(model)) == 1
    assert model["narrative"] == approved.ATTRIBUTION
    assert data["composition"]["citation_integrity_issues"] == []
    combined = " ".join(rendered_text(model).split())
    assert combined.count(" ".join(approved.ATTRIBUTION.split())) == 1
    assert not any(n.get("text") == approved.ATTRIBUTION for n in data["composition"]["sections"])
    assert len(model["items"]) == 1
    item = model["items"][0]
    assert item["reported_ip"] == "192.0.2.14"
    assert item["source_name"] in combined
    assert item["retrieved_at"] in combined
    citation_numbers = {c["number"] for c in data["composition"]["citations"]}
    assert item["citations"] and set(item["citations"]) <= citation_numbers
    raw = next(
        e for e in data["composition"]["appendix"]["entries"] if e["kind"] == "attribution_evidence"
    )
    assert raw["status"] == "recorded"
    assert raw["fields"] == list(flatten_fields(data["qualified_lead"]["whois"][0]))
    assert raw["id"] in item["appendix_entry_ids"]
    if scenario == "Registration":
        assert item["reported_asset_count"] == 70
        assert item["supporting_attribution_count"] == 1
        assert "1 supporting association / 70 reported IP addresses" in combined
        assert item["validated_at"] != item["retrieved_at"]
    if scenario == "DNS":
        assert item["corroborated_label"] == "DNS answer"
        assert item["corroborated_value"] == "192.0.2.14"
    if scenario == "Analyst_Review":
        assert item["validated_by"] == "Example Analyst"
        assert item["validated_at"] == "2026-11-07T15:45:00Z"
        assert "Analyst-reviewed registration-name match" in combined
    if scenario == "Review_Required":
        assert item["review_required"] and not item["supported"]
        assert item["supporting_attribution_count"] == 0
        assert item["validated_at"] is None
        assert "Review required" in combined
    else:
        assert item["supported"] and not item["review_required"]
        assert item["validated_at"] in combined


def test_opt_in_changes_attribution_only_and_preserves_other_pages_and_sources():
    data = specimen("Registration")
    reviewed = compose(data)
    data["draft"].pop("attribution_revision")
    legacy = compose(data)

    def segment(content, first, following):
        nodes = content["sections"]
        start = next(i for i, n in enumerate(nodes) if n.get("section_key") == first)
        end = next(i for i, n in enumerate(nodes) if n.get("section_key") == following)
        return nodes[start:end]

    assert reviewed["sections"][0] == legacy["sections"][0]
    assert segment(reviewed, "vulnerabilities", "attribution") == segment(
        legacy, "vulnerabilities", "attribution"
    )
    assert segment(reviewed, "information", "closing") == segment(legacy, "information", "closing")
    assert reviewed["citations"] == legacy["citations"]
    for partition in ("A", "C", "D"):
        assert [e for e in reviewed["appendix"]["entries"] if e["partition"] == partition] == [
            e for e in legacy["appendix"]["entries"] if e["partition"] == partition
        ]
    assert sum(n.get("exhibit_id") == "EX-ATTRIBUTION" for n in reviewed["sections"]) == 1
    assert exhibit({"composition": legacy}).get("layout_revision") is None


def test_saved_artwork_is_reused_by_pdf_word_svg_and_json_roundtrip(tmp_path, monkeypatch):
    data = specimen("DNS")
    model = exhibit(data)
    expected = prepared_pages(model)
    restored = json.loads(json.dumps(model))
    assert svg_pages(restored) == svg_pages(model)
    uncaptured = deepcopy(restored)
    uncaptured.pop("rendered_masters")
    monkeypatch.setattr(
        "workbench.exhibit_rendering.layout_attribution",
        lambda *a, **k: pytest.fail("Frozen attribution geometry was regenerated"),
    )
    monkeypatch.setattr(
        "workbench.exhibit_rendering.png",
        lambda *a, **k: pytest.fail("Frozen attribution pixels were regenerated"),
    )
    monkeypatch.setattr(
        socket, "create_connection", lambda *a, **k: pytest.fail("Export used a network lookup")
    )
    capture_exhibit_masters({"exhibits": [uncaptured]}, [restored])
    assert uncaptured == restored
    data["composition"]["exhibits"] = [restored]
    data["composition"]["sections"] = [
        n for n in data["composition"]["sections"] if n.get("exhibit_id") == model["id"]
    ]
    render_pdf(data, tmp_path / "review.pdf", tmp_path)
    render_docx(data, tmp_path / "review.docx", tmp_path)
    exports = export_exhibits(data["composition"], tmp_path / "exhibits")
    from workbench.svg_resources import without_webfonts

    with ZipFile(tmp_path / "review.docx") as z:
        # The original geometry travels unchanged in Word; fonts now live once
        # in the document font table. Standalone master bytes below stay exact.
        assert [z.read(n) for n in z.namelist() if n.endswith(".svg")] == [
            without_webfonts(p.svg) for p in expected
        ]
        assert expected[0].png in [z.read(n) for n in z.namelist() if n.endswith(".png")]
    for exported, page in zip(exports, expected):
        assert (tmp_path / "exhibits" / exported["svg"]).read_bytes() == page.svg
    text = subprocess.check_output(["pdftotext", str(tmp_path / "review.pdf"), "-"]).decode()
    assert "192.0.2.14" in text
    assert "Forward DNS match" in text
    assert len([p for p in text.split("\f") if p.strip()]) == len(expected)


@pytest.mark.parametrize("change", ["model", "geometry", "svg"])
def test_tampered_saved_attribution_requires_new_review(change):
    model = deepcopy(exhibit(specimen("DNS")))
    if change == "model":
        model["items"][0]["validated_at"] = "2026-11-08T14:20:00Z"
    elif change == "geometry":
        model["rendered_masters"]["pages"][0]["geometry"]["height"] = 1
    else:
        model["rendered_masters"]["pages"][0]["svg_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        prepared_pages(model)


def test_validated_case_reuses_attribution_artwork_and_guards_revision_change(
    review_app, monkeypatch
):
    app, client, group, state, _ = review_app
    response = client.post("/api/groups/" + group["id"] + "/review", json=accept_payload(group))
    assert response.status_code == 200, response.text
    from workbench.cases import Cases

    Cases(app.state.store).create(response.json()["lead_id"], "Attribution review fixture")
    lead = ready(client, response.json()["lead_id"], validate=False)
    response = save(client, lead, attribution_revision=REVISION)
    assert response.status_code == 200, response.text
    lead = response.json()
    response = client.post(
        f"/api/cases/{lead['case_id']}/sections/attribution/validate",
        json={"expected_revision": lead["draft_revision"]},
    )
    assert response.status_code == 200, response.text
    frozen = status(response.json(), "attribution")
    assert frozen["validated_by"] == "Test Analyst"
    assert frozen["fingerprint_version"] == 2
    assert frozen["snapshot"]["exhibits"]
    assert all("rendered_masters" not in model for model in frozen["snapshot"]["exhibits"])
    calls = len(state["calls"])
    monkeypatch.setattr(
        "workbench.exhibit_rendering.layout_attribution",
        lambda *a, **k: pytest.fail("Frozen Attribution page was rebuilt"),
    )
    response = client.get("/api/cases/" + lead["case_id"])
    assert response.status_code == 200, response.text
    retained = status(response.json(), "attribution")
    assert retained["status"] == "validated"
    assert retained["snapshot"] == frozen["snapshot"]
    assert len(state["calls"]) == calls
    denied = save(client, response.json(), attribution_revision="legacy")
    assert denied.status_code == 422 and "Attribution" in denied.text


def test_incomplete_historical_evidence_cannot_certify_new_exhibit(client, app):
    lead = prepared(client, app, validate=False)
    # Current synthetic imports include a complete evaluation timestamp. Model
    # the historical omission explicitly instead of depending on fixture gaps.
    with app.state.store.transaction() as db:
        groups = db.execute(
            "SELECT root_domain,attribution FROM case_groups WHERE case_id=?", (lead["case_id"],)
        ).fetchall()
        for group in groups:
            proof = json.loads(group["attribution"])
            for key in ("validated_at", "decision_at", "evaluated_at"):
                proof.pop(key, None)
            db.execute(
                "UPDATE case_groups SET attribution=? WHERE case_id=? AND root_domain=?",
                (json.dumps(proof), lead["case_id"], group["root_domain"]),
            )
    response = save(client, lead, attribution_revision=REVISION)
    assert response.status_code == 200, response.text
    lead = response.json()
    exhibit = next(e for e in lead["report_model"]["exhibits"] if e["type"] == "attribution")
    assert all(
        item["timestamp_note"] == "Validation time was not recorded." for item in exhibit["items"]
    )
    assert not status(lead, "attribution")["can_validate"]
    response = client.post(
        f"/api/cases/{lead['case_id']}/sections/attribution/validate",
        json={"expected_revision": lead["draft_revision"]},
    )
    assert response.status_code == 422
