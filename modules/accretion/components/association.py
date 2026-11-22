"""Associate an evaluated qualified lead through its owners, atomically.

This stage never qualifies or scores. Network enrichment is durable background
work; ownership and evaluated scope are checked before any publication writes.
"""

from contextlib import nullcontext
from dataclasses import dataclass

from modules.entities.components.repositories.association import record_group
from modules.entities.components.contact_queue import queue_initial
from modules.workspace.components.primitives import dump, now
from .dark_matter import enqueue_outcomes
from .intake.records import observation_payload
from .evaluated_lead import EvaluatedLead
from .report import Report


@dataclass(frozen=True, slots=True)
class AssociationResult:
    """Published references; contact enrichment may still be queued."""

    report_id: str
    entity_id: str
    queue_id: str
    website_capture_id: str
    observations_added: int
    contact_work_queued: bool


def associate_lead(store, evaluated: EvaluatedLead, *, db=None) -> AssociationResult:
    if not isinstance(evaluated, EvaluatedLead):
        raise TypeError("Associate requires an EvaluatedLead")
    evaluated.validate()
    lead = evaluated.lead
    evidence = lead.evidence()
    import_id = lead.report.id
    demo = lead.is_demonstration
    group, attribution = lead.group, {**evidence["attribution"], "coverage": evidence["coverage"]}
    intake_score = evaluated.assessment.payload()
    cve_records = evaluated.cve_records
    entries = [observation_payload(entry) for entry in group.observations]
    with store.transaction() if db is None else nullcontext(db) as db:
        from modules.entities.components.ownership import check_qualification_context
        from modules.leads.components.lead_queue import register_group
        from modules.leads.helpers.queue_identity import queue_id

        pending_id = queue_id(import_id, group.root_domain)
        pending = db.execute("SELECT * FROM lead_queue WHERE id=?", (pending_id,)).fetchone()
        # Evaluate's read snapshot cannot authorize later writes. Resolve
        # ownership again inside the association transaction, then persist
        # only the final qualified queue row after its evidence exists.
        association_context = check_qualification_context(
            db, group.root_domain, entries, evidence["ownership_token"]
        )
        matched, state, _, _ = association_context
        if state == "review" or (pending and pending["association_state"] == "review"):
            raise ValueError(
                "Review the ownership association and observation dates before qualifying this group"
            )
        from modules.investigations.components.outreach_policy import entity_hold
        from .awareness import actionable_scope

        if entity_hold(db, matched):
            raise ValueError("Outreach was held while this group was qualifying")
        if not demo and not actionable_scope(db, entries, entity_id=matched):
            raise ValueError("No actionable findings remain for this group")
        from modules.leads.components.lead_frontier import preview_scope

        admitted_entries = lead.actionable_entries()
        frontier_scope = preview_scope(
            db, import_id, group.root_domain, admitted_entries, entity_id=matched
        )
        if (
            intake_score.get("evaluation_scope", {}).get("fingerprint")
            != frontier_scope["fingerprint"]
        ):
            raise ValueError("Pending work changed after Evaluate; retry this qualified group")
        imported = db.execute("SELECT * FROM imports WHERE id=?", (import_id,)).fetchone()
        if imported is None or Report.from_record(imported) != lead.report:
            raise ValueError("Evaluated lead does not match the retained report")
        source_hash = lead.report.sha256
        entity_id, inserted = record_group(
            db,
            group.root_domain,
            entries,
            attribution,
            import_id=import_id,
            source_hash=source_hash,
            owner=pending["entity_id"] if pending else matched,
            owner_state=pending["association_state"] if pending else state,
            cve_records=cve_records,
            demo=demo,
        )
        if inserted:
            store.log(db, "observations", f"{inserted} observations added", entity_id)
        from modules.entities.components.registry_profile import seed_entity

        populated = seed_entity(db, entity_id, attribution)
        if populated:
            store.log(
                db,
                "entity_registry_details",
                "Populated matched registration fields: " + ", ".join(populated),
                entity_id,
            )
        contact_queued = not demo and queue_initial(db, entity_id, group.root_domain)
        from modules.investigations.components.website_evidence import bind

        bind(db, evidence["website"]["id"], entity_id, root_domain=group.root_domain)
        # Qualification records findings; notification scope is an explicit action.
        # Associate commits event/finding membership after filtering, local
        # risk evaluation and attribution. Raw imports and old case scopes
        # remain immutable; recurring events add history without new work.
        from .awareness import associate

        review = attribution.get("review") or {}
        admission_authority = {
            "authority_kind": "analyst_qualification" if review else "intake_qualification",
            "authority_ref": str(review.get("id") or attribution.get("result_id") or pending_id),
            "actor": str(review.get("reviewer") or "intake_pipeline"),
            "evidence_ref": dump(
                {
                    "attribution_result_id": attribution.get("result_id"),
                    "review_id": review.get("id"),
                    "qualified_queue_id": pending_id,
                    "website_capture_id": evidence["website"]["id"],
                    "qualification_version": 1,
                }
            ),
        }
        scopes = lead.condition_scopes()
        dispositions = []
        for index, entry in enumerate(entries):
            allowed = None if demo else scopes.get(index, ())
            reason = (
                "qualified"
                if demo or allowed
                else (
                    (entry.get("normalized", {}).get("eligibility") or {}).get("reason")
                    or "no_actionable_findings"
                )
            )
            associate(
                db,
                entry,
                import_id=import_id,
                source_sha256=source_hash,
                entity_id=entity_id,
                admitted=True,
                admitted_conditions=allowed,
                reason=reason,
                admission_authority=admission_authority,
                fallback=now(),
            )
            dispositions.append((entry, "promoted" if demo or allowed else "rejected", reason))
        queue_reference = register_group(
            db,
            import_id,
            group.root_domain,
            admitted_entries,
            entity_id=entity_id,
            qualified=True,
            intake_score=intake_score,
            association_context=association_context,
            frontier_scope=frontier_scope,
        )
        enqueue_outcomes(db, import_id, dispositions, stage="associate")
    return AssociationResult(
        import_id, entity_id, queue_reference, evidence["website"]["id"], inserted, contact_queued
    )
