"""Snapshot-local canonical Observatory reads, scoped before rich projection."""

from collections import defaultdict
import json

from modules.observatory.components import analytical_index
from modules.accretion.components.awareness_admission import (
    available as admission_available,
    state_sql,
    facts_sql,
)


def _ids(values):
    return json.dumps(list(dict.fromkeys(value for value in values if value is not None)))


def load(db, detail_id=None, *, events=True):
    owners = db.execute(
        "SELECT 1 FROM sqlite_master WHERE name='awareness_observation_owners'"
    ).fetchone()
    owner_join = (
        "LEFT JOIN awareness_observation_owners w ON w.observation_id=o.id" if owners else ""
    )
    owner = (
        "CASE WHEN w.observation_id IS NOT NULL THEN w.entity_id ELSE a.entity_id END"
        if owners
        else "a.entity_id"
    )
    recorded_owner = owner
    owner = (
        f"COALESCE((SELECT merged_into FROM leads WHERE id=({recorded_owner})),({recorded_owner}))"
    )
    columns = f"o.*,a.hostname,a.root_domain,{owner} entity_id,{recorded_owner} recorded_entity_id,a.entity_id current_entity_id,a.association_basis"
    base = f"FROM awareness_observations o JOIN awareness_assets a ON a.id=o.asset_id {owner_join}"
    findings = f"""SELECT {columns},f.id finding_id,f.condition,f.kind finding_kind,f.admitted finding_admitted,
       f.workflow,f.first_seen,f.last_seen,f.changed_at,f.handled_case_id,
       f.latest_source_key finding_source_key,f.reason finding_reason
       {base} JOIN awareness_findings f ON o.id=f.latest_observation_id"""
    if detail_id:
        row = db.execute(findings + " WHERE f.id=?", (detail_id,)).fetchone()
        if row is None:
            # Resolve indexed identifiers independently. An OR across the entire
            # observation table defeated the primary-key lookup on large workspaces.
            row = db.execute(f"SELECT {columns} {base} WHERE o.id=?", (detail_id,)).fetchone()
        if row is None:
            row = db.execute(
                f"""SELECT {columns} {base} WHERE o.id IN (
                SELECT observation_id FROM awareness_sources WHERE source_key=?
                UNION SELECT observation_id FROM awareness_sources WHERE entry_id=?) ORDER BY o.id LIMIT 1""",
                (detail_id, detail_id),
            ).fetchone()
        raw = [dict(row)] if row else []
    elif events:
        raw = [dict(row) for row in db.execute(f"SELECT {columns} {base} ORDER BY o.id")]
    else:
        raw = [dict(row) for row in db.execute(findings + " ORDER BY f.id")]
        raw.extend(
            dict(row)
            for row in db.execute(f"""SELECT {columns} {base}
             WHERE NOT EXISTS(SELECT 1 FROM awareness_memberships m WHERE m.observation_id=o.id) ORDER BY o.id""")
        )
    selected = _ids(row["id"] for row in raw)
    sources, memberships = defaultdict(list), defaultdict(list)
    for row in db.execute(
        "SELECT * FROM awareness_sources WHERE observation_id IN (SELECT value FROM json_each(?)) ORDER BY import_id,source_key",
        (selected,),
    ):
        sources[row["observation_id"]].append(dict(row))
    state = (
        state_sql(db)
        if admission_available(db)
        else "CASE WHEN o.admitted=1 AND f.admitted=1 THEN 'admitted' ELSE 'observed' END"
    )
    for row in db.execute(
        f"""SELECT m.observation_id,f.id,f.condition,f.admitted,{state} admission_state,{facts_sql(db)} approved_facts,
        f.workflow,f.changed_at,f.created_at,f.handled_case_id,f.kind,f.first_seen,f.last_seen,
        f.latest_observation_id,f.latest_source_key,f.reason FROM awareness_memberships m
        JOIN awareness_findings f ON f.id=m.finding_id JOIN awareness_observations o ON o.id=m.observation_id
        WHERE m.observation_id IN (SELECT value FROM json_each(?)) ORDER BY f.id""",
        (selected,),
    ):
        memberships[row["observation_id"]].append(dict(row))

    def scoped(sql, column, values):
        return (
            db.execute(
                sql + f" WHERE {column} IN (SELECT value FROM json_each(?))", (_ids(values),)
            )
            if detail_id
            else db.execute(sql)
        )

    import_ids = [s["import_id"] for links in sources.values() for s in links]
    imports = {
        r["id"]: dict(r)
        for r in scoped(
            "SELECT id,name,sha256,path,created_at,status FROM imports", "id", import_ids
        )
    }
    entity_ids = [r["entity_id"] for r in raw] + [r["current_entity_id"] for r in raw]
    entities = {
        r["id"]: dict(r)
        for r in scoped("SELECT id,domain,company,merged_into FROM leads", "id", entity_ids)
    }
    profiles = {
        r["entity_id"]: json.loads(r["payload"] or "{}")
        for r in scoped("SELECT entity_id,payload FROM entity_profiles", "entity_id", entity_ids)
    }
    groups = {
        r["root_domain"]: dict(r)
        for r in scoped(
            "SELECT * FROM domain_groups", "root_domain", [r["root_domain"] for r in raw]
        )
    }
    entry_ids = [
        v for links in sources.values() for s in links for v in [s.get("entry_id"), s["source_key"]]
    ]
    links = [
        dict(r) for r in scoped("SELECT entry_id,case_id FROM case_entries", "entry_id", entry_ids)
    ]
    case_ids = [r["case_id"] for r in links] + [
        f["handled_case_id"] for fs in memberships.values() for f in fs
    ]
    cases = {
        r["id"]: dict(r)
        for r in scoped(
            "SELECT id,entity_id,title,stage,created_at,updated_at,delivered_at,closed_at,intake_score FROM cases",
            "id",
            case_ids,
        )
    }
    condition_scopes = {
        (r["case_id"], r["entry_id"]): set(json.loads(r["conditions"]))
        for r in scoped(
            "SELECT case_id,entry_id,conditions FROM case_entry_conditions", "case_id", case_ids
        )
    }
    entry_cases = defaultdict(list)
    for link in links:
        if link["case_id"] in cases:
            entry_cases[link["entry_id"]].append(cases[link["case_id"]])
    pending = {}
    pending_scope = (
        " AND (entity_id IN (SELECT value FROM json_each(?)) OR root_domain IN (SELECT value FROM json_each(?)))"
        if detail_id
        else ""
    )
    pending_args = (_ids(entity_ids), _ids(r["root_domain"] for r in raw)) if detail_id else ()
    for r in db.execute(
        "SELECT id,entity_id,root_domain,intake_score FROM lead_queue WHERE status IN ('pending','deferred') AND qualified=1 AND suppression_reason='' AND superseded_by=''"
        + pending_scope
        + " ORDER BY updated_at,id",
        pending_args,
    ):
        pending[r["entity_id"] or r["root_domain"]] = dict(r)
    node_ids = [
        ("entity:" + r["entity_id"]) if r["entity_id"] else ("asset:" + r["asset_id"]) for r in raw
    ]
    finding_ids = [f["id"] for fs in memberships.values() for f in fs]
    if analytical_index.available(db):
        densities = analytical_index.densities(db, node_ids if detail_id else None)
        stats = analytical_index.finding_stats(db, finding_ids if detail_id else None)
    else:
        node = f"CASE WHEN ({owner}) IS NULL THEN 'asset:'||a.id ELSE 'entity:'||({owner}) END"
        where = f" WHERE ({node}) IN (SELECT value FROM json_each(?))" if detail_id else ""
        densities = {
            r["node_id"]: dict(r)
            for r in db.execute(
                f"""SELECT {node} node_id,count(*) observation_count,
            sum(o.admitted) admitted_count,count(*)-sum(o.admitted) dark_matter_count,
            count(DISTINCT CASE WHEN o.observed_at<>'' THEN substr(o.observed_at,1,10) END) day_count
            {base} {where} GROUP BY node_id""",
                (_ids(node_ids),) if detail_id else (),
            )
        }
        where = " WHERE m.finding_id IN (SELECT value FROM json_each(?))" if detail_id else ""
        stats = {
            r["finding_id"]: dict(r)
            for r in db.execute(
                f"""SELECT m.finding_id,count(*) observation_count,
            count(*) reported_observation_count,sum(({state})='admitted') approved_observation_count,
            sum(({state})='legacy_unknown') legacy_unknown_observation_count,
            count(DISTINCT CASE WHEN o.observed_at<>'' THEN substr(o.observed_at,1,10) END) day_count,
            group_concat(DISTINCT CASE WHEN o.observed_at<>'' THEN substr(o.observed_at,1,10) END) days,
            min(CASE WHEN o.observed_at<>'' THEN substr(o.observed_at,1,10) END) reported_first_seen,
            max(CASE WHEN o.observed_at<>'' THEN substr(o.observed_at,1,10) END) reported_last_seen,
            min(CASE WHEN ({state})='admitted' AND o.observed_at<>'' THEN substr(o.observed_at,1,10) END) approved_first_seen,
            max(CASE WHEN ({state})='admitted' AND o.observed_at<>'' THEN substr(o.observed_at,1,10) END) approved_last_seen
            FROM awareness_memberships m JOIN awareness_observations o ON o.id=m.observation_id JOIN awareness_findings f ON f.id=m.finding_id {where} GROUP BY m.finding_id""",
                (_ids(finding_ids),) if detail_id else (),
            )
        }
    exact = (
        db.execute("SELECT payload FROM entries WHERE id=?", (detail_id,)).fetchone()
        if detail_id
        else None
    )
    exact_entry = json.loads(exact["payload"]) if exact else None
    overall = (
        {}
        if detail_id
        else dict(
            db.execute("""SELECT
      (SELECT count(*) FROM awareness_findings) findings,(SELECT count(*) FROM awareness_assets) assets,
      (SELECT count(*) FROM awareness_observations) observations,
      (SELECT count(*) FROM awareness_findings WHERE admitted=1) admitted_findings,
      (SELECT count(*) FROM awareness_observations WHERE admitted=0) dark_matter_observations,
      (SELECT count(DISTINCT substr(observed_at,1,10)) FROM awareness_observations WHERE observed_at<>'') observation_days""").fetchone()
        )
    )
    return (
        imports,
        entities,
        profiles,
        groups,
        cases,
        condition_scopes,
        entry_cases,
        pending,
        densities,
        stats,
        raw,
        sources,
        memberships,
        exact_entry,
        overall,
    )
