"""Schema 19: ownership episodes and reversible workflow decisions, without evidence rewrites."""

import re
from .primitives import now


def _rebuild(db, table, transform, extra_columns="", extra_select=""):
    definition = db.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()[0]
    dependent = [
        r[0]
        for r in db.execute(
            "SELECT sql FROM sqlite_master WHERE tbl_name=? AND type IN('index','trigger') AND sql IS NOT NULL",
            (table,),
        )
    ]
    temporary = table + "_lifecycle_new"
    create = re.sub(
        r'CREATE TABLE\s+"?' + table + r'"?',
        "CREATE TABLE " + temporary,
        transform(definition),
        count=1,
        flags=re.I,
    )
    db.execute(create)
    columns = [r[1] for r in db.execute("PRAGMA table_info(" + table + ")")]
    names = ",".join('"' + c + '"' for c in columns)
    db.execute(
        f"INSERT INTO {temporary}({names}{extra_columns}) SELECT {names}{extra_select} FROM {table}"
    )
    db.execute("DROP TABLE " + table)
    db.execute(f"ALTER TABLE {temporary} RENAME TO {table}")
    for statement in dependent:
        db.execute(statement)


def schema(db):
    stamp = now()
    statements = (
        """CREATE TABLE entity_domain_associations(root_domain TEXT NOT NULL,entity_id TEXT NOT NULL REFERENCES leads(id),
            attribution_entry_id TEXT REFERENCES entries(id) DEFERRABLE INITIALLY DEFERRED,attribution TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(attribution)),PRIMARY KEY(root_domain,entity_id))""",
        "CREATE INDEX entity_domain_attribution_entry ON entity_domain_associations(attribution_entry_id)",
        "INSERT OR IGNORE INTO entity_domain_associations SELECT root_domain,entity_id,attribution_entry_id,attribution FROM domain_groups",
        "INSERT OR IGNORE INTO entity_domain_associations(root_domain,entity_id) SELECT root_domain,lead_id FROM entries",
        """CREATE TABLE entity_lifecycle_events(id TEXT PRIMARY KEY NOT NULL,event_type TEXT NOT NULL CHECK(event_type IN('transfer','reactivation','merge')),
            source_entity_id TEXT NOT NULL REFERENCES leads(id),target_entity_id TEXT REFERENCES leads(id),
            subject TEXT NOT NULL,reason TEXT NOT NULL CHECK(length(trim(reason))>0),recorded_by TEXT NOT NULL,
            effective_at TEXT NOT NULL,payload TEXT NOT NULL CHECK(json_valid(payload)))""",
        "CREATE INDEX entity_lifecycle_events_entity ON entity_lifecycle_events(source_entity_id,effective_at)",
        """CREATE TABLE asset_ownership_episodes(asset_id TEXT NOT NULL REFERENCES awareness_assets(id),episode TEXT NOT NULL,
            entity_id TEXT REFERENCES leads(id),started_at TEXT NOT NULL,ended_at TEXT,basis TEXT NOT NULL,event_id TEXT NOT NULL,
            PRIMARY KEY(asset_id,episode),CHECK(ended_at IS NULL OR started_at='' OR ended_at>=started_at))""",
        "CREATE UNIQUE INDEX asset_ownership_current ON asset_ownership_episodes(asset_id) WHERE ended_at IS NULL",
        "CREATE INDEX asset_ownership_entity ON asset_ownership_episodes(entity_id,ended_at)",
        """CREATE TABLE awareness_observation_owners(observation_id TEXT PRIMARY KEY NOT NULL REFERENCES awareness_observations(id),
            entity_id TEXT REFERENCES leads(id),ownership_episode TEXT NOT NULL,basis TEXT NOT NULL,recorded_at TEXT NOT NULL)""",
        "CREATE INDEX awareness_observation_owner_entity ON awareness_observation_owners(entity_id,observation_id)",
        """INSERT INTO asset_ownership_episodes SELECT id,'',entity_id,'',NULL,'legacy_association_timing_unknown','' FROM awareness_assets""",
    )
    for statement in statements:
        db.execute(statement)
    db.execute(
        "INSERT INTO awareness_observation_owners SELECT o.id,a.entity_id,'','legacy_association_timing_unknown',? FROM awareness_observations o JOIN awareness_assets a ON a.id=o.asset_id",
        (stamp,),
    )

    def entries(sql):
        return re.sub(
            r"REFERENCES\s+domain_groups\s*\(root_domain\s*,\s*entity_id\)",
            "REFERENCES entity_domain_associations(root_domain,entity_id)",
            sql,
            flags=re.I,
        )

    _rebuild(db, "entries", entries)

    def findings(sql):
        return re.sub(
            r"UNIQUE\s*\(asset_id\s*,\s*condition\s*,\s*service_scope\)",
            "ownership_episode TEXT NOT NULL DEFAULT '',entity_id TEXT REFERENCES leads(id),UNIQUE(asset_id,condition,service_scope,ownership_episode)",
            sql,
            flags=re.I,
        )

    _rebuild(
        db,
        "awareness_findings",
        findings,
        ",ownership_episode,entity_id",
        ",'',(SELECT entity_id FROM awareness_assets a WHERE a.id=awareness_findings.asset_id)",
    )
    db.execute(
        "CREATE INDEX awareness_findings_owner ON awareness_findings(entity_id,admitted,workflow,id)"
    )
    db.execute(
        "CREATE TRIGGER domain_association_insert AFTER INSERT ON domain_groups BEGIN INSERT OR IGNORE INTO entity_domain_associations(root_domain,entity_id,attribution_entry_id,attribution) VALUES(NEW.root_domain,NEW.entity_id,NEW.attribution_entry_id,NEW.attribution); END"
    )
    db.execute(
        "CREATE TRIGGER domain_association_update AFTER UPDATE OF entity_id ON domain_groups BEGIN INSERT OR IGNORE INTO entity_domain_associations(root_domain,entity_id) VALUES(NEW.root_domain,NEW.entity_id); END"
    )
    db.execute(
        "CREATE TRIGGER domain_association_proof_update AFTER UPDATE OF attribution_entry_id,attribution ON domain_groups WHEN NEW.entity_id=OLD.entity_id AND EXISTS(SELECT 1 FROM entries WHERE id=NEW.attribution_entry_id AND lead_id=NEW.entity_id AND root_domain=NEW.root_domain) BEGIN UPDATE entity_domain_associations SET attribution_entry_id=NEW.attribution_entry_id,attribution=NEW.attribution WHERE root_domain=NEW.root_domain AND entity_id=NEW.entity_id; END"
    )
    for table, column in (("domain_groups", "entity_id"), ("entries", "lead_id")):
        for action in ("INSERT", "UPDATE OF " + column):
            suffix = "insert" if action == "INSERT" else "update"
            db.execute(
                f"CREATE TRIGGER {table}_active_owner_{suffix} BEFORE {action} ON {table} WHEN EXISTS(SELECT 1 FROM leads WHERE id=NEW.{column} AND merged_into IS NOT NULL) BEGIN SELECT RAISE(ABORT,'Current ownership cannot target a merged business'); END"
            )
    for table in ("entity_lifecycle_events", "awareness_observation_owners"):
        key = "id" if table == "entity_lifecycle_events" else "observation_id"
        db.execute(
            f"CREATE TRIGGER {table}_immutable_replace BEFORE INSERT ON {table} WHEN EXISTS(SELECT 1 FROM {table} WHERE {key}=NEW.{key}) BEGIN SELECT RAISE(ABORT,'Recorded lifecycle evidence is immutable'); END"
        )
        for action in ("UPDATE", "DELETE"):
            db.execute(
                f"CREATE TRIGGER {table}_immutable_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'Recorded lifecycle evidence is immutable'); END"
            )
