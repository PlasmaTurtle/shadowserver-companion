"""Dark Matter owns its independent archive and its durable delivery queue."""

SCHEMA_VERSION = 1


def create_workspace_outbox(db):
    db.execute("""CREATE TABLE IF NOT EXISTS dark_matter_outbox(
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL UNIQUE,
        operation TEXT NOT NULL CHECK(operation IN ('records','outcome')),
        payload TEXT NOT NULL,
        recorded_at TEXT NOT NULL)""")


def create_archive(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS sources(
            import_id TEXT PRIMARY KEY,
            source_sha256 TEXT NOT NULL,
            name TEXT NOT NULL,
            path TEXT NOT NULL,
            metadata TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS records(
            record_id TEXT PRIMARY KEY,
            source_sha256 TEXT NOT NULL,
            sheet TEXT NOT NULL,
            row_number INTEGER NOT NULL,
            import_id TEXT NOT NULL REFERENCES sources(import_id),
            report_type TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            raw_fields TEXT NOT NULL,
            normalized_fields TEXT NOT NULL,
            errors TEXT NOT NULL,
            hostname TEXT,
            ip TEXT,
            root_domain TEXT NOT NULL,
            region TEXT,
            port INTEGER,
            asn INTEGER,
            observed_at TEXT,
            stage TEXT NOT NULL,
            outcome TEXT NOT NULL,
            reason TEXT NOT NULL,
            promoted INTEGER NOT NULL DEFAULT 0,
            recorded_at TEXT NOT NULL,
            updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS outcomes(
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            record_id TEXT NOT NULL REFERENCES records(record_id),
            import_id TEXT NOT NULL,
            stage TEXT NOT NULL,
            outcome TEXT NOT NULL,
            reason TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            UNIQUE(event_id,record_id));
        CREATE TABLE IF NOT EXISTS delivered_events(event_id TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS observed_fields(
            report_type TEXT NOT NULL,
            name TEXT NOT NULL,
            PRIMARY KEY(report_type,name));
        CREATE TABLE IF NOT EXISTS archive_state(
            id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER NOT NULL);
        INSERT OR IGNORE INTO archive_state VALUES(1,0);
        CREATE INDEX IF NOT EXISTS records_current ON records(promoted,outcome,updated_at);
        CREATE INDEX IF NOT EXISTS records_report ON records(report_type,updated_at);
        CREATE INDEX IF NOT EXISTS records_ip ON records(ip);
        CREATE INDEX IF NOT EXISTS records_root ON records(root_domain);
        CREATE INDEX IF NOT EXISTS records_region ON records(region);
        CREATE INDEX IF NOT EXISTS records_time ON records(observed_at);
        CREATE INDEX IF NOT EXISTS records_stage_reason ON records(stage,reason);
        CREATE INDEX IF NOT EXISTS outcomes_record ON outcomes(record_id,sequence);
    """)
    db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
