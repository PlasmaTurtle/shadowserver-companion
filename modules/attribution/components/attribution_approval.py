"""Reuse recorded domain-to-registrant decisions for established entities.

Ownership and recorded analyst actions live here; evidence-only validation is
kept independent so frozen report rendering never imports intake services.
"""

from copy import deepcopy
from dataclasses import asdict
import json

from .attribution_bridge import attribution_record, checked_result, domain_identity
from .attribution_approval_evidence import (
    checked_proof,
    _identity,
    snapshot_approval_matches as snapshot_approval_matches,
    valid_approval_reuse as valid_approval_reuse,
)
from modules.workspace.components.primitives import now


def _canonical_owner(db, entity_id):
    visited = set()
    while entity_id and entity_id not in visited:
        visited.add(entity_id)
        entity = db.execute("SELECT id,merged_into FROM leads WHERE id=?", (entity_id,)).fetchone()
        if not entity:
            return None
        if not entity["merged_into"]:
            return entity["id"]
        entity_id = entity["merged_into"]
    return None


def approved_proofs(store, root, evidence_store, entity_id):
    """Yield original accepted proofs for this domain's current entity only."""
    identity = domain_identity(root)
    if not identity or not entity_id or evidence_store is None:
        return
    with store.read_snapshot() as db:
        rows = db.execute(
            "SELECT r.*,j.domain,j.payload FROM attribution_reviews r "
            "JOIN jobs j ON j.id=r.job_id WHERE lower(j.domain)=? AND r.decision='accept' "
            "ORDER BY r.reviewed_at DESC,r.id DESC",
            (identity,),
        ).fetchall()
        owners = {
            lead_id: _canonical_owner(db, lead_id) for lead_id in {row["lead_id"] for row in rows}
        }
        rows = [row for row in rows if owners.get(row["lead_id"]) == entity_id]
    for row in rows:
        try:
            result = checked_result(evidence_store, row["result_id"], root)
            index = row["evidence_index"]
            partials = result.get("partial_evidence", [])
            if (
                result.get("status") != "review"
                or type(index) is not int
                or not 0 <= index < len(partials)
            ):
                continue
            evidence = partials[index]
            entries = json.loads(row["payload"])
            anchor = int(evidence["details"]["entry_id"])
            if not any(
                candidate.get("entry_id") == str(anchor) and candidate.get("ip") == evidence["ip"]
                for candidate in result.get("candidates", [])
            ):
                continue
            if (
                not isinstance(entries, list)
                or not 0 <= anchor < len(entries)
                or entries[anchor]["ip"] != evidence["ip"]
            ):
                continue
            review = {
                key: row[key]
                for key in (
                    "id",
                    "result_id",
                    "evidence_index",
                    "decision",
                    "reviewer",
                    "note",
                    "reviewed_at",
                )
            }
            proof = attribution_record(
                evidence_store,
                result["result_id"],
                root,
                result["policy"],
                evidence,
                review=review,
            )
            if checked_proof(proof, root, evidence_store):
                yield proof
        except (KeyError, ValueError, TypeError, AttributeError, IndexError):
            # Missing or corrupt historical evidence must not approve new data.
            continue


def reusable_review(store, group, evidence_store, result_id):
    """Return a new partial's proof and row index when its registrant was approved."""
    from modules.leads.components.lead_queue import association

    if evidence_store is None or not result_id:
        return None
    entries = [asdict(entry) for entry in group.observations]
    with store.read_snapshot() as db:
        entity_id, state, _, _ = association(db, group.root_domain, entries)
    if state != "known":
        return None
    try:
        result = checked_result(evidence_store, result_id, group.root_domain)
        if result.get("status") != "review":
            return None
        approved = {}
        for source in approved_proofs(store, group.root_domain, evidence_store, entity_id):
            identity = _identity(source, group.root_domain)
            if identity and source["result_id"] != result_id:
                approved.setdefault(tuple(identity.values()), (identity, source))
        for evidence in result.get("partial_evidence", []):
            anchor = int(evidence["details"]["entry_id"])
            if not 0 <= anchor < len(entries) or entries[anchor]["ip"] != evidence["ip"]:
                continue
            proof = attribution_record(
                evidence_store, result_id, group.root_domain, result["policy"], evidence
            )
            identity = _identity(proof, group.root_domain)
            source_pair = approved.get(tuple(identity.values())) if identity else None
            if not source_pair:
                continue
            _, source = source_pair
            proof["review"] = deepcopy(source["review"])
            proof["approval_reuse"] = {
                "basis": "Previously accepted domain-to-registrant association",
                "recognized_at": now(),
                **{
                    "source_" + key: source[key]
                    for key in ("result_id", "snapshot_id", "body_sha256", "ip")
                },
                "review_id": source["review"]["id"],
                "registrant_identity": identity,
                "source_proof": deepcopy(source),
            }
            if valid_approval_reuse(proof, group.root_domain, evidence_store):
                return proof, anchor
    except (KeyError, ValueError, TypeError, AttributeError, IndexError):
        return None
    return None
