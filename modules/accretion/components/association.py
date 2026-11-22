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
from .deconfliction import (
    AssociationEvidenceChanged,
    check as check_deconfliction,
    exact_host_entries,
    url_hostname,
)


@dataclass(frozen=True, slots=True)
class AssociationResult:
    """Published references; contact enrichment may still be queued."""

    report_id: str
    entity_id: str | None
    queue_id: str | None
    website_capture_id: str
    observations_added: int
    contact_work_queued: bool
    matches: tuple = ()

    def attempts(self):
        return [{"method": "associate", "status": item["action"], **item} for item in self.matches]


def _ineligible_reason(entry):
    return (entry.get("normalized", {}).get("eligibility") or {}).get(
        "reason"
    ) or "no_actionable_findings"


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
        from .awareness import actionable_scope

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
        matches, blocked = check_deconfliction(db, group.root_domain, entries, matched)
        scopes = lead.condition_scopes()
        excluded = blocked.intersection(scopes)
        if excluded:
            scopes = {idx: values for idx, values in scopes.items() if idx not in blocked}
            if not scopes:
                enqueue_outcomes(
                    db,
                    import_id,
                    [
                        (
                            entry,
                            "rejected",
                            "association_deconflicted"
                            if idx in blocked
                            else _ineligible_reason(entry),
                        )
                        for idx, entry in enumerate(entries)
                    ],
                    stage="associate",
                )
                return AssociationResult(
                    import_id, None, None, evidence["website"]["id"], 0, False, tuple(matches)
                )
            from .evaluation import evaluate_scope
            from .evaluated_lead import EvaluationScope
            from .intake.versions import project_conditions

            admitted_entries = [
                project_conditions(entries[idx], values) for idx, values in scopes.items()
            ]
            frontier_scope = preview_scope(
                db, import_id, group.root_domain, admitted_entries, entity_id=matched
            )
            intake_score = evaluate_scope(EvaluationScope(frontier_scope)).payload()
            active_cves = {
                v for e in frontier_scope["entries"] for v in e["normalized"]["active_cves"]
            }
            cve_records = [record for record in cve_records if record["id"] in active_cves]
        # A referral may have been added while the browser or registry was
        # running. Never attach its proof to a sibling merely sharing the root.
        website = evidence["website"]
        proof_hosts = {
            url_hostname(website["requested_url"]),
            url_hostname(website["final_url"]),
            str(attribution["attribution"].get("matched_domain") or "").casefold().rstrip("."),
        }
        referred_proof = next(exact_host_entries(db, proof_hosts), None)
        if referred_proof:
            raise AssociationEvidenceChanged(
                f"Evidence uses referred host {referred_proof['identifier']} "
                f"({referred_proof['external_reference']}). Retry to qualify the remaining sources."
            )
        if blocked:
            supported_hosts = {group.root_domain, "www." + group.root_domain}
            supported_hosts.update(
                entries[idx]["source"]["fields"]["hostname"].casefold().rstrip(".")
                for idx in scopes
            )
            if url_hostname(website["requested_url"]) not in supported_hosts:
                raise AssociationEvidenceChanged(
                    "The saved screenshot was requested for a different host. Retry to capture the remaining sources."
                )
            if not any(entries[idx]["ip"] == attribution["ip"] for idx in scopes):
                raise AssociationEvidenceChanged(
                    "The registration proof has no matching address in the remaining findings. "
                    "Retry to qualify the remaining sources."
                )
        imported = db.execute("SELECT * FROM imports WHERE id=?", (import_id,)).fetchone()
        if imported is None or Report.from_record(imported) != lead.report:
            raise ValueError("Evaluated lead does not match the retained report")
        source_hash = lead.report.sha256
        retained_entries = [entry for idx, entry in enumerate(entries) if idx not in blocked]
        if blocked:
            hosts = {
                entry["source"]["fields"]["hostname"].casefold().rstrip(".")
                for entry in retained_entries
            }
            attribution = {
                **attribution,
                "coverage": [row for row in attribution["coverage"] if row["hostname"] in hosts],
            }
        entity_id, inserted = record_group(
            db,
            group.root_domain,
            retained_entries,
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
        dispositions = []
        for index, entry in enumerate(entries):
            if index in blocked:
                dispositions.append((entry, "rejected", "association_deconflicted"))
                continue
            allowed = None if demo else scopes.get(index, ())
            reason = "qualified" if demo or allowed else _ineligible_reason(entry)
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
        import_id,
        entity_id,
        queue_reference,
        evidence["website"]["id"],
        inserted,
        contact_queued,
        tuple(matches),
    )
