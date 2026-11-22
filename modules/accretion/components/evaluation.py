"""Evaluate already-qualified pending work; queue persistence never scores."""

import json

from . import accretion
from .evaluated_lead import EvaluationScope, UrgencyAssessment, EvaluatedLead
from .qualified_lead import QualifiedLead
from .report import Report
from .intake.records import observation_payload
from .intake.versions import entry_fields
from modules.library.components.cve_sources import verify
from modules.library.components.intelligence.identifiers import identifiers

VERSION = 3


def evaluate_scope(scope: EvaluationScope) -> UrgencyAssessment:
    """Rank the exact pending condition projection selected by Leads."""
    if not isinstance(scope, EvaluationScope):
        raise TypeError("Evaluate requires an EvaluationScope")
    inputs = scope.inputs()
    winner = inputs["winner"]
    previous = json.loads(winner.get("intake_score") or "{}")
    evaluation = previous.get("evaluation_scope", {})
    if evaluation.get("version") == VERSION and evaluation.get("fingerprint") == scope.fingerprint:
        return UrgencyAssessment(scope, previous)
    score = accretion.score_lead(
        inputs["entries"],
        root_domain=winner["root_domain"],
        association=(winner["entity_id"], "known", "qualified", []),
        policy=inputs["policy"],
        as_of=inputs["as_of"],
    )
    score["evaluation_scope"] = {"version": VERSION, "fingerprint": scope.fingerprint}
    return UrgencyAssessment(scope, score)


def evaluate_pending(db, lead_id):
    """Re-evaluate explicit edits to qualified work before updating its queue."""
    from modules.leads.components.lead_frontier import preview_current, reconcile

    scope = preview_current(db, lead_id)
    score = evaluate_scope(EvaluationScope(scope)).payload() if scope and scope["entries"] else None
    return reconcile(db, lead_id, scope=scope, score=score)


def evaluate_lead(
    store, lead: QualifiedLead, *, checkpoint, config=None, cve_cache=None
) -> EvaluatedLead:
    """Rank qualified pending scope and resolve its local report references."""
    from .intake_progress import publish
    from modules.leads.components.lead_frontier import preview_scope
    from modules.entities.components.ownership import check_qualification_context
    from modules.investigations.components.website_evidence import get

    checkpoint()
    if not isinstance(lead, QualifiedLead):
        raise TypeError("Evaluate requires a QualifiedLead")
    lead.validate()
    evidence = lead.evidence()
    import_id = lead.report.id
    get(store, evidence["website"]["id"])
    group = lead.group
    imported = store.one("SELECT * FROM imports WHERE id=?", (import_id,))
    if not imported or Report.from_record(imported) != lead.report:
        raise ValueError("Qualified lead does not match the retained report")
    # The active worker owns its progress. A review/reconciliation of a
    # queued, paused, failed or running import must not overwrite that
    # lifecycle's stage or diagnostics while ranking one accepted group.
    show_progress = config is not None or imported["status"] == "done"
    if config is None:
        config = json.loads(imported["config"])
    original_entries = [observation_payload(entry) for entry in group.observations]
    # Evaluate only the actionable scope produced by Qualify. Supporting
    # rows and already handled conditions remain source evidence.
    entries = lead.actionable_entries()
    with store.read_snapshot() as db:
        owner, state, _, _ = check_qualification_context(
            db, group.root_domain, original_entries, evidence["ownership_token"]
        )
        if state == "review":
            raise ValueError("Review the ownership association before ranking this group")
        scope = preview_scope(db, import_id, group.root_domain, entries, entity_id=owner)
        if not scope["entries"]:
            raise ValueError("No actionable findings remain for Evaluate")
    if show_progress:
        publish(store, import_id, config, "evaluate", "Evaluating qualified leads")
    assessment = evaluate_scope(EvaluationScope(scope))
    cache = cve_cache if cve_cache is not None else {}
    records = []
    for cve_id in identifiers(entry_fields(entry).get("tag", "") for entry in scope["entries"]):
        if cve_id not in cache:
            cache[cve_id] = verify(store, cve_id, local_only=True)
        records.append(cache[cve_id])
    if show_progress:
        publish(store, import_id, config, "associate", "Associating qualified findings")
    checkpoint()
    return EvaluatedLead(lead, assessment, records)
