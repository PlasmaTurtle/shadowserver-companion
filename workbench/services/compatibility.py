"""Explicit writes retained for older entity-oriented clients and exports.

The case draft is authoritative. This projection remains until a separately
versioned migration removes the legacy fields; it never opens its own transaction.
"""

import json

from ..content_bank import snapshot_blocks
from ..presentation import document_policy
from ..primitives import dump, now
from ..report_layouts import CURRENT_REVISIONS, pristine_layout_defaults
from ..report_explainers import select_report_explainers
from ..finding_explainers import select_finding_explainers


def project_legacy_draft(db, entity_id, draft):
    db.execute(
        "UPDATE leads SET draft=?,draft_revision=draft_revision+1,status='in_progress',updated_at=? WHERE id=?",
        (dump(draft), now(), entity_id),
    )


def initialize_legacy_draft(store, cases, lead):
    """Pin missing legacy defaults once without recording a user edit."""
    # Capture defaults once without counting this as analyst work. This keeps
    # untouched leads eligible for consolidation and never changes history.
    pin_layouts = pristine_layout_defaults(lead) and any(
        key not in lead["draft"] for key in CURRENT_REVISIONS
    )
    pin_report_pages = (
        pin_layouts or lead["draft"].get("information_revision") == "information-2026-11-10-v1"
    ) and "report_explainer_snapshots" not in lead["draft"]
    pin_finding_snippets = (
        pin_layouts
        or lead["draft"].get("finding_explainer_revision") == "finding-explainers-2026-11-10-v1"
    ) and "finding_explainer_snapshots" not in lead["draft"]
    if lead.get("case", {}).get("stage") == "in_progress" and (
        pin_layouts
        or pin_report_pages
        or pin_finding_snippets
        or any(key not in lead["draft"] for key in ("explainer_snapshots", "document_policy"))
    ):
        with store.transaction() as db:
            current = cases.require(db, lead["case_id"], editable=True)
            saved = json.loads(current["draft"])
            if "explainer_snapshots" not in saved:
                saved["explainer_snapshots"] = snapshot_blocks(db)
            saved.setdefault("document_policy", document_policy(store.settings()))
            if pin_layouts:
                for key, revision in CURRENT_REVISIONS.items():
                    saved.setdefault(key, revision)
            if pin_report_pages:
                saved["report_explainer_snapshots"] = select_report_explainers(lead)
            if pin_finding_snippets:
                saved["finding_explainer_snapshots"] = select_finding_explainers(lead)
            db.execute("UPDATE cases SET draft=? WHERE id=?", (dump(saved), lead["case_id"]))
            lead["draft"] = saved
