"""Fresh-start helper. Never accepts an arbitrary deletion target."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import stat
import tempfile


def _regular_tree(path):
    for item in (path, *path.parents):
        if item.is_symlink() or (
            item.exists() and getattr(item.lstat(), "st_file_attributes", 0) & 0x400
        ):
            raise ValueError("Data path contains a link or junction; records were retained")
    if path.exists():
        if not path.is_dir():
            raise ValueError("Data path is not a directory; records were retained")
        for item in path.rglob("*"):
            mode = item.lstat()
            if (
                stat.S_ISLNK(mode.st_mode)
                or getattr(mode, "st_file_attributes", 0) & 0x400
                or not (stat.S_ISREG(mode.st_mode) or stat.S_ISDIR(mode.st_mode))
            ):
                raise ValueError("Data contains a link or nonregular file; records were retained")


def start_fresh(local_app_data, *, edition="standard", variant=""):
    # Keep this standalone: the installer invokes it with -I -S before importing
    # any installed code. Only the selected edition's fixed namespace is allowed.
    namespaces = {"standard": "OutreachWorkbench", "chaos": "ShadowserverCompanionChaos"}
    if not isinstance(edition, str) or edition not in namespaces:
        raise ValueError("Unknown application edition; records were retained")
    if not isinstance(variant, str) or variant not in {"", "dark_matter"}:
        raise ValueError("Unknown application variant; records were retained")
    if variant and edition != "chaos":
        raise ValueError(
            "DarkMatter requires the Chaos experimental edition; records were retained"
        )
    namespace = (
        "ShadowserverCompanionDarkMatter" if variant == "dark_matter" else namespaces[edition]
    )
    parent = Path(local_app_data).absolute() / namespace
    workspace = parent / "data"
    pending = parent / ".data-companion-transfer"
    restore_points = parent / "data-restore-points"
    # Preflight both targets before any rename, including obsolete pending imports.
    _regular_tree(workspace)
    _regular_tree(pending)
    _regular_tree(restore_points)
    parent.mkdir(parents=True, exist_ok=True)
    quarantine = Path(tempfile.mkdtemp(prefix=".fresh-start-", dir=parent))
    moved = []
    try:
        for source, name in (
            (workspace, "data"),
            (pending, "pending"),
            (restore_points, "restore-points"),
        ):
            if source.exists():
                destination = quarantine / name
                source.rename(destination)
                moved.append((source, destination))
        workspace.mkdir()
    except Exception:
        for source, destination in reversed(moved):
            if not source.exists():
                destination.rename(source)
        if not any(quarantine.iterdir()):
            quarantine.rmdir()
        raise
    # The app now sees an empty data directory, with no pending restore to override it.
    shutil.rmtree(quarantine)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirmation", required=True, choices=("DELETE",))
    parser.add_argument("--edition", required=True, choices=("standard", "chaos"))
    parser.add_argument("--variant", default="", choices=("", "dark_matter"))
    args = parser.parse_args()
    local = os.environ.get("LOCALAPPDATA")
    if not local or not Path(local).is_absolute():
        raise ValueError("Windows local app-data directory is unavailable")
    start_fresh(local, edition=args.edition, variant=args.variant)
    print(
        "Started fresh. Working data, managed restore points and pending data changes were deleted."
    )


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        raise SystemExit(str(error)) from error
