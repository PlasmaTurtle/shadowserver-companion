"""Disposable, transactional Observatory counters and a purpose-scoped revision.

Canonical observations, membership approval and recorded ownership remain the
source of truth. Triggers maintain small day counters in the same transaction;
explicit reconciliation can verify or rebuild these projections without touching
evidence. Read paths never repair or write the index.
"""

import json

OBSERVATIONS = """SELECT o.id observation_id,
 CASE WHEN l.id IS NULL THEN 'asset:'||o.asset_id ELSE 'entity:'||COALESCE(l.merged_into,l.id) END node_id,
 substr(o.observed_at,1,10) day,o.admitted,
 EXISTS(SELECT 1 FROM awareness_memberships um WHERE um.observation_id=o.id AND um.admission_state='legacy_unknown') unknown
 FROM awareness_observations o JOIN awareness_assets a ON a.id=o.asset_id
 LEFT JOIN awareness_observation_owners w ON w.observation_id=o.id
 LEFT JOIN leads l ON l.id=CASE WHEN w.observation_id IS NOT NULL THEN w.entity_id ELSE a.entity_id END"""

MEMBERSHIPS = """SELECT m.observation_id,m.finding_id,substr(o.observed_at,1,10) day,
 m.admission_state FROM awareness_memberships m
 JOIN awareness_observations o ON o.id=m.observation_id"""


_COLUMNS = {
    "analytical_observations": ["observation_id", "node_id", "day", "admitted", "unknown"],
    "analytical_memberships": ["observation_id", "finding_id", "day", "admission_state"],
    "analytical_density_days": ["node_id", "day", "reported", "approved", "unknown"],
    "analytical_finding_days": ["finding_id", "day", "reported", "approved", "unknown"],
}


def _schema_differences(db):
    return {
        table: {"schema_mismatch": 1}
        for table, columns in _COLUMNS.items()
        if [r[1] for r in db.execute("PRAGMA table_info(" + table + ")")] != columns
    }


def available(db):
    return (
        db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='analytical_revision'"
        ).fetchone()
        is not None
    )


def revision(db):
    if not available(db):
        return None
    row = db.execute("SELECT token FROM analytical_revision WHERE id=1").fetchone()
    return row[0] if row else None


def _counter_triggers(db, fact, counter, keys, amounts):
    columns = ",".join([*keys, *amounts])
    conflict = ",".join(keys)
    for action, old, sign in [("insert", "NEW", 1), ("delete", "OLD", -1)]:
        values = ",".join(
            [
                *(f"{old}.{key}" for key in keys),
                *(f"{sign}*({expression.format(row=old)})" for expression in amounts.values()),
            ]
        )
        updates = ",".join(f"{name}={name}+excluded.{name}" for name in amounts)
        where = " AND ".join(f"{key}={old}.{key}" for key in keys)
        db.execute(f"""CREATE TRIGGER {fact}_{action} AFTER {action.upper()} ON {fact} BEGIN
          INSERT INTO {counter}({columns}) VALUES({values})
            ON CONFLICT({conflict}) DO UPDATE SET {updates};
          DELETE FROM {counter} WHERE {where} AND reported=0;
        END""")


def schema(db):
    db.execute(
        "CREATE TABLE analytical_revision(id INTEGER PRIMARY KEY CHECK(id=1),token TEXT NOT NULL)"
    )
    db.execute("INSERT INTO analytical_revision VALUES(1,lower(hex(randomblob(16))))")
    db.execute("""CREATE TABLE analytical_observations(observation_id TEXT PRIMARY KEY,
      node_id TEXT NOT NULL,day TEXT NOT NULL,admitted INTEGER NOT NULL,unknown INTEGER NOT NULL) WITHOUT ROWID""")
    db.execute("""CREATE TABLE analytical_density_days(node_id TEXT NOT NULL,day TEXT NOT NULL,
      reported INTEGER NOT NULL,approved INTEGER NOT NULL,unknown INTEGER NOT NULL,PRIMARY KEY(node_id,day)) WITHOUT ROWID""")
    db.execute("""CREATE TABLE analytical_memberships(observation_id TEXT NOT NULL,finding_id TEXT NOT NULL,
      day TEXT NOT NULL,admission_state TEXT NOT NULL,PRIMARY KEY(observation_id,finding_id)) WITHOUT ROWID""")
    db.execute("""CREATE TABLE analytical_finding_days(finding_id TEXT NOT NULL,day TEXT NOT NULL,
      reported INTEGER NOT NULL,approved INTEGER NOT NULL,unknown INTEGER NOT NULL,
      PRIMARY KEY(finding_id,day)) WITHOUT ROWID""")
    _counter_triggers(
        db,
        "analytical_observations",
        "analytical_density_days",
        ["node_id", "day"],
        {"reported": "1", "approved": "{row}.admitted", "unknown": "{row}.unknown"},
    )
    _counter_triggers(
        db,
        "analytical_memberships",
        "analytical_finding_days",
        ["finding_id", "day"],
        {
            "reported": "1",
            "approved": "{row}.admission_state='admitted'",
            "unknown": "{row}.admission_state='legacy_unknown'",
        },
    )
    for table, identifier in [
        ("awareness_observations", "id"),
        ("awareness_observation_owners", "observation_id"),
    ]:
        for action in ("INSERT", "UPDATE", "DELETE"):
            references = (
                ["OLD", "NEW"] if action == "UPDATE" else ["OLD" if action == "DELETE" else "NEW"]
            )
            ids = ",".join(f"{ref}.{identifier}" for ref in references)
            db.execute(f"""CREATE TRIGGER analytical_{table}_{action.lower()} AFTER {action} ON {table} BEGIN
              DELETE FROM analytical_observations WHERE observation_id IN ({ids});
              INSERT INTO analytical_observations {OBSERVATIONS} WHERE o.id IN ({ids});
              DELETE FROM analytical_memberships WHERE observation_id IN ({ids});
              INSERT INTO analytical_memberships {MEMBERSHIPS} WHERE m.observation_id IN ({ids});
            END""")
    for action in ("INSERT", "UPDATE", "DELETE"):
        references = (
            ["OLD", "NEW"] if action == "UPDATE" else ["OLD" if action == "DELETE" else "NEW"]
        )
        clauses = " OR ".join(
            f"(observation_id={r}.observation_id AND finding_id={r}.finding_id)" for r in references
        )
        selected = " OR ".join(
            f"(m.observation_id={r}.observation_id AND m.finding_id={r}.finding_id)"
            for r in references
        )
        db.execute(f"""CREATE TRIGGER analytical_membership_{action.lower()} AFTER {action} ON awareness_memberships BEGIN
          DELETE FROM analytical_memberships WHERE {clauses};
          INSERT INTO analytical_memberships {MEMBERSHIPS} WHERE {selected};
          DELETE FROM analytical_observations WHERE observation_id IN ({",".join(r + ".observation_id" for r in references)});
          INSERT INTO analytical_observations {OBSERVATIONS} WHERE o.id IN ({",".join(r + ".observation_id" for r in references)});
        END""")
    db.execute(f"""CREATE TRIGGER analytical_asset_owner AFTER UPDATE OF entity_id ON awareness_assets
      WHEN OLD.entity_id IS NOT NEW.entity_id BEGIN
      DELETE FROM analytical_observations WHERE observation_id IN (SELECT id FROM awareness_observations WHERE asset_id=NEW.id);
      INSERT INTO analytical_observations {OBSERVATIONS} WHERE o.asset_id=NEW.id;
    END""")
    affected = """SELECT o.id FROM awareness_observations o JOIN awareness_assets a ON a.id=o.asset_id
      LEFT JOIN awareness_observation_owners w ON w.observation_id=o.id
      WHERE CASE WHEN w.observation_id IS NOT NULL THEN w.entity_id ELSE a.entity_id END=NEW.id"""
    db.execute(f"""CREATE TRIGGER analytical_entity_merge AFTER UPDATE OF merged_into ON leads
      WHEN OLD.merged_into IS NOT NEW.merged_into BEGIN
      DELETE FROM analytical_observations WHERE observation_id IN ({affected});
      INSERT INTO analytical_observations {OBSERVATIONS} WHERE o.id IN ({affected});
    END""")
    # Only tables consumed by the Observatory projection invalidate its cache.
    # Immutable archived revisions and unrelated lookup cache entries do not.
    tables = [
        "awareness_observations",
        "awareness_observation_owners",
        "awareness_memberships",
        "awareness_assets",
        "awareness_findings",
        "awareness_sources",
        "imports",
        "leads",
        "entity_profiles",
        "domain_groups",
        "cases",
        "case_entries",
        "case_entry_conditions",
        "lead_queue",
    ]
    for table in tables + ["cache"]:
        for action in ("INSERT", "UPDATE", "DELETE"):
            condition = ""
            if table == "cache":
                refs = (
                    ["OLD", "NEW"]
                    if action == "UPDATE"
                    else ["OLD" if action == "DELETE" else "NEW"]
                )
                condition = "WHEN " + " OR ".join(
                    f"{r}.key GLOB 'intelligence-latest:*' OR {r}.key GLOB 'cve-reference:*'"
                    for r in refs
                )
            db.execute(f"""CREATE TRIGGER analytical_revision_{table}_{action.lower()} AFTER {action} ON {table} {condition} BEGIN
              UPDATE analytical_revision SET token=lower(hex(randomblob(16))) WHERE id=1;
            END""")
    rebuild(db)


def rebuild(db):
    """Caller owns the explicit maintenance/migration transaction."""
    if _schema_differences(db):
        raise ValueError(
            "Analytical projection schema is unsupported; restore and upgrade a supported database before rebuilding."
        )
    db.execute("DELETE FROM analytical_observations")
    db.execute("DELETE FROM analytical_memberships")
    # Clear any stray/corrupted counters as well as the normal trigger reductions.
    db.execute("DELETE FROM analytical_density_days")
    db.execute("DELETE FROM analytical_finding_days")
    db.execute("INSERT INTO analytical_observations " + OBSERVATIONS)
    db.execute("INSERT INTO analytical_memberships " + MEMBERSHIPS)
    db.execute("UPDATE analytical_revision SET token=lower(hex(randomblob(16))) WHERE id=1")


def reconcile(db):
    """Compare canonical facts and counters without changing either."""
    if not available(db):
        return {"available": False, "healthy": False, "differences": {}}
    schema_errors = _schema_differences(db)
    if schema_errors:
        return {"available": True, "healthy": False, "differences": schema_errors}
    expected = {
        "analytical_observations": OBSERVATIONS,
        "analytical_memberships": MEMBERSHIPS,
        "analytical_density_days": f"SELECT node_id,day,count(*),sum(admitted),sum(unknown) FROM ({OBSERVATIONS}) GROUP BY node_id,day",
        "analytical_finding_days": f"SELECT finding_id,day,count(*),sum(admission_state='admitted'),sum(admission_state='legacy_unknown') FROM ({MEMBERSHIPS}) GROUP BY finding_id,day",
    }
    differences = {}
    for table, query in expected.items():
        missing = db.execute(
            f"SELECT count(*) FROM ({query} EXCEPT SELECT * FROM {table})"
        ).fetchone()[0]
        extra = db.execute(
            f"SELECT count(*) FROM (SELECT * FROM {table} EXCEPT {query})"
        ).fetchone()[0]
        differences[table] = {"missing_or_changed": missing, "extra_or_changed": extra}
    return {
        "available": True,
        "healthy": not any(v for pair in differences.values() for v in pair.values()),
        "differences": differences,
    }


def densities(db, node_ids=None):
    where, args = (
        ("", ())
        if node_ids is None
        else ("WHERE node_id IN (SELECT value FROM json_each(?))", (json.dumps(node_ids),))
    )
    return {
        r["node_id"]: dict(r)
        for r in db.execute(
            f"""SELECT node_id,sum(reported) observation_count,
       sum(approved) admitted_count,sum(reported-approved) dark_matter_count,sum(unknown) legacy_unknown_density,
       sum(day<>'') day_count FROM analytical_density_days {where} GROUP BY node_id""",
            args,
        )
    }


def finding_stats(db, finding_ids=None):
    where, args = (
        ("", ())
        if finding_ids is None
        else ("WHERE finding_id IN (SELECT value FROM json_each(?))", (json.dumps(finding_ids),))
    )
    return {
        r["finding_id"]: dict(r)
        for r in db.execute(
            f"""SELECT finding_id,
       sum(reported) observation_count,sum(reported) reported_observation_count,
       sum(approved) approved_observation_count,sum(unknown) legacy_unknown_observation_count,
       sum(day<>'') day_count,group_concat(CASE WHEN day<>'' THEN day END) days,
       min(CASE WHEN day<>'' THEN day END) reported_first_seen,max(CASE WHEN day<>'' THEN day END) reported_last_seen,
       min(CASE WHEN day<>'' AND approved>0 THEN day END) approved_first_seen,
       max(CASE WHEN day<>'' AND approved>0 THEN day END) approved_last_seen
       FROM analytical_finding_days {where} GROUP BY finding_id""",
            args,
        )
    }
