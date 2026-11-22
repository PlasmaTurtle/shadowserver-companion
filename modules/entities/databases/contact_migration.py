"""Schema 8: append-only discovery evidence and independently reviewed contacts."""


def schema_eight(db):
    for statement in (
        """CREATE TABLE contact_runs(
          id TEXT PRIMARY KEY, entity_id TEXT NOT NULL REFERENCES leads(id),
          original_entity_id TEXT NOT NULL REFERENCES leads(id), root_domain TEXT NOT NULL,
          status TEXT NOT NULL, scope TEXT NOT NULL, limits_json TEXT NOT NULL,
          payload TEXT NOT NULL, created_at TEXT NOT NULL, finished_at TEXT NOT NULL)""",
        "CREATE INDEX contact_runs_entity ON contact_runs(entity_id,created_at)",
        """CREATE TABLE contact_candidates(
          id TEXT PRIMARY KEY, entity_id TEXT NOT NULL REFERENCES leads(id),
          root_domain TEXT NOT NULL, candidate_key TEXT NOT NULL, payload TEXT NOT NULL,
          revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>=1),
          decision TEXT NOT NULL DEFAULT 'pending' CHECK(decision IN ('pending','confirmed','ignored')),
          reviewed_by TEXT NOT NULL DEFAULT '', reviewed_at TEXT NOT NULL DEFAULT '',
          first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
          latest_run_id TEXT NOT NULL REFERENCES contact_runs(id),
          missing_from_latest INTEGER NOT NULL DEFAULT 0 CHECK(missing_from_latest IN (0,1)),
          UNIQUE(entity_id,root_domain,candidate_key))""",
        """CREATE TABLE contact_sources(
          candidate_id TEXT NOT NULL REFERENCES contact_candidates(id),
          run_id TEXT NOT NULL REFERENCES contact_runs(id), payload TEXT NOT NULL,
          PRIMARY KEY(candidate_id,run_id))""",
        """CREATE TABLE contact_reviews(
          id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL REFERENCES contact_candidates(id),
          revision INTEGER NOT NULL, action TEXT NOT NULL, actor TEXT NOT NULL,
          created_at TEXT NOT NULL, detail TEXT NOT NULL)""",
        """CREATE TABLE contact_discovery_locks(
          entity_id TEXT PRIMARY KEY REFERENCES leads(id), job_id TEXT NOT NULL)""",
    ):
        db.execute(statement)
    for operation in ("UPDATE", "DELETE"):
        db.execute(f"""CREATE TRIGGER immutable_contact_reviews_{operation.lower()}
          BEFORE {operation} ON contact_reviews BEGIN
          SELECT RAISE(ABORT, 'Contact review history is immutable'); END""")
