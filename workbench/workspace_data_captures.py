"""Verify restored vulnerability-source files without fetching or adopting evidence."""

import hashlib
import json

from .package_files import member_path
from . import compact_json
from .source_references import cve_response_sources


def _record_sources(records):
    for record in records:
        if isinstance(record, dict):
            yield from cve_response_sources(record)


def _capture_references(store):
    for row in store.all("SELECT key,payload FROM cache"):
        family = row["key"].partition(":")[0]
        if family not in {
            "cve-reference",
            "cve-version",
            "intelligence-version",
            "risk-proof",
            "risk-version",
            "acquisition-version",
            "risk-attempt",
            "risk-refresh",
        }:
            continue
        payload = json.loads(row["payload"])
        if not isinstance(payload, dict):
            raise ValueError("Backup contains invalid captured-source metadata")
        if family in {"cve-reference", "cve-version", "intelligence-version"}:
            yield from cve_response_sources(payload)
        elif family == "risk-proof":
            yield payload
        elif family == "risk-version":
            yield payload.get("source", {})
        elif family in {"acquisition-version", "risk-attempt"}:
            yield payload.get("response", {})
        else:
            attempt = payload.get("attempt")
            if isinstance(attempt, dict):
                yield attempt.get("response", {})
    # Case-pinned revisions can predate the reusable bank or outlive its latest
    # selection. Old section validations retain their original source references.
    for table in ("leads", "cases"):
        for row in store.all(f"SELECT draft FROM {table}"):
            draft = json.loads(row["draft"])
            yield from _record_sources(draft.get("cve_records", []))
            # Excluding an observation removes its finding from recipient copy,
            # but the exact pinned source must remain safe to restore on inclusion.
            archived = draft.get("observation_scope_archive", {}).get("cve_records", {})
            yield from _record_sources(archived.values())
    for row in store.all("SELECT snapshot_json FROM section_validations"):
        saved = compact_json.loads(row["snapshot_json"])
        yield from _record_sources(saved.get("frozen_fields", {}).get("cve_records", []))


def _validate_risk_projections(store):
    from .aegis.json import strict_json_loads
    from .intelligence.acquisition import retained_risk_data

    def canonical(value):
        return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)

    rows = store.all("""SELECT c.key,c.payload,p.payload AS proof
        FROM cache c JOIN cache p ON p.key='risk-proof:' || substr(c.key,6)
        WHERE c.key LIKE 'risk:%'""")
    for row in rows:
        proof = strict_json_loads(row["proof"], require_object=True)
        # Older embedded records without a verifiable capture remain historical
        # data. Acquisition will not reuse them as a captured provider response.
        if not proof.get("record_path") or not (proof.get("body_sha256") or proof.get("sha256")):
            continue
        raw = retained_risk_data(store, row["key"][5:], proof)
        cached = strict_json_loads(row["payload"], require_object=True)
        if canonical(raw) != canonical(cached):
            raise ValueError("Backup cached source differs from its retained provider response")


def _validate_reference_projections(store):
    from .aegis.json import strict_json_loads
    from .intelligence.acquisition import validate_reference_projection

    for row in store.all("SELECT key,payload FROM cache WHERE key LIKE 'cve-reference:%'"):
        record = strict_json_loads(row["payload"], require_object=True)
        if (
            record.get("id")
            and record.get("source") in {"NVD", "CVE Program"}
            and record.get("record_path")
            and (record.get("body_sha256") or record.get("sha256"))
        ):
            validate_reference_projection(store, row["key"].partition(":")[2], record)


def validate_capture_data(store, *, checkpoint=None, registry=True):
    """Reject missing or changed declared captures in an isolated restored Store.

    Metadata without a capture path remains valid: failed acquisitions and older
    embedded source records do not imply that a local response was ever saved.
    Raw provider JSON is never traversed for similarly named fields.
    """
    from .evidence_registry import validate_registry
    from .artifact_registry import validate_registry as validate_artifacts

    if registry:
        with store.read_snapshot() as db:
            validate_registry(db, root=store.root, checkpoint=checkpoint)
            validate_artifacts(store.root, db, checkpoint=checkpoint)
    checked = {}
    try:
        for source in _capture_references(store):
            if checkpoint:
                checkpoint("Verifying pinned and cached source captures")
            if not isinstance(source, dict) or not source.get("record_path"):
                continue
            relative = source["record_path"]
            expected = source.get("body_sha256") or source.get("sha256")
            if relative not in checked:
                try:
                    path = member_path(store.root, relative)
                except (OSError, ValueError) as error:
                    raise ValueError("Backup is missing a captured vulnerability source") from error
                with path.open("rb") as stream:
                    checked[relative] = hashlib.file_digest(stream, "sha256").hexdigest()
            if expected and checked[relative] != expected:
                raise ValueError("Backup vulnerability source failed its recorded SHA-256 check")
        _validate_risk_projections(store)
        _validate_reference_projections(store)
    except (KeyError, TypeError, AttributeError, OSError) as error:
        raise ValueError(f"Backup captured sources could not be verified: {error}") from error
