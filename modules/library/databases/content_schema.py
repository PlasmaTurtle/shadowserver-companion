"""Retain explainer revisions without reconstructing unavailable historical wording."""

import json


def schema(db):
    """Apply within the caller's transaction; preserve existing current rows and cache."""
    db.execute("""CREATE TABLE explainer_state(
        block_id TEXT PRIMARY KEY NOT NULL REFERENCES explainers(id),
        archived_at TEXT NOT NULL DEFAULT '')""")
    db.execute("""CREATE TABLE explainer_revisions(
        block_id TEXT NOT NULL REFERENCES explainers(id),
        revision INTEGER NOT NULL CHECK(revision>=1),
        title TEXT NOT NULL, body TEXT NOT NULL, sources TEXT NOT NULL,
        source_metadata TEXT NOT NULL CHECK(json_valid(source_metadata)),
        updated_at TEXT NOT NULL, actor TEXT NOT NULL DEFAULT '',
        action TEXT NOT NULL, restored_from INTEGER,
        archived_at TEXT NOT NULL DEFAULT '',
        PRIMARY KEY(block_id,revision))""")
    for row in db.execute("SELECT * FROM explainers").fetchall():
        metadata = db.execute(
            "SELECT payload FROM cache WHERE key=?",
            (f"block-sources:{row['id']}:{row['revision']}",),
        ).fetchone()
        citations = json.loads(metadata[0]) if metadata else []
        if not isinstance(citations, list):
            raise ValueError("Explainer citation metadata must be a list")
        db.execute("INSERT INTO explainer_state(block_id) VALUES(?)", (row["id"],))
        db.execute(
            """INSERT INTO explainer_revisions
            (block_id,revision,title,body,sources,source_metadata,updated_at,action)
            VALUES(?,?,?,?,?,?,?,'legacy_current')""",
            (
                *[row[key] for key in ("id", "revision", "title", "body", "sources")],
                json.dumps(citations, ensure_ascii=False, allow_nan=False),
                row["updated_at"],
            ),
        )
    for operation in ("UPDATE", "DELETE"):
        db.execute(
            f"""CREATE TRIGGER explainer_revisions_no_{operation.lower()}
            BEFORE {operation} ON explainer_revisions BEGIN
            SELECT RAISE(ABORT,'Explainer revisions are immutable'); END"""
        )
