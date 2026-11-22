"""Atomic file publication and contained reads with explicit paths and bytes.

Callers own directory creation, trusted roots, serialization and transaction policy.
Contained paths retain immutable-package semantics; they are not a sandbox against
another process replacing the directory tree concurrently.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import tempfile


class FileTooLarge(ValueError):
    """The requested file exceeds the caller's byte limit."""


class DigestMismatch(ValueError):
    """The file bytes do not match the caller's expected SHA-256 digest."""


def atomic_write(destination: Path, content: bytes) -> None:
    """Publish bytes with same-directory replacement, or raise an I/O error.

    Flush and fsync the temporary file before closing and replacing the destination.
    Clean up the unique temporary file on failure. This is a single-file publication,
    not a multi-file transaction or a guarantee that a rename survives power loss.
    The destination's parent must already exist; callers coordinate concurrent writes.
    """
    destination = Path(destination)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _relative_path(name: str) -> PurePosixPath:
    if not isinstance(name, str) or "\\" in name or ":" in name:
        raise ValueError("Invalid relative path")
    relative = PurePosixPath(name)
    if relative.is_absolute() or relative.as_posix() != name or ".." in relative.parts:
        raise ValueError("Invalid relative path")
    return relative


def contained_file(root: Path, relative: str) -> Path:
    """Return an existing file below root using a canonical POSIX relative name.

    Reject symlinks at the root and along the member path, traversal, ambiguous file
    names and paths resolving outside root. Return a Path without opening a handle.
    Invalid/missing paths raise ValueError; filesystem I/O failures raise OSError.
    """
    parts = _relative_path(relative)
    if (
        not relative
        or any(ord(c) < 32 for c in relative)
        or any(part.endswith((".", " ")) for part in parts.parts)
    ):
        raise ValueError("Invalid relative file name")
    root = Path(root)
    path = root
    if path.is_symlink():
        raise ValueError("File roots cannot be symbolic links")
    for part in parts.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("File paths cannot be symbolic links")
    if not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("File is missing or outside its root")
    return path


def contained_directory(root: Path, relative: str) -> Path:
    """Return an existing contained directory without traversing child symlinks.

    The caller supplies the trusted root; '.' is allowed to select that directory.
    Directory-name acceptance is preserved from the immutable-package reader.
    """
    parts = _relative_path(relative)
    root = Path(root)
    folder = root
    for part in parts.parts:
        folder = folder / part
        if folder.is_symlink():
            raise ValueError("Directories cannot be symbolic links")
    if not folder.is_dir() or not folder.resolve().is_relative_to(root.resolve()):
        raise ValueError("Directory is missing or outside its root")
    return folder


def read_contained_file(
    root: Path,
    relative: str,
    *,
    sha256: str | None = None,
    max_bytes: int | None = None,
) -> bytes:
    """Read a contained file, optionally bounding size and checking its digest.

    The limit is checked before allocation and while reading, including file growth.
    Oversize and mismatched content raise FileTooLarge and DigestMismatch respectively;
    other path/I/O failures follow contained_file. No JSON or domain policy is applied.
    """
    if max_bytes is not None and (type(max_bytes) is not int or max_bytes < 0):
        raise ValueError("File byte limit must be a nonnegative integer")
    path = contained_file(root, relative)
    if max_bytes is not None and path.stat().st_size > max_bytes:
        raise FileTooLarge(f"File exceeds the {max_bytes} byte read limit")
    with path.open("rb") as stream:
        content = stream.read() if max_bytes is None else stream.read(max_bytes + 1)
    if max_bytes is not None and len(content) > max_bytes:
        raise FileTooLarge(f"File exceeds the {max_bytes} byte read limit")
    if sha256 is not None and hashlib.sha256(content).hexdigest() != sha256:
        raise DigestMismatch("File content differs from its expected SHA-256 digest")
    return content
