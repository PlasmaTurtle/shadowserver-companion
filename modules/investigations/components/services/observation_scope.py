"""Atomic, reasoned recipient-scope edits without mutating source observations."""

from copy import deepcopy

from ..cases import Cases
from modules.library.components.intelligence.identifiers import identifiers
from modules.accretion.components.intake.versions import entry_fields
from ..observation_scope import address_issue, apply_scope
from modules.workspace.components.primitives import dump, now
from ..report_drafts import hydrated_draft, narrative_groups
from ..report_snapshot import snapshot
from ..repositories.reviews import SectionReviewRepository
from ..reviews.policy import fingerprints
from .compatibility import project_legacy_draft


def _scoped_draft(lead, draft, settings):
    """Move out-of-scope selections to an internal archive; restore exact pins."""
    archive = deepcopy(draft.get("observation_scope_archive", {}))
    cves = set(identifiers(entry_fields(entry).get("tag", "") for entry in lead["entries"]))
    records = archive.setdefault("cve_records", {})
    records.update({record["id"]: deepcopy(record) for record in draft.get("cve_records", [])})
    draft["cve_records"] = [deepcopy(record) for key, record in records.items() if key in cves]
    for field in ("cve_dispositions", "selected_ssvc_assessments"):
        saved = archive.setdefault(field, {})
        saved.update(deepcopy(draft.get(field, {})))
        draft[field] = {key: deepcopy(value) for key, value in saved.items() if key in cves}
    from ..report_explainers import select_report_explainers
    from ..finding_explainers import select_finding_explainers

    for field, selected in (
        ("report_explainer_snapshots", select_report_explainers(lead)),
        (
            "finding_explainer_snapshots",
            select_finding_explainers(lead, draft["finding_explainer_revision"]),
        ),
    ):
        saved = archive.setdefault(field, {})
        saved.update({item["id"]: deepcopy(item) for item in draft.get(field, [])})
        draft[field] = [deepcopy(saved.get(item["id"], item)) for item in selected]
    values = archive.setdefault("narrative_values", {})
    values.update(deepcopy(draft.get("narrative_values", {})))
    keys = {group["key"] for group in narrative_groups(lead, draft)}
    draft["narrative_values"] = {
        key: deepcopy(value) for key, value in values.items() if key in keys
    }
    draft["observation_scope_archive"] = archive
    draft["reviewed"] = False
    draft["cve_reviewed"] = False
    lead["draft"] = draft
    return hydrated_draft(lead, settings)


class ObservationScopeService:
    def __init__(self, store):
        self.store = store
        self.cases = Cases(store)

    def update(self, case_id, values):
        store = self.store
        reason = values["reason"].strip()
        if not reason:
            raise ValueError(
                "Explain why these observations belong in or outside this notification"
            )
        with store.transaction() as db:
            case = self.cases.require(db, case_id, values["expected_version"], editable=True)
            if case["draft_revision"] != values["expected_revision"]:
                raise ValueError("This draft changed. Reload before changing observation scope.")
            actor = store.settings().get("analyst_name", "").strip()
            if not actor:
                raise ValueError("Set your analyst name before changing observation scope")
            lead = self.cases.repository.view(case_id, db)
            entries = {entry["id"]: entry for entry in lead["scope_source_entries"]}
            selected = list(dict.fromkeys(values["entry_ids"]))
            if not selected or not set(selected) <= entries.keys():
                raise ValueError("Select observations belonging to this notification")
            if values["decision"] == "include" and any(
                address_issue(entries[key]) for key in selected
            ):
                raise ValueError(
                    "Nonpublic or invalid IP observations must stay out of a public-scan notification. Preserve them internally by excluding them with a reason."
                )
            draft = hydrated_draft(lead, store.settings())
            before = snapshot(
                store, case["entity_id"], case_id, include_reviews=False, capture_sections=()
            )
            decisions = deepcopy(draft.get("observation_scope", {}))
            stamp = now()
            for key in selected:
                decisions[key] = {
                    "decision": values["decision"],
                    "reason": reason,
                    "actor": actor,
                    "decided_at": stamp,
                }
            draft["observation_scope"] = decisions
            changed = apply_scope(deepcopy(lead), draft)
            draft = _scoped_draft(changed, draft, store.settings())
            after = snapshot(
                store,
                case["entity_id"],
                case_id,
                include_reviews=False,
                draft_override=draft,
                capture_sections=(),
            )
            old_hashes, new_hashes = fingerprints(before, lead), fingerprints(after, changed)
            reviews = SectionReviewRepository(store)
            frozen = reviews.active(case_id, db)
            affected = [
                key
                for key in frozen
                if old_hashes[key]["content_hash"] != new_hashes[key]["content_hash"]
            ]
            if affected and not values.get("reopen_affected", False):
                raise ValueError(
                    "Changing this scope requires reopening "
                    + ", ".join(key.title() for key in affected)
                    + ". Confirm reopening affected sections with your scope reason."
                )
            for key in affected:
                reviews.event(
                    db,
                    case_id,
                    key,
                    "reopened",
                    actor,
                    "Observation scope: " + reason,
                    frozen[key]["revision"],
                )
            db.execute(
                "UPDATE cases SET draft=?,draft_revision=draft_revision+1,version=version+1,updated_at=? WHERE id=?",
                (dump(draft), stamp, case_id),
            )
            project_legacy_draft(db, case["entity_id"], draft)
            store.log(
                db,
                "observation_scope_changed",
                dump(
                    {
                        "decision": values["decision"],
                        "entry_ids": selected,
                        "reason": reason,
                        "actor": actor,
                        "reopened_sections": affected,
                    }
                ),
                case["entity_id"],
                case_id,
            )
        store.export_all()
        return affected
