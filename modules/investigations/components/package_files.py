"""The single bounded manifest reader and package-facing file read adapter."""

from modules.tools.components.filesystem import (
    DigestMismatch,
    FileTooLarge,
    contained_file as member_path,
    contained_directory as package_folder,
    read_contained_file,
)
from modules.workspace.components.aegis.json import strict_json_loads

__all__ = ["member_path", "package_folder", "read_member", "read_manifest", "parsed_manifest"]

MAX_PACKAGE_MANIFEST_BYTES = 20 * 1024 * 1024


def read_member(folder, name, digest=None):
    try:
        return read_contained_file(folder, name, sha256=digest)
    except DigestMismatch as error:
        raise ValueError("Report package has changed files") from error


def read_manifest(folder):
    """The package's metadata name and 20 MiB policy belong to Investigations."""
    try:
        return read_contained_file(folder, "manifest.json", max_bytes=MAX_PACKAGE_MANIFEST_BYTES)
    except FileTooLarge as error:
        raise ValueError("Report package manifest exceeds the 20 MiB read limit") from error


def parsed_manifest(folder):
    """Return strict object metadata plus its unchanged bytes for identity binding."""
    raw = read_manifest(folder)
    return strict_json_loads(raw, max_bytes=MAX_PACKAGE_MANIFEST_BYTES, require_object=True), raw
