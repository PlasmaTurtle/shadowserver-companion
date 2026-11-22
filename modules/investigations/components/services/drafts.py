"""Transactional report-editing operations.

HTTP validation lives in api_models. These operations own the writer transaction,
revision check, pinned-source rules, section guards, audit events, and the legacy
entity projection. No source is fetched or silently adopted while saving.
"""

from copy import deepcopy
import json

from modules.investigations.components import approved_template as approved
from modules.library.components.content_bank import snapshot_blocks
from modules.library.components.intelligence.identifiers import identifiers
from modules.accretion.components.intake.versions import entry_fields
from ..cve_state import guard_cve_states
from ..outreach_template import apply_outreach_template
from modules.ui.components.presentation import document_policy
from ..report_drafts import hydrated_draft, narrative_groups
from ..report_layouts import CURRENT_LAYOUTS, adopt_current_layouts, apply_layout_copy
from ..report_snapshot import snapshot
from ..reviews.queries import SectionReviewQueries
from ..reviews.policy import check_revision
from modules.workspace.components.primitives import dump, now
from .compatibility import project_legacy_draft
from modules.library.components.intelligence.selection_identity import same_selection
from modules.library.components.repositories.sources import SourceRepository
from modules.settings.components.sender_identity import (
    capture_profile,
    effective_settings,
    pin_submitted,
)


class DraftRevisionConflict(ValueError):
    """The editor submitted a revision that has already been superseded."""


def _pinned_fields(store, data, prior):
    pin_submitted(data, prior)
    pinned_policy = prior.get("document_policy") or document_policy(store.settings())
    if data.get("document_policy") and data["document_policy"] != pinned_policy:
        raise ValueError(
            "Document presentation is read-only. Use the explicit presentation adoption action."
        )
    data["document_policy"] = pinned_policy
    if data.get("source_restrictions") != prior.get("source_restrictions", []):
        raise ValueError("Source restrictions cannot be changed through the report editor.")
    if data.get("cve_state_history") != prior.get("cve_state_history", []):
        raise ValueError("CVE state history is read-only and retained by the server.")
    from ..observation_scope import SCOPE_FIELDS

    for key in SCOPE_FIELDS:
        if key in data and data[key] != prior.get(key, {}):
            raise ValueError("Observation scope is read-only here. Use the report scope review.")
        data[key] = deepcopy(prior.get(key, {}))


def _source_records(db, lead, data, prior):
    reported = set(identifiers(entry_fields(e).get("tag", "") for e in lead["entries"]))
    record_ids = [item.get("id") for item in data["cve_records"]]
    if any(not isinstance(key, str) for key in record_ids) or len(record_ids) != len(
        set(record_ids)
    ):
        raise ValueError("Each source record needs one distinct reported CVE identifier")
    if not set(record_ids) <= reported or not set(data["cve_dispositions"]) <= reported:
        raise ValueError(
            "Source selections and dispositions must belong to this case’s reported CVEs"
        )
    old_records = {item.get("id"): item for item in prior.get("cve_records", [])}
    for record in data["cve_records"]:
        if same_selection(old_records.get(record["id"]), record):
            continue
        if not SourceRepository.selection_available(db, record):
            raise ValueError(
                "Published source text and metrics are read-only. Retrieve the record or document an official-text fallback."
            )
    for cve_id, selection in data["selected_ssvc_assessments"].items():
        record = next((r for r in data["cve_records"] if r.get("id") == cve_id), None)
        if not record or selection not in {r.get("id") for r in record.get("ssvc_assessments", [])}:
            raise ValueError(
                "The selected SSVC assessment must belong to this case’s pinned CVE revision."
            )
    cached_states = SourceRepository.current_states(db, reported)
    data["cve_state_history"] = guard_cve_states(
        data["cve_records"],
        prior.get("cve_records", []),
        prior.get("cve_state_history", []),
        cached_states,
        data["cve_dispositions"],
    )


def _explainer_snapshots(db, data, prior):
    pinned = {b["id"]: b for b in prior.get("explainer_snapshots", [])}
    latest = {row["id"]: row for row in snapshot_blocks(db)}
    submitted = {}
    for block in data["explainer_snapshots"]:
        key = block.get("id")
        if not isinstance(key, str) or key in submitted:
            raise ValueError("Explainer snapshots must have distinct IDs")
        if block != pinned.get(key) and block != latest.get(key):
            raise ValueError(
                "Edit case wording through overrides; saved library revisions are read-only"
            )
        submitted[key] = block
    # Old clients may omit snapshot fields; keep the already captured bank.
    for key, block in pinned.items():
        submitted.setdefault(key, block)
    for key in data["selected_explainers"]:
        if key not in submitted:
            if key not in latest:
                raise ValueError("Selected explainer is unavailable")
            submitted[key] = latest[key]
    if not set(data["explainer_overrides"]) <= set(submitted):
        raise ValueError("Case wording must refer to an available explainer")
    for value in data["explainer_overrides"].values():
        if not set(value) <= {"title", "body"} or any(len(text) > 20000 for text in value.values()):
            raise ValueError("Case wording supports title and body edits only")
    data["explainer_snapshots"] = list(submitted.values())


class DraftService:
    """Case edits and their compatibility projection commit together."""

    def __init__(self, store, cases):
        self.store = store
        self.cases = cases

    def save(self, lead, fields, expected_revision):
        store, cases = self.store, self.cases
        lead_id, case_id = lead["id"], lead["case_id"]
        data = deepcopy(fields)
        with store.transaction() as db:
            current = cases.require(db, case_id, editable=True)
            if current["draft_revision"] != expected_revision:
                raise DraftRevisionConflict(
                    "This draft changed in another window. Reload before saving."
                )
            # Fetch dependencies under the same writer lock used by the guards.
            lead = cases.view(case_id)
            data["selected_explainers"] = list(dict.fromkeys(data["selected_explainers"]))
            prior = json.loads(current["draft"])
            defaults = hydrated_draft(lead, store.settings())
            # Report-family pages are immutable pinned bank revisions. Refresh
            # through deliberate presentation adoption, never client-edited JSON.
            expected_pages = defaults.get("report_explainer_snapshots", [])
            if data.get("report_explainer_snapshots") not in (None, [], expected_pages):
                raise ValueError(
                    "Report-type explanations are read-only. Adopt the current presentation to refresh them."
                )
            data["report_explainer_snapshots"] = expected_pages
            expected_findings = defaults.get("finding_explainer_snapshots", [])
            if data.get("finding_explainer_snapshots") not in (None, [], expected_findings):
                raise ValueError(
                    "Technical finding explanations are read-only. Adopt the current presentation to refresh them."
                )
            data["finding_explainer_snapshots"] = expected_findings
            # Old clients do not know the revision fields. Their omission must
            # not downgrade the report the analyst just loaded.
            for key in CURRENT_LAYOUTS:
                data.setdefault(key, defaults[key])
            # Wording revisions are server-owned. Switching generators is an
            # explicit presentation adoption and must pass the freeze guard.
            data["narrative_revision"] = defaults["narrative_revision"]
            data["addressee_revision"] = defaults["addressee_revision"]
            _pinned_fields(store, data, prior)
            if prior.get("template_revision") != approved.REVISION:
                db.execute(
                    "INSERT OR IGNORE INTO cache VALUES(?,?,?)",
                    ("pre-approved-template:" + lead["case_id"], dump(prior), now()),
                )
            approved.apply_template(lead, data, effective_settings(store.settings(), data))
            apply_layout_copy(data)
            apply_outreach_template(lead, data)
            group_keys = {g["key"] for g in narrative_groups(lead, data)}
            if not set(data["narrative_values"]) <= group_keys:
                raise ValueError("Narrative values must refer to this case’s findings")
            _source_records(db, lead, data, prior)
            _explainer_snapshots(db, data, prior)
            before = snapshot(
                store, lead_id, lead["case_id"], include_reviews=False, capture_sections=()
            )
            after = snapshot(
                store,
                lead_id,
                lead["case_id"],
                include_reviews=False,
                draft_override=data,
                capture_sections=(),
            )
            SectionReviewQueries(store).guard_draft(db, before, after, lead)
            # A source adoption requires a subsequent review; a bank refresh alone
            # never changes a case. Ordinary narrative edits remain analyst prose.
            sensitive = (
                "cve_records",
                "cve_dispositions",
                "selected_explainers",
                "explainer_snapshots",
                "explainer_overrides",
                "report_template",
                "narrative_values",
                "report_date",
                "selected_ssvc_assessments",
                "outreach_template",
            )
            defaults = hydrated_draft(lead, store.settings())
            changed = any(data[key] != defaults.get(key) for key in sensitive)
            if changed:
                data["reviewed"] = False
                store.log(
                    db,
                    "report_content_adopted",
                    "Adopted report sources, template, or reusable wording; review required",
                    lead_id,
                    lead["case_id"],
                )
            db.execute(
                "UPDATE cases SET draft=?,draft_revision=draft_revision+1,version=version+1,updated_at=? WHERE id=?",
                (dump(data), now(), lead["case_id"]),
            )
            project_legacy_draft(db, lead_id, data)
            store.log(db, "draft_saved", "Saved case report draft", lead_id, case_id)
        store.export_all()

    def adopt_presentation(self, case_id, expected_revision, reason):
        store, cases = self.store, self.cases
        with store.transaction() as db:
            case = cases.require(db, case_id, editable=True)
            check_revision(case, expected_revision)
            lead = cases.view(case_id)
            before = snapshot(
                store, case["entity_id"], case_id, include_reviews=False, capture_sections=()
            )
            draft = hydrated_draft(lead, store.settings())
            draft["document_policy"] = document_policy(store.settings())
            draft["sender_profile"] = capture_profile(store.settings())
            approved.apply_template(lead, draft, effective_settings(store.settings(), draft))
            adopt_current_layouts(draft)
            from ..report_explainers import select_report_explainers

            draft["report_explainer_snapshots"] = select_report_explainers(lead)
            from ..finding_explainers import select_finding_explainers

            draft["finding_explainer_snapshots"] = select_finding_explainers(lead)
            apply_outreach_template(lead, draft)
            after = snapshot(
                store,
                case["entity_id"],
                case_id,
                include_reviews=False,
                draft_override=draft,
                capture_sections=(),
            )
            SectionReviewQueries(store).guard_draft(db, before, after, lead)
            draft["reviewed"] = False
            db.execute(
                "UPDATE cases SET draft=?,draft_revision=draft_revision+1,version=version+1,updated_at=? WHERE id=?",
                (dump(draft), now(), case_id),
            )
            store.log(db, "document_presentation_adopted", reason, case["entity_id"], case_id)
        return case["entity_id"]
