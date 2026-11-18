"""Atomic evidence-store migrations, preserving captured bytes and result JSON."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

SCHEMA_VERSION = 2


def _schema_one(db):
    for sql in (
        'CREATE TABLE IF NOT EXISTS snapshots(id TEXT PRIMARY KEY, metadata TEXT NOT NULL, body BLOB NOT NULL)',
        'CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, snapshot_ids TEXT NOT NULL, expires REAL NOT NULL)',
        'CREATE TABLE IF NOT EXISTS cooldowns(authority TEXT PRIMARY KEY, retry_at REAL NOT NULL)',
        'CREATE TABLE IF NOT EXISTS results(id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL)',
    ):
        db.execute(sql)


def result_metadata(payload):
    data = json.loads(payload)
    policy = data.get('policy', {})
    # Policy IDs already contain the version (e.g. root-domain-v2).
    # Custom policies without an ID remain NULL; never invent their version.
    return data['root_domain'], data['status'], policy.get('id')


def _schema_two(db):
    db.execute('''CREATE TABLE results_new(
      id TEXT PRIMARY KEY NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL CHECK(json_valid(payload)),
      root_domain TEXT NOT NULL, status TEXT NOT NULL
        CHECK(status IN ('matched','review','no_match','incomplete','deferred','no_eligible_ip')),
      policy_version TEXT,
      CHECK(json_extract(payload,'$.result_id') IS id),
      CHECK(json_extract(payload,'$.evaluated_at') IS created_at),
      CHECK(json_extract(payload,'$.root_domain') IS root_domain),
      CHECK(json_extract(payload,'$.status') IS status),
      CHECK(json_extract(payload,'$.policy.id') IS policy_version))''')
    for row in db.execute('SELECT rowid,* FROM results'):
        db.execute('INSERT INTO results_new(rowid,id,created_at,payload,root_domain,status,policy_version) VALUES(?,?,?,?,?,?,?)',
                   (row['rowid'], row['id'], row['created_at'], row['payload'], *result_metadata(row['payload'])))
    db.execute('DROP TABLE results')
    db.execute('ALTER TABLE results_new RENAME TO results')
    db.execute('CREATE INDEX results_created ON results(created_at DESC)')
    db.execute('CREATE INDEX results_domain_created ON results(root_domain,created_at DESC)')
    db.execute('CREATE INDEX results_status_created ON results(status,created_at DESC)')


MIGRATIONS = {1: _schema_one, 2: _schema_two}


def migrate(db: sqlite3.Connection, path: str):
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version not in range(SCHEMA_VERSION + 1):
        raise ValueError(f'Unsupported attribution database version {version}; supported through {SCHEMA_VERSION}')
    if version == SCHEMA_VERSION:
        return
    existing = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' LIMIT 1").fetchone()
    if existing and path != ':memory:':
        folder = Path(path).parent / 'backups'
        folder.mkdir(parents=True, exist_ok=True)
        backup = folder / f'attribution-before-schema-{SCHEMA_VERSION}-{uuid4().hex[:8]}.sqlite3'
        with closing(sqlite3.connect(backup)) as target:
            db.backup(target)
    try:
        db.execute('BEGIN IMMEDIATE')
        for target in range(version + 1, SCHEMA_VERSION + 1):
            MIGRATIONS[target](db)
            db.execute(f'PRAGMA user_version={target}')
        db.commit()
    except Exception:
        db.rollback()
        raise
