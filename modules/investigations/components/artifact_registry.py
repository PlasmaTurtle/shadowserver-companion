"""Persist package digests and original identities independently of current ownership."""

import hashlib
import json

from modules.workspace.components.aegis.json import strict_json_loads
from .artifact_identity import closure_identity, report_identity
from .package_files import package_folder, parsed_manifest

IDENTITY_COLUMNS = {
    "report": (
        "id",
        "lead_id",
        "case_id",
        "revision",
        "created_at",
        "certified_at",
        "certified_by",
        "certification_source",
    ),
    "closure": (
        "id",
        "case_id",
        "created_at",
        "closed_by",
        "disposition",
        "conclusion",
        "snapshot_sha256",
    ),
}
TABLES = {"report": "reports", "closure": "case_closures"}


def available(db):
    return (
        db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='artifact_records'"
        ).fetchone()
        is not None
    )


def _resolve(db, entity_id):
    row = db.execute("SELECT id,merged_into FROM leads WHERE id=?", (entity_id,)).fetchone()
    return (row["merged_into"] or row["id"]) if row else None


def _identity(kind, row):
    return {key: row[key] for key in IDENTITY_COLUMNS[kind]}


def _check_identity(db, kind, row, manifest):
    if kind == "report":
        report_identity(row, manifest, lambda entity_id: _resolve(db, entity_id))
        for key in ("certified_by", "certified_at"):
            if key in manifest and manifest[key] != row[key]:
                raise ValueError("Report package certification differs from its saved identity")
    else:
        closure_identity(row, manifest)


def register_artifact(db, root, kind, artifact_id, *, legacy=False):
    """Record a completed package inside the same transaction as its owner row.

    Old unavailable packages retain an explicit unknown manifest binding. New
    packages require a valid manifest and never inherit that legacy exception.
    """
    if not available(db):
        return
    table = TABLES[kind]
    row = db.execute(f"SELECT * FROM {table} WHERE id=?", (artifact_id,)).fetchone()
    if row is None:
        raise ValueError("Artifact has no saved owner record")
    row = dict(row)
    digest = None
    binding = "legacy_unverified"
    try:
        if root is None:
            raise ValueError("Workspace location is unavailable")
        manifest, raw = parsed_manifest(package_folder(root, row["path"]))
        _check_identity(db, kind, row, manifest)
        digest = hashlib.sha256(raw).hexdigest()
        binding = "legacy_manifest" if legacy else "verified_manifest"
    except (OSError, ValueError, KeyError, TypeError):
        if not legacy:
            raise
    db.execute(
        """INSERT INTO artifact_records(kind,artifact_id,report_id,closure_id,path,manifest_sha256,identity_json,binding_state)
        VALUES(?,?,?,?,?,?,?,?)""",
        (
            kind,
            artifact_id,
            artifact_id if kind == "report" else None,
            artifact_id if kind == "closure" else None,
            row["path"],
            digest,
            json.dumps(_identity(kind, row), sort_keys=True, ensure_ascii=False, allow_nan=False),
            binding,
        ),
    )


def verify_binding(db, kind, record, raw):
    """Validate exact saved manifest bytes without requiring unrelated render files."""
    if not available(db):
        return
    record = dict(record)
    saved = db.execute(
        "SELECT * FROM artifact_records WHERE kind=? AND path=?", (kind, record["path"])
    ).fetchone()
    if saved is None:
        # Recovery supplies a path-only record before committing its owner.
        if "id" in record:
            raise ValueError("Saved artifact has no immutable registry record")
        return
    table = TABLES[kind]
    owner = db.execute(f"SELECT * FROM {table} WHERE id=?", (saved["artifact_id"],)).fetchone()
    if owner is None:
        raise ValueError("Artifact registry has no saved owner")
    identity = strict_json_loads(saved["identity_json"], require_object=True)
    if identity != _identity(kind, owner) or owner["path"] != saved["path"]:
        raise ValueError("Artifact identity differs from its immutable registry record")
    if any(key in record and record[key] != value for key, value in identity.items()):
        raise ValueError("Supplied artifact identity differs from its immutable registry record")
    if "id" in record and record["id"] != saved["artifact_id"]:
        raise ValueError("Artifact is owned by a different saved record")
    if (
        saved["manifest_sha256"] is not None
        and hashlib.sha256(raw).hexdigest() != saved["manifest_sha256"]
    ):
        raise ValueError("Artifact manifest differs from its saved digest")


def validate_registry(root, db, *, checkpoint=None):
    """Read-only identity and manifest checks; no Store initialization or migration."""
    if not available(db):
        return {"available": False, "artifacts": 0, "legacy_unverified": 0}
    count = unknown = 0
    for kind, table in TABLES.items():
        if db.execute(
            f"SELECT 1 FROM {table} o LEFT JOIN artifact_records a ON a.kind=? AND a.artifact_id=o.id WHERE a.artifact_id IS NULL LIMIT 1",
            (kind,),
        ).fetchone():
            raise ValueError("Saved artifact has no immutable registry record")
    for saved in db.execute("SELECT * FROM artifact_records"):
        if checkpoint:
            checkpoint("Verifying immutable artifact identities")
        count += 1
        table = TABLES[saved["kind"]]
        owner = db.execute(f"SELECT * FROM {table} WHERE id=?", (saved["artifact_id"],)).fetchone()
        if owner is None:
            raise ValueError("Artifact registry has no saved owner")
        if saved["binding_state"] == "legacy_unverified":
            unknown += 1
            # Missing old packages remain visible as unknown; never infer proof.
            verify_binding(db, saved["kind"], dict(owner), b"")
            continue
        manifest, raw = parsed_manifest(package_folder(root, saved["path"]))
        verify_binding(db, saved["kind"], dict(owner), raw)
        _check_identity(db, saved["kind"], dict(owner), manifest)
    return {"available": True, "artifacts": count, "legacy_unverified": unknown}


def create_schema(db):
    duplicate = db.execute(
        "SELECT path FROM reports GROUP BY path HAVING count(*)>1 LIMIT 1"
    ).fetchone()
    if duplicate:
        raise ValueError("Cannot upgrade: report package path is assigned to multiple records")
    db.execute("CREATE UNIQUE INDEX report_artifact_path ON reports(path)")
    db.execute("""CREATE TABLE artifact_records(
        kind TEXT NOT NULL CHECK(kind IN('report','closure')),artifact_id TEXT NOT NULL,
        report_id TEXT REFERENCES reports(id),closure_id TEXT REFERENCES case_closures(id),
        path TEXT NOT NULL UNIQUE,manifest_sha256 TEXT,
        identity_json TEXT NOT NULL CHECK(json_valid(identity_json) AND json_type(identity_json)='object'),
        binding_state TEXT NOT NULL CHECK(binding_state IN('verified_manifest','legacy_manifest','legacy_unverified')),
        PRIMARY KEY(kind,artifact_id),CHECK((kind='report' AND report_id IS NOT NULL AND report_id=artifact_id AND closure_id IS NULL) OR
            (kind='closure' AND closure_id IS NOT NULL AND closure_id=artifact_id AND report_id IS NULL)),
        CHECK(manifest_sha256 IS NULL OR (length(manifest_sha256)=64 AND manifest_sha256 NOT GLOB '*[^0-9a-f]*')),
        CHECK((binding_state='legacy_unverified')=(manifest_sha256 IS NULL)))""")
    db.execute("""CREATE TRIGGER immutable_artifact_records_replace BEFORE INSERT ON artifact_records
        WHEN EXISTS(SELECT 1 FROM artifact_records WHERE (kind=NEW.kind AND artifact_id=NEW.artifact_id) OR path=NEW.path)
        BEGIN SELECT RAISE(ABORT,'Immutable artifact registry cannot be replaced'); END""")
    for operation in ("UPDATE", "DELETE"):
        db.execute(f"""CREATE TRIGGER immutable_artifact_records_{operation.lower()} BEFORE {operation} ON artifact_records
            BEGIN SELECT RAISE(ABORT,'Artifact registry is immutable'); END""")
    for kind, table in TABLES.items():
        collision = "o.id=NEW.id OR o.path=NEW.path"
        collision += (
            " OR (o.lead_id=NEW.lead_id AND o.revision=NEW.revision)"
            if kind == "report"
            else " OR o.case_id=NEW.case_id"
        )
        db.execute(f"""CREATE TRIGGER immutable_{table}_replace BEFORE INSERT ON {table}
            WHEN EXISTS(SELECT 1 FROM {table} o JOIN artifact_records a ON a.kind='{kind}' AND a.artifact_id=o.id WHERE {collision})
            BEGIN SELECT RAISE(ABORT,'Certified artifact identity is immutable'); END""")
        columns = (*IDENTITY_COLUMNS[kind], "path")
        changed = " OR ".join(f"NEW.{key} IS NOT OLD.{key}" for key in columns)
        db.execute(f"""CREATE TRIGGER immutable_{table}_identity BEFORE UPDATE OF {",".join(columns)} ON {table}
            WHEN ({changed}) AND EXISTS(SELECT 1 FROM artifact_records WHERE kind='{kind}' AND artifact_id=OLD.id)
            BEGIN SELECT RAISE(ABORT,'Certified artifact identity is immutable'); END""")


def backfill(db, root):
    for kind, table in TABLES.items():
        for row in db.execute(f"SELECT id FROM {table}").fetchall():
            register_artifact(db, root, kind, row["id"], legacy=True)
