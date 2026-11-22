"""Build genuine earlier schemas from current test records, without dropping new constraints."""

import sqlite3
from contextlib import closing

from modules.workspace.databases.migrations import _schema_one, _schema_two, _schema_three


def schema_snapshot(source, version):
    """Build the actual historical schema, then copy only its retained columns.

    Later constraints and triggers cannot be simulated by dropping a few tables.
    The copied rows keep their IDs and rowids; source files are never touched.
    """
    from modules.workspace.databases.migrations import MIGRATIONS

    old = sqlite3.connect(":memory:")
    old.row_factory = sqlite3.Row
    old.execute("PRAGMA foreign_keys=OFF")
    try:
        for target in range(1, version + 1):
            MIGRATIONS[target](old)
        source_tables = {
            row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        source_rowid_tables = {row[1] for row in source.execute("PRAGMA table_list") if not row[4]}
        old_rowid_tables = {row[1] for row in old.execute("PRAGMA table_list") if not row[4]}
        tables = [
            row[0]
            for row in old.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        for table in tables:
            if table not in source_tables:
                continue
            old_columns = [row[1] for row in old.execute('PRAGMA table_info("' + table + '")')]
            source_columns = {
                row[1] for row in source.execute('PRAGMA table_info("' + table + '")')
            }
            columns = [name for name in old_columns if name in source_columns]
            names = ",".join('"' + name + '"' for name in columns)
            # Newer schemas can use WITHOUT ROWID. Preserve rowids only when
            # both versions have them; declared primary keys always survive.
            copied_names = (
                "rowid," if table in source_rowid_tables & old_rowid_tables else ""
            ) + names
            marks = ",".join("?" for _ in range(len(columns) + (copied_names != names)))
            old.execute('DELETE FROM "' + table + '"')
            for row in source.execute("SELECT " + copied_names + ' FROM "' + table + '"'):
                old.execute(
                    'INSERT INTO "' + table + '"(' + copied_names + ") VALUES(" + marks + ")",
                    tuple(row),
                )
        old.execute(f"PRAGMA user_version={version}")
        old.commit()
        return old
    except Exception:
        old.close()
        raise


def restore_schema(db, version):
    """Replace a test fixture with a genuine earlier schema before upgrading it."""
    with closing(schema_snapshot(db, version)) as old:
        # SQLite backup requires the destination outside a transaction. This is
        # test fixture construction, before the migration under examination.
        db.commit()
        old.backup(db)


def remove_awareness_schema(db):
    restore_schema(db, 14)


def remove_intake_schema(db):
    restore_schema(db, 9)


def remove_empty_contact_schema(db):
    restore_schema(db, 7)


def legacy_database(store, version=2, review_columns=False):
    with closing(sqlite3.connect(":memory:")) as old, closing(store.connect()) as source:
        old.row_factory = sqlite3.Row
        _schema_one(old)
        if version >= 2:
            _schema_two(old)
        if version >= 3:
            _schema_three(old)
        if review_columns and version < 3:
            old.execute("ALTER TABLE jobs ADD COLUMN refresh_requested INTEGER NOT NULL DEFAULT 0")
            old.execute("""CREATE TABLE attribution_reviews(
              id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id), result_id TEXT NOT NULL,
              evidence_index INTEGER, decision TEXT NOT NULL, reviewer TEXT NOT NULL,
              note TEXT NOT NULL, reviewed_at TEXT NOT NULL, lead_id TEXT REFERENCES leads(id))""")
        tables = [
            r[0]
            for r in old.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        for table in tables:
            columns = [r["name"] for r in old.execute(f"PRAGMA table_info({table})")]
            names, marks = ",".join(columns), ",".join("?" for _ in columns)
            for row in source.execute(f"SELECT rowid AS original_rowid,* FROM {table}"):
                values = dict(row)
                if table == "hostnames":
                    values["entity_id"] = source.execute(
                        "SELECT entity_id FROM domain_groups WHERE root_domain=?",
                        (row["root_domain"],),
                    ).fetchone()[0]
                old.execute(
                    f"INSERT INTO {table}(rowid,{names}) VALUES(?,{marks})",
                    (row["original_rowid"], *(values[c] for c in columns)),
                )
        old.execute(f"PRAGMA user_version={version}")
        old.commit()
        old.backup(source)
