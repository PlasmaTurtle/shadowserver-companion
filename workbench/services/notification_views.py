"""Working and historical notification projections."""

from __future__ import annotations

import json
from fastapi import HTTPException
from ..report_drafts import hydrated_draft, readiness, narrative_groups
import workbench.compact_json as compact_json
from ..report_snapshot import snapshot
from ..reviews.queries import SectionReviewQueries
from ..attribution_display import attribution_summaries
from ..presentation import document_policy, HANDLING
from ..report_layouts import layout_update_available
from .compatibility import initialize_legacy_draft
from ..package_integrity import verification_operation


def _editor_artwork_metadata(value):
    """Project artwork metadata without changing stored review/package bytes.

    The editor reads content, geometry and digests; full image and font blobs
    belong in the verified snapshot download and document export, not each GET.
    This is deliberately the last step, after integrity and stale-review checks.
    """
    if isinstance(value, list):
        return [_editor_artwork_metadata(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if key == "rendered_masters" and isinstance(item, dict):
            result[key] = {
                **{name: content for name, content in item.items() if name != "resources"},
                "metadata_only": True,
                "pages": [
                    {
                        name: content
                        for name, content in page.items()
                        if name not in {"svg", "png", "standalone_svg"}
                    }
                    for page in item.get("pages", [])
                ],
            }
        else:
            result[key] = _editor_artwork_metadata(item)
    return result


@verification_operation
def load_notification(store, cases, lead_id, case_id=None):
    """Build the editor projection; initializes missing legacy defaults and records stale reviews.

    Historical packages are read from their certified snapshot without re-composition.
    These existing write effects are retained explicitly for compatibility.
    """
    case_id = case_id or cases.default_id(lead_id)
    lead = cases.view(case_id) if case_id else store.lead(lead_id)
    if not lead:
        raise HTTPException(404, "Notification not found")
    if lead["id"] != lead_id:
        raise HTTPException(
            409, f"This entity was combined into {lead['company']}. Open it from the lead queue."
        )
    # Sidecar acquisition facts are read-only and separate from editable captions.
    from ..image_evidence import metadata_path

    for item in lead.get("evidence", []):
        metadata_file = store.path(metadata_path(item["id"]))
        if metadata_file.is_file():
            metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
            if metadata.get("website_capture"):
                item["capture"] = metadata["website_capture"]
    initialize_legacy_draft(store, cases, lead)
    lead["draft"] = hydrated_draft(lead, store.settings())
    lead["narrative_groups"] = narrative_groups(lead, lead["draft"])
    from ..sender_identity import approved_copy

    lead["readiness"] = readiness(lead, lead["draft"], store.settings())
    lead["attribution_summaries"] = attribution_summaries(store, lead)
    reviews = SectionReviewQueries(store)
    report_id = lead.get("case", {}).get("certified_report_id")
    historical = bool(report_id and lead.get("case", {}).get("stage") != "in_progress")
    if historical:
        report = store.one("SELECT * FROM reports WHERE id=? AND case_id=?", (report_id, case_id))
        try:
            _, raw = store.artifacts.snapshot_inventory(report)
            data = compact_json.loads(raw)
            if data.get("case_id", data.get("notification_id")) != case_id:
                raise ValueError("Certified snapshot belongs to a different case")
            lead["draft"] = data["draft"]
            lead["section_reviews"] = [
                {**r, "can_validate": False} for r in data.get("section_reviews", [])
            ]
            lead["historical_report"] = {
                "id": report_id,
                "revision": report["revision"],
                "app_version": data.get("app_version"),
                "handling_label": data.get("handling", {}).get("label"),
                "snapshot_verified": True,
            }
        except (OSError, ValueError, KeyError, TypeError) as error:
            data = {
                "draft": lead["draft"],
                "composition": {"sections": [], "exhibits": [], "appendix": {}},
                "readiness": [
                    {
                        "key": "historical_package",
                        "label": "Restore the certified report package: " + str(error),
                        "ok": False,
                    }
                ],
            }
            lead["section_reviews"] = []
            lead["historical_report"] = {"id": report_id, "snapshot_verified": False}
    else:
        data = snapshot(store, lead_id, case_id, include_reviews=False, capture_sections=())
        lead["section_reviews"] = reviews.describe(data, lead)
    lead["section_history"] = reviews.history(case_id)
    lead["readiness"] = data["readiness"]
    lead["report_model"] = data["composition"]
    from ..observation_scope import legacy_scope_warning

    lead["scope_warning"] = legacy_scope_warning(lead) if historical else None
    lead["approved_copy"] = approved_copy(lead["draft"])
    if lead["draft"].get("information_revision") == "information-2026-11-10-v1":
        from ..report_explainers import selection_notices

        lead["report_explainer_notices"] = selection_notices(lead)
    lead["handling_policy"] = data.get("handling", HANDLING)
    from ..sender_identity import update_available

    lead["sender_profile_update_available"] = not historical and update_available(
        store.settings(), lead["draft"]
    )
    lead["presentation_update_available"] = not historical and (
        lead["draft"].get("document_policy") != document_policy(store.settings())
        or layout_update_available(lead["draft"])
        or lead["sender_profile_update_available"]
    )
    # Certified snapshots already contain their section readiness decisions.
    # Keep one result per check rather than duplicating all five on every load.
    checks = {row["key"] for row in lead["readiness"]}
    lead["readiness"] += [
        {
            "key": "section_" + r["key"],
            "label": r["label"] + " validated and current",
            "ok": r["status"] == "validated",
        }
        for r in lead["section_reviews"]
        if "section_" + r["key"] not in checks
    ]
    return _editor_artwork_metadata(lead)
