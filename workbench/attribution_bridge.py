"""The workbench adapter. Registration policy lives only in the standalone module."""

from dataclasses import asdict
from attribution import AttributionModule, CandidateIP, Settings
from attribution.matching import normalize_domain


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
    def __init__(self, store, config):
        self.result_id = None
        self.module = AttributionModule.open(
            store.root / "attribution.sqlite3",
            settings=Settings(
                timeout=config["timeout"], retries=config["retries"], interval=config["interval"]
            ),
        )

    def close(self):
        self.module.close()

    def qualify(self, group, *, refresh=False, candidate_indices=None):
        result = self.module.attribute(
            group.hostname,
            [
                CandidateIP(str(i), entry.ip, str(entry.source.fields["hostname"]))
                for i, entry in enumerate(group.entries)
                if candidate_indices is None or i in candidate_indices
            ],
            refresh=refresh,
        )
        checked_result(self.module.store, result.result_id, group.hostname)
        self.result_id = result.result_id
        group.attempts = [{**asdict(a), "result_id": result.result_id} for a in result.attempts]
        if result.status != "matched":
            status = {"incomplete": "deferred", "no_eligible_ip": "no_public_ip"}.get(
                result.status, result.status
            )
            return status, None
        evidence = result.evidence[0]
        # Reorder the original observation, never synthesize a replacement row.
        group.entries.insert(0, group.entries.pop(int(result.matched_entry_id)))
        return "qualified", attribution_record(
            self.module.store, result.result_id, result.root_domain, result.policy, asdict(evidence)
        )
