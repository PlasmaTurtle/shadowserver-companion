"""Workspace-backed Library research preferences; caller owns migration transaction."""


def schema(db):
    db.execute("""CREATE TABLE library_saved_views(
        id TEXT PRIMARY KEY NOT NULL,
        name TEXT NOT NULL,
        selection TEXT NOT NULL CHECK(json_valid(selection)),
        revision INTEGER NOT NULL CHECK(revision>=1),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        import_key TEXT UNIQUE)""")
