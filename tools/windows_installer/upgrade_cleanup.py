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
import tempfile
import time
from contextlib import closing
import sys

MAX_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_FILES = 50_000
POLICY = "program-assets-and-synthetic-fixtures-v1"
BOOTSTRAP_PROTOCOL = 1
BOOTSTRAP_LEDGER = "bootstrap-ledger.json"
READY_MARKER = "installation-ready.ini"
TASK_JOURNAL = "installation-task.json"
APP_FOLDERS = {
    "static",
    "schemas",
    "tools",
    "fonts",
    "components",
    "examples",
    "docs",
    "workbench",
    "resources",
}
APP_FILES = {
    "AGENTS.md",
    "CHANGELOG.md",
    "DEPENDENCIES.md",
    "VERSION",
    "VALIDATION.md",
    "REPORT_REQUIREMENTS.md",
    "CONTRIBUTING.md",
    "MODULES.md",
    "requirements-constraints.txt",
    "run.py",
    "RELEASE.json",
    "DEVELOPMENT.md",
    "desktop.py",
    "SUPPORT.md",
    "ARCHITECTURE.md",
    "SECURITY.md",
    "HOME_VALIDATION.md",
    "README.md",
    "excel_intake.py",
}
MODULES = {
    "investigations",
    "observatory",
    "leads",
    "ui",
    "attribution",
    "accretion",
    "settings",
    "entities",
    "workspace",
    "activity",
    "library",
    "tools",
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


def protected_parts(parts: tuple[str, ...]) -> bool:
    """Only the named Workspace module is program code; nested user data stays protected."""
    return any(
        part.casefold() in PROTECTED
        and not (index == 2 and parts[:2] == ("app", "modules") and part == "workspace")
        for index, part in enumerate(parts)
    )


def program_module(parts: tuple[str, ...]) -> bool:
    if parts == ("app", "modules", "__init__.py"):
        return True
    if len(parts) < 4 or parts[:2] != ("app", "modules") or parts[2] not in MODULES:
        return False
    return (len(parts) == 4 and parts[3] == "__init__.py") or (
        len(parts) >= 5
        and parts[3]
        in {
            "components",
            "tools",
            "helpers",
            "databases",
            "static",
            "docs",
            "fonts",
            "schemas",
            "resources",
            "examples",
        }
    )


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
    if protected_parts(parts):
        raise UpgradeError(f"Workspace path is outside upgrade cleanup policy: {name}")
    allowed = (
        name in {"Getting started.txt", "Third-party notices.txt"}
        or (len(parts) == 2 and parts[0] == "app" and parts[1] in APP_FILES)
        or (len(parts) >= 3 and parts[0] == "app" and parts[1] in APP_FOLDERS)
        or program_module(parts)
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


def manifest_app_id(manifest):
    edition, variant = manifest_identity(manifest)
    return (
        "ShadowserverCompanionDarkMatter"
        if variant == "dark_matter"
        else "ShadowserverCompanionChaos"
        if edition == "chaos"
        else "OutreachWorkbench"
    )


def bootstrap_spec(manifest, *, required=False):
    """Bootstrap ownership is separate from the replaceable payload inventory."""
    spec = manifest.get("bootstrap")
    if spec is None and not required:
        return None
    if not isinstance(spec, dict) or set(spec) != {"protocol", "path", "sha256"}:
        raise UpgradeError("Missing or invalid bootstrap inventory")
    digest = spec["sha256"]
    if (
        type(spec["protocol"]) is not int
        or spec["protocol"] != BOOTSTRAP_PROTOCOL
        or not isinstance(digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", digest)
        or spec["path"] != f"bootstrap/launch-{digest}.exe"
    ):
        raise UpgradeError("Unsupported bootstrap protocol or ownership path")
    return spec


def installation_root(install_dir):
    root = Path(os.path.abspath(install_dir))
    for part in (root, *root.parents):
        try:
            info = _plain_file(part)
        except FileNotFoundError:
            continue
        if not stat.S_ISDIR(info.st_mode):
            raise UpgradeError("Installation location is not a directory")
    return root


def bootstrap_ledger(root, metadata):
    """Validate recorded immutable launchers; never infer ownership from a name."""
    path = safe_target(root, (BOOTSTRAP_LEDGER,))
    if not path.exists():
        ledger = {"schema": 1, "app_id": manifest_app_id(metadata), "active": None, "files": {}}
        prior = safe_target(root, ("payload-manifest.json",))
        if prior.exists():
            _, previous = read_inventory(prior, with_metadata=True)
            if manifest_identity(previous) != manifest_identity(metadata):
                raise UpgradeError("Different application identity owns the prior bootstrap")
            if spec := bootstrap_spec(previous):
                ledger["active"] = spec["path"]
                ledger["files"][spec["path"]] = spec["sha256"]
    else:
        if path.stat().st_size > 64 * 1024:
            raise UpgradeError("Bootstrap ownership ledger exceeds its size limit")
        try:
            ledger = json.loads(path.read_bytes(), object_pairs_hook=_unique_object)
        except (ValueError, RecursionError) as error:
            raise UpgradeError("Invalid bootstrap ownership ledger") from error
    if (
        not isinstance(ledger, dict)
        or set(ledger) != {"schema", "app_id", "active", "files"}
        or type(ledger["schema"]) is not int
        or ledger["schema"] != 1
        or ledger["app_id"] != manifest_app_id(metadata)
        or not isinstance(ledger["files"], dict)
        or len(ledger["files"]) > 128
        or (
            ledger["active"] is not None
            and (not isinstance(ledger["active"], str) or ledger["active"] not in ledger["files"])
        )
    ):
        raise UpgradeError("Invalid bootstrap ownership ledger")
    for name, digest in ledger["files"].items():
        bootstrap_spec({"bootstrap": {"protocol": 1, "path": name, "sha256": digest}})
        target = safe_target(root, tuple(name.split("/")))
        if target.exists() and sha256(target) != digest:
            raise UpgradeError(f"An owned immutable bootstrap was modified: {name}")
    return ledger


def _atomic_state(root, name, content):
    target = safe_target(root, (name,))
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".installation-", suffix=".tmp", dir=root, delete=False
        ) as output:
            temporary = Path(output.name)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        safe_target(root, (name,))
        temporary.replace(target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _write_ledger(root, ledger):
    _atomic_state(root, BOOTSTRAP_LEDGER, (json.dumps(ledger, indent=2) + "\n").encode("utf-8"))


def _install_bootstrap(root, source, spec):
    """Publish a verified launcher without ever replacing an existing executable."""
    target = safe_target(root, tuple(spec["path"].split("/")))
    if target.exists():
        if sha256(target) != spec["sha256"]:
            raise UpgradeError("Immutable bootstrap destination has different bytes")
        return
    target.parent.mkdir(exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".launch-", suffix=".tmp", dir=target.parent, delete=False
        ) as output:
            temporary = Path(output.name)
            with source.open("rb") as incoming:
                for block in iter(lambda: incoming.read(1024 * 1024), b""):
                    output.write(block)
            output.flush()
            os.fsync(output.fileno())
        if sha256(temporary) != spec["sha256"]:
            raise UpgradeError("Staged bootstrap changed during installation")
        safe_target(root, tuple(spec["path"].split("/")))
        try:
            if os.name == "nt":
                # Windows rename fails if the destination already exists.
                temporary.rename(target)
            else:
                os.link(temporary, target)  # Same no-replacement contract in portable tests.
        except FileExistsError:
            if sha256(target) != spec["sha256"]:
                raise UpgradeError("Immutable bootstrap destination changed")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _schedule_transition(action, root, metadata, launcher, **options):
    local = os.environ.get("LOCALAPPDATA")
    if not local or not Path(local).is_absolute():
        raise UpgradeError("Windows did not provide the workspace location")
    adapter = runpy.run_path(str(Path(__file__).with_name("windows_schedule.py")))
    return adapter[action](
        root,
        Path(local) / manifest_app_id(metadata) / "data",
        launcher,
        journal_path=safe_target(root, (TASK_JOURNAL,)),
        **options,
    )


def prepare_installation(install_dir, next_manifest, source, **options):
    """Called under StartInstall: validate first, then make interrupted work inert."""
    root = installation_root(install_dir)
    _, metadata = read_inventory(next_manifest, with_metadata=True)
    spec = bootstrap_spec(metadata, required=True)
    source = Path(source)
    info = _plain_file(source)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_size > 16 * 1024 * 1024
        or sha256(source) != spec["sha256"]
    ):
        raise UpgradeError("Staged bootstrap failed its inventory check")
    ledger = bootstrap_ledger(root, metadata)
    destination = safe_target(root, tuple(spec["path"].split("/")))
    if destination.exists() and sha256(destination) != spec["sha256"]:
        raise UpgradeError("Immutable bootstrap destination has different bytes")
    ready = safe_target(root, (READY_MARKER,))
    if ready.exists() and not ledger["files"]:
        raise UpgradeError("Unowned installation-ready marker; program files were retained")
    if spec["path"] not in ledger["files"] and len(ledger["files"]) >= 128:
        raise UpgradeError("Bootstrap ownership ledger is full; no program files were changed")

    def begin():
        root.mkdir(parents=True, exist_ok=True)
        _schedule_transition(
            "prepare_upgrade", root, metadata, destination, owned_bootstraps=dict(ledger["files"])
        )
        ready.unlink(missing_ok=True)
        ledger["files"][spec["path"]] = spec["sha256"]
        _write_ledger(root, ledger)
        _install_bootstrap(root, source, spec)

    return cleanup(root, next_manifest, before_mutation=begin, **options)


def commit_installation(install_dir, next_manifest):
    """Publish readiness only after every payload byte and task action is complete."""
    root = installation_root(install_dir)
    expected, metadata = read_inventory(next_manifest, with_metadata=True)
    spec = bootstrap_spec(metadata, required=True)
    installed = safe_target(root, ("payload-manifest.json",))
    if read_inventory(installed, with_metadata=True) != (expected, metadata):
        raise UpgradeError("Installed payload inventory does not match this installer")
    ledger = bootstrap_ledger(root, metadata)
    if ledger["files"].get(spec["path"]) != spec["sha256"]:
        raise UpgradeError("The new bootstrap was not prepared by this installation")
    launcher = safe_target(root, tuple(spec["path"].split("/")))
    if not launcher.is_file() or sha256(launcher) != spec["sha256"]:
        raise UpgradeError("The installed bootstrap is incomplete")
    for name, digest in expected.items():
        target = safe_target(root, member_parts(name))
        if not target.is_file() or sha256(target) != digest:
            raise UpgradeError(f"Installed program file is incomplete: {name}")
    _schedule_transition("commit_upgrade", root, metadata, launcher)
    ledger["active"] = spec["path"]
    _write_ledger(root, ledger)
    _atomic_state(
        root,
        READY_MARKER,
        f"[installation]\r\napp_id={manifest_app_id(metadata)}\r\nprotocol={BOOTSTRAP_PROTOCOL}\r\n".encode(
            "ascii"
        ),
    )


def check_workspace_compatibility(manifest):
    maximum = manifest.get("database_schema_max")
    local = os.environ.get("LOCALAPPDATA")
    if maximum is None or not local:
        return
    if not isinstance(maximum, int) or maximum < 1:
        raise UpgradeError("Invalid supported database schema")
    namespace = manifest_app_id(manifest)
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
            dirs[:] = [
                name
                for name in dirs
                if not protected_parts((Path(directory) / name).relative_to(root).parts)
            ]
            for name in dirs:
                _plain_file(base / name)
            for name in files:
                path = base / name
                info = _plain_file(path)
                if not stat.S_ISREG(info.st_mode):
                    raise UpgradeError(f"Program member is not a regular file: {path}")
                if path.suffix.lower() in {".pyc", ".pyo"}:
                    parts = path.relative_to(root).parts
                    if protected_parts(parts):
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
            dirs[:] = [
                name
                for name in dirs
                if not protected_parts((Path(directory) / name).relative_to(root).parts)
            ]
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
            dirs[:] = [
                name
                for name in dirs
                if not protected_parts((Path(directory) / name).relative_to(root).parts)
            ]
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
    files, metadata = read_inventory(installed_manifest, with_metadata=True)
    for name in files:
        safe_target(root, member_parts(name))
    caches = generated_caches(root)
    if bootstrap_spec(metadata):
        bootstrap_ledger(root, metadata)
        remove_scheduled_task(installed_manifest, install_dir=root)
        # No supported launcher may enter a partly removed runtime, even if
        # uninstall is interrupted after this point.
        safe_target(root, (READY_MARKER,)).unlink(missing_ok=True)
    return remove_caches(root, caches)


def remove_bootstraps(install_dir, installed_manifest, *, wait_seconds=8):
    """Remove only recorded launchers after runtime removal; tolerate a gate waiter.

    A launcher can have its own image open while waiting for StartInstall. It
    cannot enter Python because readiness is already withdrawn. Give that bounded
    wait time to expire; on a persistent lock, retain state for an explicit retry.
    """
    root = installation_root(install_dir)
    _, metadata = read_inventory(installed_manifest, with_metadata=True)
    ledger = bootstrap_ledger(root, metadata)
    # The embedded uninstaller proves its own launcher even when a previous
    # interrupted removal lost the local ledger or payload inventory.
    if spec := bootstrap_spec(metadata):
        ledger["files"][spec["path"]] = spec["sha256"]
    if safe_target(root, (READY_MARKER,)).exists():
        raise UpgradeError("Withdraw installation readiness before removing bootstraps")
    deadline = time.monotonic() + wait_seconds
    for name, digest in ledger["files"].items():
        while True:
            target = safe_target(root, tuple(name.split("/")))
            if not target.exists():
                break
            if sha256(target) != digest:
                raise UpgradeError(f"An owned immutable bootstrap was modified: {name}")
            try:
                target.unlink()
                break
            except PermissionError as error:
                if time.monotonic() >= deadline:
                    raise UpgradeError(
                        "A launcher is still open. Close it and retry uninstall; working records are retained."
                    ) from error
                time.sleep(min(0.1, max(0, deadline - time.monotonic())))
    safe_target(root, (BOOTSTRAP_LEDGER,)).unlink(missing_ok=True)
    folder = safe_target(root, ("bootstrap",), directory=True)
    try:
        folder.rmdir()
    except FileNotFoundError:
        pass
    except OSError as error:
        if error.errno not in {errno.ENOTEMPTY, errno.EEXIST}:
            raise


def remove_scheduled_task(manifest_path: Path, *, install_dir=None) -> None:
    """Use the staged standard-library adapter, not a possibly broken old app."""
    _, metadata = read_inventory(manifest_path, with_metadata=True)
    namespace = manifest_app_id(metadata)
    local = os.environ.get("LOCALAPPDATA")
    if not local or not Path(local).is_absolute():
        raise UpgradeError("Windows did not provide the workspace location")
    adapter = runpy.run_path(str(Path(__file__).with_name("windows_schedule.py")))
    if bootstrap_spec(metadata):
        if install_dir is None:
            raise UpgradeError("Installation directory is required for bootstrap task removal")
        root = installation_root(install_dir)
        owned = bootstrap_ledger(root, metadata)["files"]
        spec = bootstrap_spec(metadata, required=True)
        owned[spec["path"]] = spec["sha256"]
        for name, digest in owned.items():
            path = safe_target(root, tuple(name.split("/")))
            if path.exists() and sha256(path) != digest:
                raise UpgradeError(f"An owned immutable bootstrap was modified: {name}")
        adapter["remove_installation_task"](
            root,
            Path(local) / namespace / "data",
            journal_path=safe_target(root, (TASK_JOURNAL,)),
            owned_bootstraps=owned,
        )
    else:
        adapter["configure"](Path(local) / namespace / "data", False)


def cleanup(
    install_dir: Path,
    next_manifest: Path,
    *,
    reset_data=False,
    known_installation=False,
    before_mutation=None,
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
        if before_mutation is not None:
            before_mutation()
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
    if before_mutation is not None:
        before_mutation()
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
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--uninstall", action="store_true")
    action.add_argument("--remove-task", action="store_true")
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--commit", action="store_true")
    action.add_argument("--remove-bootstraps", action="store_true")
    parser.add_argument("--bootstrap-source", type=Path)
    parser.add_argument("--known-installation", action="store_true")
    parser.add_argument(
        "--reset-data",
        action="store_true",
        help="Interactive installer has confirmed a complete data reset",
    )
    args = parser.parse_args()
    if args.prepare and args.bootstrap_source is None:
        parser.error("--prepare requires --bootstrap-source")
    try:
        if args.remove_task:
            remove_scheduled_task(args.next_manifest, install_dir=args.install_dir)
            print("Removed this workspace's optional scheduled task.")
            return 0
        if args.commit:
            commit_installation(args.install_dir, args.next_manifest)
            print("Verified the installed payload and committed launch readiness.")
            return 0
        if args.remove_bootstraps:
            remove_bootstraps(args.install_dir, args.next_manifest)
            print("Removed recorded immutable launchers; unrelated files retained.")
            return 0
        if args.prepare:
            removed = prepare_installation(
                args.install_dir,
                args.next_manifest,
                args.bootstrap_source,
                reset_data=args.reset_data,
                known_installation=args.known_installation,
            )
        else:
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
        print(f"Installation maintenance stopped: {exc}", file=sys.stderr)
        return 1
    print(
        f"Verified prior inventory; removed {len(removed)} obsolete program files. Workspaces retained."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
