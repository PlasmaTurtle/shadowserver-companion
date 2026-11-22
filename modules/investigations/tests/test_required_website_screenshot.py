"""A report needs a relevant, intact website image, including functioning login pages."""

import json

import pytest

from modules.investigations.components.report_screenshots import relevant_screenshots
from modules.investigations.components.report_snapshot import snapshot
from modules.investigations.components.image_evidence import metadata_path
from modules.investigations.tests.support.report_api import opened
from tests.support.workbench import app, client


@pytest.mark.parametrize(
    "status,http_status,accepted",
    [
        ("captured", 200, True),
        ("login_required", 401, True),
        ("login_required", 200, True),
        ("challenge", 403, False),
        ("partial", 200, False),
        ("load_failed", 500, False),
    ],
)
def test_website_requirement_uses_capture_outcome_and_report_scope(status, http_status, accepted):
    evidence = {
        "kind": "website",
        "included": True,
        "source_url": "https://example.com",
        "capture": {
            "capture_status": status,
            "http_status": http_status,
            "final_url": "http://login.example.com/signin",
        },
    }
    lead = {"domain_groups": [{"root_domain": "example.com"}], "evidence": [evidence]}
    assert bool(relevant_screenshots(lead)) is accepted
    evidence["capture"]["final_url"] = "https://unrelated.example.org"
    assert relevant_screenshots(lead) == []


def test_other_images_and_excluded_screenshots_do_not_satisfy_website_requirement():
    lead = {"domain_groups": [{"root_domain": "example.com"}], "evidence": []}
    assert relevant_screenshots(lead) == []
    evidence = {"kind": "cve", "included": True, "source_url": "https://example.com"}
    lead["evidence"].append(evidence)
    assert relevant_screenshots(lead) == []
    evidence.update(kind="website", included=False)
    assert relevant_screenshots(lead) == []
    evidence["included"] = True
    assert relevant_screenshots(lead) == [evidence]


@pytest.mark.parametrize("include_appendix", [True, False])
def test_required_website_image_is_in_primary_report_with_either_appendix_setting(include_appendix):
    from modules.investigations.tools.preview_attribution import specimen
    from modules.investigations.components.report_composition import compose

    data = specimen("Registration")
    root = data["qualified_lead"]["validated_leads"][0]["hostname"]
    data["evidence"] = [
        {
            "id": "website",
            "kind": "website",
            "included": True,
            "source_url": "https://" + root,
            "captured_at": "2026-11-21T12:00:00Z",
            "caption": "Functioning organization website",
            "sha256": "1" * 64,
        }
    ]
    data["draft"]["include_appendix"] = include_appendix
    content = compose(data)
    images = [node for node in content["sections"] if node.get("kind") == "image"]
    assert [node["id"] for node in images] == ["website"]
    assert images[0]["section_owner"] == "attribution"
    assert not any(
        node.get("id") == "website" for node in content.get("supporting_appendix_sections", [])
    )


def _checks(app, lead):
    data = snapshot(
        app.state.store, lead["id"], lead["case_id"], include_reviews=False, capture_sections=()
    )
    return {item["key"]: item["ok"] for item in data["readiness"]}


def test_missing_screenshot_blocks_review_and_certification(client, app):
    lead = opened(client, app)
    with app.state.store.transaction() as db:
        db.execute("UPDATE evidence SET included=0 WHERE case_id=?", (lead["case_id"],))
    checks = _checks(app, lead)
    assert checks["website_screenshot"] is False
    assert checks["evidence_integrity"] is False
    current = client.get("/api/cases/" + lead["case_id"]).json()
    attribution = next(item for item in current["section_reviews"] if item["key"] == "attribution")
    assert not attribution["can_validate"]
    response = client.post("/api/leads/" + lead["id"] + "/finalize?case_id=" + lead["case_id"])
    assert response.status_code == 422
    assert "website screenshot" in response.text
    assert app.state.store.all("SELECT * FROM reports") == []


@pytest.mark.parametrize("changed", ["original", "preview", "metadata", "provenance"])
def test_report_checks_retained_original_preview_and_metadata(client, app, changed):
    lead = opened(client, app)
    evidence = next(item for item in lead["evidence"] if item["kind"] == "website")
    assert _checks(app, lead)["evidence_integrity"]
    store = app.state.store
    if changed in {"metadata", "provenance"}:
        path = store.path(metadata_path(evidence["id"]))
        metadata = json.loads(path.read_text(encoding="utf-8"))
        if changed == "metadata":
            metadata.pop("preview_sha256")
        else:
            metadata["website_capture"]["final_url"] += "/altered"
            metadata.pop("website_capture_id")
        path.write_text(json.dumps(metadata), encoding="utf-8")
    else:
        store.path(evidence["path" if changed == "original" else "preview_path"]).write_bytes(
            b"changed"
        )
    assert _checks(app, lead)["evidence_integrity"] is False
