"""Validate package membership without following links or collecting extra files."""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from functools import wraps
from pathlib import Path
import re
from types import SimpleNamespace
from . import compact_json
from .package_files import (
    member_path as member_path,
    package_folder as package_folder,
    read_member as read_member,
    read_manifest as _read_manifest,
)

_VERIFIED = ContextVar("report_package_verification", default=None)
MAX_PACKAGE_MANIFEST_BYTES = 20 * 1024 * 1024


class LegacyUnvalidatedEvidence(ValueError):
    """A certified snapshot embeds old web content that cannot be reexported."""

    def __init__(self):
        super().__init__(
            "This internal record contains legacy unvalidated web content. "
            "Recipient documents remain available. Certify a new report revision "
            "to create a validated internal record."
        )


@contextmanager
def verification_scope():
    """Reuse successful checks only within one explicit read operation.

    There is no persistent cache or modification-time shortcut. Export still
    reads and verifies every delivered byte against the certified manifest.
    Nested projections participate in their caller's bounded scope.
    """
    if _VERIFIED.get() is not None:
        yield
        return
    token = _VERIFIED.set({})
    try:
        yield
    finally:
        _VERIFIED.reset(token)


def verification_operation(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with verification_scope():
            return function(*args, **kwargs)

    return wrapped


def read_manifest(folder):
    return _read_manifest(folder, max_bytes=MAX_PACKAGE_MANIFEST_BYTES)


def parsed_manifest(folder):
    """Read bounded package metadata through the shared strict object parser."""
    from attribution.models import parse_json

    raw = read_manifest(folder)
    return parse_json(raw), raw


def validated_inventory(folder, required):
    cache = _VERIFIED.get()
    cache_key = str(folder.resolve())
    if cache is not None and cache_key in cache:
        manifest, raw = cache[cache_key]
        if not required <= manifest["files"].keys():
            raise ValueError("Incomplete report package manifest")
        return deepcopy(manifest), raw
    # Reuse the strict response parser: duplicate JSON names cannot choose a
    # different member depending on which consumer inspects the manifest.
    manifest, raw = parsed_manifest(folder)
    files = manifest.get("files")
    if not isinstance(files, dict) or not required <= files.keys() or "manifest.json" in files:
        raise ValueError("Incomplete report package manifest")
    normalized = set()
    for name, digest in files.items():
        if (
            not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or name.casefold() in normalized
        ):
            raise ValueError("Invalid report package manifest")
        normalized.add(name.casefold())
        # Verification must not allocate an entire artifact. Backup members can
        # be much larger than the bounded JSON models, and this path also runs
        # before restore acceptance and ordinary report availability checks.
        with member_path(folder, name).open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != digest:
            raise ValueError("Report package has changed files")
    if cache is not None:
        cache[cache_key] = (deepcopy(manifest), raw)
    return manifest, raw


def write_recipient_export(archive, folder, manifest, manifest_bytes, *, include_appendix=False):
    """Deliver only explicitly chosen recipient documents, never case records."""
    names = ["notification.pdf"]
    if include_appendix:
        if "supporting-appendix.pdf" not in manifest["files"]:
            raise ValueError("This report has no separately retained supporting appendix")
        names.append("supporting-appendix.pdf")
    delivered = {}
    for name in names:
        digest = manifest["files"][name]
        archive.writestr(name, read_member(folder, name, digest))
        delivered[name] = digest
    # The original complete manifest would disclose internal filenames. This
    # transport manifest intentionally names only the selected public documents.
    archive.writestr(
        "recipient-manifest.json",
        json.dumps(
            {
                "schema_version": 1,
                "kind": "recipient-notification-package",
                "report_id": manifest.get("report_id"),
                "revision": manifest.get("revision"),
                "handling": "TLP:AMBER",
                "certified_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                "files": delivered,
                "separate_supporting_appendix_included": include_appendix,
                "description": "Selected certified documents; this is not a full case record or workspace backup.",
            },
            indent=2,
        )
        + "\n",
    )


def write_export(archive, folder, manifest, manifest_bytes):
    """Export declared bytes, omitting legacy raw contact website responses.

    A legacy transformed transport keeps its certified manifest and snapshot
    byte-for-byte. export-manifest.json verifies the delivered filenames,
    explicitly records omitted responses and maps retained renamed members back
    to the certified names; the original manifest
    must not be mistaken for a direct inventory of the transformed ZIP.
    """
    files = manifest["files"]
    snapshot_bytes = read_member(folder, "snapshot.json", files["snapshot.json"])
    snapshot = compact_json.loads(snapshot_bytes)
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("evidence", []), list):
        raise ValueError("Invalid report snapshot")
    raw_paths = {e.get("path") for e in snapshot.get("evidence", []) if isinstance(e, dict)}
    legacy_contact_paths = {
        name
        for name in files
        if name.startswith("evidence/contact-") and name.endswith(".body.txt")
    }
    research = snapshot.get("contact_research") or {}
    if not isinstance(research, dict) or not isinstance(research.get("runs", []), list):
        raise ValueError("Invalid report contact research snapshot")
    from .contact_evidence import is_derived_snapshot

    for run in research.get("runs", []):
        if not isinstance(run, dict) or not isinstance(run.get("snapshots", []), list):
            raise ValueError("Invalid report contact research snapshot")
        for captured in run.get("snapshots", []):
            if not isinstance(captured, dict):
                raise ValueError("Invalid report contact source snapshot")
            if not is_derived_snapshot(captured) and isinstance(captured.get("path"), str):
                legacy_contact_paths.add(captured["path"])
    omitted = {
        name: {
            "sha256": files[name],
            "reason": "Raw contact website response omitted by current evidence policy",
        }
        for name in sorted(legacy_contact_paths & files.keys())
    }
    provider_contexts = _provider_export_contexts(snapshot, files)
    provider_store = SimpleNamespace(root=folder, path=lambda name: member_path(folder, name))
    renames = {}
    existing = {name.casefold() for name in files}
    for name in sorted(raw_paths & files.keys()):
        if Path(name).suffix.lower() != ".bin":
            destination = name + ".bin"
            if destination.casefold() in existing:
                raise ValueError("Legacy evidence export filename collision")
            renames[name] = destination
            existing.add(destination.casefold())
    if (renames or omitted or provider_contexts) and (
        "export-manifest.json" in existing or "certified-manifest.json" in existing
    ):
        raise ValueError("Legacy evidence export manifest collision")
    delivered = {}
    for name, digest in files.items():
        if name in omitted:
            continue
        if name in provider_contexts:
            from .report_package import _provider_capture

            try:
                for source, cve_id, publisher in provider_contexts[name]:
                    content = _provider_capture(
                        provider_store, source, cve_id=cve_id, publisher=publisher
                    )
                    if hashlib.sha256(content).hexdigest() != digest:
                        raise ValueError("Report package has changed provider bytes")
            except (OSError, ValueError) as error:
                if any(
                    source.get("record") is not None for source, _, _ in provider_contexts[name]
                ):
                    # Older snapshots can embed the same unvalidated response.
                    # Do not rewrite a certified snapshot or quietly export its
                    # copy after dropping only the standalone captured file.
                    raise LegacyUnvalidatedEvidence() from error
                omitted[name] = {
                    "sha256": digest,
                    "reason": "Provider response omitted by current validation policy: "
                    + str(error),
                }
                continue
        else:
            content = (
                snapshot_bytes if name == "snapshot.json" else read_member(folder, name, digest)
            )
        destination = renames.get(name, name)
        archive.writestr(destination, content)
        delivered[destination] = digest
    transformed = bool(renames or omitted)
    manifest_name = "certified-manifest.json" if transformed else "manifest.json"
    archive.writestr(manifest_name, manifest_bytes)
    if transformed:
        delivered[manifest_name] = hashlib.sha256(manifest_bytes).hexdigest()
        transport = {
            "schema_version": 1,
            "kind": "safe-evidence-transport",
            "handling": "TLP:AMBER",
            "certified_manifest": manifest_name,
            "certified_manifest_sha256": delivered[manifest_name],
            "filename_mapping": renames,
            "omitted_files": omitted,
            "files": delivered,
            "verification": (
                "Verify delivered files against this inventory. To verify the original certified "
                "manifest, resolve retained member names through filename_mapping. Retained bytes "
                "are unchanged. Members in omitted_files were deliberately not delivered; their "
                "original certified hashes are recorded. The preserved snapshot and certified "
                "manifest use original names and may reference omitted files. This transport is "
                "not the complete certified package or a workspace backup."
            ),
        }
        archive.writestr("export-manifest.json", json.dumps(transport, indent=2) + "\n")


def _provider_export_contexts(snapshot, files):
    """Index explicit captured provider members; never follow arbitrary paths."""
    from .source_capture import cve_response_sources

    contexts = {}

    def add(source, cve_id="", publisher=""):
        if not isinstance(source, dict):
            raise ValueError("Invalid report provider source metadata")
        name = source.get("record_path")
        if isinstance(name, str) and name in files:
            contexts.setdefault(name, []).append((source, cve_id, publisher))

    draft = snapshot.get("draft") or {}
    if not isinstance(draft, dict) or not isinstance(draft.get("cve_records", []), list):
        raise ValueError("Invalid report provider records")
    for record in draft.get("cve_records", []):
        if not isinstance(record, dict):
            raise ValueError("Invalid report provider record")
        for source in cve_response_sources(record):
            add(source, record.get("id", ""), record.get("source", ""))
    sources = snapshot.get("source_snapshots", [])
    if not isinstance(sources, list):
        raise ValueError("Invalid report provider snapshots")
    for source in sources:
        if (
            isinstance(source, dict)
            and isinstance(source.get("record"), dict)
            and "response_text" in source["record"]
        ):
            raise LegacyUnvalidatedEvidence()
        add(source)
    return contexts
