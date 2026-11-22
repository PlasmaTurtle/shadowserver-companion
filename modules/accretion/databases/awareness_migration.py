"""Canonical observations and findings created only by Associate."""


def schema(db):
    statements = (
        """CREATE TABLE awareness_assets(
          id TEXT PRIMARY KEY,asset_key TEXT NOT NULL UNIQUE,hostname TEXT NOT NULL,
          root_domain TEXT NOT NULL,entity_id TEXT REFERENCES leads(id),association_basis TEXT NOT NULL,
          created_at TEXT NOT NULL,updated_at TEXT NOT NULL)""",
        "CREATE INDEX awareness_assets_entity ON awareness_assets(entity_id,id)",
        "CREATE INDEX awareness_assets_root ON awareness_assets(root_domain,entity_id)",
        """CREATE TABLE awareness_observations(
          id TEXT PRIMARY KEY,asset_id TEXT NOT NULL REFERENCES awareness_assets(id),
          observed_at TEXT NOT NULL,admitted INTEGER NOT NULL CHECK(admitted IN(0,1)),
          reason TEXT NOT NULL,summary TEXT NOT NULL,normalized TEXT NOT NULL,ip TEXT NOT NULL,
          endpoint_key TEXT NOT NULL,first_recorded_at TEXT NOT NULL,last_recorded_at TEXT NOT NULL,
          source_key TEXT NOT NULL)""",
        "CREATE INDEX awareness_observations_asset ON awareness_observations(asset_id,observed_at,id)",
        "CREATE INDEX awareness_observations_endpoint ON awareness_observations(endpoint_key,admitted,observed_at DESC)",
        "CREATE INDEX awareness_observations_admission ON awareness_observations(admitted,observed_at)",
        """CREATE TABLE awareness_sources(
          import_id TEXT NOT NULL REFERENCES imports(id),source_key TEXT NOT NULL,
          observation_id TEXT NOT NULL REFERENCES awareness_observations(id),source_sha256 TEXT NOT NULL,
          sheet TEXT NOT NULL,row_number INTEGER NOT NULL,entry_id TEXT NOT NULL,workbook TEXT NOT NULL,
          PRIMARY KEY(import_id,source_key))""",
        "CREATE INDEX awareness_sources_observation ON awareness_sources(observation_id,import_id)",
        "CREATE INDEX awareness_sources_legacy ON awareness_sources(source_key)",
        "CREATE INDEX awareness_sources_entry ON awareness_sources(entry_id)",
        """CREATE TABLE awareness_findings(
          id TEXT PRIMARY KEY,asset_id TEXT NOT NULL REFERENCES awareness_assets(id),condition TEXT NOT NULL,
          service_scope TEXT NOT NULL,kind TEXT NOT NULL,admitted INTEGER NOT NULL CHECK(admitted IN(0,1)),
          workflow TEXT NOT NULL,first_seen TEXT NOT NULL,last_seen TEXT NOT NULL,changed_at TEXT NOT NULL,
          last_fingerprint TEXT NOT NULL,latest_observation_id TEXT NOT NULL REFERENCES awareness_observations(id),
          handled_case_id TEXT NOT NULL,created_at TEXT NOT NULL,latest_source_key TEXT NOT NULL DEFAULT '',
          reason TEXT NOT NULL DEFAULT '',
          UNIQUE(asset_id,condition,service_scope))""",
        "CREATE INDEX awareness_findings_admission ON awareness_findings(admitted,workflow,changed_at)",
        "CREATE INDEX awareness_findings_asset ON awareness_findings(asset_id,admitted)",
        """CREATE TABLE awareness_memberships(
          finding_id TEXT NOT NULL REFERENCES awareness_findings(id),
          observation_id TEXT NOT NULL REFERENCES awareness_observations(id),
          PRIMARY KEY(finding_id,observation_id))""",
        "CREATE INDEX awareness_memberships_observation ON awareness_memberships(observation_id,finding_id)",
        """CREATE TABLE case_entry_conditions(
          case_id TEXT NOT NULL REFERENCES cases(id),entry_id TEXT NOT NULL REFERENCES entries(id),
          conditions TEXT NOT NULL,PRIMARY KEY(case_id,entry_id))""",
    )
    for statement in statements:
        db.execute(statement)
