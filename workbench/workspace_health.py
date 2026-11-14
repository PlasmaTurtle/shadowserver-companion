"""Read-only workspace diagnostics, usable without application initialization.

Never construct Store/EvidenceStore here: their startup migrations and recovery
are intentionally inappropriate when diagnosing a damaged or newer workspace.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import time

from .migrations import SCHEMA_VERSION
from .primitives import now
from .workspace_data import backup_status, digest, restore_dir


from .workspace_read import readonly


_progress = ContextVar("workspace_health_progress", default=lambda message: None)


class InspectionStopped(RuntimeError):
    pass


def checkpoint(message):
    _progress.get()(message)


def _bytes(path):
    try:
        return path.stat().st_size if path.is_file() and not path.is_symlink() else 0
    except OSError:
        return 0


def _storage(path):
    if not path.exists():
        return {"bytes": 0, "files": 0}
    total, count = 0, 0
    for file in path.rglob("*"):
        checkpoint("Measuring retained storage")
        if file.is_symlink() or file.is_junction():
            raise ValueError("Storage contains a linked path")
        if file.is_file():
            count += 1
            total += file.stat().st_size
        if count > 100000:
            raise ValueError("Storage inventory exceeds its file budget")
    return {"bytes": total, "files": count}


class ReadEvidence:
    """Attribution reader implementing the validator contract without migrations."""

    def __init__(self, path):
        self.scope = readonly(path)

    def __enter__(self):
        self.db = self.scope.__enter__()
        return self

    def __exit__(self, *args):
        return self.scope.__exit__(*args)

    def result(self, identifier):
        row = self.db.execute("SELECT payload FROM results WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise ValueError("Referenced attribution result is missing")
        return json.loads(row[0])

    def snapshot(self, identifier):
        from attribution.models import ResponseSnapshot

        checkpoint("Verifying retained contact and attribution sources")
        row = self.db.execute(
            "SELECT metadata,body FROM snapshots WHERE id=?", (identifier,)
        ).fetchone()
        if row is None:
            raise ValueError("Referenced attribution snapshot is missing")
        metadata = json.loads(row[0])
        body = bytes(row[1])
        if (
            metadata.get("snapshot_id") != identifier
            or metadata.pop("body_size") != len(body)
            or hashlib.sha256(body).hexdigest() != metadata.get("body_sha256")
        ):
            raise ValueError("Referenced attribution snapshot failed its identity or SHA-256 check")
        return ResponseSnapshot(body=body, **metadata)


class ReadRecords:
    """Minimal read facade for the existing artifact/capture validators."""

    def __init__(self, root, db):
        self.root, self.db = root, db

    def all(self, sql, args=()):
        for number, row in enumerate(self.db.execute(sql, args)):
            checkpoint("Checking saved source references")
            if number >= 100000:
                raise InspectionStopped(
                    "Workspace reference check exceeds its row budget. Use a verified export for complete validation."
                )
            yield dict(row)

    def one(self, sql, args=()):
        row = self.db.execute(sql, args).fetchone()
        return dict(row) if row is not None else None

    def path(self, relative):
        from .package_integrity import member_path

        return member_path(self.root, Path(relative).as_posix())

    @contextmanager
    def read_snapshot(self):
        yield self.db

    def resolve_entity(self, entity_id):
        seen = set()
        while entity_id:
            if entity_id in seen:
                raise ValueError("Entity merge history contains a cycle")
            seen.add(entity_id)
            row = self.one("SELECT merged_into FROM leads WHERE id=?", (entity_id,))
            if row is None:
                raise ValueError("Report references a missing original business")
            if not row["merged_into"]:
                return entity_id
            entity_id = row["merged_into"]


def _main_checks(root, db):
    from .package_integrity import member_path, verification_scope
    from .repositories.artifacts import ArtifactRepository
    from .workspace_data_captures import validate_capture_data

    records = ReadRecords(root, db)
    counts = {}
    for table in ("imports", "leads", "entries", "cases", "reports", "case_closures"):
        counts[table] = db.execute("SELECT count(*) FROM " + table).fetchone()[0]
    # Foreign keys cannot express these cross-record ownership relationships.
    queries = (
        "SELECT 1 FROM entries e LEFT JOIN entity_domain_associations a ON a.root_domain=e.root_domain AND a.entity_id=e.lead_id WHERE a.root_domain IS NULL LIMIT 1",
        "SELECT 1 FROM case_entries ce JOIN cases c ON c.id=ce.case_id JOIN entries e ON e.id=ce.entry_id WHERE c.entity_id<>e.lead_id LIMIT 1",
        "SELECT 1 FROM reports r JOIN cases c ON c.id=r.case_id WHERE r.entity_id<>c.entity_id LIMIT 1",
        "SELECT 1 FROM contact_candidates c JOIN contact_runs r ON r.id=c.latest_run_id WHERE c.entity_id<>r.entity_id OR c.root_domain<>r.root_domain LIMIT 1",
    )
    for query in queries:
        checkpoint("Checking record ownership")
        if db.execute(query).fetchone():
            raise ValueError("Saved records have conflicting business or case ownership")
    for row in records.all("SELECT id FROM leads WHERE merged_into IS NOT NULL"):
        records.resolve_entity(row["id"])
    for table in ("imports", "evidence"):
        for row in records.all("SELECT path,sha256 FROM " + table):
            checkpoint("Verifying original files and evidence")
            if digest(member_path(root, row["path"])) != row["sha256"]:
                raise ValueError("An original report or evidence file failed its SHA-256 check")
    validate_capture_data(records, checkpoint=checkpoint, registry=False)
    from .workspace_data_attribution import _references
    from .workspace_data_contacts import validate_contact_data

    results, snapshots, inherited = _references(records)
    if (results or snapshots or inherited) and not (root / "attribution.sqlite3").is_file():
        raise ValueError("Attribution history references a missing attribution database")
    validate_contact_data(records, evidence_factory=ReadEvidence)
    artifacts = ArtifactRepository(records)
    with verification_scope():
        for row in records.all("SELECT * FROM reports"):
            checkpoint("Verifying report packages")
            artifacts.package_inventory(row)
        for row in records.all("SELECT * FROM case_closures"):
            checkpoint("Verifying closing packages")
            artifacts.closure_inventory(row)
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='evidence_revisions'").fetchone():
        from .evidence_registry import validate_registry

        counts["registry"] = validate_registry(db, root=root, checkpoint=checkpoint)
        from .artifact_registry import validate_registry as validate_artifacts

        counts["artifacts"] = validate_artifacts(root, db, checkpoint=checkpoint)
    from .analytical_index import reconcile

    counts["analytical_index"] = reconcile(db)
    from .awareness_admission import validate

    counts["admission"] = validate(db)
    return counts


def _attribution_checks(root, db, *, references):
    """Validate against main-store pointers captured before this read snapshot.

    Attribution publication commits immutable results/captures before a main-store
    pointer can refer to them. Reading the pointers first therefore gives a safe
    cross-store cut without blocking concurrent acquisition writers.
    """
    from .attribution_bridge import same_domain

    digests = {}
    for row in db.execute("SELECT id,metadata,body FROM snapshots"):
        checkpoint("Verifying attribution responses")
        meta = json.loads(row["metadata"])
        content = bytes(row["body"])
        value = hashlib.sha256(content).hexdigest()
        if (
            meta.get("snapshot_id") != row["id"]
            or len(content) != meta.get("body_size")
            or value != meta.get("body_sha256")
        ):
            raise ValueError("A retained attribution response failed its identity or SHA-256 check")
        digests[row["id"]] = value
    results, referenced_snapshots, inherited = references or (set(), [], [])
    snapshot_refs, domains = list(referenced_snapshots), {}
    for row in db.execute("SELECT id,payload FROM results"):
        item = json.loads(row["payload"])
        if item.get("result_id") != row["id"]:
            raise ValueError("A retained attribution result has inconsistent identity")
        domains[row["id"]] = item.get("root_domain")
        for proof in item.get("evidence", []) + item.get("partial_evidence", []):
            snapshot_refs.append((proof["snapshot_id"], None))
            snapshot_refs.extend((sid, None) for sid in proof.get("supporting_snapshot_ids", []))
        for attempt in item.get("attempts", []):
            snapshot_refs.extend((sid, None) for sid in attempt.get("snapshot_ids", []))
    if any(not same_domain(domains.get(result), domain) for result, domain in results):
        raise ValueError("Attribution references a missing result or a different business")
    if any(
        sid not in digests or expected and digests[sid] != expected
        for sid, expected in snapshot_refs
    ):
        raise ValueError("Attribution references a missing or changed retained response")
    if inherited:
        from .attribution_approval_evidence import valid_approval_reuse

        with ReadEvidence(root / "attribution.sqlite3") as evidence:
            if any(
                not valid_approval_reuse(proof, domain, evidence) for proof, domain in inherited
            ):
                raise ValueError("Inherited attribution approval failed its integrity check")
    return {"snapshots": len(digests), "results": len(domains)}


def _feeds(db, kind):
    from .cve_catalog.risk_policy import freshness

    metadata = {row[0]: json.loads(row[1]) for row in db.execute("SELECT key,value FROM metadata")}
    if kind == "catalog" and metadata.get("analytics_schema", 2) not in (1, 2):
        raise ValueError(
            "Catalog analytics was created by a newer application. Use its compatible application version."
        )
    current = datetime.now(timezone.utc)
    states = (
        {"nvd": {"last_success_at": metadata.get("last_success_at")}}
        if kind == "catalog"
        else {name: metadata.get(name, {}) for name in ("epss", "kev")}
    )
    return {
        name: {
            "last_success_at": state.get("last_success_at"),
            "score_date": state.get("score_date"),
            **freshness(name, state, current),
        }
        for name, state in states.items()
    }


def _inspect_workspace(root):
    """Return independent results for every store; one bad store hides no others."""
    root = Path(root).absolute()
    reference = Path(str(root) + "-reference") / "nvd"
    results = []
    attribution_references = None
    for name, path, expected in (
        ("workspace", root / "workbench.sqlite3", SCHEMA_VERSION),
        ("attribution", root / "attribution.sqlite3", 2),
        ("catalog", reference / "catalog.sqlite3", 1),
        ("risk", reference / "risk.sqlite3", 1),
    ):
        result = {
            "store": name,
            "status": "absent",
            "schema": None,
            "supported_schema": expected,
            "database_bytes": _bytes(path),
            "wal_bytes": _bytes(Path(str(path) + "-wal")),
            "shm_bytes": _bytes(Path(str(path) + "-shm")),
        }
        results.append(result)
        checkpoint("Checking " + name + " database")
        if not path.exists():
            if name == "workspace":
                result.update(
                    status="error",
                    message="Workspace database is missing. Select a verified backup in recovery.",
                )
            continue
        try:
            if path.is_symlink():
                raise ValueError("Database must be a regular file, not a symbolic link")
            with readonly(path) as db:
                version = db.execute("PRAGMA user_version").fetchone()[0]
                result["schema"] = version
                if version > expected:
                    result.update(
                        status="incompatible",
                        message="Created by a newer application. Use that version, or select an older verified backup in recovery.",
                    )
                    continue
                if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("SQLite integrity check failed")
                if db.execute("PRAGMA foreign_key_check").fetchone():
                    raise ValueError("Database has missing record references")
                result.update(
                    status="ok",
                    integrity="ok",
                    foreign_keys="ok",
                    free_page_bytes=db.execute("PRAGMA freelist_count").fetchone()[0]
                    * db.execute("PRAGMA page_size").fetchone()[0],
                )
                if version != expected:
                    result.update(
                        status="upgrade_required",
                        message="An application upgrade is required before full reference checks. The original was not migrated.",
                    )
                elif name == "workspace":
                    from .workspace_data_attribution import _references

                    # Capture pointers from this existing workspace snapshot,
                    # before opening/pinning the separate attribution snapshot.
                    attribution_references = _references(ReadRecords(root, db))
                    result["counts"] = _main_checks(root, db)
                    result["references"] = "ok"
                    index = result["counts"]["analytical_index"]
                    if index.get("available") and not index.get("healthy"):
                        incompatible = any(
                            difference.get("schema_mismatch")
                            for difference in index.get("differences", {}).values()
                        )
                        result.update(
                            status="incompatible" if incompatible else "needs_rebuild",
                            message=(
                                "Analytical table layout does not match this application. Preserve the workspace and use a compatible build or a verified backup; counter rebuilding cannot repair this layout."
                                if incompatible
                                else "Disposable analytical counters differ from their source records. Rebuild them in Settings."
                            ),
                        )
                elif name == "attribution":
                    result["counts"] = _attribution_checks(
                        root, db, references=attribution_references
                    )
                    result["references"] = (
                        "ok" if attribution_references is not None else "internal_only"
                    )
                    if attribution_references is None:
                        result["message"] = (
                            "Retained attribution history was checked. Cross-store references require a readable, compatible workspace database."
                        )
                else:
                    result["feeds"] = _feeds(db, name)
        except (OSError, sqlite3.Error, ValueError, KeyError, TypeError, AttributeError) as error:
            # Database exceptions never include SQL rows, contacts, or source bodies.
            result.update(
                status="error",
                message=str(error)[:300]
                or "Verification failed. Preserve this workspace and select a verified backup.",
                detail=type(error).__name__,
            )
    storage = {}
    for name in (
        "originals",
        "evidence",
        "reports",
        "closures",
        "inbox",
        "operations",
        "backups",
        "exports",
    ):
        try:
            checkpoint("Measuring " + name + " storage")
            storage[name] = _storage(root / name)
        except OSError, ValueError:
            storage[name] = {
                "status": "error",
                "message": "Storage contains an unsafe or unreadable path",
            }
    for name, path in (("reference_data", reference), ("restore_points", restore_dir(root))):
        try:
            storage[name] = _storage(path)
        except OSError, ValueError:
            storage[name] = {
                "status": "error",
                "message": "Storage contains an unsafe or unreadable path",
            }
    try:
        backup = backup_status(root)
    except OSError, ValueError, json.JSONDecodeError:
        backup = {"last_export": None, "restore_points": [], "status": "unreadable"}
    warnings = []
    if backup.get("status") == "unreadable":
        warnings.append(
            "Backup history could not be read. Preserve restore-point ZIPs and verify a selected export before relying on it."
        )
    for item in results:
        counts = item.get("counts", {})
        unknown = counts.get("registry", {}).get("legacy_unknown", 0)
        unbound = counts.get("artifacts", {}).get("legacy_unverified", 0)
        if unknown:
            warnings.append(
                f"{unknown} legacy capture references have no recorded digest; their existence was checked, but original byte identity cannot be certified."
            )
        if unbound:
            warnings.append(
                f"{unbound} legacy artifact records lack a verifiable original registry binding."
            )
    from .workspace_maintenance import plan

    try:
        cleanup = plan(root)
    except OSError, sqlite3.Error, ValueError:
        cleanup = {
            "available": False,
            "message": "Cleanup is unavailable until database compatibility and integrity are restored.",
        }
    result = {
        "checked_at": now(),
        "ok": all(row["status"] in ("ok", "absent") for row in results)
        and all(row.get("status") != "error" for row in storage.values()),
        "stores": results,
        "storage": storage,
        "free_disk_bytes": shutil.disk_usage(root if root.exists() else root.parent).free,
        "last_verified_backup": backup.get("last_export"),
        "restore_point_count": len(backup.get("restore_points", [])),
        "maintenance": cleanup,
        "warnings": warnings,
        "recovery": "Close the app, then run: python -m workbench.workspace_recovery --data-dir PATH check",
    }
    try:
        from .planner_maintenance import status

        result["query_planner"] = status(root)
    except ImportError:
        pass
    return result


def inspect_workspace(root, *, progress=lambda message: None, cancelled=lambda: False, timeout=120):
    deadline = time.monotonic() + timeout

    def update(message):
        if cancelled():
            raise InspectionStopped("Workspace check cancelled; saved data was not changed")
        if time.monotonic() >= deadline:
            raise InspectionStopped(
                "Workspace check reached its time budget. Use a verified export for a complete large-workspace validation."
            )
        progress(message)

    token = _progress.set(update)
    try:
        return _inspect_workspace(root)
    finally:
        _progress.reset(token)
