"""Numbered, atomic SQLite upgrades. Source payloads and IDs remain unchanged."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from modules.investigations.databases.case_migration import schema_four
from modules.attribution.databases.asset_attribution_migration import migrate_asset_attributions

from modules.entities.databases.contact_migration import schema_eight
from modules.investigations.components.outreach_policy import migrate_outreach_policy
from modules.leads.databases.lead_queue_migration import schema_ten
from modules.accretion.databases.awareness_admission_migration import schema as schema_seventeen
from modules.investigations.databases.evidence_registry_migration import schema as schema_eighteen
from modules.entities.databases.lifecycle_migration import schema as schema_nineteen
from modules.observatory.components.analytical_index import schema as schema_twenty
from modules.accretion.databases.deconfliction import schema as schema_twenty_four

SCHEMA_VERSION = 24

LEGACY_SCHEMA = r"""
                
                CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS imports(
                  id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL,
                  name TEXT NOT NULL, path TEXT NOT NULL, created_at TEXT NOT NULL,
                  status TEXT NOT NULL DEFAULT 'queued', stage TEXT NOT NULL DEFAULT 'Queued',
                  message TEXT NOT NULL DEFAULT '', config TEXT NOT NULL,
                  rows_read INTEGER NOT NULL DEFAULT 0, valid_rows INTEGER NOT NULL DEFAULT 0,
                  rejected TEXT NOT NULL DEFAULT '{}', groups_total INTEGER NOT NULL DEFAULT 0,
                  groups_done INTEGER NOT NULL DEFAULT 0, qualified INTEGER NOT NULL DEFAULT 0,
                  error TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS jobs(
                  id TEXT PRIMARY KEY, import_id TEXT NOT NULL REFERENCES imports(id),
                  domain TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                  attempts TEXT NOT NULL DEFAULT '[]', error TEXT NOT NULL DEFAULT '',
                  UNIQUE(import_id,domain));
                CREATE TABLE IF NOT EXISTS leads(
                  id TEXT PRIMARY KEY, domain TEXT NOT NULL UNIQUE, company TEXT NOT NULL DEFAULT '',
                  status TEXT NOT NULL DEFAULT 'new', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                  attribution TEXT NOT NULL, attribution_entry_id TEXT NOT NULL,
                  draft TEXT NOT NULL DEFAULT '{}', draft_revision INTEGER NOT NULL DEFAULT 0,
                  new_observations INTEGER NOT NULL DEFAULT 0, demo INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS entries(
                  id TEXT PRIMARY KEY, lead_id TEXT NOT NULL REFERENCES leads(id),
                  import_id TEXT REFERENCES imports(id), payload TEXT NOT NULL,
                  ip TEXT NOT NULL, hostname TEXT NOT NULL, tag TEXT NOT NULL,
                  version TEXT NOT NULL, observed_at TEXT NOT NULL DEFAULT '');
                CREATE INDEX IF NOT EXISTS entries_lead ON entries(lead_id);
                CREATE TABLE IF NOT EXISTS evidence(
                  id TEXT PRIMARY KEY, lead_id TEXT NOT NULL REFERENCES leads(id),
                  kind TEXT NOT NULL, filename TEXT NOT NULL, path TEXT NOT NULL,
                  preview_path TEXT NOT NULL, caption TEXT NOT NULL, source_url TEXT NOT NULL,
                  captured_at TEXT NOT NULL, sha256 TEXT NOT NULL, included INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS reports(
                  id TEXT PRIMARY KEY, lead_id TEXT NOT NULL REFERENCES leads(id),
                  revision INTEGER NOT NULL, created_at TEXT NOT NULL, path TEXT NOT NULL,
                  sent_at TEXT, delivery_note TEXT NOT NULL DEFAULT '', UNIQUE(lead_id,revision));
                CREATE TABLE IF NOT EXISTS explainers(
                  id TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL,
                  sources TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS cache(
                  key TEXT PRIMARY KEY, payload TEXT NOT NULL, retrieved_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events(
                  id INTEGER PRIMARY KEY AUTOINCREMENT, lead_id TEXT, action TEXT NOT NULL,
                  detail TEXT NOT NULL, created_at TEXT NOT NULL);
                """


def _schema_one(db):
    for statement in LEGACY_SCHEMA.split(";"):
        if statement.strip():
            db.execute(statement)


def _schema_two(db):
    db.execute("ALTER TABLE leads ADD COLUMN merged_into TEXT REFERENCES leads(id)")
    db.execute("ALTER TABLE reports ADD COLUMN entity_id TEXT REFERENCES leads(id)")
    db.execute("UPDATE reports SET entity_id=lead_id")
    db.execute(
        "CREATE TABLE domain_groups(root_domain TEXT PRIMARY KEY, entity_id TEXT NOT NULL REFERENCES leads(id), attribution_entry_id TEXT NOT NULL, attribution TEXT NOT NULL)"
    )
    db.execute(
        "CREATE TABLE hostnames(name TEXT PRIMARY KEY, root_domain TEXT NOT NULL REFERENCES domain_groups(root_domain), entity_id TEXT NOT NULL REFERENCES leads(id))"
    )
    db.execute("CREATE INDEX hostnames_entity ON hostnames(entity_id)")
    for row in db.execute("SELECT * FROM leads").fetchall():
        db.execute(
            "INSERT INTO domain_groups VALUES(?,?,?,?)",
            (row["domain"], row["id"], row["attribution_entry_id"], row["attribution"]),
        )
        for entry in db.execute(
            "SELECT DISTINCT hostname FROM entries WHERE lead_id=?", (row["id"],)
        ).fetchall():
            db.execute(
                "INSERT OR IGNORE INTO hostnames VALUES(?,?,?)",
                (entry["hostname"], row["domain"], row["id"]),
            )
        if not row["company"]:
            primary = db.execute(
                "SELECT hostname FROM entries WHERE id=?", (row["attribution_entry_id"],)
            ).fetchone()
            db.execute(
                "UPDATE leads SET company=? WHERE id=?",
                (primary["hostname"] if primary else row["domain"], row["id"]),
            )


# Every reference in these definitions names the final table. Rebuilds run with
# foreign_keys disabled outside the transaction and are checked before commit.
SCHEMA_THREE = {
    "imports": """
      id TEXT PRIMARY KEY NOT NULL, fingerprint TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL,
      name TEXT NOT NULL, path TEXT NOT NULL, created_at TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','running','paused','needs_retry','done','error')),
      stage TEXT NOT NULL DEFAULT 'Queued', message TEXT NOT NULL DEFAULT '', config TEXT NOT NULL,
      rows_read INTEGER NOT NULL DEFAULT 0 CHECK(rows_read>=0),
      valid_rows INTEGER NOT NULL DEFAULT 0 CHECK(valid_rows>=0), rejected TEXT NOT NULL DEFAULT '{}',
      groups_total INTEGER NOT NULL DEFAULT 0 CHECK(groups_total>=0),
      groups_done INTEGER NOT NULL DEFAULT 0 CHECK(groups_done>=0),
      qualified INTEGER NOT NULL DEFAULT 0 CHECK(qualified>=0), error TEXT NOT NULL DEFAULT '' """,
    "jobs": """
      id TEXT PRIMARY KEY NOT NULL, import_id TEXT NOT NULL REFERENCES imports(id),
      domain TEXT NOT NULL, payload TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','qualified','deferred','no_public_ip','no_match','review','dismissed')),
      attempts TEXT NOT NULL DEFAULT '[]', error TEXT NOT NULL DEFAULT '',
      refresh_requested INTEGER NOT NULL DEFAULT 0 CHECK(refresh_requested IN (0,1)),
      attribution_result_id TEXT, UNIQUE(import_id,domain)""",
    "leads": """
      id TEXT PRIMARY KEY NOT NULL, domain TEXT NOT NULL UNIQUE, company TEXT NOT NULL DEFAULT '',
      status TEXT NOT NULL DEFAULT 'new' CHECK(status IN ('new','in_progress','completed','deferred')),
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL, attribution TEXT NOT NULL,
      attribution_entry_id TEXT NOT NULL REFERENCES entries(id) DEFERRABLE INITIALLY DEFERRED,
      draft TEXT NOT NULL DEFAULT '{}', draft_revision INTEGER NOT NULL DEFAULT 0 CHECK(draft_revision>=0),
      new_observations INTEGER NOT NULL DEFAULT 0 CHECK(new_observations>=0),
      demo INTEGER NOT NULL DEFAULT 0 CHECK(demo IN (0,1)), merged_into TEXT REFERENCES leads(id),
      CHECK(merged_into IS NULL OR merged_into!=id)""",
    "entries": """
      id TEXT PRIMARY KEY NOT NULL, lead_id TEXT NOT NULL REFERENCES leads(id),
      import_id TEXT REFERENCES imports(id), payload TEXT NOT NULL,
      ip TEXT NOT NULL, hostname TEXT NOT NULL, tag TEXT NOT NULL,
      version TEXT NOT NULL, observed_at TEXT NOT NULL DEFAULT '', root_domain TEXT NOT NULL,
      UNIQUE(id,root_domain),
      FOREIGN KEY(hostname,root_domain) REFERENCES hostnames(name,root_domain) DEFERRABLE INITIALLY DEFERRED,
      FOREIGN KEY(root_domain,lead_id) REFERENCES domain_groups(root_domain,entity_id) DEFERRABLE INITIALLY DEFERRED""",
    "domain_groups": """
      root_domain TEXT PRIMARY KEY NOT NULL, entity_id TEXT NOT NULL REFERENCES leads(id),
      attribution_entry_id TEXT NOT NULL REFERENCES entries(id) DEFERRABLE INITIALLY DEFERRED,
      attribution TEXT NOT NULL, UNIQUE(root_domain,entity_id),
      FOREIGN KEY(attribution_entry_id,root_domain) REFERENCES entries(id,root_domain) DEFERRABLE INITIALLY DEFERRED""",
    "hostnames": """
      name TEXT PRIMARY KEY NOT NULL, root_domain TEXT NOT NULL REFERENCES domain_groups(root_domain),
      UNIQUE(name,root_domain)""",
    "evidence": """
      id TEXT PRIMARY KEY NOT NULL, lead_id TEXT NOT NULL REFERENCES leads(id),
      kind TEXT NOT NULL, filename TEXT NOT NULL, path TEXT NOT NULL,
      preview_path TEXT NOT NULL, caption TEXT NOT NULL, source_url TEXT NOT NULL,
      captured_at TEXT NOT NULL, sha256 TEXT NOT NULL,
      included INTEGER NOT NULL DEFAULT 1 CHECK(included IN (0,1))""",
    "reports": """
      id TEXT PRIMARY KEY NOT NULL, lead_id TEXT NOT NULL REFERENCES leads(id),
      revision INTEGER NOT NULL CHECK(revision>=1), created_at TEXT NOT NULL, path TEXT NOT NULL,
      sent_at TEXT, delivery_note TEXT NOT NULL DEFAULT '',
      entity_id TEXT NOT NULL REFERENCES leads(id), UNIQUE(lead_id,revision)""",
    "explainers": """
      id TEXT PRIMARY KEY NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
      sources TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>=1), updated_at TEXT NOT NULL""",
    "attribution_reviews": """
      id TEXT PRIMARY KEY NOT NULL, job_id TEXT NOT NULL REFERENCES jobs(id),
      result_id TEXT NOT NULL, evidence_index INTEGER CHECK(evidence_index IS NULL OR evidence_index>=0),
      decision TEXT NOT NULL CHECK(decision IN ('accept','dismiss')),
      reviewer TEXT NOT NULL, note TEXT NOT NULL, reviewed_at TEXT NOT NULL,
      lead_id TEXT REFERENCES leads(id),
      CHECK((decision='accept' AND evidence_index IS NOT NULL AND lead_id IS NOT NULL)
         OR (decision='dismiss' AND lead_id IS NULL))""",
}

INDEXES = (
    ("entries_lead", "entries(lead_id)"),
    ("entries_import", "entries(import_id)"),
    ("entries_hostname", "entries(hostname,root_domain)"),
    ("entries_group_owner", "entries(root_domain,lead_id)"),
    ("domain_groups_entity", "domain_groups(entity_id)"),
    ("domain_groups_canonical", "domain_groups(lower(root_domain))"),
    ("hostnames_root", "hostnames(root_domain)"),
    ("leads_merged", "leads(merged_into)"),
    ("evidence_lead", "evidence(lead_id)"),
    ("reports_entity_created", "reports(entity_id,created_at DESC)"),
    ("reviews_job_time", "attribution_reviews(job_id,reviewed_at)"),
    ("reviews_result_time", "attribution_reviews(result_id,reviewed_at)"),
    ("jobs_import_status", "jobs(import_id,status)"),
    ("jobs_status", "jobs(status)"),
    ("jobs_domain_status", "jobs(lower(domain),status)"),
    ("events_lead_id", "events(lead_id,id DESC)"),
)


def _columns(db, table):
    return [row["name"] for row in db.execute(f"PRAGMA table_info({table})")]


def _schema_three(db):
    # 0.2.0 and 0.2.1 both recorded version 2. These are the only legacy
    # variants; compatibility detection stays inside this numbered migration.
    if "refresh_requested" not in _columns(db, "jobs"):
        db.execute("ALTER TABLE jobs ADD COLUMN refresh_requested INTEGER NOT NULL DEFAULT 0")
    db.execute("""CREATE TABLE IF NOT EXISTS attribution_reviews(
      id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id),
      result_id TEXT NOT NULL, evidence_index INTEGER, decision TEXT NOT NULL,
      reviewer TEXT NOT NULL, note TEXT NOT NULL, reviewed_at TEXT NOT NULL,
      lead_id TEXT REFERENCES leads(id))""")
    conflict = db.execute("""SELECT h.name FROM hostnames h
      LEFT JOIN domain_groups g ON g.root_domain=h.root_domain
      WHERE g.root_domain IS NULL OR h.entity_id!=g.entity_id LIMIT 1""").fetchone()
    if conflict:
        raise ValueError(
            f"Conflicting hostname ownership: {conflict['name']}; existing database was not changed"
        )
    db.execute("ALTER TABLE entries ADD COLUMN root_domain TEXT")
    db.execute(
        """UPDATE entries SET root_domain=(SELECT root_domain FROM hostnames WHERE name=entries.hostname)"""
    )
    db.execute("ALTER TABLE jobs ADD COLUMN attribution_result_id TEXT")
    for row in db.execute("SELECT id,attempts FROM jobs").fetchall():
        attempts = json.loads(row["attempts"])
        result_id = next((a.get("result_id") for a in attempts if a.get("result_id")), None)
        db.execute("UPDATE jobs SET attribution_result_id=? WHERE id=?", (result_id, row["id"]))
    for table, definition in SCHEMA_THREE.items():
        db.execute(f"CREATE TABLE {table}_new({definition})")
        columns = ",".join(_columns(db, table + "_new"))
        # Preserve rowid order as well as IDs, original row JSON, and history.
        db.execute(f"INSERT INTO {table}_new(rowid,{columns}) SELECT rowid,{columns} FROM {table}")
        db.execute(f"DROP TABLE {table}")
        db.execute(f"ALTER TABLE {table}_new RENAME TO {table}")
    for name, target in INDEXES:
        db.execute(f"CREATE INDEX {name} ON {target}")
    conflict = db.execute("""SELECT l.id FROM leads l JOIN entries e ON e.id=l.attribution_entry_id
      JOIN domain_groups g ON g.root_domain=e.root_domain
      WHERE l.merged_into IS NULL AND g.entity_id!=l.id LIMIT 1""").fetchone()
    if conflict:
        raise ValueError(
            "Attribution entry belongs to a different entity; existing database was not changed"
        )


def schema_five(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS entity_profiles(entity_id TEXT PRIMARY KEY REFERENCES leads(id), payload TEXT NOT NULL DEFAULT '{}')"
    )
    for row in db.execute("SELECT id,draft FROM leads").fetchall():
        drafts = [json.loads(row["draft"])]
        drafts += [
            json.loads(c["draft"])
            for c in db.execute(
                "SELECT draft FROM cases WHERE entity_id=? ORDER BY updated_at", (row["id"],)
            ).fetchall()
        ]
        profile = {}
        for draft in drafts:
            for key in (
                "contact_name",
                "contact_title",
                "contact_email",
                "address",
                "city",
                "state",
            ):
                if draft.get(key):
                    profile[key] = draft[key]
        db.execute(
            "INSERT OR IGNORE INTO entity_profiles VALUES(?,?)", (row["id"], json.dumps(profile))
        )


def schema_six(db):
    # Existing cases deliberately receive no retrospective certifications.
    db.execute("""CREATE TABLE section_validations (
      id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id),
      section_key TEXT NOT NULL, revision INTEGER NOT NULL,
      validated_at TEXT NOT NULL, validated_by TEXT NOT NULL,
      content_hash TEXT NOT NULL, snapshot_json TEXT NOT NULL,
      UNIQUE(case_id, section_key, revision))""")
    db.execute("""CREATE TABLE section_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL REFERENCES cases(id),
      section_key TEXT NOT NULL, action TEXT NOT NULL,
      actor TEXT NOT NULL, created_at TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '',
      revision INTEGER NOT NULL, validation_id TEXT REFERENCES section_validations(id),
      dependency_hash TEXT NOT NULL DEFAULT '')""")
    db.execute("CREATE INDEX section_event_case ON section_events(case_id, section_key, id)")
    # The application appends revisions; database-level guards protect the audit
    # record even if a future route accidentally attempts an in-place change.
    for table in ("section_validations", "section_events"):
        for operation in ("UPDATE", "DELETE"):
            db.execute(f"""CREATE TRIGGER immutable_{table}_{operation.lower()}
              BEFORE {operation} ON {table} BEGIN
              SELECT RAISE(ABORT, 'Section certification history is immutable'); END""")


def schema_seven(db):
    db.execute("""CREATE TABLE IF NOT EXISTS entity_field_reviews (
      entity_id TEXT NOT NULL REFERENCES leads(id),
      field TEXT NOT NULL CHECK(field IN ('name','address','city','state')),
      status TEXT NOT NULL CHECK(status IN ('pending','confirmed','ignored')),
      value_hash TEXT NOT NULL, reviewed_by TEXT NOT NULL, reviewed_at TEXT NOT NULL,
      PRIMARY KEY(entity_id, field))""")
    migrate_asset_attributions(db)


def schema_nine(db):
    migrate_outreach_policy(db)
    columns = {row[1] for row in db.execute("PRAGMA table_info(events)")}
    if "actor" not in columns:
        db.execute("ALTER TABLE events ADD COLUMN actor TEXT NOT NULL DEFAULT ''")
    if "metadata" not in columns:
        db.execute("ALTER TABLE events ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}'")
    db.execute("CREATE INDEX IF NOT EXISTS events_case_id ON events(case_id,id)")
    db.execute("CREATE INDEX IF NOT EXISTS events_entity_id ON events(lead_id,id)")
    db.execute("CREATE INDEX IF NOT EXISTS events_action_id ON events(action,id)")
    db.execute("CREATE INDEX IF NOT EXISTS cases_stage_activity ON cases(stage,updated_at,id)")
    db.execute("CREATE INDEX IF NOT EXISTS leads_activity ON leads(updated_at,id)")
    db.execute("CREATE INDEX IF NOT EXISTS entries_entity_observed ON entries(lead_id,observed_at)")


def schema_eleven(db):
    # Both paths are called for each incoming group; unindexed lookups make
    # import association grow with every previously retained observation.
    db.execute("CREATE INDEX entries_ip_owner ON entries(ip,lead_id)")
    db.execute("CREATE INDEX hostnames_name_lower ON hostnames(lower(name))")
    db.execute(
        "CREATE INDEX IF NOT EXISTS domain_groups_canonical ON domain_groups(lower(root_domain))"
    )


def schema_twelve(db):
    # Existing work remains unscored; only new Accretion evaluations populate
    # these snapshots. In particular, migration does not recertify old reports.
    db.execute("ALTER TABLE lead_queue ADD COLUMN intake_score TEXT NOT NULL DEFAULT '{}'")
    db.execute("ALTER TABLE cases ADD COLUMN intake_score TEXT NOT NULL DEFAULT '{}'")


def schema_thirteen(db):
    for column in ("observation_day", "signal_hash", "superseded_by", "suppression_reason"):
        db.execute(f"ALTER TABLE lead_queue ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
    db.execute("ALTER TABLE lead_queue ADD COLUMN delta TEXT NOT NULL DEFAULT '{}'")
    db.execute(
        "CREATE INDEX lead_queue_current_entity ON lead_queue(entity_id,qualified,status,superseded_by,observation_day)"
    )
    db.execute(
        "CREATE TABLE entity_contact_queue(entity_id TEXT PRIMARY KEY REFERENCES leads(id), status TEXT NOT NULL DEFAULT 'pending', updated_at TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '')"
    )
    db.execute("CREATE INDEX entity_contacts_pending ON entity_contact_queue(status,updated_at)")
    db.execute(
        "INSERT INTO entity_contact_queue(entity_id) SELECT id FROM leads WHERE merged_into IS NULL AND demo=0 AND NOT EXISTS(SELECT 1 FROM contact_runs WHERE entity_id=leads.id)"
    )


def schema_fourteen(db):
    from modules.entities.components.registry_profile import migrate as migrate_registry_profiles

    migrate_registry_profiles(db)
    db.execute("ALTER TABLE entity_contact_queue ADD COLUMN mode TEXT NOT NULL DEFAULT 'initial'")


def schema_fifteen(db):
    from modules.accretion.databases.awareness_migration import schema

    schema(db)


def schema_sixteen(db):
    # Preparation is private case work, not a report revision or delivery event.
    # No existing report, source, or case draft is rewritten during migration.
    db.execute(
        """CREATE TABLE IF NOT EXISTS outreach_preparations(
          case_id TEXT PRIMARY KEY NOT NULL REFERENCES cases(id),
          revision INTEGER NOT NULL CHECK(revision>=1),
          subject TEXT NOT NULL, message TEXT NOT NULL, call_outline TEXT NOT NULL,
          context_json TEXT NOT NULL, context_hash TEXT NOT NULL,
          updated_at TEXT NOT NULL, updated_by TEXT NOT NULL)"""
    )


def schema_twenty_one(db):
    from modules.accretion.databases.dark_matter_schema import create_workspace_outbox

    create_workspace_outbox(db)
    db.execute("DROP TABLE IF EXISTS intake_observations")


def schema_twenty_two(db):
    from modules.investigations.databases.website_capture_schema import schema

    schema(db)
    db.execute("ALTER TABLE jobs ADD COLUMN qualification TEXT NOT NULL DEFAULT '{}'")


def schema_twenty_three(db):
    from modules.library.databases.content_schema import schema as content_schema
    from modules.library.databases.research_schema import schema as research_schema

    content_schema(db)
    research_schema(db)


MIGRATIONS = {
    1: _schema_one,
    2: _schema_two,
    3: _schema_three,
    4: schema_four,
    5: schema_five,
    6: schema_six,
    7: schema_seven,
    8: schema_eight,
    9: schema_nine,
    10: schema_ten,
    11: schema_eleven,
    12: schema_twelve,
    13: schema_thirteen,
    14: schema_fourteen,
    15: schema_fifteen,
    16: schema_sixteen,
    17: schema_seventeen,
    18: schema_eighteen,
    19: schema_nineteen,
    20: schema_twenty,
    21: schema_twenty_one,
    22: schema_twenty_two,
    23: schema_twenty_three,
    24: schema_twenty_four,
}


def migrate(db: sqlite3.Connection, backup_dir: Path):
    """Upgrade once, back up existing records, and roll back the whole upgrade on failure."""
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version not in range(SCHEMA_VERSION + 1):
        raise ValueError(
            f"Unsupported workbench database version {version}; supported through {SCHEMA_VERSION}"
        )
    if version == SCHEMA_VERSION:
        return
    existing = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' LIMIT 1"
    ).fetchone()
    if existing:
        backup_dir.mkdir(parents=True, exist_ok=True)
        with closing(
            sqlite3.connect(
                backup_dir / f"before-schema-{SCHEMA_VERSION}-{uuid4().hex[:8]}.sqlite3"
            )
        ) as backup:
            db.backup(backup)
    db.execute("PRAGMA foreign_keys=OFF")
    try:
        db.execute("BEGIN IMMEDIATE")
        for target in range(version + 1, SCHEMA_VERSION + 1):
            MIGRATIONS[target](db)
            db.execute(f"PRAGMA user_version={target}")
        violations = db.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise ValueError(
                f"Database migration found {len(violations)} invalid references; existing database was not changed"
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.execute("PRAGMA foreign_keys=ON")
