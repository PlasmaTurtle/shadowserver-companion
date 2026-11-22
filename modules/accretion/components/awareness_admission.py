"""Exact condition/measurement qualification, independent of workflow state.

Events retain source-level assertions. Membership state is their monotonic
projection; an unresolved legacy assertion cannot be erased by a later sighting.
"""

import hashlib
import json

from modules.workspace.components.primitives import dump, now

CONTRACT_VERSION = 1


def available(db):
    return bool(
        db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='awareness_admission_events'"
        ).fetchone()
    )


def state_sql(db, alias="m", observation_alias="o"):
    if available(db):
        return f"{alias}.admission_state"
    return f"CASE WHEN {observation_alias}.admitted=1 THEN 'admitted' ELSE 'observed' END"


def record(
    db,
    *,
    finding_id,
    observation_id,
    import_id,
    source_key,
    admitted,
    fields,
    reason="",
    authority_kind="intake_qualification",
    authority_ref="",
    policy_version="",
    decision_at=None,
    actor="intake_pipeline",
    evidence_ref="",
):
    if not available(db):
        return
    source = db.execute(
        "SELECT s.*,i.config,i.sha256 import_sha256 FROM awareness_sources s JOIN imports i ON i.id=s.import_id WHERE s.import_id=? AND s.source_key=? AND s.observation_id=?",
        (import_id, source_key, observation_id),
    ).fetchone()
    if not source:
        raise ValueError("Condition admission requires an exact retained source occurrence")
    if source["source_sha256"] != source["import_sha256"]:
        raise ValueError("Condition admission source hash does not match its retained import")
    config = json.loads(source["config"])
    policy = {
        key: config[key]
        for key in ("accretion_policy", "profile", "profile_version", "attribution_policy")
        if key in config
    }
    policy_version = policy_version or hashlib.sha256(dump(policy).encode()).hexdigest()
    state = "admitted" if admitted else "observed"
    authority_kind = authority_kind if admitted else "source_assertion"
    authority_ref = authority_ref or str(source["entry_id"] or source_key)
    if not admitted:
        authority_ref += ":" + str(reason)[:200]
    evidence_ref = evidence_ref or dump(
        {
            "sha256": source["source_sha256"],
            "sheet": source["sheet"],
            "row": source["row_number"],
            "entry_id": source["entry_id"],
        }
    )
    if len(evidence_ref) > 4000:
        raise ValueError("Admission evidence must use compact references, at most 4000 characters")
    facts = {
        key: str(fields.get(key) or "")[:2000]
        for key in (
            "timestamp",
            "ip",
            "hostname",
            "protocol",
            "port",
            "version",
            "product",
            "severity",
        )
    }
    identity = [
        finding_id,
        observation_id,
        import_id,
        source_key,
        state,
        CONTRACT_VERSION,
        policy_version,
        authority_kind,
        authority_ref,
    ]
    event_id = hashlib.sha256(dump(identity).encode()).hexdigest()
    stamp = now()
    db.execute(
        """INSERT OR IGNORE INTO awareness_admission_events
        (id,finding_id,observation_id,import_id,source_key,state,contract_version,policy_version,
         decision_at,recorded_at,authority_kind,authority_ref,actor,reason,evidence_ref,facts_json)
        SELECT ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
        WHERE NOT EXISTS(SELECT 1 FROM awareness_admission_events WHERE id=?)""",
        (
            event_id,
            finding_id,
            observation_id,
            import_id,
            source_key,
            state,
            CONTRACT_VERSION,
            policy_version,
            stamp if decision_at is None else decision_at,
            stamp,
            authority_kind,
            authority_ref,
            actor,
            str(reason)[:2000],
            evidence_ref,
            dump(facts),
            event_id,
        ),
    )


def source_is_admitted(db, entry, finding_ids):
    """A qualified queue may only reuse approvals for all of its exact pairs."""
    ref = (entry.get("normalized") or {}).get("observation_ref", "")
    ids = list(finding_ids)
    if not ids:
        return True
    state = state_sql(db)
    approved = {
        row[0]
        for row in db.execute(
            "SELECT DISTINCT m.finding_id FROM awareness_sources s JOIN awareness_observations o ON o.id=s.observation_id JOIN awareness_memberships m ON m.observation_id=o.id WHERE s.source_key=? AND "
            + state
            + "='admitted' AND m.finding_id IN ("
            + ",".join("?" for _ in ids)
            + ")",
            (ref, *ids),
        )
    }
    return approved == set(ids)


def facts_sql(db, finding="m.finding_id", observation="o.id"):
    """Approved assertion facts survive replacement of an observation's summary."""
    if not available(db):
        return "NULL"
    return (
        "(SELECT ae.facts_json FROM awareness_admission_events ae WHERE ae.finding_id="
        + finding
        + " AND ae.observation_id="
        + observation
        + " AND ae.state='admitted' ORDER BY ae.recorded_at DESC,ae.id DESC LIMIT 1)"
    )


def validate(db):
    """Read-only restore/health validation of the exact admission projection."""
    if not available(db):
        return None
    checks = {
        "invalid_membership_state": "SELECT count(*) FROM awareness_memberships WHERE admission_state NOT IN('admitted','observed','legacy_unknown') OR admission_projection_version<>1",
        "approval_without_authority": "SELECT count(*) FROM awareness_memberships m WHERE m.admission_state='admitted' AND NOT EXISTS(SELECT 1 FROM awareness_admission_events e WHERE e.finding_id=m.finding_id AND e.observation_id=m.observation_id AND e.state='admitted')",
        "unprojected_approval": "SELECT count(*) FROM awareness_admission_events e LEFT JOIN awareness_memberships m ON m.finding_id=e.finding_id AND m.observation_id=e.observation_id WHERE e.state='admitted' AND (m.admission_state IS NULL OR m.admission_state<>'admitted')",
        "source_mismatch": "SELECT count(*) FROM awareness_admission_events e LEFT JOIN awareness_sources s ON s.import_id=e.import_id AND s.source_key=e.source_key WHERE s.observation_id IS NULL OR s.observation_id<>e.observation_id",
        "invalid_event": "SELECT count(*) FROM awareness_admission_events WHERE state NOT IN('observed','admitted') OR contract_version<>1 OR NOT json_valid(facts_json) OR json_type(facts_json)<>'object' OR length(evidence_ref)>4000 OR length(authority_kind)=0",
    }
    violations = {
        key: count for key, query in checks.items() if (count := db.execute(query).fetchone()[0])
    }
    if violations:
        raise ValueError("Invalid condition admission provenance: " + dump(violations))
    counts = {state: 0 for state in ("admitted", "observed", "legacy_unknown")}
    counts.update(
        {
            row[0]: row[1]
            for row in db.execute(
                "SELECT admission_state,count(*) FROM awareness_memberships GROUP BY admission_state"
            )
        }
    )
    counts["events"] = db.execute("SELECT count(*) FROM awareness_admission_events").fetchone()[0]
    return counts


def observation_states_sql(db, alias="o"):
    """Disjoint physical categories; broad historic qualification is separate.

    A measurement qualifies here when any exact condition has retained approval.
    A legacy aggregate approval without exact pair authority is unavailable,
    never a new negative qualification decision.
    """
    state = state_sql(db, observation_alias=alias)
    approved = f"EXISTS(SELECT 1 FROM awareness_memberships m WHERE m.observation_id={alias}.id AND {state}='admitted')"
    unknown = f"(NOT {approved} AND ({alias}.admitted=1 OR EXISTS(SELECT 1 FROM awareness_memberships m WHERE m.observation_id={alias}.id AND {state}='legacy_unknown')))"
    return approved, unknown
