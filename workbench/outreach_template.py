"""Shared notification narrative with an explicit targeted-outreach alternative."""

from .notification_narrative import generate_narrative, REVISION
from .notification_narrative_v1 import generate_narrative as generate_v1, REVISION as V1_REVISION
from .notification_narrative_v2 import generate_narrative as generate_v2, REVISION as V2_REVISION
from .approved_template import generate_narrative as generate_legacy
from .notification_narrative_v4 import (
    generate_narrative as generate_v4,
    REVISION as V4_REVISION,
    SOURCE_AWARE_REVISIONS,
    apply_copy,
)
from .notification_narrative_v5 import generate_narrative as generate_v5, REVISION as V5_REVISION

SUPPORTED_NARRATIVE_REVISIONS = frozenset(
    ("legacy", V1_REVISION, V2_REVISION, REVISION, V4_REVISION, V5_REVISION)
)

TARGETED_REVISION = "targeted-2026-11-07-v1"
TARGETED_DESCRIPTION = "Optional targeted-outreach narrative. Selecting it explicitly adopts the two scope changes; the established critical template remains unchanged."


def apply_outreach_template(lead, draft):
    # Saved drafts pin generation as well as page presentation. Regenerating
    # through that version still exposes changed source/entity dependencies to
    # section-freeze checks; copying static saved prose would hide those edits.
    revision = draft.get("narrative_revision") or REVISION
    if revision == "legacy":
        generator = generate_legacy
    elif revision == V1_REVISION:
        generator = generate_v1
    elif revision == V2_REVISION:
        generator = generate_v2
    elif revision == REVISION:
        generator = generate_narrative
    elif revision == V4_REVISION:
        generator = generate_v4
    elif revision == V5_REVISION:
        generator = generate_v5
    else:
        raise ValueError(
            "Unsupported saved narrative revision; adopt a supported report presentation."
        )
    draft["narrative"] = generator(lead, draft)
    draft["narrative_revision"] = revision
    if revision in SOURCE_AWARE_REVISIONS:
        apply_copy(lead, draft)
    if draft.get("outreach_template") == "targeted-v1":
        # Generated only from controlled prose and its defined insertables.
        # The legacy approved source file is intentionally untouched.
        draft["narrative"] = (
            draft["narrative"]
            .replace("a critical security finding", "a reported security finding")
            .replace("critical security findings", "reported security findings")
            .replace(
                "critical vulnerability handling procedures",
                "your organization’s vulnerability handling procedures",
            )
        )
    from .sender_identity import apply_identity_copy

    return apply_identity_copy(draft, narrative=revision != V5_REVISION)


def narrative_scope_issue(lead, draft):
    from .notification_narrative_v4 import source_context, HTTP_TYPES

    contexts = [source_context(entry) for entry in lead.get("entries", [])]
    if draft.get("narrative_revision") not in SOURCE_AWARE_REVISIONS and any(
        context["id"] not in HTTP_TYPES and context["kind"] != "observation" for context in contexts
    ):
        return "Adopt the current report presentation for this source report type."
    # A critical vulnerability can bring other observations into a case as
    # context. That does not authorize ordinary prevention wording for incident
    # indicators: each such case still needs the explicit targeted choice.
    if (
        any(context["kind"] == "compromise_indicator" for context in contexts)
        and draft.get("outreach_template") != "targeted-v1"
    ):
        return "Select the targeted-outreach narrative to review reported compromise indicators."
    targeted_only = (
        bool(lead.get("entries"))
        and not any(
            str(e.get("source", {}).get("fields", {}).get("severity", "")).casefold() == "critical"
            for e in lead.get("entries", [])
        )
        and any(
            e.get("normalized", {}).get("eligibility", {}).get("outreach_mode") == "targeted"
            for e in lead.get("entries", [])
        )
    )
    if targeted_only and draft.get("outreach_template") != "targeted-v1":
        return "Select the targeted-outreach narrative for this noncritical notification."
    return None
