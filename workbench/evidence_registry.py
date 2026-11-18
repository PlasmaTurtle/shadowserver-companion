"""Immutable source revisions and explicit captured-byte references.

Lookup responses stay in cache. A revision key keeps its historical identity and
its exact stored JSON bytes; updates and deletion are prohibited by the schema.
"""

from __future__ import annotations

import hashlib
from pathlib import PurePosixPath
import re

from .aegis.json import strict_json_loads
from .source_references import cve_response_sources

FAMILIES = frozenset({"cve-version", "risk-version", "intelligence-version", "acquisition-version"})
HEX = re.compile(r"[0-9a-f]{64}")


def available(db):
    return (
        db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='evidence_revisions'"
        ).fetchone()
        is not None
    )


def revision_key(key):
    family, _, identifier = key.partition(":")
    return (family, identifier) if family in FAMILIES else None


def source_references(family, payload):
    if family in {"cve-version", "intelligence-version"}:
        yield from cve_response_sources(payload)
    elif family == "risk-version":
        yield payload.get("source", {})
    elif family == "acquisition-version":
        yield payload.get("response", {})


def capture_fields(source):
    """Describe declared proof, without inventing a digest for old records."""
    if not isinstance(source, dict) or not source.get("record_path"):
        return None
    path = source["record_path"]
    if (
        not isinstance(path, str)
        or not path
        or "\\" in path
        or ":" in path
        or any(ord(c) < 32 for c in path)
    ):
        raise ValueError("Evidence registry capture path is invalid")
    relative = PurePosixPath(path)
    if (
        relative.is_absolute()
        or relative.as_posix() != path
        or any(part in ("", ".", "..") or part.endswith((".", " ")) for part in relative.parts)
    ):
        raise ValueError("Evidence registry capture path is outside the workspace")
    digest = source.get("body_sha256") or source.get("sha256") or None
    if digest is not None and (not isinstance(digest, str) or not HEX.fullmatch(digest)):
        raise ValueError("Evidence registry capture digest is invalid")
    identifier = hashlib.sha256((path + "\0" + (digest or "unknown")).encode()).hexdigest()
    provider = source.get("publisher") or source.get("source") or ""
    if not isinstance(provider, str):
        provider = ""
    return {
        "id": identifier,
        "path": path,
        "sha256": digest,
        "provider": provider,
        "media_type": str(source.get("content_type") or source.get("media_type") or ""),
        "captured_at": str(source.get("retrieved_at") or source.get("captured_at") or ""),
        "binding_state": "declared_digest" if digest else "legacy_unknown",
    }


def register_revision(db, key, payload, stamp, *, strict_insert=False):
    kind = revision_key(key)
    if not kind or not kind[1]:
        raise ValueError("Invalid immutable source revision key")
    value = strict_json_loads(payload, max_bytes=256 * 1024 * 1024, require_object=True)
    existing = db.execute(
        "SELECT payload,payload_sha256 FROM evidence_revisions WHERE key=?", (key,)
    ).fetchone()
    if existing is not None and not strict_insert:
        # Stable intelligence IDs exclude transient acquisition fields. Preserve
        # the first published record just as the former INSERT OR IGNORE did.
        if hashlib.sha256(existing["payload"].encode()).hexdigest() != existing["payload_sha256"]:
            raise ValueError("Saved evidence revision failed its payload digest")
        return
    provider = value.get("publisher") or value.get("source") or ""
    if not isinstance(provider, str):
        provider = provider.get("publisher", "") if isinstance(provider, dict) else ""
        provider = provider if isinstance(provider, str) else ""
    db.execute(
        "INSERT INTO evidence_revisions(key,family,revision_id,provider,payload,payload_sha256,retrieved_at) VALUES(?,?,?,?,?,?,?)",
        (
            key,
            kind[0],
            kind[1],
            provider,
            payload,
            hashlib.sha256(payload.encode()).hexdigest(),
            stamp,
        ),
    )
    for source in source_references(kind[0], value):
        fields = capture_fields(source)
        if fields is None:
            continue
        db.execute(
            "INSERT INTO evidence_captures(id,path,sha256,provider,media_type,captured_at,binding_state) SELECT :id,:path,:sha256,:provider,:media_type,:captured_at,:binding_state WHERE NOT EXISTS(SELECT 1 FROM evidence_captures WHERE id=:id)",
            fields,
        )
        db.execute(
            "INSERT INTO evidence_revision_captures SELECT ?,? WHERE NOT EXISTS(SELECT 1 FROM evidence_revision_captures WHERE revision_key=? AND capture_id=?)",
            (key, fields["id"], key, fields["id"]),
        )


def get_record(db, key):
    if revision_key(key) and available(db):
        row = db.execute(
            "SELECT key,payload,retrieved_at,payload_sha256 FROM evidence_revisions WHERE key=?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        if hashlib.sha256(row["payload"].encode()).hexdigest() != row["payload_sha256"]:
            raise ValueError("Saved evidence revision failed its payload digest")
        return {name: row[name] for name in ("key", "payload", "retrieved_at")}
    row = db.execute("SELECT key,payload,retrieved_at FROM cache WHERE key=?", (key,)).fetchone()
    return dict(row) if row is not None else None


def validate_registry(db, *, root=None, checkpoint=None):
    """Read-only relational/projection checks; returns explicit legacy uncertainty."""
    if not available(db):
        return {"available": False, "revisions": 0, "captures": 0, "legacy_unknown": 0}
    count = 0
    for row in db.execute("SELECT * FROM evidence_revisions"):
        if checkpoint:
            checkpoint("Verifying saved evidence revisions")
        count += 1
        value = strict_json_loads(row["payload"], max_bytes=256 * 1024 * 1024, require_object=True)
        if hashlib.sha256(row["payload"].encode()).hexdigest() != row["payload_sha256"]:
            raise ValueError("Evidence revision payload differs from its saved digest")
        expected = {
            fields["id"]
            for source in source_references(row["family"], value)
            if (fields := capture_fields(source)) is not None
        }
        actual = {
            r[0]
            for r in db.execute(
                "SELECT capture_id FROM evidence_revision_captures WHERE revision_key=?",
                (row["key"],),
            )
        }
        if expected != actual:
            raise ValueError("Evidence revision capture references are incomplete or inconsistent")
    orphan = db.execute(
        "SELECT 1 FROM evidence_revision_captures x LEFT JOIN evidence_revisions r ON r.key=x.revision_key LEFT JOIN evidence_captures c ON c.id=x.capture_id WHERE r.key IS NULL OR c.id IS NULL LIMIT 1"
    ).fetchone()
    if orphan:
        raise ValueError("Evidence registry contains a dangling reference")
    for capture in db.execute("SELECT * FROM evidence_captures"):
        if checkpoint:
            checkpoint("Verifying captured evidence files")
        fields = capture_fields({"record_path": capture["path"], "sha256": capture["sha256"]})
        if fields["id"] != capture["id"] or fields["binding_state"] != capture["binding_state"]:
            raise ValueError("Evidence capture identity is inconsistent")
        if root is not None:
            from .package_files import member_path

            try:
                path = member_path(root, capture["path"])
                with path.open("rb") as stream:
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
            except (OSError, ValueError) as error:
                raise ValueError("Backup is missing a captured vulnerability source") from error
            if capture["sha256"] and digest != capture["sha256"]:
                raise ValueError("Backup vulnerability source failed its recorded SHA-256 check")
    totals = db.execute(
        "SELECT count(*) n,sum(binding_state='legacy_unknown') unknown FROM evidence_captures"
    ).fetchone()
    return {
        "available": True,
        "revisions": count,
        "captures": totals["n"],
        "legacy_unknown": totals["unknown"] or 0,
    }
