"""Retained website captures exist before an entity or notification is created."""


def schema(db):
    db.execute("""CREATE TABLE website_captures(
        id TEXT PRIMARY KEY NOT NULL,
        root_domain TEXT NOT NULL,
        requested_url TEXT NOT NULL,
        final_url TEXT NOT NULL,
        capture_status TEXT NOT NULL,
        captured_at TEXT NOT NULL,
        path TEXT NOT NULL UNIQUE,
        preview_path TEXT NOT NULL UNIQUE,
        metadata_path TEXT NOT NULL UNIQUE,
        sha256 TEXT NOT NULL,
        preview_sha256 TEXT NOT NULL,
        metadata_sha256 TEXT NOT NULL
    )""")
    db.execute("""CREATE TABLE website_capture_entities(
        capture_id TEXT NOT NULL REFERENCES website_captures(id),
        entity_id TEXT NOT NULL REFERENCES leads(id),
        PRIMARY KEY(capture_id,entity_id)
    )""")
    db.execute("CREATE INDEX website_capture_entity ON website_capture_entities(entity_id)")
    db.execute("""CREATE TABLE website_capture_cases(
        capture_id TEXT NOT NULL REFERENCES website_captures(id),
        case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
        evidence_id TEXT NOT NULL UNIQUE REFERENCES evidence(id) ON DELETE CASCADE,
        PRIMARY KEY(capture_id,case_id)
    )""")
