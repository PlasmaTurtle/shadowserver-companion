"""Add canonical awareness without changing original imports or report evidence."""

from contextlib import closing
import csv
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

from .awareness import associate, mark_handled, settle_findings
from .intake.identity import signature


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
        """CREATE TABLE awareness_migration_warnings(
          import_id TEXT PRIMARY KEY REFERENCES imports(id),reason TEXT NOT NULL)""",
    )
    for statement in statements:
        db.execute(statement)
    backfill(db)


def backfill(db):
    """Recover event membership in a single migration with bounded file readers.

    Known prior approval survives queue retirement. Unknown historical rows stay
    unadmitted; migration never invents a successful qualification. Missing or
    changed originals leave explicit warnings and retained evidence still works.
    """
    from .dark_matter import usable_fields
    from .intake import read_entries

    db.execute(
        "CREATE TEMP TABLE IF NOT EXISTS awareness_legacy_signals(signal TEXT PRIMARY KEY,entity_id TEXT,admitted INTEGER,reason TEXT,workflow TEXT)"
    )
    for row in db.execute("SELECT * FROM intake_observations"):
        fields = json.loads(row["summary"])
        entry = {
            "source": {
                "fields": fields,
                "sheet": fields.get("sheet", ""),
                "row": fields.get("row", 0),
            },
            "ip": fields.get("ip", ""),
            "normalized": {"observation_ref": row["observation_id"]},
        }
        admitted = row["disposition"] == "lead" or row["reason"] in {
            "superseded",
            "unchanged_reported",
            "ignored",
        }
        workflow = (
            "handled"
            if row["handled_case_id"]
            else "ignored"
            if row["reason"] == "ignored"
            else "unworked"
        )
        db.execute(
            "INSERT INTO awareness_legacy_signals VALUES(?,?,?,?,?) ON CONFLICT(signal) DO UPDATE SET admitted=MAX(admitted,excluded.admitted),entity_id=COALESCE(entity_id,excluded.entity_id)",
            (signature(entry), row["entity_id"] or None, int(admitted), row["reason"], workflow),
        )
        associate(
            db,
            entry,
            import_id=row["import_id"],
            entity_id=row["entity_id"] or None,
            admitted=admitted,
            reason=row["reason"],
            fallback=row["observed_at"] or row["recorded_at"],
            workflow=workflow,
        )
        if row["handled_case_id"]:
            mark_handled(db, entry, row["handled_case_id"])
    for row in db.execute("SELECT * FROM entries"):
        entry = json.loads(row["payload"])
        entry.setdefault("normalized", {})["observation_ref"] = row["id"]
        db.execute(
            "INSERT INTO awareness_legacy_signals VALUES(?,?,?,?,?) ON CONFLICT(signal) DO UPDATE SET admitted=1,entity_id=excluded.entity_id",
            (signature(entry), row["lead_id"], 1, "", "unworked"),
        )
        associate(
            db,
            entry,
            import_id=row["import_id"],
            entity_id=row["lead_id"],
            admitted=True,
            fallback=row["observed_at"],
        )
        for link in db.execute("SELECT case_id FROM case_entries WHERE entry_id=?", (row["id"],)):
            mark_handled(db, entry, link[0])
    main_path = next((r[2] for r in db.execute("PRAGMA database_list") if r[1] == "main"), "")
    if main_path:
        root = Path(main_path).resolve().parent
        for item in db.execute("SELECT * FROM imports ORDER BY created_at,id"):
            config = json.loads(item["config"])
            try:
                path = (root / item["path"]).resolve()
                if not path.is_relative_to(root):
                    raise ValueError("Original source path is outside the workspace")
                digest = hashlib.sha256()
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                if digest.hexdigest() != item["sha256"]:
                    raise ValueError("Original source checksum does not match")
                regions = {str(v).casefold() for v in config.get("regions", [])} or None
                with closing(read_entries(path, config.get("sheet", ""))) as reader:
                    for index, source in enumerate(reader, 1):
                        if index > 250000:
                            raise ValueError("Original source exceeds the row limit")
                        if not usable_fields(source.fields, regions):
                            continue
                        entry = {"source": asdict(source), "ip": source.fields.get("ip", "")}
                        prior = db.execute(
                            "SELECT * FROM awareness_legacy_signals WHERE signal=?",
                            (signature(entry),),
                        ).fetchone()
                        associate(
                            db,
                            entry,
                            import_id=item["id"],
                            source_sha256=item["sha256"],
                            entity_id=prior["entity_id"] if prior else None,
                            admitted=bool(prior and prior["admitted"]),
                            reason=prior["reason"] if prior else "historical_unadmitted",
                            fallback=item["created_at"],
                            workflow=prior["workflow"] if prior else "unworked",
                        )
            except (
                OSError,
                ValueError,
                KeyError,
                TypeError,
                csv.Error,
                ParseError,
                BadZipFile,
            ) as error:
                db.execute(
                    "INSERT OR REPLACE INTO awareness_migration_warnings VALUES(?,?)",
                    (item["id"], str(error)[:300]),
                )
    db.execute("DROP TABLE awareness_legacy_signals")
    settle_findings(db, [r[0] for r in db.execute("SELECT id FROM awareness_findings")])
    # Upgrading the index is not a fresh observation. Preserve conservative
    # acquisition chronology instead of making the entire map newly changed.
    db.execute("""UPDATE awareness_findings SET created_at=COALESCE((
      SELECT min(i.created_at) FROM awareness_memberships m JOIN awareness_sources s ON s.observation_id=m.observation_id
      JOIN imports i ON i.id=s.import_id WHERE m.finding_id=awareness_findings.id),created_at)""")
    db.execute("UPDATE awareness_findings SET changed_at=created_at")
    # Legacy compact memory remains a compatibility summary, not admission authority.
    db.execute(
        "UPDATE intake_observations SET disposition='lead' WHERE reason IN ('superseded','unchanged_reported','ignored')"
    )
