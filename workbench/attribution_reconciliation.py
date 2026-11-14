"""Apply established attribution to waiting reviews without inventing decisions.

The original source and lookup result remain evidence. Only the work queue and
admission projection change; an explicit rejection or requested refresh is never
overridden by this reconciliation.
"""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import asdict
import json
import logging

from attribution import EvidenceStore

from .attribution_bridge import checked_result, domain_identity
from .cve_sources import verify
from .intake import ValidatedLeads, restore_entry
from .intelligence.identifiers import identifiers
from .primitives import dump, now

LOG = logging.getLogger(__name__)


def _paused(intake):
    maintenance = getattr(intake.store, "maintenance", None)
    return intake.stop_event.is_set() or bool(maintenance and maintenance.is_set())


def refresh_import_summary(db, import_id):
    """Refresh queue-derived counts without changing the import lifecycle."""
    imported = db.execute("SELECT * FROM imports WHERE id=?", (import_id,)).fetchone()
    counts = db.execute(
        "SELECT count(*) total,COALESCE(sum(status!='pending'),0) done,"
        "COALESCE(sum(status='qualified'),0) qualified,"
        "COALESCE(sum(status='pending'),0) pending,COALESCE(sum(status='review'),0) review,"
        "COALESCE(sum(status='deferred'),0) deferred,"
        "COALESCE(sum(status='qualified' AND EXISTS(SELECT 1 FROM json_each(jobs.attempts) "
        "WHERE json_extract(value,'$.reason') IN "
        "('established_endpoint_reused','approved_registrant_reused','established_review_reconciled'))),0) reused "
        "FROM jobs WHERE import_id=?",
        (import_id,),
    ).fetchone()
    config = json.loads(imported["config"])
    config.setdefault("intake_progress", {}).update(
        associated_groups=counts["done"], reused_groups=counts["reused"], updated_at=now()
    )
    message = imported["message"]
    if imported["status"] not in {"running", "error", "paused"}:
        message = (
            f"{counts['pending']} groups queued; {counts['review']} awaiting review; {counts['deferred']} need a retry"
            if counts["pending"] or counts["review"] or counts["deferred"]
            else "All groups processed"
        )
    db.execute(
        "UPDATE imports SET groups_done=?,qualified=?,config=?,message=? WHERE id=?",
        (counts["done"], counts["qualified"], dump(config), message, import_id),
    )


def reconcile_reviews(intake, root_domain, *, evidence_store=None):
    """Promote waiting siblings only when saved evidence supports reuse.

    Call after the initiating analyst decision commits. The intake recognizer
    owns the reuse policy, including identity and endpoint checks; this function
    only reconciles jobs that were already waiting before that decision.
    """
    from .attribution_approval import reusable_review
    from .intake_reuse import recognize_group

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
            group = ValidatedLeads(
                job["domain"], [restore_entry(entry) for entry in json.loads(job["payload"])]
            )
            if not group.entries:
                continue
            try:
                recognition = recognize_group(store, group, evidence_store=evidence)
                if recognition["state"] != "known":
                    continue
                # The waiting job may contain conflicting new registration
                # evidence even when this exact endpoint was approved before.
                # Examine its own saved partial first; known ownership alone is
                # insufficient to discard such a conflict.
                inherited = reusable_review(store, group, evidence, job["attribution_result_id"])
                if inherited is not None:
                    proof, anchor = inherited
                else:
                    proof = recognition["attribution"]
                    anchor = recognition.get("anchor_index")
                    if proof is None:
                        continue
                    original_result = checked_result(
                        evidence, job["attribution_result_id"], job["domain"]
                    )
                    if original_result["status"] != "review" or not (
                        job["attribution_result_id"] == proof.get("result_id")
                        or any(
                            partial.get("snapshot_id") == proof.get("snapshot_id")
                            and partial.get("ip") == proof.get("ip")
                            for partial in original_result.get("partial_evidence", [])
                        )
                    ):
                        continue
                group.entries.insert(0, group.entries.pop(anchor))
                records = []
                for cve_id in identifiers(
                    entry.source.fields.get("tag", "") for entry in group.entries
                ):
                    if cve_id not in cves:
                        cves[cve_id] = verify(store, cve_id, local_only=True)
                    records.append(cves[cve_id])
            except (ValueError, KeyError, TypeError, IndexError, AttributeError) as error:
                # An incomplete/corrupt historical proof stays reviewable; it
                # must not undo a separate analyst decision already committed.
                LOG.warning("Attribution review %s could not be reconciled: %s", job["id"], error)
                continue
            with store.transaction() as db:
                from .lead_queue import association

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
                    db, group.hostname, [asdict(entry) for entry in group.entries]
                )
                if state != "known" or owner != recognition["entity_id"]:
                    continue
                lead_id = intake.accept_group(
                    job["import_id"], group, proof, cve_records=records, db=db
                )
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
                    "UPDATE jobs SET status='qualified',attempts=?,attribution_result_id=?,error='' WHERE id=?",
                    (dump(attempts), proof.get("result_id"), job["id"]),
                )
                refresh_import_summary(db, job["import_id"])
                store.log(
                    db,
                    "attribution_reused",
                    f"Applied established attribution for {job['domain']} to waiting review {job['id']}; original result {job['attribution_result_id']} retained",
                    lead_id,
                )
            promoted.append(job["id"])
    return promoted


def reconcile_backlog(intake):
    """Repair outstanding duplicates from earlier releases using saved proof."""
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
        intake.store.export_all()
    return promoted
