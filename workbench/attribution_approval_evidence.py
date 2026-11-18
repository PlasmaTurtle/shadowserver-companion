"""Read-only validation of saved attribution decisions and their evidence.

These helpers accept captured records and evidence-store readers only. They do
not look up entity ownership or import intake, workflow, or reporting services.
"""

from ipaddress import ip_address
from urllib.parse import urlsplit

from attribution.name_matching import folded, name_fields

from .attribution_bridge import checked_result, same_domain


def _authority(url):
    """Keep registry namespaces distinct, including APIs sharing one host."""
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
    ):
        return None
    for resource in ("/ip/", "/entity/"):
        if resource in parts.path:
            base, identifier = parts.path.rsplit(resource, 1)
            if identifier and "/" not in identifier:
                return f"https://{parts.netloc.lower()}{base}/"
    return None


def _covers(proof):
    evidence = proof.get("evidence") or {}
    details = evidence.get("details") or {}
    record = proof.get("record") or {}
    try:
        address = ip_address(proof["ip"])
        left = ip_address(details["network_start"])
        right = ip_address(details["network_end"])
        if address != ip_address(evidence["ip"]) or not left <= address <= right:
            return False
        if record.get("objectClassName") == "ip network":
            return (
                ip_address(record["startAddress"]) == left
                and ip_address(record["endAddress"]) == right
            )
        return True
    except (KeyError, ValueError, TypeError):
        return False


def _identity(proof, root):
    evidence = proof.get("evidence") or {}
    match = evidence.get("match") or {}
    if (
        evidence.get("method") != "rdap_keyword"
        or not same_domain(match.get("target_domain"), root)
        or not same_domain((proof.get("attribution") or {}).get("root_domain"), root)
        or not _covers(proof)
    ):
        return None
    authority = _authority(proof.get("source_url") or "")
    if not authority or evidence.get("source_url") != proof.get("source_url"):
        return None
    for value, pointer, handle, roles, field_type in name_fields(proof.get("record") or {}):
        if (
            pointer == match.get("field_path")
            and value == match.get("value")
            and handle
            and handle == match.get("entity_handle")
            and "registrant" in roles
            and field_type in {"entity_name", "organization_name"}
            and field_type == match.get("field_type")
        ):
            # Handle and name must both agree; names are not an identity key.
            return {
                "authority": authority,
                "handle": handle,
                "name": " ".join(folded(value).split()),
            }
    return None


def _checked_proof(proof, root, evidence_store):
    """Verify a partial against its exact immutable result and response."""
    result = checked_result(evidence_store, proof["result_id"], root)
    evidence = proof["evidence"]
    if result.get("status") != "review" or evidence not in result.get("partial_evidence", []):
        return False
    snapshot = evidence_store.snapshot(proof["snapshot_id"])
    if (
        proof["snapshot_id"] != evidence.get("snapshot_id")
        or snapshot.status_code != 200
        or snapshot.body_sha256 != proof.get("body_sha256")
        or snapshot.record() != proof.get("record")
        or snapshot.source_url != proof.get("source_url")
        or snapshot.retrieved_at != proof.get("retrieved_at")
        or snapshot.retrieved_at != evidence.get("retrieved_at")
        or result.get("evaluated_at") != proof.get("evaluated_at")
        or result.get("policy") != proof.get("policy")
    ):
        return False
    for snapshot_id in evidence.get("supporting_snapshot_ids", []):
        evidence_store.snapshot(snapshot_id)
    return True


def snapshot_approval_matches(proof, root):
    """Check inherited-decision provenance in a self-contained frozen snapshot."""
    try:
        reuse = proof["approval_reuse"]
        source = reuse["source_proof"]
        review = proof["review"]
        if (
            source.get("approval_reuse")
            or review != source.get("review")
            or review.get("decision") != "accept"
            or review.get("result_id") != source.get("result_id")
            or review.get("id") != reuse.get("review_id")
            or not review.get("reviewed_at")
            or not review.get("reviewer")
            or proof.get("result_id") == source.get("result_id")
            or any(
                reuse.get("source_" + key) != source.get(key)
                for key in ("result_id", "snapshot_id", "body_sha256", "ip")
            )
        ):
            return False
        source_identity = _identity(source, root)
        return bool(
            source_identity
            and source_identity == _identity(proof, root) == reuse.get("registrant_identity")
        )
    except (KeyError, ValueError, TypeError, AttributeError):
        return False


def valid_approval_reuse(proof, root, evidence_store):
    """Verify current and original evidence without inventing an analyst action."""
    if evidence_store is None or not snapshot_approval_matches(proof, root):
        return False
    try:
        source = proof["approval_reuse"]["source_proof"]
        result = checked_result(evidence_store, source["result_id"], root)
        index = source["review"]["evidence_index"]
        return bool(
            type(index) is int
            and 0 <= index < len(result.get("partial_evidence", []))
            and result["partial_evidence"][index] == source["evidence"]
            and _checked_proof(source, root, evidence_store)
            and _checked_proof(proof, root, evidence_store)
        )
    except (KeyError, ValueError, TypeError, AttributeError, IndexError):
        return False
