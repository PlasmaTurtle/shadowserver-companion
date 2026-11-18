"""Verified workspace transfers, applied before any database or worker opens."""

from __future__ import annotations

from contextlib import closing, contextmanager
from contextvars import ContextVar
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import stat
import tempfile
import threading
import uuid
from types import SimpleNamespace
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

from .migrations import SCHEMA_VERSION
from .primitives import now

FOLDERS = ("originals", "evidence", "reports", "closures", "inbox", "operations")
DATABASES = ("workbench.sqlite3", "attribution.sqlite3")
MAX_ARCHIVE = 2 * 1024**3
MAX_EXPANDED = 8 * 1024**3
MAX_MEMBERS = 100_000
MAX_MANIFEST = 20 * 1024**2
DISK_RESERVE = 32 * 1024**2
RESTORE_POINTS = 3
ISOLATED_VALIDATION = ContextVar("workspace_backup_validation", default=False)
RESTART_MESSAGE = "Close and reopen the app to apply."
WINDOWS_DEVICES = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {
    prefix + number for prefix in ("COM", "LPT") for number in "123456789¹²³"
}


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def regular_tree(path):
    """Reject symlinks and Windows junctions before copying or removing a tree."""
    path = Path(path).absolute()
    for item in (path, *path.parents):
        if item.is_symlink() or (
            item.exists() and getattr(item.lstat(), "st_file_attributes", 0) & 0x400
        ):
            raise ValueError("Workspace paths cannot contain links or junctions")
    if path.exists():
        for item in path.rglob("*"):
            mode = item.lstat()
            if stat.S_ISLNK(mode.st_mode) or getattr(mode, "st_file_attributes", 0) & 0x400:
                raise ValueError("Workspace files cannot contain links or junctions")
            if not (stat.S_ISREG(mode.st_mode) or stat.S_ISDIR(mode.st_mode)):
                raise ValueError("Workspace contains a nonregular file")


def transfer_dir(root):
    root = Path(root).absolute()
    return root.parent / ("." + root.name + "-companion-transfer")


def restore_dir(root):
    root = Path(root).absolute()
    return root.parent / (root.name + "-restore-points")


def _require_space(folder, required):
    folder = Path(folder)
    while not folder.exists():
        folder = folder.parent
    if shutil.disk_usage(folder).free < required + DISK_RESERVE:
        raise ValueError(
            "Not enough free disk space to safely verify this backup; current data was retained"
        )


def backup_status(root):
    folder = restore_dir(root)
    regular_tree(folder)
    path = folder / "status.json"
    if not path.exists():
        return {"last_export": None, "restore_points": [], "retention": RESTORE_POINTS}
    if path.stat().st_size > 64 * 1024:
        raise ValueError("Backup status is invalid")
    record = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(record, dict) or not isinstance(record.get("restore_points", []), list):
        raise ValueError("Backup status is invalid")
    record["retention"] = RESTORE_POINTS
    return record


def _save_backup_status(root, record):
    folder = restore_dir(root)
    regular_tree(folder)
    folder.mkdir(parents=True, exist_ok=True)
    _write_json(folder / "status.json", record)


def restore_point_path(root, identifier):
    if (
        not isinstance(identifier, str)
        or len(identifier) != 32
        or any(c not in "0123456789abcdef" for c in identifier)
    ):
        raise ValueError("Unknown restore point")
    record = next(
        (p for p in backup_status(root).get("restore_points", []) if p.get("id") == identifier),
        None,
    )
    path = restore_dir(root) / (identifier + ".zip")
    if record is None or not path.is_file() or digest(path) != record.get("sha256"):
        raise ValueError("Restore point is missing or changed")
    return path


def create_restore_point(store, reason="before_import"):
    archive = export_workspace(store)
    folder = restore_dir(store.root)
    temporary = folder / (uuid.uuid4().hex + ".partial")
    identifier = uuid.uuid4().hex
    destination = folder / (identifier + ".zip")
    try:
        _require_space(folder, archive.stat().st_size)
        shutil.copyfile(archive, temporary)
        with temporary.open("r+b") as stream:
            os.fsync(stream.fileno())
        temporary.replace(destination)
        status = backup_status(store.root)
        point = {
            "id": identifier,
            "created_at": now(),
            "reason": reason,
            "bytes": destination.stat().st_size,
            "sha256": digest(destination),
        }
        previous = status.get("restore_points", [])
        status["restore_points"] = [point, *previous][:RESTORE_POINTS]
        _save_backup_status(store.root, status)
        for old in previous[RESTORE_POINTS - 1 :]:
            old_id = old.get("id", "")
            if len(old_id) == 32 and all(c in "0123456789abcdef" for c in old_id):
                (folder / (old_id + ".zip")).unlink(missing_ok=True)
        return point
    except Exception:
        # Never leave an unlisted retained copy when publication fails.
        if not any(
            p.get("id") == identifier for p in backup_status(store.root).get("restore_points", [])
        ):
            destination.unlink(missing_ok=True)
        raise
    finally:
        archive.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)


def before_schema_upgrade(root, old_version, new_version):
    """Full recoverable snapshot before a live schema change; isolated checks never recurse."""
    if ISOLATED_VALIDATION.get() or not 0 < old_version < new_version:
        return None
    return create_restore_point(
        SimpleNamespace(root=Path(root).absolute(), lock=threading.RLock()),
        f"before_schema_{old_version}_to_{new_version}",
    )


def _write_json(path, value):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _file_inventory(root):
    return {
        path.relative_to(root).as_posix(): digest(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _check_staged(root, record):
    if _file_inventory(root) != record.get("files"):
        raise ValueError("Staged workspace has changed; current records were not replaced")
    _check_database(root / "workbench.sqlite3")


def _journal(root):
    folder = transfer_dir(root)
    regular_tree(folder)
    path = folder / "pending.json"
    if not path.exists():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    if (
        record.get("format") != 1
        or record.get("workspace") != str(Path(root).absolute())
        or record.get("operation") not in ("import", "delete")
        or record.get("phase") not in ("ready", "old_moved", "installed")
    ):
        raise ValueError("Invalid pending workspace change; current records were not opened")
    return record


def apply_pending_workspace(root):
    """Recover interrupted renames and switch workspaces before Store construction."""
    root = Path(root).absolute()
    record = _journal(root)
    if record is None:
        return
    folder = transfer_dir(root)
    staged, previous = folder / "replacement", folder / "previous"
    regular_tree(root)
    if record["operation"] == "delete":
        regular_tree(restore_dir(root))
    # A crash between a rename and journal update is recovered from the fixed paths.
    if record["phase"] == "ready":
        if not staged.is_dir():
            raise ValueError("Pending data is missing; current records were not replaced")
        _check_staged(staged, record)
        if root.exists() and not previous.exists():
            root.rename(previous)
        record["phase"] = "old_moved"
        _write_json(folder / "pending.json", record)
    if record["phase"] == "old_moved":
        try:
            if staged.exists():
                if root.exists():
                    raise ValueError("Workspace destination is occupied")
                staged.rename(root)
            if not root.is_dir():
                raise ValueError("Replacement workspace is missing")
            _check_staged(root, record)
        except Exception:
            if root.exists() and not staged.exists():
                root.rename(staged)
            if previous.exists() and not root.exists():
                previous.rename(root)
            record["phase"] = "ready"
            _write_json(folder / "pending.json", record)
            raise
        record["phase"] = "installed"
        _write_json(folder / "pending.json", record)
    # Also recheck after a crash recorded as installed: never discard the old
    # tree if the replacement disappeared or changed before cleanup completed.
    _check_staged(root, record)
    # Deletion is intentionally after the replacement passes database validation.
    if previous.exists():
        shutil.rmtree(previous)
    if record["operation"] == "delete" and restore_dir(root).exists():
        shutil.rmtree(restore_dir(root))
    shutil.rmtree(folder)


def _check_database(path, *, workbench=True):
    if not path.is_file():
        raise ValueError("Backup is missing its database")
    try:
        # Imported databases are standalone snapshots. Immutable mode avoids
        # creating WAL/SHM sidecars while checking a staged file's exact bytes.
        with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro&immutable=1", uri=True)) as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Backup database failed its integrity check")
            if db.execute("PRAGMA foreign_key_check").fetchone():
                raise ValueError("Backup database has broken record references")
            if workbench:
                version = db.execute("PRAGMA user_version").fetchone()[0]
                if not 1 <= version <= SCHEMA_VERSION:
                    raise ValueError("Backup database version is unsupported by this app")
                tables = {
                    r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }
                if not {"settings", "imports", "leads", "entries", "evidence", "reports"} <= tables:
                    raise ValueError("Backup does not contain a Companion database")
    except sqlite3.DatabaseError as error:
        raise ValueError("Backup database is invalid") from error


MAX_REPORT_SNAPSHOT_BYTES = 256 * 1024 * 1024


def _read_snapshot(path, kind):
    """Bound source allocation before decoding legacy or compact snapshots."""
    from .compact_json import loads

    if path.stat().st_size > MAX_REPORT_SNAPSHOT_BYTES:
        raise ValueError(f"Backup {kind} snapshot exceeds the 256 MiB read limit")
    with path.open("rb") as stream:
        raw = stream.read(MAX_REPORT_SNAPSHOT_BYTES + 1)
    if len(raw) > MAX_REPORT_SNAPSHOT_BYTES:
        raise ValueError(f"Backup {kind} snapshot exceeds the 256 MiB read limit")
    try:
        return loads(raw)
    except (ValueError, TypeError, RecursionError, UnicodeError) as error:
        raise ValueError(f"Backup {kind} snapshot could not be decoded: {error}") from error


def _validate_report_snapshot(path):
    """Check report models without rewriting legacy or compact snapshot bytes."""
    model = _read_snapshot(path, "report")
    if not isinstance(model, dict) or not isinstance(model.get("draft"), dict):
        raise ValueError("Backup report snapshot must contain a report object and draft")
    # These fields were introduced in different historical revisions. Validate
    # their broad shape only when present; do not require modern schema fields.
    shapes = {
        "composition": dict,
        "qualified_lead": dict,
        "evidence": list,
        "readiness": list,
        "section_reviews": list,
        "section_history": list,
        "section_validations": list,
    }
    if any(key in model and not isinstance(model[key], kind) for key, kind in shapes.items()):
        raise ValueError("Backup report snapshot contains an invalid report field")


def _validate_closing_snapshot(path):
    """Closing records require the same bounded preflight as notifications."""
    model = _read_snapshot(path, "closing")
    required = ("case_id", "created_at", "closed_by", "disposition", "conclusion")
    if not isinstance(model, dict) or any(not isinstance(model.get(key), str) for key in required):
        raise ValueError("Backup closing snapshot contains invalid closing fields")
    if model["case_id"] != path.parent.parent.name:
        raise ValueError("Backup closing snapshot belongs to a different case")
    shapes = {
        "profile": dict,
        "document_policy": dict,
        "reports": list,
        "attempts": list,
        "events": list,
    }
    if any(key in model and not isinstance(model[key], kind) for key, kind in shapes.items()):
        raise ValueError("Backup closing snapshot contains an invalid closing field")


def validate_workspace(root):
    """Upgrade only the isolated copy, then verify referenced originals and packages."""
    _check_database(root / "workbench.sqlite3")
    if (root / "attribution.sqlite3").exists():
        _check_database(root / "attribution.sqlite3", workbench=False)
    from .package_integrity import member_path, package_folder

    # Startup migration/recovery may read snapshots before the Store is ready.
    # Preflight both recorded reports and completed, not-yet-recorded packages
    # at that boundary, so neither path bypasses the bounded decoder.
    with closing(
        sqlite3.connect(f"{(root / 'workbench.sqlite3').as_uri()}?mode=ro&immutable=1", uri=True)
    ) as db:
        report_paths = {row[0] for row in db.execute("SELECT path FROM reports")}
        # Older supported schemas predate case closures; migration supplies the
        # table later, while any on-disk orphan still needs preflight now.
        has_closures = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='case_closures'"
        ).fetchone()
        closure_paths = (
            {row[0] for row in db.execute("SELECT path FROM case_closures")}
            if has_closures
            else set()
        )
    report_paths.update(
        path.parent.relative_to(root).as_posix()
        for path in (root / "reports").glob("*/v*/manifest.json")
    )
    checked_snapshots = set()
    for relative in report_paths:
        folder = package_folder(root, relative)
        _validate_report_snapshot(member_path(folder, "snapshot.json"))
        checked_snapshots.add(relative)
    closure_paths.update(
        path.parent.relative_to(root).as_posix()
        for path in (root / "closures").glob("*/*/manifest.json")
    )
    for relative in closure_paths:
        folder = package_folder(root, relative)
        _validate_closing_snapshot(member_path(folder, "snapshot.json"))
    from .store import Store

    store = Store(root)
    from .workspace_data_attribution import validate_attribution_data
    from .workspace_data_captures import validate_capture_data
    from .workspace_data_contacts import validate_contact_data
    from .outreach_preparation import validate_saved_preparation
    from .observation_scope import validate_saved_scope
    from .sender_identity import validate_saved_profile
    from .awareness_admission import validate as validate_admission

    validate_attribution_data(store)
    validate_capture_data(store)
    validate_contact_data(store)
    for preparation in store.all("SELECT * FROM outreach_preparations"):
        validate_saved_preparation(preparation)
    with store.read_snapshot() as db:
        validate_admission(db)
        scope_ids = {}
        for entry in db.execute("SELECT case_id,entry_id FROM case_entries"):
            scope_ids.setdefault(entry["case_id"], set()).add(entry["entry_id"])
        for case in db.execute("SELECT id,draft FROM cases"):
            try:
                draft = json.loads(case["draft"])
            except (TypeError, ValueError) as error:
                raise ValueError("Backup case draft is invalid") from error
            if not isinstance(draft, dict):
                raise ValueError("Backup case draft is invalid")
            validate_saved_profile(draft)
            validate_saved_scope(draft, scope_ids.get(case["id"], set()))
    for table in ("imports", "evidence"):
        for row in store.all(f"SELECT * FROM {table}"):
            if digest(member_path(root, row["path"])) != row["sha256"]:
                raise ValueError(f"Backup {table} file failed its SHA-256 check")
            if table == "evidence" and row.get("preview_path"):
                preview = member_path(root, row["preview_path"])
                from .image_evidence import metadata_path

                metadata_file = store.path(metadata_path(row["id"]))
                if metadata_file.is_file():
                    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
                    if (
                        metadata.get("sha256") != row["sha256"]
                        or metadata.get("original_filename") != row["filename"]
                    ):
                        raise ValueError(
                            "Backup screenshot metadata does not match the evidence record"
                        )
                    if (
                        metadata.get("preview_sha256")
                        and digest(preview) != metadata["preview_sha256"]
                    ):
                        raise ValueError(
                            "Backup screenshot preview failed its recorded SHA-256 check"
                        )
    for row in store.all("SELECT * FROM reports"):
        if row["path"] not in checked_snapshots:
            folder = package_folder(root, row["path"])
            _validate_report_snapshot(member_path(folder, "snapshot.json"))
        store.package_inventory(row)
    for row in store.all("SELECT * FROM case_closures"):
        store.closure_inventory(row)
    _check_database(root / "workbench.sqlite3")


def export_workspace(store):
    regular_tree(store.root)
    source_bytes = sum(p.stat().st_size for p in store.root.rglob("*") if p.is_file())
    _require_space(Path(tempfile.gettempdir()), source_bytes * 3)
    handle, archive_path = tempfile.mkstemp(suffix=".zip")
    os.close(handle)
    archive_path = Path(archive_path)
    try:
        with tempfile.TemporaryDirectory() as temporary, store.lock:
            temp = Path(temporary)
            for name in DATABASES:
                source_path = store.root / name
                if not source_path.is_file():
                    continue
                with (
                    closing(sqlite3.connect(source_path)) as source,
                    closing(sqlite3.connect(temp / name)) as destination,
                ):
                    source.backup(destination)
            files = {f"data/{name}": temp / name for name in DATABASES if (temp / name).exists()}
            for name in FOLDERS:
                for path in sorted((store.root / name).rglob("*")):
                    if path.is_file():
                        if name == "operations" and (
                            path.name.endswith(".tmp")
                            or any(
                                part.startswith(".render-")
                                for part in path.relative_to(store.root / name).parts
                            )
                        ):
                            continue
                        files["data/" + path.relative_to(store.root).as_posix()] = path
            manifest = {
                "format": "companion-workspace",
                "version": 1,
                "created_at": now(),
                "files": {},
            }
            if len(files) + 1 > MAX_MEMBERS:
                raise ValueError("Workspace exceeds the backup member limit; no backup was offered")
            for name, path in files.items():
                manifest["files"][name] = digest(path)
            manifest_bytes = json.dumps(manifest, sort_keys=True).encode("utf-8")
            if len(manifest_bytes) > MAX_MANIFEST:
                raise ValueError(
                    "Workspace exceeds the backup manifest limit; no backup was offered"
                )
            expanded = sum(path.stat().st_size for path in files.values()) + len(manifest_bytes)
            if expanded > MAX_EXPANDED:
                raise ValueError("Workspace exceeds the restore size limit; no backup was offered")
            # Evidence PDFs/images are already compressed; prefer fast exports.
            with ZipFile(archive_path, "w", ZIP_DEFLATED, compresslevel=1) as archive:
                for name, path in files.items():
                    archive.write(path, name)
                    if archive_path.stat().st_size > MAX_ARCHIVE:
                        raise ValueError(
                            "Backup exceeds the compressed restore size limit; no backup was offered"
                        )
                archive.writestr("manifest.json", manifest_bytes)
            if archive_path.stat().st_size > MAX_ARCHIVE:
                raise ValueError(
                    "Backup exceeds the compressed restore size limit; no backup was offered"
                )
            # Exercise the actual restore path on an isolated copy, including
            # SQLite, package/evidence hashes and schema compatibility.
            token = ISOLATED_VALIDATION.set(True)
            try:
                unpack_workspace(archive_path, temp / "restore-check")
            finally:
                ISOLATED_VALIDATION.reset(token)
            status = backup_status(store.root)
            status["last_export"] = {
                "verified_at": now(),
                "bytes": archive_path.stat().st_size,
                "sha256": digest(archive_path),
                "expanded_bytes": expanded,
                "members": len(files) + 1,
            }
            _save_backup_status(store.root, status)
        return archive_path
    except Exception:
        archive_path.unlink(missing_ok=True)
        raise


def unpack_workspace(archive_path, target):
    """Extract only known workspace members; legacy exports remain importable."""
    archive_path, target = Path(archive_path), Path(target)
    if archive_path.stat().st_size > MAX_ARCHIVE:
        raise ValueError("Backup exceeds the compressed restore size limit")
    try:
        with ZipFile(archive_path) as archive:
            members = archive.infolist()
            if len(members) > MAX_MEMBERS or sum(m.file_size for m in members) > MAX_EXPANDED:
                raise ValueError("Backup is too large to import")
            _require_space(target.parent, sum(m.file_size for m in members) * 2)
            seen, files = set(), {}
            for item in members:
                name = item.filename
                relative = PurePosixPath(name)
                normalized = name.rstrip("/")
                if (
                    not name
                    or "\\" in name
                    or ":" in name
                    or any(ord(c) < 32 for c in name)
                    or relative.is_absolute()
                    or relative.as_posix() != normalized
                    or any(
                        p in (".", "..")
                        or p.endswith((".", " "))
                        or p.split(".", 1)[0].upper() in WINDOWS_DEVICES
                        for p in relative.parts
                    )
                    or normalized.casefold() in seen
                    or item.flag_bits & 1
                    or stat.S_ISLNK(item.external_attr >> 16)
                ):
                    raise ValueError("Backup contains an unsafe or duplicate path")
                seen.add(normalized.casefold())
                if name == "manifest.json":
                    if item.file_size > MAX_MANIFEST:
                        raise ValueError("Backup manifest is too large")
                    continue
                parts = relative.parts
                if parts[0] != "data" or (
                    len(parts) > 1 and parts[1] not in (*FOLDERS, *DATABASES)
                ):
                    raise ValueError("Backup contains an unexpected workspace file")
                if item.is_dir():
                    continue
                if len(parts) < 2 or (parts[1] in DATABASES and len(parts) != 2):
                    raise ValueError("Backup contains an invalid database path")
                destination = target.joinpath(*parts[1:])
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item) as source, destination.open("xb") as output:
                    shutil.copyfileobj(source, output, length=1024**2)
                files[name] = digest(destination)
            if "manifest.json" in archive.namelist():
                from attribution.models import parse_json

                manifest = parse_json(archive.read("manifest.json"))
                if (
                    manifest.get("format") != "companion-workspace"
                    or manifest.get("version") != 1
                    or manifest.get("files") != files
                ):
                    raise ValueError("Backup manifest or SHA-256 verification failed")
        token = ISOLATED_VALIDATION.set(True)
        try:
            validate_workspace(target)
        finally:
            ISOLATED_VALIDATION.reset(token)
    except (BadZipFile, sqlite3.Error, KeyError, TypeError, OSError) as error:
        raise ValueError(f"Backup could not be verified: {error}") from error


class WorkspaceData:
    """Admission gate shared by HTTP requests and the idle inbox worker."""

    def __init__(self, app, store):
        self.app, self.store = app, store
        self.lock = threading.RLock()
        self.active_requests = 0
        self.preparing = False
        self.updating = False
        self.pending = _journal(store.root)
        store.maintenance = threading.Event()
        if self.pending:
            store.maintenance.set()
        # Reference feeds have independent timers. Bind the already-created
        # managers without initializing an unavailable optional catalog.
        catalog = getattr(app.state, "cve_catalog", None)
        if catalog is not None:
            catalog.maintenance = store.maintenance
        manager = getattr(catalog, "manager", catalog)
        if manager is not None:
            manager.maintenance = store.maintenance
            risk = getattr(manager, "risk", None)
            if risk is not None:
                risk.maintenance = store.maintenance

    def status(self):
        return {
            "pending": self.pending["operation"] if self.pending else None,
            "preparing": self.preparing,
            "updating": self.updating,
            "message": RESTART_MESSAGE if self.pending else "",
            "backup": backup_status(self.store.root),
            "backup_limits": {
                "compressed_bytes": MAX_ARCHIVE,
                "expanded_bytes": MAX_EXPANDED,
                "members": MAX_MEMBERS,
            },
            "restore_point_skipped": bool(
                self.pending and self.pending.get("restore_point_skipped")
            ),
        }

    def enter_request(self, path, method):
        with self.lock:
            if self.updating and path != "/api/software/status":
                return (
                    "A software update is starting. The workspace will reopen after installation."
                )
            control = path.startswith("/api/data/") or path == "/api/backup"
            if self.preparing and path != "/api/data/status":
                return "A data operation is in progress. Try again when it finishes."
            if (
                self.pending
                and method not in ("GET", "HEAD", "OPTIONS")
                and path != "/api/data/cancel"
            ):
                return "A data change is staged. " + RESTART_MESSAGE + " Or cancel it in Settings."
            if not control:
                self.active_requests += 1
        return None

    def exit_request(self, path):
        if not (path.startswith("/api/data/") or path == "/api/backup"):
            with self.lock:
                self.active_requests -= 1

    def _require_idle_services(self, action):
        # Never hold the store writer lock while acquiring service locks: a
        # worker can hold its service lock before committing to the workspace.
        for name in (
            "report_operations",
            "source_jobs",
            "website_jobs",
            "asset_attribution_jobs",
            "contact_discovery_jobs",
            "contact_jobs",
            "api_acquisition",
            "acquisition_schedule",
            "workspace_health_jobs",
            "entity_dns",
        ):
            service = getattr(self.app.state, name, None)
            if service is not None and service.busy():
                raise ValueError(f"Wait for active reports and lookups to finish before {action}.")
        catalog = getattr(self.app.state, "cve_catalog", None)
        busy = getattr(catalog, "busy", None)
        if busy is not None and busy():
            raise ValueError(
                f"Wait for CVE catalog, risk feed and product index updates to finish before {action}."
            )

    def begin_update(self):
        """Reserve an idle workspace before handing its runtime to the installer."""
        with self.lock:
            # The authenticated install request itself owns one admission slot.
            if self.preparing or self.pending or self.updating or self.active_requests > 1:
                return "Finish current work or cancel the staged data change before updating."
            self.updating = True
            self.store.maintenance.set()
            try:
                with self.store.lock:
                    if self.store.one(
                        "SELECT id FROM imports WHERE status IN ('queued','running') LIMIT 1"
                    ):
                        raise ValueError("Wait for report intake to finish before updating.")
                self._require_idle_services("updating")
            except Exception as error:
                self.cancel_update()
                if isinstance(error, ValueError):
                    return str(error)
                raise
        return None

    def cancel_update(self):
        with self.lock:
            self.updating = False
            if not self.preparing and not self.pending:
                self.store.maintenance.clear()

    @contextmanager
    def operation(self):
        with self.lock:
            if self.preparing or self.pending or self.updating or self.active_requests:
                raise ValueError(
                    "Finish current work or cancel the staged data change before continuing"
                )
            self.preparing = True
            self.store.maintenance.set()
        try:
            self._require_idle_services("managing data")
            with self.store.lock:
                if self.store.one(
                    "SELECT id FROM imports WHERE status IN ('queued','running') LIMIT 1"
                ):
                    raise ValueError("Wait for report intake to finish before managing data")
                # Keep the writer reservation throughout backup/staging; only
                # service inspection belongs outside this consistency boundary.
                yield
        finally:
            with self.lock:
                self.preparing = False
                if not self.pending:
                    self.store.maintenance.clear()

    def stage(self, operation, archive_path=None, *, retain_current=True):
        with self.operation():
            folder = transfer_dir(self.store.root)
            regular_tree(folder)
            if folder.exists():
                shutil.rmtree(folder)
            staged = folder / "replacement"
            staged.mkdir(parents=True)
            try:
                if operation == "import":
                    unpack_workspace(archive_path, staged)
                    if retain_current:
                        create_restore_point(self.store, "before_import")
                elif operation == "delete":
                    from .store import Store

                    Store(staged)
                    regular_tree(restore_dir(self.store.root))
                else:
                    raise ValueError("Unknown data operation")
                record = {
                    "format": 1,
                    "workspace": str(self.store.root),
                    "operation": operation,
                    "phase": "ready",
                    "created_at": now(),
                    "files": _file_inventory(staged),
                    "restore_point_skipped": operation == "import" and not retain_current,
                }
                _write_json(folder / "pending.json", record)
                self.pending = record
            except Exception:
                shutil.rmtree(folder)
                raise
        return self.status()

    def cancel(self):
        with self.lock:
            if self.preparing:
                raise ValueError("Wait for the current data operation to finish")
            folder = transfer_dir(self.store.root)
            regular_tree(folder)
            if folder.exists():
                shutil.rmtree(folder)
            self.pending = None
            self.store.maintenance.clear()
        return self.status()
