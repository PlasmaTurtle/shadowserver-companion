"""Offline recovery entry point. No normal application or Store is initialized.

python -m workbench.workspace_recovery --data-dir PATH check
python -m workbench.workspace_recovery --data-dir PATH restore BACKUP --confirm RESTORE
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager, closing
import json
import os
from pathlib import Path
import sqlite3
import threading
from types import SimpleNamespace
from uuid import uuid4

from .workspace_data import (
    _check_database,
    _file_inventory,
    _require_space,
    _write_json,
    create_restore_point,
    regular_tree,
    transfer_dir,
    unpack_workspace,
)
from .workspace_health import inspect_workspace
from .workspace_lock import acquire_lock


def _marker(root):
    return root.parent / ("." + root.name + "-companion-recovery.json")


def guard_interrupted_recovery(root):
    """Startup must not create an empty workspace after a crash between renames."""
    root = Path(root).absolute()
    if _marker(root).exists():
        raise ValueError(
            "Offline recovery was interrupted. Preserve the recovery folder and run workspace_recovery rollback --confirm ROLLBACK before reopening the app."
        )


@contextmanager
def exclusive_workspace(root, *, allow_interrupted=False):
    root = Path(root).absolute()
    if not root.parent.is_dir():
        raise ValueError("The workspace parent folder does not exist")
    guard = acquire_lock(root.parent, "." + root.name + "-companion.lock")
    try:
        if not allow_interrupted:
            guard_interrupted_recovery(root)
        if root.exists():
            regular_tree(root)
            # Probe legacy launchers too; release before a Windows folder rename.
            if (root / "workspace.lock").exists():
                legacy = acquire_lock(root)
                legacy.close()
        if transfer_dir(root).exists():
            raise ValueError(
                "A data change is already staged. Cancel it in the app before offline recovery."
            )
        yield root
    finally:
        guard.close()


def restore(root, archive, *, confirmation, cancelled=lambda: False):
    """Verify first, preserve the entire previous tree, then install atomically.

    Both moves stay on the same volume. A failed install rolls back the original;
    the durable record identifies preserved/staged trees after a process crash.
    """
    if confirmation != "RESTORE":
        raise ValueError("Use --confirm RESTORE to apply the selected backup")
    with exclusive_workspace(root) as root:
        archive = Path(archive).absolute()
        if not archive.is_file() or archive.is_symlink():
            raise ValueError("Select a regular backup ZIP file")
        recovery = root.parent / (root.name + "-recovery-" + uuid4().hex)
        recovery.mkdir()
        staged, preserved = recovery / "replacement", recovery / "preserved"
        journal = recovery / "recovery.json"
        record = {
            "format": 1,
            "workspace": str(root),
            "phase": "verifying",
            "preserved": str(preserved),
            "recovery_folder": recovery.name,
        }
        _write_json(journal, record)
        moved = False
        installed = False
        try:
            unpack_workspace(archive, staged)
            inventory = _file_inventory(staged)
            if cancelled():
                raise InterruptedError("Recovery cancelled before replacing the workspace")
            record.update(phase="verified", files=inventory)
            _write_json(journal, record)
            _write_json(_marker(root), record)
            if root.exists():
                os.replace(root, preserved)
                moved = True
            record["phase"] = "original_preserved"
            _write_json(journal, record)
            if cancelled():
                raise InterruptedError("Recovery cancelled before installing the backup")
            os.replace(staged, root)
            installed = True
            if _file_inventory(root) != inventory:
                raise ValueError("Verified backup changed during installation")
            _check_database(root / "workbench.sqlite3")
            record["phase"] = "completed"
            _write_json(journal, record)
            _marker(root).unlink(missing_ok=True)
            return {
                "ok": True,
                "workspace": str(root),
                "preserved_workspace": str(preserved) if moved else None,
                "recovery_record": str(journal),
            }
        except BaseException:
            if installed and root.exists():
                os.replace(root, staged)
            if moved and preserved.exists() and not root.exists():
                os.replace(preserved, root)
            record["phase"] = "rolled_back"
            _write_json(journal, record)
            _marker(root).unlink(missing_ok=True)
            # Keep staged bytes and diagnostics for inspection; never erase the
            # current/damaged workspace or another recovery's preserved tree.
            raise


def rollback(root, *, confirmation):
    if confirmation != "ROLLBACK":
        raise ValueError("Use --confirm ROLLBACK to recover the preserved original workspace")
    with exclusive_workspace(root, allow_interrupted=True) as root:
        marker = _marker(root)
        if not marker.is_file() or marker.is_symlink() or marker.stat().st_size > 20 * 1024**2:
            raise ValueError("No valid interrupted recovery record is available")
        record = json.loads(marker.read_text(encoding="utf-8"))
        folder = record.get("recovery_folder", "")
        prefix = root.name + "-recovery-"
        suffix = folder.removeprefix(prefix)
        if (
            record.get("format") != 1
            or record.get("workspace") != str(root)
            or not folder.startswith(prefix)
            or len(suffix) != 32
            or any(char not in "0123456789abcdef" for char in suffix)
        ):
            raise ValueError("Interrupted recovery record has an invalid workspace identity")
        recovery = root.parent / folder
        regular_tree(recovery)
        preserved = recovery / "preserved"
        interrupted = recovery / "interrupted-install"
        if preserved.is_dir():
            if root.exists():
                if interrupted.exists():
                    raise ValueError(
                        "An interrupted installation is already preserved; inspect the recovery folder before proceeding"
                    )
                os.replace(root, interrupted)
            try:
                os.replace(preserved, root)
            except BaseException:
                if interrupted.exists() and not root.exists():
                    os.replace(interrupted, root)
                raise
        elif not root.exists():
            raise ValueError("The preserved original is missing; do not initialize a new workspace")
        record["phase"] = "rolled_back"
        _write_json(recovery / "recovery.json", record)
        marker.unlink()
        return {
            "ok": True,
            "workspace": str(root),
            "recovery_record": str(recovery / "recovery.json"),
        }


def compact(root, *, confirmation):
    if confirmation != "COMPACT":
        raise ValueError("Use --confirm COMPACT after reviewing workspace health")
    with exclusive_workspace(root) as root:
        health = inspect_workspace(root)
        core = [item for item in health["stores"] if item["store"] in ("workspace", "attribution")]
        if any(item["status"] not in ("ok", "absent") for item in core):
            raise ValueError("Repair workspace integrity and references before compaction")
        _require_space(
            root.parent, sum(item["database_bytes"] * 3 + item["wal_bytes"] for item in core)
        )
        point = create_restore_point(
            SimpleNamespace(root=root, lock=threading.RLock()), "before_compaction"
        )
        reclaimed = 0
        for name in ("workbench.sqlite3", "attribution.sqlite3"):
            path = root / name
            if not path.is_file():
                continue
            with closing(sqlite3.connect(path, timeout=2)) as db:
                db.execute("PRAGMA busy_timeout=2000")
                # Keep the SQLite exclusive lock through checkpoint and VACUUM,
                # rejecting even an external unmanaged reader/writer.
                db.execute("PRAGMA locking_mode=EXCLUSIVE")
                db.execute("BEGIN EXCLUSIVE")
                db.commit()
                if db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]:
                    raise ValueError(
                        "Database is in use. Close all workspace programs before compaction."
                    )
                before = path.stat().st_size
                db.execute("VACUUM")
                if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Compaction verification failed; restore the saved checkpoint")
            reclaimed += max(0, before - path.stat().st_size)
        return {"ok": True, "reclaimed_database_bytes": reclaimed, "restore_point": point}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Inspect or recover a workspace without starting the application. Close the app before restore or compaction."
    )
    parser.add_argument("--data-dir", type=Path, required=True)
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("check", help="Read-only database, evidence, storage and feed checks")
    recover = commands.add_parser(
        "restore", help="Verify a selected ZIP and preserve the previous workspace"
    )
    recover.add_argument("archive", type=Path)
    recover.add_argument("--confirm", required=True)
    vacuum = commands.add_parser(
        "compact", help="Compact compatible databases with a verified restore point"
    )
    vacuum.add_argument("--confirm", required=True)
    undo = commands.add_parser(
        "rollback", help="Recover the preserved original after an interrupted offline restore"
    )
    undo.add_argument("--confirm", required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "check":
            result = inspect_workspace(args.data_dir)
        elif args.action == "restore":
            result = restore(args.data_dir, args.archive, confirmation=args.confirm)
        elif args.action == "compact":
            result = compact(args.data_dir, confirmation=args.confirm)
        else:
            result = rollback(args.data_dir, confirmation=args.confirm)
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1
    except (OSError, ValueError, sqlite3.Error, SystemExit, RuntimeError) as error:
        print(
            json.dumps(
                {
                    "ok": False,
                    "message": str(error),
                    "action": "Preserve the workspace. Close running instances and select a verified backup explicitly.",
                },
                indent=2,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
