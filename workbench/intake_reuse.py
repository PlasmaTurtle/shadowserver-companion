"""Recognize history without confusing an approved identity with one report row.

Automatic endpoint evidence has a bounded reuse window. An explicit analyst
identity decision does not expire with that cache, or depend on a service port.
New addresses still need their own evidence; all source timestamps stay intact.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import ipaddress
import json

from .intake.versions import entry_fields
from .intake.records import WhoisRecord

ASSOCIATION_REUSE_SECONDS = 7 * 86400


def endpoint(entry):
    fields = entry_fields(asdict(entry) if not isinstance(entry, dict) else entry)
    address = str(fields.get("ip") or "").strip()
    try:
        address = ipaddress.ip_address(address).compressed
    except ValueError:
        pass
    return (
        str(fields.get("hostname") or "").strip().casefold().rstrip("."),
        address,
        str(fields.get("protocol") or "").strip().casefold(),
        str(fields.get("port") or "").strip(),
    )


def _age(stamp, current):
    try:
        value = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        if value.tzinfo is None:
            return None
        age = (current - value.astimezone(timezone.utc)).total_seconds()
        return age if age >= 0 else None
    except ValueError, TypeError:
        return None


def _proof_matches(proof, root, evidence_store):
    from .attribution_bridge import checked_result, same_domain

    if not same_domain((proof.get("attribution") or {}).get("root_domain"), root):
        return False
    try:
        if proof.get("result_id"):
            if evidence_store is None:
                return False
            result = checked_result(evidence_store, proof["result_id"], root)
            review = proof.get("review") or {}
            if proof.get("approval_reuse"):
                from .attribution_approval_evidence import valid_approval_reuse

                if not valid_approval_reuse(proof, root, evidence_store):
                    return False
            elif result.get("status") != "matched" and not (
                result.get("status") == "review"
                and review.get("decision") == "accept"
                and review.get("result_id") == proof["result_id"]
            ):
                return False
            evidence_rows = result.get(
                "evidence" if result.get("status") == "matched" else "partial_evidence", []
            )
            if not any(
                value.get("snapshot_id") == proof.get("snapshot_id")
                and value.get("ip") == proof.get("ip")
                for value in evidence_rows
            ):
                return False
            snapshot = evidence_store.snapshot(proof["snapshot_id"])
            if snapshot.body_sha256 != proof.get("body_sha256"):
                return False
            evidence = proof.get("evidence") or {}
            if evidence.get("ip") != proof.get("ip"):
                return False
            for snapshot_id in evidence.get("supporting_snapshot_ids", []):
                evidence_store.snapshot(snapshot_id)
            return True
        # Legacy embedded proofs have no result reference. Recheck their exact
        # registration-domain relationship locally before reusing it.
        record = WhoisRecord(
            proof["ip"],
            proof["registry"],
            proof["source_url"],
            proof["retrieved_at"],
            proof["record"],
            proof.get("protocol", "RDAP"),
        )
        return record.protocol == "RDAP" and record.find_domain(root) is not None
    except KeyError, ValueError, TypeError, AttributeError:
        return False


def recognize_group(store, group, *, evidence_store=None, refresh=False, clock=None):
    """Return reusable proof and only the endpoint indexes needing examination.

    Does not mutate ownership, qualification, source payloads, or workflow.
    One indexed history lookup per distinct endpoint bounds repeated-row cost.
    """
    from .awareness import recognize
    from .lead_queue import association

    entries = [asdict(entry) for entry in group.entries]
    current = clock or datetime.now(timezone.utc)
    with store.read_snapshot() as db:
        owner, state, basis, candidates = association(db, group.hostname, entries)
        history = {}
        for entry in entries:
            key = endpoint(entry)
            if key not in history:
                history[key] = recognize(db, entry, entity_id=owner)
        known = {
            key
            for key, value in history.items()
            if value.get("endpoint_seen") and value.get("owner_matches", True)
        }
        new_indices = [i for i, entry in enumerate(entries) if endpoint(entry) not in known]
        from .ownership import available as ownership_available

        saved = db.execute(
            "SELECT g.entity_id,g.attribution,e.payload FROM "
            + ("entity_domain_associations" if ownership_available(db) else "domain_groups")
            + " g "
            "JOIN entries e ON e.id=g.attribution_entry_id WHERE lower(g.root_domain)=? AND g.entity_id=?",
            (group.hostname.casefold(), owner),
        ).fetchone()
    result = {
        "entity_id": owner,
        "state": state,
        "basis": basis,
        "candidates": candidates,
        "known_endpoints": len(known),
        "new_endpoints": len(history) - len(known),
        "candidate_indices": new_indices if known and new_indices and not refresh else None,
        "attribution": None,
    }
    if refresh or state != "known":
        return result
    # The latest report's anchor is a presentation choice, not the identity of
    # an approval. Older accepted results remain available after that changes.
    proofs = []
    if saved and saved["entity_id"] == owner:
        proofs.append(json.loads(saved["attribution"]))
    if evidence_store is not None:
        from .attribution_approval import approved_proofs

        proofs.extend(approved_proofs(store, group.hostname, evidence_store, owner))
    seen = set()
    for candidate in proofs:
        key = (candidate.get("result_id"), candidate.get("snapshot_id"), candidate.get("ip"))
        if key in seen:
            continue
        seen.add(key)
        manual = (candidate.get("review") or {}).get("decision") == "accept"
        # RDAP describes an address/network and registrant, not a TCP port.
        # A new address is never manufactured from the old supporting proof.
        pending = [
            i for i in new_indices if not (manual and entries[i]["ip"] == candidate.get("ip"))
        ]
        if pending:
            continue
        anchor = next(
            (i for i, entry in enumerate(entries) if entry["ip"] == candidate.get("ip")), None
        )
        if anchor is None:
            continue
        if not manual:
            original = json.loads(saved["payload"]) if saved else {}
            if endpoint(entries[anchor])[:2] != endpoint(original)[:2]:
                continue
            age = _age(candidate.get("evaluated_at") or candidate.get("retrieved_at"), current)
            if age is None or age > ASSOCIATION_REUSE_SECONDS:
                continue
        if not _proof_matches(candidate, group.hostname, evidence_store):
            continue
        proof = deepcopy(candidate)
        proof["reuse"] = {
            "basis": "Previously approved domain and address; original analyst decision retained"
            if manual
            else "Previously admitted hostname and address; historical attribution reused",
            "recognized_at": current.isoformat(),
            "source_evaluated_at": proof.get("evaluated_at") or proof.get("retrieved_at"),
            "maximum_age_seconds": None if manual else ASSOCIATION_REUSE_SECONDS,
            "fresh_lookup": False,
        }
        result.update(attribution=proof, anchor_index=anchor)
        return result
    return result
