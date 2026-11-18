"""Schema 18: retain source revisions and strengthen ownership boundaries."""

from pathlib import Path

from .aegis.json import strict_json_loads
from .evidence_registry import FAMILIES, register_revision

JSON_COLUMNS = (
    ("cases", "draft", "object"),
    ("cases", "entity_snapshot", "object"),
    ("leads", "draft", "object"),
    ("leads", "attribution", "object"),
    ("entity_profiles", "payload", "object"),
    ("outreach_preparations", "context_json", "object"),
    ("events", "metadata", "object"),
    ("section_validations", "snapshot_json", "object"),
    ("cache", "payload", None),
)


def _json_guards(db):
    for table, column, shape in JSON_COLUMNS:
        if column not in {r[1] for r in db.execute(f"PRAGMA table_info({table})")}:
            continue
        for row in db.execute(f"SELECT {column} FROM {table}"):
            try:
                strict_json_loads(
                    row[0], max_bytes=256 * 1024 * 1024, require_object=shape == "object"
                )
            except (ValueError, TypeError) as error:
                raise ValueError(
                    f"Cannot upgrade: {table}.{column} contains invalid JSON; restore or review the original data"
                ) from error
        condition = f"NOT json_valid(NEW.{column})"
        if shape:
            condition += f" OR json_type(NEW.{column})!='{shape}'"
        for operation in ("INSERT", "UPDATE"):
            clause = operation if operation == "INSERT" else f"UPDATE OF {column}"
            db.execute(f"""CREATE TRIGGER valid_json_{table}_{column}_{operation.lower()}
                BEFORE {clause} ON {table} WHEN {condition}
                BEGIN SELECT RAISE(ABORT,'Invalid server-owned JSON'); END""")


def _ownership(db):
    orphan = db.execute("""SELECT 1 FROM case_entry_conditions c LEFT JOIN case_entries e
        ON e.case_id=c.case_id AND e.entry_id=c.entry_id WHERE e.entry_id IS NULL LIMIT 1""").fetchone()
    if orphan:
        raise ValueError("Cannot upgrade: case condition scope is not owned by its case")
    for row in db.execute("SELECT conditions FROM case_entry_conditions"):
        if not isinstance(strict_json_loads(row[0]), list):
            raise ValueError("Cannot upgrade: case condition scope must be a JSON array")
    mismatch = db.execute("""SELECT 1 FROM section_events e LEFT JOIN section_validations v
        ON v.id=e.validation_id AND v.case_id=e.case_id AND v.section_key=e.section_key
        WHERE e.validation_id IS NOT NULL AND v.id IS NULL LIMIT 1""").fetchone()
    if mismatch:
        raise ValueError("Cannot upgrade: section event references a different case or section")
    db.execute("""CREATE TABLE case_entry_conditions_v18(
        case_id TEXT NOT NULL REFERENCES cases(id),entry_id TEXT NOT NULL REFERENCES entries(id),
        conditions TEXT NOT NULL CHECK(json_valid(conditions) AND json_type(conditions)='array'),
        PRIMARY KEY(case_id,entry_id),
        FOREIGN KEY(case_id,entry_id) REFERENCES case_entries(case_id,entry_id))""")
    db.execute("INSERT INTO case_entry_conditions_v18 SELECT * FROM case_entry_conditions")
    db.execute("DROP TABLE case_entry_conditions")
    db.execute("ALTER TABLE case_entry_conditions_v18 RENAME TO case_entry_conditions")
    db.execute(
        "CREATE UNIQUE INDEX section_validation_identity ON section_validations(id,case_id,section_key)"
    )
    db.execute("""CREATE TABLE section_events_v18(
        id INTEGER PRIMARY KEY AUTOINCREMENT,case_id TEXT NOT NULL REFERENCES cases(id),
        section_key TEXT NOT NULL,action TEXT NOT NULL,actor TEXT NOT NULL,created_at TEXT NOT NULL,
        reason TEXT NOT NULL DEFAULT '',revision INTEGER NOT NULL,validation_id TEXT,
        dependency_hash TEXT NOT NULL DEFAULT '',
        FOREIGN KEY(validation_id,case_id,section_key) REFERENCES section_validations(id,case_id,section_key))""")
    sequence = db.execute("SELECT seq FROM sqlite_sequence WHERE name='section_events'").fetchone()
    db.execute("INSERT INTO section_events_v18 SELECT * FROM section_events")
    db.execute("DROP TABLE section_events")
    db.execute("ALTER TABLE section_events_v18 RENAME TO section_events")
    if sequence:
        db.execute(
            "UPDATE sqlite_sequence SET seq=MAX(seq,?) WHERE name='section_events'", (sequence[0],)
        )
    db.execute("CREATE INDEX section_event_case ON section_events(case_id,section_key,id)")
    _immutable(db, "section_events", "Section certification history is immutable")
    _replace_guard(
        db,
        "section_validations",
        "id=NEW.id OR (case_id=NEW.case_id AND section_key=NEW.section_key AND revision=NEW.revision)",
    )


def _immutable(db, table, message="Evidence registry is immutable"):
    keys = [row[1] for row in db.execute(f"PRAGMA table_info({table})") if row[5]]
    _replace_guard(db, table, " AND ".join(f"{key}=NEW.{key}" for key in keys))
    for operation in ("UPDATE", "DELETE"):
        db.execute(f"""CREATE TRIGGER immutable_{table}_{operation.lower()}
            BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'{message}'); END""")


def _replace_guard(db, table, predicate):
    # SQLite REPLACE can bypass DELETE triggers when recursive_triggers is off.
    db.execute(f"""CREATE TRIGGER immutable_{table}_replace BEFORE INSERT ON {table}
        WHEN EXISTS(SELECT 1 FROM {table} WHERE {predicate})
        BEGIN SELECT RAISE(ABORT,'Immutable history cannot be replaced'); END""")


def _revisions(db):
    db.execute("""CREATE TABLE evidence_revisions(
        key TEXT PRIMARY KEY NOT NULL,family TEXT NOT NULL CHECK(family IN('cve-version','risk-version','intelligence-version','acquisition-version')),
        revision_id TEXT NOT NULL CHECK(length(revision_id)>0),provider TEXT NOT NULL,
        payload TEXT NOT NULL CHECK(json_valid(payload) AND json_type(payload)='object'),
        payload_sha256 TEXT NOT NULL CHECK(length(payload_sha256)=64 AND payload_sha256 NOT GLOB '*[^0-9a-f]*'),
        retrieved_at TEXT NOT NULL, UNIQUE(family,revision_id), CHECK(key=family||':'||revision_id))""")
    db.execute(
        "CREATE INDEX evidence_revision_provider ON evidence_revisions(family,provider,retrieved_at)"
    )
    db.execute("""CREATE TABLE evidence_captures(
        id TEXT PRIMARY KEY NOT NULL CHECK(length(id)=64 AND id NOT GLOB '*[^0-9a-f]*'),path TEXT NOT NULL,sha256 TEXT,
        provider TEXT NOT NULL,media_type TEXT NOT NULL,captured_at TEXT NOT NULL,
        binding_state TEXT NOT NULL CHECK(binding_state IN('declared_digest','legacy_unknown')),
        CHECK(sha256 IS NULL OR (length(sha256)=64 AND sha256 NOT GLOB '*[^0-9a-f]*')),
        CHECK((binding_state='legacy_unknown')=(sha256 IS NULL)))""")
    db.execute("CREATE INDEX evidence_capture_path ON evidence_captures(path)")
    db.execute("""CREATE TABLE evidence_revision_captures(
        revision_key TEXT NOT NULL REFERENCES evidence_revisions(key),
        capture_id TEXT NOT NULL REFERENCES evidence_captures(id),PRIMARY KEY(revision_key,capture_id))""")
    db.execute(
        "CREATE INDEX evidence_capture_revisions ON evidence_revision_captures(capture_id,revision_key)"
    )
    for family in sorted(FAMILIES):
        for row in db.execute("SELECT * FROM cache WHERE key GLOB ?", (family + ":*",)).fetchall():
            register_revision(
                db, row["key"], row["payload"], row["retrieved_at"], strict_insert=True
            )
        db.execute("DELETE FROM cache WHERE key GLOB ?", (family + ":*",))
    for table in ("evidence_revisions", "evidence_captures", "evidence_revision_captures"):
        _immutable(db, table)
    predicate = " OR ".join(f"NEW.key GLOB '{family}:*'" for family in sorted(FAMILIES))
    for operation in ("INSERT", "UPDATE"):
        db.execute(f"""CREATE TRIGGER cache_no_revisions_{operation.lower()} BEFORE {operation} ON cache
            WHEN {predicate} BEGIN SELECT RAISE(ABORT,'Immutable revisions belong in the evidence registry'); END""")


def schema(db):
    """The caller owns the atomic migration transaction and foreign-key check."""
    _ownership(db)
    _json_guards(db)
    _revisions(db)
    from .artifact_registry import create_schema, backfill

    create_schema(db)
    location = next((row[2] for row in db.execute("PRAGMA database_list") if row[1] == "main"), "")
    backfill(db, Path(location).parent if location else None)
