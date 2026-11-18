"""Dependency-free safe paths and bounded immutable package file readers."""

import hashlib
from pathlib import Path, PurePosixPath

MAX_PACKAGE_MANIFEST_BYTES = 20 * 1024 * 1024


def member_path(folder: Path, name: str) -> Path:
    if (
        not isinstance(name, str)
        or not name
        or "\\" in name
        or ":" in name
        or any(ord(c) < 32 for c in name)
    ):
        raise ValueError("Invalid package member name")
    relative = PurePosixPath(name)
    if (
        relative.is_absolute()
        or relative.as_posix() != name
        or any(p in ("", ".", "..") or p.endswith((".", " ")) for p in relative.parts)
    ):
        raise ValueError("Invalid package member name")
    path = folder
    if path.is_symlink():
        raise ValueError("Package directories cannot be symbolic links")
    for part in relative.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("Package members cannot be symbolic links")
    if not path.resolve().is_relative_to(folder.resolve()) or not path.is_file():
        raise ValueError("Package member is missing or outside its package")
    return path


def read_member(folder, name, digest=None):
    content = member_path(folder, name).read_bytes()
    if digest is not None and hashlib.sha256(content).hexdigest() != digest:
        raise ValueError("Report package has changed files")
    return content


def read_manifest(folder, *, max_bytes=MAX_PACKAGE_MANIFEST_BYTES):
    """Bound package metadata before allocation, including a concurrent growth check."""
    path = member_path(folder, "manifest.json")
    if path.stat().st_size > max_bytes:
        raise ValueError("Report package manifest exceeds the 20 MiB read limit")
    with path.open("rb") as stream:
        raw = stream.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError("Report package manifest exceeds the 20 MiB read limit")
    return raw


def package_folder(root, relative):
    """Keep a package path inside the workspace without traversing links."""
    if not isinstance(relative, str) or "\\" in relative or ":" in relative:
        raise ValueError("Invalid package directory")
    parts = PurePosixPath(relative)
    if parts.is_absolute() or parts.as_posix() != relative or ".." in parts.parts:
        raise ValueError("Invalid package directory")
    folder = root
    for part in parts.parts:
        folder = folder / part
        if folder.is_symlink():
            raise ValueError("Package directories cannot be symbolic links")
    if not folder.is_dir() or not folder.resolve().is_relative_to(root.resolve()):
        raise ValueError("Invalid package directory")
    return folder


def parsed_manifest(folder):
    """Read bounded package metadata through the shared strict object parser."""
    from .aegis.json import strict_json_loads

    raw = read_manifest(folder)
    return strict_json_loads(raw, max_bytes=MAX_PACKAGE_MANIFEST_BYTES, require_object=True), raw
