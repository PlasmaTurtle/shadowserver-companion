"""Entity projections over Accretion's canonical records; no identity reconstruction."""

import json

from ..awareness_admission import facts_sql, state_sql, observation_states_sql
from .. import ownership


def directory(db, entity_id=None):
    approved, unknown = observation_states_sql(db)
    modern = ownership.available(db)
    join = "LEFT JOIN awareness_observation_owners w ON w.observation_id=o.id" if modern else ""
    observed_owner = (
        "CASE WHEN w.observation_id IS NOT NULL THEN w.entity_id ELSE a.entity_id END"
        if modern
        else "a.entity_id"
    )
    observed_owner = (
        f"COALESCE((SELECT merged_into FROM leads WHERE id=({observed_owner})),({observed_owner}))"
    )
    finding_owner = (
        "COALESCE((SELECT merged_into FROM leads WHERE id=f.entity_id),f.entity_id)"
        if modern
        else "a.entity_id"
    )
    scope = " WHERE entity_id=?" if entity_id else " WHERE entity_id IS NOT NULL"
    args = (entity_id,) * 3 if entity_id else ()
    sql = f"""WITH asset_pairs AS (
        SELECT a.entity_id,a.id,a.hostname FROM awareness_assets a
        UNION SELECT {observed_owner} entity_id,a.id,a.hostname
        FROM awareness_observations o JOIN awareness_assets a ON a.id=o.asset_id {join}
      ), assets AS (
        SELECT entity_id,count(*) asset_count,sum(hostname<>'') hostname_count
        FROM asset_pairs {scope} GROUP BY entity_id
      ), owned_observations AS (
        SELECT o.*,{observed_owner} entity_id,{approved} pair_approved,{unknown} pair_unknown FROM awareness_observations o
        JOIN awareness_assets a ON a.id=o.asset_id {join}
      ), observations AS (
        SELECT entity_id,count(*) observations,COALESCE(sum(admitted),0) known_aggregate_qualified_observations,COALESCE(sum(pair_approved),0) approved_observations,
        COALESCE(sum(pair_unknown),0) legacy_unknown_observation_count,
        count(*)-COALESCE(sum(pair_approved),0)-COALESCE(sum(pair_unknown),0) dark_matter_observations,
        count(DISTINCT NULLIF(ip,'')) ips,
        count(DISTINCT NULLIF(substr(observed_at,1,10),'')) observation_days,
        min(NULLIF(observed_at,'')) first_seen,max(NULLIF(observed_at,'')) last_seen
        FROM owned_observations {scope} GROUP BY entity_id
      ), owned_findings AS (
        SELECT f.admitted,f.condition,{finding_owner} entity_id FROM awareness_findings f
        JOIN awareness_assets a ON a.id=f.asset_id
      ), findings AS (
        SELECT entity_id,sum(admitted) findings,count(*)-sum(admitted) unapproved_findings,
        group_concat(DISTINCT CASE WHEN admitted=1 THEN condition END) tags
        FROM owned_findings {scope} GROUP BY entity_id
      ) SELECT a.entity_id,a.asset_count,a.hostname_count,
        COALESCE(o.observations,0) observations,COALESCE(o.known_aggregate_qualified_observations,0) known_aggregate_qualified_observations,COALESCE(o.approved_observations,0) approved_observations,
        COALESCE(o.dark_matter_observations,0) dark_matter_observations,
        COALESCE(o.legacy_unknown_observation_count,0) legacy_unknown_observation_count,COALESCE(o.ips,0) ips,
        COALESCE(o.observation_days,0) observation_days,o.first_seen,o.last_seen,
        COALESCE(f.findings,0) findings,COALESCE(f.unapproved_findings,0) unapproved_findings,
        COALESCE(f.tags,'') tags
        FROM assets a LEFT JOIN observations o ON o.entity_id=a.entity_id
        LEFT JOIN findings f ON f.entity_id=a.entity_id"""
    return {r["entity_id"]: dict(r) for r in db.execute(sql, args)}


def detail(db, entity_id):
    summary = directory(db, entity_id).get(
        entity_id,
        {
            "observations": 0,
            "approved_observations": 0,
            "dark_matter_observations": 0,
            "legacy_unknown_observation_count": 0,
            "observation_days": 0,
            "findings": 0,
            "unapproved_findings": 0,
            "asset_count": 0,
            "hostname_count": 0,
            "ips": 0,
            "first_seen": None,
            "last_seen": None,
        },
    )
    findings = []
    owner = "f.entity_id" if ownership.available(db) else "a.entity_id"
    pair_state = state_sql(db, observation_alias="x")
    for row in db.execute(
        """SELECT f.id,f.condition,f.service_scope,f.first_seen,f.last_seen,
        f.workflow,a.hostname,a.entity_id current_entity_id,o.summary,o.normalized,
        """
        + facts_sql(db, finding="f.id", observation="f.latest_observation_id")
        + """ approved_facts,
        (SELECT count(*) FROM awareness_memberships m JOIN awareness_observations x
          ON x.id=m.observation_id WHERE m.finding_id=f.id AND """
        + pair_state
        + """='admitted') observation_count,
        (SELECT count(*) FROM awareness_memberships m WHERE m.finding_id=f.id) reported_observation_count,
        (SELECT count(*) FROM awareness_memberships m JOIN awareness_observations x
          ON x.id=m.observation_id WHERE m.finding_id=f.id AND """
        + pair_state
        + """='legacy_unknown') legacy_unknown_observation_count
        FROM awareness_findings f JOIN awareness_assets a ON a.id=f.asset_id
        JOIN awareness_observations o ON o.id=f.latest_observation_id
        WHERE """
        + owner
        + """ IN(SELECT id FROM leads WHERE id=? OR merged_into=?) AND f.admitted=1 ORDER BY f.changed_at DESC,f.id LIMIT 250""",
        (entity_id, entity_id),
    ):
        row = dict(row)
        fields, normalized = json.loads(row.pop("summary")), json.loads(row.pop("normalized"))
        row["version"] = (
            normalized.get("raw_version")
            or fields.get("component_version")
            or fields.get("version")
            or ""
        )
        approved_facts = row.pop("approved_facts")
        if approved_facts:
            row["version"] = json.loads(approved_facts).get("version", "")
        row["approved_observation_count"] = row["observation_count"]
        row["qualification_state"] = "admitted" if row["observation_count"] else "legacy_unknown"
        row["can_reactivate"] = (
            row["workflow"] == "ignored" and row["current_entity_id"] == entity_id
        )
        if not row["observation_count"]:
            row["version"] = ""
            row["legacy_first_seen"], row["legacy_last_seen"] = row["first_seen"], row["last_seen"]
            row["first_seen"] = row["last_seen"] = ""
        row["intake_cve_assessments"] = normalized.get("accretion_cves") or {}
        findings.append(row)
    observed_join = (
        "LEFT JOIN awareness_observation_owners w ON w.observation_id=o.id"
        if ownership.available(db)
        else ""
    )
    observed_owner = (
        "CASE WHEN w.observation_id IS NOT NULL THEN w.entity_id ELSE a.entity_id END"
        if ownership.available(db)
        else "a.entity_id"
    )
    observed_owner = (
        f"COALESCE((SELECT merged_into FROM leads WHERE id=({observed_owner})),({observed_owner}))"
    )
    approved, unknown = observation_states_sql(db)
    connections = [
        dict(r)
        for r in db.execute(
            f"""SELECT a.hostname host,o.ip,
        count(*) count,sum({approved}) approved_count,sum({unknown}) legacy_unknown_count,
        count(*)-sum({approved})-sum({unknown}) dark_matter_count,
        min(o.id) observation_id
        FROM awareness_observations o JOIN awareness_assets a ON a.id=o.asset_id
        {observed_join} WHERE ({observed_owner})=? AND a.hostname<>'' AND o.ip<>''
        GROUP BY a.hostname,o.ip ORDER BY count(*) DESC,a.hostname,o.ip LIMIT 500""",
            (entity_id,),
        )
    ]
    for connection in connections:
        connection["entry_ids"] = [connection.pop("observation_id")]
    return {
        "awareness": summary,
        "awareness_findings": findings,
        "awareness_connections": connections,
        "awareness_findings_truncated": summary["findings"] > len(findings),
        "awareness_connections_limited": len(connections) == 500,
    }
