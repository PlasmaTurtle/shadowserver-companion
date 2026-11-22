"""Authoritative reuse of an existing attribution for a related source group."""

from copy import deepcopy
from datetime import datetime, timezone
import json

from .attribution_approval import approved_proofs, reusable_review, _canonical_owner
from .attribution_approval_evidence import checked_proof, valid_approval_reuse
from .attribution_bridge import (
    AttributionDecision,
    EvidenceReader,
    checked_result,
    group_coverage,
    same_domain,
)

ASSOCIATION_REUSE_SECONDS = 7 * 86400


def _recorded_approval(store, proof, root, entity_id, evidence_store):
    review = proof.get("review") or {}
    if review.get("decision") != "accept" or review.get("result_id") != proof.get("result_id"):
        return False
    result = checked_result(evidence_store, proof["result_id"], root)
    index = review.get("evidence_index")
    if (
        result.get("status") != "review"
        or type(index) is not int
        or not 0 <= index < len(result.get("partial_evidence", []))
        or result["partial_evidence"][index] != proof.get("evidence")
    ):
        return False
    with store.read_snapshot() as db:
        row = db.execute(
            "SELECT r.*,j.domain,j.payload FROM attribution_reviews r JOIN jobs j ON j.id=r.job_id "
            "WHERE r.id=?",
            (review.get("id"),),
        ).fetchone()
        if not row:
            return False
        entries = json.loads(row["payload"])
        anchor = int(proof["evidence"]["details"]["entry_id"])
        if (
            not isinstance(entries, list)
            or not 0 <= anchor < len(entries)
            or entries[anchor]["ip"] != proof["ip"]
            or not any(
                candidate.get("entry_id") == str(anchor) and candidate.get("ip") == proof["ip"]
                for candidate in result.get("candidates", [])
            )
        ):
            return False
        return bool(
            same_domain(row["domain"], root)
            and _canonical_owner(db, row["lead_id"]) == entity_id
            and all(
                row[key] == review.get(key)
                for key in (
                    "id",
                    "result_id",
                    "evidence_index",
                    "decision",
                    "reviewer",
                    "note",
                    "reviewed_at",
                )
            )
        )


def reusable_proof(store, proof, root, evidence_store, entity_id, *, clock=None):
    """Check exact evidence and current approval before applying its group rule.

    Embedded registration strings are insufficient. Automatic proof expires;
    an actual recorded analyst identity approval remains valid until withdrawn.
    """
    if not proof or not evidence_store or not entity_id:
        return False
    try:
        if not checked_proof(proof, root, evidence_store):
            return False
        if proof.get("approval_reuse"):
            return valid_approval_reuse(proof, root, evidence_store) and _recorded_approval(
                store, proof["approval_reuse"]["source_proof"], root, entity_id, evidence_store
            )
        result = checked_result(evidence_store, proof["result_id"], root)
        if result["status"] == "review":
            return _recorded_approval(store, proof, root, entity_id, evidence_store)
        current = clock or datetime.now(timezone.utc)
        stamp = datetime.fromisoformat(proof["evaluated_at"].replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return False
        age = (current - stamp.astimezone(timezone.utc)).total_seconds()
        return 0 <= age <= ASSOCIATION_REUSE_SECONDS
    except (KeyError, ValueError, TypeError, AttributeError, IndexError):
        return False


def reuse_attribution(
    store, group, evidence_store, *, entity_id, saved_proof=None, refresh=False, clock=None
):
    """Return one explicit group decision without performing network requests.

    The caller checks mutable ownership before this call and again at commit.
    Saved proof is tried before enumerating older analyst approvals. Immutable
    evidence reads are shared within this operation, while live reviews are not.
    """
    if refresh or not entity_id or evidence_store is None:
        return None
    evidence = (
        evidence_store
        if isinstance(evidence_store, EvidenceReader)
        else EvidenceReader(evidence_store)
    )
    current = clock or datetime.now(timezone.utc)

    def candidates():
        if saved_proof:
            yield saved_proof
        yield from approved_proofs(store, group.root_domain, evidence, entity_id)

    seen = set()
    for candidate in candidates():
        key = (candidate.get("result_id"), candidate.get("snapshot_id"), candidate.get("ip"))
        if key in seen:
            continue
        seen.add(key)
        if not reusable_proof(
            store, candidate, group.root_domain, evidence, entity_id, clock=current
        ):
            continue
        proof = deepcopy(candidate)
        manual = (proof.get("review") or {}).get("decision") == "accept"
        proof["reuse"] = {
            "basis": "Recorded domain attribution covers this related hostname/root group",
            "recognized_at": current.isoformat(),
            "source_evaluated_at": proof["evaluated_at"],
            "maximum_age_seconds": None if manual else ASSOCIATION_REUSE_SECONDS,
            "fresh_lookup": False,
        }
        coverage = group_coverage(group, proof)
        return AttributionDecision(
            "qualified",
            proof,
            proof["result_id"],
            (
                {
                    "method": "history",
                    "status": "matched",
                    "reason": "established_group_reused",
                    "message": proof["reuse"]["basis"],
                    "result_id": proof["result_id"],
                    "ip": proof["ip"],
                },
            ),
            coverage,
        )
    return None


def reuse_review(store, group, evidence_store, result_id):
    """Apply a real prior registrant approval to compatible new partial evidence."""
    evidence = (
        evidence_store
        if isinstance(evidence_store, EvidenceReader)
        else EvidenceReader(evidence_store)
    )
    inherited = reusable_review(store, group, evidence, result_id)
    if inherited is None:
        return None
    proof, _ = inherited
    return AttributionDecision(
        "qualified",
        proof,
        result_id,
        (
            {
                "method": "history",
                "status": "matched",
                "reason": "approved_registrant_reused",
                "message": "Applied the recorded approval for this registrant to its new evidence",
                "result_id": result_id,
                "source_result_id": proof["approval_reuse"]["source_result_id"],
                "ip": proof["ip"],
            },
        ),
        group_coverage(group, proof),
    )
