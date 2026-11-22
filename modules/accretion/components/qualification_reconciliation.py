"""Apply established attribution to waiting reviews without inventing decisions.

The original source and lookup result remain evidence. Only the work queue and
admission projection change; an explicit rejection or requested refresh is never
overridden by this reconciliation.
"""

from __future__ import annotations

from contextlib import nullcontext
import json
import logging

from attribution import EvidenceStore

from modules.attribution.components.attribution_bridge import checked_result, domain_identity
from modules.attribution.components.attribution_reuse import reuse_attribution, reuse_review
from .qualification import complete_lead, local_scope
from .report import Report, ReportCandidate
from .intake.records import observation_payload
from modules.workspace.components.primitives import dump, now

LOG = logging.getLogger(__name__)


def _paused(intake):
    maintenance = getattr(intake.store, "maintenance", None)
    return intake.stop_event.is_set() or bool(maintenance and maintenance.is_set())


def refresh_import_summary(db, import_id, *, exports_pending=False):
    """Refresh queue-derived counts without changing the import lifecycle."""
    imported = db.execute("SELECT * FROM imports WHERE id=?", (import_id,)).fetchone()
    counts = db.execute(
        "SELECT count(*) total,COALESCE(sum(status!='pending'),0) done,"
        "COALESCE(sum(status='qualified'),0) qualified,"
        "COALESCE(sum(status='pending'),0) pending,COALESCE(sum(status='review'),0) review,"
        "COALESCE(sum(status='deferred'),0) deferred,"
        "COALESCE(sum(status='qualified' AND EXISTS(SELECT 1 FROM json_each(jobs.attempts) "
        "WHERE json_extract(value,'$.reason') IN "
        "('established_group_reused','approved_registrant_reused','established_review_reconciled'))),0) reused "
        "FROM jobs WHERE import_id=?",
        (import_id,),
    ).fetchone()
    config = json.loads(imported["config"])
    config.setdefault("intake_progress", {}).update(
        associated_groups=counts["qualified"], reused_groups=counts["reused"], updated_at=now()
    )
    if exports_pending:
        config["intake_progress"]["exports_pending"] = True
    message = imported["message"]
    stage = imported["stage"]
    if imported["status"] not in {"running", "error", "paused"}:
        waiting = counts["pending"] or counts["review"] or counts["deferred"]
        message = (
            f"{counts['pending']} groups queued; {counts['review']} awaiting review; {counts['deferred']} need a retry"
            if waiting
            else "All groups processed"
        )
        if imported["status"] == "done":
            stage = "Qualification needs attention" if waiting else "Finished"
            config["intake_progress"].update(
                phase="qualify" if waiting else "complete", detail=stage
            )
    db.execute(
        "UPDATE imports SET groups_done=?,qualified=?,config=?,message=?,stage=? WHERE id=?",
        (counts["done"], counts["qualified"], dump(config), message, stage, import_id),
    )


def reconcile_reviews(intake, root_domain, *, evidence_store=None):
    """Promote waiting siblings only when saved evidence supports reuse.

    Call after the initiating analyst decision commits. Attribution owns proof
    validation and group coverage; this function applies complete qualification
    evidence only to jobs already waiting before that decision.
    """

    root = domain_identity(root_domain)
    if not root:
        return []
    store = intake.store
    # Existing roots preserve their original spelling. This expression matches
    # jobs_domain_status so each approval reads only that domain's waiting work.
    waiting = [
        row
        for row in store.all(
            "SELECT * FROM jobs WHERE lower(domain)=? AND status='review' ORDER BY rowid", (root,)
        )
        if not row["refresh_requested"]
        and not any(
            attempt.get("reason") == "explicit_attribution_refresh"
            for attempt in json.loads(row["attempts"])
        )
    ]
    if not waiting:
        return []
    promoted, cves = [], {}
    context = (
        nullcontext(evidence_store)
        if evidence_store is not None
        else EvidenceStore(store.root / "attribution.sqlite3")
    )
    with context as evidence:
        for job in waiting:
            if _paused(intake):
                break
            try:
                payload = json.loads(job["payload"])
                if not payload:
                    continue
                report = Report.from_record(
                    store.one("SELECT * FROM imports WHERE id=?", (job["import_id"],))
                )
                candidate = ReportCandidate.restore(report, job["domain"], payload)
                group = candidate.group
                recognition, findings, reason = local_scope(store, group)
                if reason or recognition["state"] != "known":
                    continue
                inherited = reuse_review(store, group, evidence, job["attribution_result_id"])
                if inherited is None:
                    inherited = reuse_attribution(
                        store,
                        group,
                        evidence,
                        entity_id=recognition["entity_id"],
                        saved_proof=recognition["saved_proof"],
                    )
                    if inherited is None:
                        continue
                    original = checked_result(evidence, job["attribution_result_id"], job["domain"])
                    proof = inherited.proof
                    if original["status"] != "review" or not (
                        job["attribution_result_id"] == proof.get("result_id")
                        or any(
                            p.get("snapshot_id") == proof.get("snapshot_id")
                            and p.get("ip") == proof.get("ip")
                            for p in original.get("partial_evidence", [])
                        )
                    ):
                        continue
                proof = inherited.proof
                saved = json.loads(job["qualification"])
                saved["findings"] = list(findings)
                saved["ownership_token"] = recognition["ownership_token"]
                lead = complete_lead(store, candidate, proof, inherited.coverage, saved)
                evaluated = intake.evaluate_lead(lead, cve_cache=cves)
            except (ValueError, KeyError, TypeError, IndexError, AttributeError) as error:
                # An incomplete/corrupt historical proof stays reviewable; it
                # must not undo a separate analyst decision already committed.
                LOG.warning("Attribution review %s could not be reconciled: %s", job["id"], error)
                continue
            with store.transaction() as db:
                from modules.entities.components.ownership import association

                current = db.execute("SELECT * FROM jobs WHERE id=?", (job["id"],)).fetchone()
                if (
                    not current
                    or current["status"] != "review"
                    or current["refresh_requested"]
                    or current["attribution_result_id"] != job["attribution_result_id"]
                    or current["payload"] != job["payload"]
                ):
                    continue
                owner, state, _, _ = association(
                    db,
                    group.root_domain,
                    [observation_payload(entry) for entry in group.observations],
                )
                if state != "known" or owner != recognition["entity_id"]:
                    continue
                from modules.entities.components.ownership import OwnershipChanged

                try:
                    lead_id = intake.associate_lead(evaluated, db=db).entity_id
                except OwnershipChanged:
                    continue
                attempts = json.loads(job["attempts"])
                if job["attribution_result_id"] and not any(
                    attempt.get("result_id") == job["attribution_result_id"] for attempt in attempts
                ):
                    # Export/restore follows result_id references in attempts,
                    # even for older jobs whose provider attempt list is empty.
                    attempts.append(
                        {
                            "method": "history",
                            "status": "retained",
                            "reason": "original_review_retained",
                            "result_id": job["attribution_result_id"],
                        }
                    )
                attempts.append(
                    {
                        "method": "history",
                        "status": "matched",
                        "reason": "established_review_reconciled",
                        "message": "Applied an established attribution decision to this waiting review.",
                        "reconciled_at": now(),
                        "result_id": proof.get("result_id"),
                        "previous_result_id": job["attribution_result_id"],
                        **(
                            {"source_result_id": proof["approval_reuse"]["source_result_id"]}
                            if proof.get("approval_reuse")
                            else {}
                        ),
                        "ip": proof["ip"],
                    }
                )
                db.execute(
                    "UPDATE jobs SET status='qualified',attempts=?,attribution_result_id=?,qualification=?,error='' WHERE id=?",
                    (dump(attempts), proof.get("result_id"), dump(lead.evidence()), job["id"]),
                )
                refresh_import_summary(db, job["import_id"], exports_pending=True)
                store.log(
                    db,
                    "attribution_reused",
                    f"Applied established attribution for {job['domain']} to waiting review {job['id']}; original result {job['attribution_result_id']} retained",
                    lead_id,
                )
            promoted.append(job["id"])
    return promoted


def reconcile_backlog(intake):
    """Resume waiting reviews using saved proof after startup or interruption."""
    if _paused(intake):
        return []
    roots = intake.store.all(
        "SELECT DISTINCT lower(domain) root FROM jobs WHERE status='review' ORDER BY root"
    )
    if not roots:
        return []
    promoted = []
    with EvidenceStore(intake.store.root / "attribution.sqlite3") as evidence:
        for row in roots:
            if _paused(intake):
                break
            promoted.extend(reconcile_reviews(intake, row["root"], evidence_store=evidence))
    if promoted:
        intake.export_pending()
    return promoted
