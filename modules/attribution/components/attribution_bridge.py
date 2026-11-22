"""The workbench adapter. Registration policy lives only in the standalone module."""

from dataclasses import asdict, dataclass
import json
from attribution import AttributionModule, CandidateIP, Settings
from attribution.matching import normalize_domain
from attribution.rdap import normalize_ip


@dataclass(frozen=True, slots=True)
class AttributionDecision:
    """A group's attribution output; source observations are never rearranged."""

    status: str
    proof: dict | None
    result_id: str | None
    attempts: tuple[dict, ...] = ()
    coverage: tuple[dict, ...] = ()


class EvidenceReader:
    """Cache immutable records for one qualification/reconciliation operation."""

    def __init__(self, store):
        self.store = store
        self._results = {}
        self._snapshots = {}

    def result(self, identity):
        if identity not in self._results:
            self._results[identity] = self.store.result(identity)
        return self._results[identity]

    def snapshot(self, identity):
        if identity not in self._snapshots:
            self._snapshots[identity] = self.store.snapshot(identity)
        return self._snapshots[identity]


def group_coverage(group, proof):
    """Apply the group rule without rearranging or fabricating source rows."""
    return source_coverage(
        group.root_domain,
        (
            {
                "ip": entry.ip,
                "source": {
                    "workbook": entry.source.workbook,
                    "sheet": entry.source.sheet,
                    "row": entry.source.row,
                    "fields": entry.source.fields,
                },
            }
            for entry in group.observations
        ),
        proof,
    )


def source_coverage(root_domain, entries, proof):
    """Record every original source's relationship to one immutable proof.

    Used by qualification and explicit case-evidence adoption. This records
    coverage under the root-group rule; it never claims an individual lookup
    for another address or changes the original proof.
    """
    root = domain_identity(root_domain)
    if not root or not same_domain((proof.get("attribution") or {}).get("root_domain"), root):
        raise ValueError("Attribution proof does not cover this domain group")
    matched = domain_identity(proof["attribution"].get("matched_domain"))
    proof_ip = normalize_ip(proof["ip"])
    rows = []
    for index, entry in enumerate(entries):
        source = entry["source"]
        hostname = domain_identity(source["fields"].get("hostname"))
        if not hostname or not (hostname == root or hostname.endswith("." + root)):
            raise ValueError("Observation hostname is outside its attribution group")
        basis = (
            "matched_address"
            if normalize_ip(entry["ip"]) == proof_ip
            else "shared_hostname"
            if hostname == matched
            else "shared_root_domain"
        )
        rows.append(
            {
                "entry_id": str(index),
                "ip": entry["ip"],
                "hostname": hostname,
                "relationship": basis,
                "root_domain": root,
                "proof_result_id": proof["result_id"],
                "proof_ip": proof["ip"],
                "source": {key: source[key] for key in ("workbook", "sheet", "row")},
            }
        )
    return tuple(rows)


def _source_key(source, address, hostname):
    return (source["workbook"], source["sheet"], source["row"], address, hostname)


def coverage_covers(entries, proof):
    """Validate scoped sources in linear time against explicit retained coverage.

    Presentation order may change. Source location, address and hostname identify
    an observation; the original numeric entry index is descriptive. This checks
    coverage only, independently of the original snapshot/result proof validation.
    """
    try:
        root = domain_identity(proof["attribution"]["root_domain"])
        matched = domain_identity(proof["attribution"]["matched_domain"])
        proof_ip = normalize_ip(proof["ip"])
        if not root or not proof.get("result_id") or not proof.get("coverage"):
            return False
        covered = set()
        for row in proof["coverage"]:
            address = normalize_ip(row["ip"])
            hostname = domain_identity(row["hostname"])
            relationship = (
                "matched_address"
                if address == proof_ip
                else "shared_hostname"
                if hostname == matched
                else "shared_root_domain"
            )
            if (
                not hostname
                or not (hostname == root or hostname.endswith("." + root))
                or row["hostname"] != hostname
                or row.get("root_domain") != root
                or row.get("relationship") != relationship
                or row.get("proof_result_id") != proof["result_id"]
                or row.get("proof_ip") != proof["ip"]
            ):
                return False
            covered.add(_source_key(row["source"], address, hostname))
        found = False
        for entry in entries:
            source = entry["source"]
            key = _source_key(
                source, normalize_ip(entry["ip"]), domain_identity(source["fields"].get("hostname"))
            )
            if key not in covered:
                return False
            found = True
        return found
    except (KeyError, ValueError, TypeError, AttributeError):
        return False


def coverage_matches(entry, proof):
    """Check one source observation; use coverage_covers for a complete scope."""
    return coverage_covers((entry,), proof)


def domain_identity(value):
    """Canonical DNS identity; no root reduction or subdomain matching."""
    try:
        return normalize_domain(value)
    except ValueError:
        return None


def same_domain(left, right):
    identity = domain_identity(left)
    return identity is not None and identity == domain_identity(right)


def attribution_record(store, result_id, root_domain, policy, evidence, *, review=None):
    """The same evidence shape feeds automatic and analyst-approved leads."""
    result = checked_result(store, result_id, root_domain)
    # The public application proof uses the same JSON shape as stored results,
    # including array-valued snapshot references (dataclass asdict keeps tuples).
    evidence = json.loads(json.dumps(evidence))
    key = "evidence" if result["status"] == "matched" else "partial_evidence"
    if evidence not in result.get(key, []) or policy != result["policy"]:
        raise ValueError("Attribution evidence does not belong to its saved result")
    response = store.snapshot(evidence["snapshot_id"])
    return {
        "ip": evidence["ip"],
        "registry": evidence["source_name"],
        "source_url": evidence["source_url"],
        "retrieved_at": evidence["retrieved_at"],
        "protocol": "DNS" if evidence["method"] == "dns" else "RDAP",
        "attribution": {
            "root_domain": result["root_domain"],
            "matched_domain": evidence["match"]["matched_domain"],
            "field": evidence["match"]["field_path"],
            "value": evidence["match"]["value"],
        },
        "record": response.record(),
        "result_id": result_id,
        # Evaluation is the attribution decision; retrieval may be much older
        # when the module reused a cached registration or DNS response.
        "evaluated_at": result["evaluated_at"],
        "from_cache": evidence.get("from_cache", False),
        "snapshot_id": evidence["snapshot_id"],
        "body_sha256": response.body_sha256,
        "policy": policy,
        "evidence": evidence,
        **({"review": review} if review else {}),
    }


def checked_result(store, result_id, root_domain):
    """Validate the application-level reference to the standalone database."""
    try:
        result = store.result(result_id)
    except KeyError as error:
        raise ValueError(
            "Saved attribution result is missing from the attribution database"
        ) from error
    if result.get("result_id") != result_id or not same_domain(
        result.get("root_domain"), root_domain
    ):
        raise ValueError("Attribution result does not belong to this domain group")
    return result


class RegistrationAttribution:
    def __init__(self, store, config, *, cancel_event=None):
        self.module = AttributionModule.open(
            store.root / "attribution.sqlite3",
            settings=Settings(
                timeout=config["timeout"], retries=config["retries"], interval=config["interval"]
            ),
            cancel_event=cancel_event,
        )

    def close(self):
        self.module.close()

    def qualify(self, group, *, refresh=False, candidate_indices=None):
        selected = None if candidate_indices is None else set(candidate_indices)
        result = self.module.attribute(
            group.root_domain,
            [
                CandidateIP(str(i), entry.ip, str(entry.source.fields["hostname"]))
                for i, entry in enumerate(group.observations)
                if selected is None or i in selected
            ],
            refresh=refresh,
        )
        checked_result(self.module.store, result.result_id, group.root_domain)
        attempts = tuple({**asdict(a), "result_id": result.result_id} for a in result.attempts)
        if result.status != "matched":
            status = {"incomplete": "deferred", "no_eligible_ip": "no_public_ip"}.get(
                result.status, result.status
            )
            return AttributionDecision(status, None, result.result_id, attempts)
        evidence = result.evidence[0]
        proof = attribution_record(
            self.module.store, result.result_id, result.root_domain, result.policy, asdict(evidence)
        )
        return AttributionDecision(
            "qualified", proof, result.result_id, attempts, group_coverage(group, proof)
        )
