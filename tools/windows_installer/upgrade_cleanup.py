"""Remove only unchanged, obsolete installer-owned program files before upgrade.

Standalone standard-library helper staged outside the installation by NSIS. Case
workspaces are outside this policy, even if an installed inventory is modified.
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import runpy
import stat
import sqlite3
from contextlib import closing
import sys

MAX_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_FILES = 50_000
POLICY = "program-assets-and-synthetic-fixtures-v1"
APP_FOLDERS = {
    "workbench",
    "static",
    "schemas",
    "fonts",
    "examples",
    "tools",
    "components",
    "docs",
    "resources",
}
APP_FILES = {
    "run.py",
    "excel_intake.py",
    "desktop.py",
    "VERSION",
    "RELEASE.json",
    "HOME_VALIDATION.md",
    "README.md",
    "CHANGELOG.md",
    "VALIDATION.md",
    "DEPENDENCIES.md",
    "REPORT_REQUIREMENTS.md",
    "ARCHITECTURE.md",
    "DEVELOPMENT.md",
    "SECURITY.md",
    "requirements-constraints.txt",
}
PROTECTED = {
    "data",
    "data-demo",
    "demo-data",
    "workspace",
    "workspaces",
    "evidence",
    "reports",
    "completed",
    "backups",
    "backup",
    "logs",
    "imports",
    "exports",
    "uploads",
}
RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(10)),
    *(f"lpt{i}" for i in range(10)),
}


class UpgradeError(ValueError):
    """Upgrade cannot safely remove prior program assets."""


def member_parts(name: str) -> tuple[str, ...]:
    if not isinstance(name, str) or not name or len(name) > 1024:
        raise UpgradeError("Invalid inventory filename")
    parts = PurePosixPath(name).parts
    if not parts or PurePosixPath(name).is_absolute() or "/".join(parts) != name:
        raise UpgradeError(f"Noncanonical inventory path: {name!r}")
    for part in parts:
        if (
            part in {".", ".."}
            or part.endswith((".", " "))
            or any(ord(c) < 32 or c in '\\:<>"|?*' for c in part)
            or part.split(".", 1)[0].casefold() in RESERVED
        ):
            raise UpgradeError(f"Unsafe inventory path: {name!r}")
    # No inventory can authorize cleanup of user records, including a workspace
    # accidentally placed beneath an otherwise approved program directory.
    if any(p.casefold() in PROTECTED for p in parts):
        raise UpgradeError(f"Workspace path is outside upgrade cleanup policy: {name}")
    allowed = (
        name in {"Getting started.txt", "Third-party notices.txt"}
        or (len(parts) == 2 and parts[0] == "app" and parts[1] in APP_FILES)
        or (len(parts) >= 3 and parts[0] == "app" and parts[1] in APP_FOLDERS)
        or (
            len(parts) == 2
            and parts[0] == "runtime"
            and PurePosixPath(name).suffix.lower()
            in {".exe", ".dll", ".pyd", ".zip", "._pth", ".txt", ".cat"}
        )
        or (len(parts) >= 4 and parts[:3] == ("runtime", "Lib", "site-packages"))
    )
    if not allowed:
        raise UpgradeError(f"Path is outside program/runtime cleanup policy: {name}")
    return parts


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise UpgradeError("Duplicate inventory JSON key")
        result[key] = value
    return result


def _plain_file(path: Path) -> os.stat_result:
    info = path.lstat()
    # Windows junctions and other reparse points are not allowed either.
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise UpgradeError(f"Linked/reparse-point path is not permitted: {path}")
    return info


def read_inventory(path: Path, *, with_metadata=False):
    info = _plain_file(path)
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_MANIFEST_BYTES:
        raise UpgradeError("Inventory must be a regular file within the size limit")
    with path.open("rb") as source:
        data = source.read(MAX_MANIFEST_BYTES + 1)
    if len(data) > MAX_MANIFEST_BYTES:
        raise UpgradeError("Inventory exceeds size limit")
    try:
        manifest = json.loads(data, object_pairs_hook=_unique_object)
    except (ValueError, RecursionError) as exc:
        raise UpgradeError("Invalid inventory JSON") from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("distribution_policy") != POLICY
        or not isinstance(manifest.get("application_version"), str)
        or not re.fullmatch(r"\d+\.\d+\.\d+", manifest["application_version"])
    ):
        raise UpgradeError("Unrecognized installer inventory schema")
    files = manifest.get("files")
    if not isinstance(files, dict) or not 1 <= len(files) <= MAX_FILES:
        raise UpgradeError("Invalid installer file inventory")
    names = set()
    for name, digest in files.items():
        member_parts(name)
        if name.casefold() in names:
            raise UpgradeError(f"Case-colliding inventory filename: {name}")
        names.add(name.casefold())
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise UpgradeError(f"Invalid SHA-256 inventory digest: {name}")
    return (files, manifest) if with_metadata else files


def manifest_edition(manifest):
    release = manifest.get("release", {})
    edition = release.get("edition", "standard") if isinstance(release, dict) else None
    if not isinstance(edition, str) or edition not in {"standard", "chaos"}:
        raise UpgradeError("Unrecognized installer edition; program files were retained")
    return edition


def manifest_identity(manifest):
    edition = manifest_edition(manifest)
    variant = manifest.get("release", {}).get("variant", "")
    if (
        not isinstance(variant, str)
        or variant not in {"", "dark_matter"}
        or (variant and edition != "chaos")
    ):
        raise UpgradeError("Unrecognized installer variant; program files were retained")
    return edition, variant


def check_workspace_compatibility(manifest):
    maximum = manifest.get("database_schema_max")
    local = os.environ.get("LOCALAPPDATA")
    if maximum is None or not local:
        return
    if not isinstance(maximum, int) or maximum < 1:
        raise UpgradeError("Invalid supported database schema")
    edition, variant = manifest_identity(manifest)
    namespace = (
        "ShadowserverCompanionDarkMatter"
        if variant == "dark_matter"
        else "ShadowserverCompanionChaos"
        if edition == "chaos"
        else "OutreachWorkbench"
    )
    workspace = Path(local).absolute() / namespace / "data"
    database = workspace / "workbench.sqlite3"
    for part in (database, *database.parents):
        if part.exists() or part.is_symlink():
            _plain_file(part)
    if not database.exists():
        return
    try:
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
    except sqlite3.Error as error:
        raise UpgradeError(
            "Existing data compatibility could not be checked; program files were retained"
        ) from error
    if version > maximum:
        raise UpgradeError(
            f"Existing data uses schema {version}; this installer supports through {maximum}. "
            "Use a compatible application version or restore its matching backup."
        )


def safe_target(root: Path, parts: tuple[str, ...], *, directory: bool = False) -> Path:
    current = root
    for index, part in enumerate(parts):
        current = current / part
        try:
            info = _plain_file(current)
        except FileNotFoundError:
            return current.joinpath(*parts[index + 1 :])
        if index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise UpgradeError(f"Program path parent is not a directory: {current}")
        if index == len(parts) - 1 and not (
            stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
        ):
            raise UpgradeError(f"Inventory member is not a regular file: {current}")
    return current


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def generated_caches(root: Path) -> list[Path]:
    """Inventory disposable Python bytecode without following links or user data.

    -B prevents current launchers creating caches, but older launches, task runners
    and runtime tools can leave them behind. They are not in the shipped manifest.
    """
    result = []
    for folder in (root / "app", root / "runtime"):
        if not folder.exists() and not folder.is_symlink():
            continue
        if not stat.S_ISDIR(_plain_file(folder).st_mode):
            raise UpgradeError(f"Program root is not a directory: {folder}")
        for directory, dirs, files in os.walk(folder, followlinks=False):
            base = Path(directory)
            # Never traverse case records even if somebody put them below app/.
            dirs[:] = [name for name in dirs if name.casefold() not in PROTECTED]
            for name in dirs:
                _plain_file(base / name)
            for name in files:
                path = base / name
                info = _plain_file(path)
                if not stat.S_ISREG(info.st_mode):
                    raise UpgradeError(f"Program member is not a regular file: {path}")
                if path.suffix.lower() in {".pyc", ".pyo"}:
                    parts = path.relative_to(root).parts
                    if any(part.casefold() in PROTECTED for part in parts):
                        continue
                    # Only Python cache locations, not arbitrary .pyc exports.
                    if "__pycache__" in parts or path.with_suffix(".py").is_file():
                        result.append(path)
    return result


def remove_caches(root: Path, caches: list[Path]) -> list[str]:
    removed = []
    parents = set()
    # Empty cache folders also survive a static file inventory uninstall.
    for folder in (root / "app", root / "runtime"):
        if not folder.exists():
            continue
        for directory, dirs, _files in os.walk(folder, followlinks=False):
            dirs[:] = [name for name in dirs if name.casefold() not in PROTECTED]
            base = Path(directory)
            if "__pycache__" in base.relative_to(root).parts:
                for parent in (base, *base.parents):
                    if parent == root:
                        break
                    parents.add(parent)
    for path in caches:
        path = safe_target(root, path.relative_to(root).parts)
        path.unlink()
        removed.append(path.relative_to(root).as_posix())
        for parent in path.parents:
            if parent == root:
                break
            parents.add(parent)
    for parent in sorted(parents, key=lambda p: (-len(p.parts), str(p))):
        try:
            parent = safe_target(root, parent.relative_to(root).parts, directory=True)
            parent.rmdir()
        except FileNotFoundError:
            pass
        except OSError as exc:
            if exc.errno not in {errno.ENOTEMPTY, errno.EEXIST}:
                raise
    return removed


def repair_without_inventory(
    root: Path, next_files: dict, caches: list[Path], metadata: dict, *, known_installation=False
) -> None:
    """Accept a partial known payload or cache-only leftovers, not unknown code."""
    cache_set = set(caches)
    allowed = {name.casefold() for name in next_files}
    edition, variant = manifest_identity(metadata)
    namespace = (
        "ShadowserverCompanionDarkMatter"
        if variant == "dark_matter"
        else "ShadowserverCompanionChaos"
        if edition == "chaos"
        else "OutreachWorkbench"
    )
    local = os.environ.get("LOCALAPPDATA")
    canonical = (
        bool(local)
        and Path(local).is_absolute()
        and os.path.normcase(str(root))
        == os.path.normcase(str(Path(local).absolute() / "Programs" / namespace))
    )
    owned = known_installation or canonical
    release_path = root / "app" / "RELEASE.json"
    if release_path.exists():
        info = _plain_file(release_path)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 65536:
            raise UpgradeError("Existing release metadata cannot be verified")
        try:
            release = json.loads(release_path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError):
            release = None  # A known location can repair corrupt program metadata.
        if isinstance(release, dict) and "edition" in release:
            if manifest_identity({"release": release}) != (edition, variant):
                raise UpgradeError("Different application edition is installed here")
            owned = True
            previous = release.get("version", "")
            if isinstance(previous, str) and re.fullmatch(r"\d+\.\d+\.\d+", previous):
                if tuple(map(int, previous.split("."))) > tuple(
                    map(int, metadata["application_version"].split("."))
                ):
                    raise UpgradeError("A newer application is installed; downgrade stopped")
    for folder in (root / "app", root / "runtime"):
        if not folder.exists():
            continue
        for directory, dirs, files in os.walk(folder, followlinks=False):
            base = Path(directory)
            dirs[:] = [name for name in dirs if name.casefold() not in PROTECTED]
            for name in dirs:
                _plain_file(base / name)
            for name in files:
                path = base / name
                _plain_file(path)
                if not owned:
                    raise UpgradeError(
                        "Existing program has no inventory or recognized installation identity. "
                        "Select the application's program folder; working records are retained."
                    )
                if path in cache_set:
                    continue
                relative = path.relative_to(root).as_posix()
                if relative.casefold() not in allowed:
                    raise UpgradeError(
                        "Existing program has no inventory and contains unrecognized code: "
                        f"{relative}. Move that file aside or choose a fresh program folder; "
                        "working records are retained."
                    )


def uninstall(install_dir: Path, installed_manifest: Path) -> list[str]:
    """Remove generated bytecode before NSIS deletes its static owned inventory.

    The manifest is embedded in this uninstaller and staged with a fresh runtime;
    neither a missing installed interpreter nor a removed local manifest blocks it.
    """
    root = Path(os.path.abspath(install_dir))
    for part in (root, *root.parents):
        if part.exists() or part.is_symlink():
            if not stat.S_ISDIR(_plain_file(part).st_mode):
                raise UpgradeError("Installation location is not a directory")
    files = read_inventory(installed_manifest)
    for name in files:
        safe_target(root, member_parts(name))
    caches = generated_caches(root)
    return remove_caches(root, caches)


def remove_scheduled_task(manifest_path: Path) -> None:
    """Use the staged standard-library adapter, not a possibly broken old app."""
    _, metadata = read_inventory(manifest_path, with_metadata=True)
    edition, variant = manifest_identity(metadata)
    namespace = (
        "ShadowserverCompanionDarkMatter"
        if variant == "dark_matter"
        else "ShadowserverCompanionChaos"
        if edition == "chaos"
        else "OutreachWorkbench"
    )
    local = os.environ.get("LOCALAPPDATA")
    if not local or not Path(local).is_absolute():
        raise UpgradeError("Windows did not provide the workspace location")
    adapter = runpy.run_path(str(Path(__file__).with_name("windows_schedule.py")))
    adapter["configure"](Path(local) / namespace / "data", False)


def cleanup(
    install_dir: Path, next_manifest: Path, *, reset_data=False, known_installation=False
) -> list[str]:
    # abspath preserves link components instead of concealing them with resolve().
    root = Path(os.path.abspath(install_dir))
    for part in (root, *root.parents):
        try:
            info = _plain_file(part)
        except FileNotFoundError:
            continue
        if not stat.S_ISDIR(info.st_mode):
            raise UpgradeError("Installation location is not a directory")
    next_files, next_metadata = read_inventory(next_manifest, with_metadata=True)
    next_identity = manifest_identity(next_metadata)
    caches = generated_caches(root)
    prior_path = root / "payload-manifest.json"
    if not prior_path.exists() and not prior_path.is_symlink():
        repair_without_inventory(
            root, next_files, caches, next_metadata, known_installation=known_installation
        )
        for name in next_files:
            safe_target(root, member_parts(name))
        if not reset_data:
            check_workspace_compatibility(next_metadata)
        return remove_caches(root, caches)
    prior_files, prior_metadata = read_inventory(prior_path, with_metadata=True)
    if manifest_identity(prior_metadata) != next_identity:
        raise UpgradeError(
            "Different application edition or variant is installed here; use the separate edition's folder. "
            "Program files and working records were retained."
        )
    if not reset_data:
        check_workspace_compatibility(next_metadata)
    if tuple(map(int, next_metadata["application_version"].split("."))) < tuple(
        map(int, prior_metadata["application_version"].split("."))
    ):
        raise UpgradeError(
            "A newer application is installed; downgrade stopped before changing program files"
        )
    # Check all old and new destinations before changing anything. This also
    # prevents the subsequent overlay from writing through a linked directory.
    for name in prior_files.keys() | next_files.keys():
        safe_target(root, member_parts(name))
    next_names = {name.casefold() for name in next_files}
    obsolete_names = [name for name in prior_files if name.casefold() not in next_names]
    obsolete = []
    for name in obsolete_names:
        digest = prior_files[name]
        target = safe_target(root, member_parts(name))
        if not target.exists():
            continue
        if sha256(target) != digest:
            raise UpgradeError(f"Obsolete program file was modified; upgrade stopped: {name}")
        obsolete.append((name, digest))
    # Preflight is complete: changed obsolete files never cause partial cleanup.
    # Unlisted files stay put. Only empty prior-inventory parent directories may
    # later be removed with rmdir; empty old .dist-info still affects discovery.
    removed = remove_caches(root, caches)
    for name, digest in obsolete:
        target = safe_target(root, member_parts(name))
        if sha256(target) != digest:
            raise UpgradeError(f"Program file changed during upgrade; upgrade stopped: {name}")
        target.unlink()
        removed.append(name)
    preserved_roots = {
        ("app",),
        ("runtime",),
        ("runtime", "Lib"),
        ("runtime", "Lib", "site-packages"),
    }
    parents = set()
    for name in obsolete_names:
        parts = member_parts(name)
        for length in range(1, len(parts)):
            parent = parts[:length]
            if parent not in preserved_roots:
                parents.add(parent)
    for parts in sorted(parents, key=lambda p: (-len(p), p)):
        target = safe_target(root, parts, directory=True)
        try:
            target.rmdir()
        except FileNotFoundError:
            pass
        except OSError as exc:
            if exc.errno not in {errno.ENOTEMPTY, errno.EEXIST}:
                raise
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-dir", required=True, type=Path)
    parser.add_argument("--next-manifest", required=True, type=Path)
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--remove-task", action="store_true")
    parser.add_argument("--known-installation", action="store_true")
    parser.add_argument(
        "--reset-data",
        action="store_true",
        help="Interactive installer has confirmed a complete data reset",
    )
    args = parser.parse_args()
    try:
        if args.remove_task:
            remove_scheduled_task(args.next_manifest)
            print("Removed this workspace's optional scheduled task.")
            return 0
        removed = (
            uninstall(args.install_dir, args.next_manifest)
            if args.uninstall
            else cleanup(
                args.install_dir,
                args.next_manifest,
                reset_data=args.reset_data,
                known_installation=args.known_installation,
            )
        )
    except (OSError, ValueError) as exc:
        print(f"Upgrade stopped before installing program files: {exc}", file=sys.stderr)
        return 1
    print(
        f"Verified prior inventory; removed {len(removed)} obsolete program files. Workspaces retained."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
