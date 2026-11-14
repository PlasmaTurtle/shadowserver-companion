"""Pinned report-layout revisions and explicit adoption of reviewed pages.

New cases use the current reviewed layouts. Existing drafts retain their saved
revisions (including implicit legacy values) until the analyst adopts the new
presentation through the normal section-freeze guards.
"""

from . import introduction_model, vulnerability_model, attribution_model
from . import information_model, closing_page_model, appendix_view
from .notification_narrative_v5 import REVISION as NARRATIVE_REVISION
from .approved_template import ADDRESSEE, ADDRESSEE_REVISION
from .finding_explainers import REVISION as FINDING_EXPLAINER_REVISION


CURRENT_LAYOUTS = {
    "finding_explainer_revision": FINDING_EXPLAINER_REVISION,
    "introduction_revision": introduction_model.REVISION,
    "vulnerability_revision": vulnerability_model.CURRENT_REVISION,
    "attribution_revision": attribution_model.REVISION,
    "information_revision": information_model.REVISION,
    "closing_revision": closing_page_model.REVISION,
    "appendix_revision": appendix_view.COMPACT_REVISION,
}
CURRENT_REVISIONS = {
    **CURRENT_LAYOUTS,
    "narrative_revision": NARRATIVE_REVISION,
    "addressee_revision": ADDRESSEE_REVISION,
}


def pristine_layout_defaults(lead):
    """Only untouched intake placeholders may adopt defaults without an edit."""
    case = lead.get("case", {})
    saved = lead.get("draft", {})
    return (
        case.get("stage", "in_progress") == "in_progress"
        and case.get("draft_revision", lead.get("draft_revision", 0)) == 0
        and not any(key in saved for key in ("template_revision", "subject", "intro"))
    )


def layout_defaults(lead):
    if pristine_layout_defaults(lead):
        return dict(CURRENT_REVISIONS)
    return {key: "legacy" for key in CURRENT_REVISIONS}


def apply_layout_copy(draft):
    """Keep builder text aligned with the explicitly selected introduction."""
    if draft.get("introduction_revision") == introduction_model.REVISION:
        draft["intro"] = introduction_model.INTRO
        draft["subject"] = introduction_model.SUBJECT
    return draft


def adopt_current_layouts(draft):
    draft.update(CURRENT_REVISIONS)
    draft["contact_name"] = ADDRESSEE
    return apply_layout_copy(draft)


def layout_update_available(draft):
    return any(draft.get(key, "legacy") != revision for key, revision in CURRENT_REVISIONS.items())
