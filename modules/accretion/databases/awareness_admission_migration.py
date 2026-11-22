"""Schema 17: conservative, provenance-backed condition admission."""

import json

from ..components.awareness import (
    asset_key,
    conditions,
    digest,
    service_scope,
    source_key,
    timestamp,
)
from ..components.awareness_admission import record
from ..components.intake.versions import entry_fields
from modules.workspace.components.primitives import dump, now


def schema(db):
    db.execute(
        "ALTER TABLE awareness_memberships ADD COLUMN admission_state TEXT NOT NULL DEFAULT 'legacy_unknown' CHECK(admission_state IN ('observed','admitted','legacy_unknown'))"
    )
    db.execute(
        "ALTER TABLE awareness_memberships ADD COLUMN admission_projection_version INTEGER NOT NULL DEFAULT 1 CHECK(admission_projection_version=1)"
    )
    statements = [
        """CREATE TABLE awareness_admission_events(
          id TEXT PRIMARY KEY NOT NULL,finding_id TEXT NOT NULL,observation_id TEXT NOT NULL,
          import_id TEXT NOT NULL,source_key TEXT NOT NULL,
          state TEXT NOT NULL CHECK(state IN ('observed','admitted')),
          contract_version INTEGER NOT NULL CHECK(contract_version=1),policy_version TEXT NOT NULL,
          decision_at TEXT NOT NULL,recorded_at TEXT NOT NULL,
          authority_kind TEXT NOT NULL CHECK(length(authority_kind)>0),authority_ref TEXT NOT NULL,
          actor TEXT NOT NULL,reason TEXT NOT NULL,evidence_ref TEXT NOT NULL CHECK(length(evidence_ref)<=4000),
          facts_json TEXT NOT NULL CHECK(json_valid(facts_json) AND json_type(facts_json)='object'),
          FOREIGN KEY(finding_id,observation_id) REFERENCES awareness_memberships(finding_id,observation_id),
          FOREIGN KEY(import_id,source_key) REFERENCES awareness_sources(import_id,source_key),
          UNIQUE(finding_id,observation_id,import_id,source_key,state,contract_version,policy_version,authority_kind,authority_ref))""",
        "CREATE INDEX awareness_memberships_admission ON awareness_memberships(finding_id,admission_state,observation_id)",
        "CREATE INDEX awareness_admission_pair ON awareness_admission_events(finding_id,observation_id,recorded_at,id)",
        "CREATE INDEX awareness_admission_source ON awareness_admission_events(import_id,source_key)",
        """CREATE TRIGGER awareness_admission_source_immutable BEFORE UPDATE OF import_id,source_key,observation_id,source_sha256,sheet,row_number ON awareness_sources
        WHEN EXISTS(SELECT 1 FROM awareness_admission_events e WHERE e.import_id=OLD.import_id AND e.source_key=OLD.source_key)
        BEGIN SELECT RAISE(ABORT,'Admission source identity is immutable'); END""",
        """CREATE TRIGGER awareness_admission_source_match BEFORE INSERT ON awareness_admission_events
        WHEN NOT EXISTS(SELECT 1 FROM awareness_sources s WHERE s.import_id=NEW.import_id AND s.source_key=NEW.source_key AND s.observation_id=NEW.observation_id)
        BEGIN SELECT RAISE(ABORT,'Admission source does not match observation'); END""",
        """CREATE TRIGGER awareness_admission_immutable_insert BEFORE INSERT ON awareness_admission_events
        WHEN EXISTS(SELECT 1 FROM awareness_admission_events e WHERE e.id=NEW.id OR
          (e.finding_id=NEW.finding_id AND e.observation_id=NEW.observation_id
           AND e.import_id=NEW.import_id AND e.source_key=NEW.source_key AND e.state=NEW.state
           AND e.contract_version=NEW.contract_version AND e.policy_version=NEW.policy_version
           AND e.authority_kind=NEW.authority_kind AND e.authority_ref=NEW.authority_ref))
        BEGIN SELECT RAISE(ABORT,'Admission events are append-only'); END""",
        """CREATE TRIGGER awareness_admission_source_replace BEFORE INSERT ON awareness_sources
        WHEN EXISTS(SELECT 1 FROM awareness_sources s WHERE s.import_id=NEW.import_id AND s.source_key=NEW.source_key
          AND (s.observation_id<>NEW.observation_id OR s.source_sha256<>NEW.source_sha256 OR s.sheet<>NEW.sheet OR s.row_number<>NEW.row_number)
          AND EXISTS(SELECT 1 FROM awareness_admission_events e WHERE e.import_id=s.import_id AND e.source_key=s.source_key))
        BEGIN SELECT RAISE(ABORT,'Admission source identity is immutable'); END""",
        """CREATE TRIGGER awareness_admission_immutable_update BEFORE UPDATE ON awareness_admission_events
        BEGIN SELECT RAISE(ABORT,'Admission events are append-only'); END""",
        """CREATE TRIGGER awareness_admission_immutable_delete BEFORE DELETE ON awareness_admission_events
        BEGIN SELECT RAISE(ABORT,'Admission events are append-only'); END""",
        """CREATE TRIGGER awareness_admission_project AFTER INSERT ON awareness_admission_events
        WHEN NEW.state='admitted' BEGIN
          UPDATE awareness_memberships SET admission_state='admitted' WHERE finding_id=NEW.finding_id AND observation_id=NEW.observation_id;
        END""",
        """CREATE TRIGGER awareness_membership_admission_guard BEFORE UPDATE OF admission_state ON awareness_memberships
        WHEN (OLD.admission_state='admitted' AND NEW.admission_state<>'admitted')
          OR (OLD.admission_state='legacy_unknown' AND NEW.admission_state='observed')
          OR (NEW.admission_state='admitted' AND NOT EXISTS(SELECT 1 FROM awareness_admission_events e WHERE e.finding_id=NEW.finding_id AND e.observation_id=NEW.observation_id AND e.state='admitted'))
        BEGIN SELECT RAISE(ABORT,'Admission state requires retained authority'); END""",
        """CREATE TRIGGER awareness_membership_admission_insert BEFORE INSERT ON awareness_memberships
        WHEN NEW.admission_state='admitted' OR EXISTS(SELECT 1 FROM awareness_memberships m WHERE m.finding_id=NEW.finding_id AND m.observation_id=NEW.observation_id) BEGIN SELECT RAISE(ABORT,'Admission requires retained pair authority'); END""",
        """CREATE TABLE awareness_admission_migration_report(
          version INTEGER PRIMARY KEY,recorded_at TEXT NOT NULL,counts_json TEXT NOT NULL CHECK(json_valid(counts_json)),
          authority TEXT NOT NULL)""",
    ]
    for statement in statements:
        db.execute(statement)
    # Retained entries are committed only by final successful qualification.
    # No compact memory, date proximity, representative tags or delivery inference.
    for row in db.execute("""SELECT e.id,e.payload,e.import_id,s.source_key,s.observation_id,
        s.source_sha256,s.sheet,s.row_number,i.sha256,o.asset_id,o.observed_at,o.ip,o.summary,o.normalized
        FROM entries e JOIN awareness_sources s ON s.entry_id=e.id AND s.import_id=e.import_id
        JOIN imports i ON i.id=s.import_id JOIN awareness_observations o ON o.id=s.observation_id""").fetchall():
        entry = json.loads(row["payload"])
        fields = entry_fields(entry)
        raw = entry.get("source") or {}
        normalized = entry.get("normalized") or {}
        if row["source_sha256"] != row["sha256"] or (
            normalized.get("source_sha256") and normalized["source_sha256"] != row["sha256"]
        ):
            continue
        if (
            source_key(entry, row["sha256"]) != row["source_key"]
            or str(raw.get("sheet") or "") != row["sheet"]
            or raw.get("row") != row["row_number"]
        ):
            continue
        key, _, ip = asset_key(entry)
        if digest(["asset", key]) != row["asset_id"] or ip != row["ip"]:
            continue
        canonical_fields = entry_fields(
            {
                "source": {"fields": json.loads(row["summary"])},
                "normalized": json.loads(row["normalized"]),
            }
        )
        if any(
            str(fields.get(key) or "").strip().casefold()
            != str(canonical_fields.get(key) or "").strip().casefold()
            for key in ("version", "product")
        ):
            continue
        observed = timestamp(fields.get("timestamp"))
        if observed and observed != row["observed_at"]:
            continue
        for condition, _ in conditions(entry):
            fid = digest(["finding", row["asset_id"], condition, service_scope(entry)])
            if not db.execute(
                "SELECT 1 FROM awareness_memberships WHERE finding_id=? AND observation_id=?",
                (fid, row["observation_id"]),
            ).fetchone():
                continue
            record(
                db,
                finding_id=fid,
                observation_id=row["observation_id"],
                import_id=row["import_id"],
                source_key=row["source_key"],
                admitted=True,
                fields=fields,
                authority_kind="legacy_retained_qualified_entry",
                authority_ref=row["id"],
                policy_version="legacy-retained-entry-v1",
                decision_at="",
                actor="not_recorded",
                reason="Exact retained qualified entry; original decision time and actor were not recorded",
            )
    counts = {state: 0 for state in ("admitted", "observed", "legacy_unknown")}
    counts.update(
        {
            row[0]: row[1]
            for row in db.execute(
                "SELECT admission_state,count(*) FROM awareness_memberships GROUP BY admission_state"
            )
        }
    )
    db.execute(
        "INSERT INTO awareness_admission_migration_report VALUES(?,?,?,?)",
        (
            17,
            now(),
            dump(counts),
            "Exact retained qualified entries only; unprovable prior qualification remains legacy_unknown",
        ),
    )
    # Preserve known aggregate legacy qualification and workflow; exact timeline
    # is rebuilt only where retained pair authority exists.
    for row in db.execute(
        "SELECT DISTINCT finding_id id FROM awareness_memberships WHERE admission_state='admitted'"
    ).fetchall():
        observations = db.execute(
            """SELECT o.* FROM awareness_memberships m JOIN awareness_observations o ON o.id=m.observation_id WHERE m.finding_id=? AND m.admission_state='admitted' ORDER BY o.observed_at,o.id""",
            (row["id"],),
        ).fetchall()
        db.execute(
            "UPDATE awareness_findings SET first_seen=?,last_seen=?,latest_observation_id=?,latest_source_key=?,last_fingerprint='' WHERE id=?",
            (
                observations[0]["observed_at"],
                observations[-1]["observed_at"],
                observations[-1]["id"],
                observations[-1]["source_key"],
                row["id"],
            ),
        )
