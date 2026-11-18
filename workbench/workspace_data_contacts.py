"""Validate every retained contact response in an isolated restored workspace."""

import json
from attribution import EvidenceStore
from .attribution_bridge import checked_result
from .asset_attribution import _verify_snapshots
from .contact_evidence import snapshot_path, fingerprint, is_derived_snapshot
from .contact_discovery.policy import (
    hostname,
    approved_url,
    MAX_TOTAL_BYTES,
    MAX_REQUESTS,
    MAX_CANDIDATES,
)


def _candidate_in_run(row, run_row):
    if (row["entity_id"], row["root_domain"]) != (run_row["entity_id"], run_row["root_domain"]):
        raise ValueError(
            "Contact candidate and retained run belong to different businesses or roots"
        )
    run = json.loads(run_row["payload"])
    candidates = [
        candidate for candidate in run["candidates"] if candidate["key"] == row["candidate_key"]
    ]
    if len(candidates) != 1:
        raise ValueError("Contact candidate does not identify one retained discovery result")
    return candidates[0], run


def _validate_sources(store, row, run_row, source_row):
    original, run = _candidate_in_run(row, run_row)
    snapshots = {snapshot["id"]: snapshot for snapshot in run["snapshots"]}
    if len(snapshots) != len(run["snapshots"]):
        raise ValueError("Contact discovery has duplicate response identities")
    expected = []
    for source in original["sources"]:
        saved = snapshots.get(source["snapshot_id"])
        if not saved or saved["url"] != source["url"]:
            raise ValueError("Contact source does not identify its retained response")
        expected.append(
            {
                **source,
                "run_id": run_row["id"],
                "retrieved_at": saved["retrieved_at"],
                "sha256": saved["sha256"],
            }
        )
    if not expected or json.loads(source_row["payload"]) != expected:
        raise ValueError("Contact provenance differs from its retained discovery result")


def validate_candidate(store, row):
    """Bind the value being reviewed or used to its original captured result."""
    try:
        run_row = store.one("SELECT * FROM contact_runs WHERE id=?", (row["latest_run_id"],))
        if not run_row:
            raise ValueError("Contact candidate is missing its latest retained discovery result")
        original, _ = _candidate_in_run(row, run_row)
        payload = json.loads(row["payload"])
        fields = (
            "kind",
            "value",
            "name",
            "role",
            "purpose",
            "routing_label",
            "routing_options",
            "route_type",
            "original_url",
            "external_destination",
            "purpose_conflict",
            "recommended_for_outreach",
        )
        if any(payload.get(field, "") != original.get(field, "") for field in fields):
            raise ValueError(
                "Contact candidate differs from its retained published value or identity"
            )
        source_row = store.one(
            "SELECT * FROM contact_sources WHERE candidate_id=? AND run_id=?",
            (row["id"], run_row["id"]),
        )
        if not source_row:
            raise ValueError("Contact candidate is missing its retained source provenance")
        _validate_sources(store, row, run_row, source_row)
    except (KeyError, TypeError, AttributeError, json.JSONDecodeError) as error:
        raise ValueError("Contact candidate provenance could not be verified") from error


def validate_contact_data(
    store, entity_id=None, *, allow_unavailable_legacy=False, evidence_factory=EvidenceStore
):
    """Validate all history, including superseded runs, before restore or export."""
    try:
        _validate_contact_data(
            store,
            entity_id,
            allow_unavailable_legacy=allow_unavailable_legacy,
            evidence_factory=evidence_factory,
        )
    except (KeyError, TypeError, AttributeError, json.JSONDecodeError) as error:
        raise ValueError("Backup contact discovery provenance could not be verified") from error


def _validate_contact_data(
    store, entity_id=None, *, allow_unavailable_legacy=False, evidence_factory=EvidenceStore
):
    predicate, args = (" WHERE entity_id=?", (entity_id,)) if entity_id is not None else ("", ())
    for row in store.all("SELECT * FROM contact_runs" + predicate, args):
        run, scope = json.loads(row["payload"]), json.loads(row["scope"])
        if (
            not 0 <= run.get("request_count", 0) <= MAX_REQUESTS
            or len(run["snapshots"]) > MAX_REQUESTS
            or len(run["candidates"]) > MAX_CANDIDATES
            or len({s["id"] for s in run["snapshots"]}) != len(run["snapshots"])
        ):
            raise ValueError("Backup contact discovery exceeded its capture budget")
        if run["root_hostname"] != row["root_domain"] or scope["root_domain"] != row["root_domain"]:
            raise ValueError("Backup contact discovery root does not match its saved scope")
        if scope["entity_id"] != row["original_entity_id"]:
            raise ValueError("Backup contact discovery differs from its original business identity")
        group = store.one(
            "SELECT entity_id FROM domain_groups WHERE root_domain=?", (row["root_domain"],)
        )
        entity = store.one("SELECT domain FROM leads WHERE id=?", (row["entity_id"],))
        entity_domain = (
            scope.get("basis") == "entity_domain"
            and entity
            and entity["domain"] == row["root_domain"]
        )
        if not entity_domain and (not group or group["entity_id"] != row["entity_id"]):
            raise ValueError("Backup contact discovery root belongs to another business")
        root = hostname(row["root_domain"])
        aliases = run.get("aliases", [])
        paired = root[4:] if root.startswith("www.") else "www." + root
        if any(hostname(alias) != paired for alias in aliases):
            raise ValueError("Backup contact discovery includes an unapproved hostname")
        # Retained history keeps its literal hosts; the current default pair
        # must not expand the trusted scope of an older saved run.
        hosts = {root, *aliases}
        expected = scope.pop("fingerprint")
        if fingerprint(scope) != expected:
            raise ValueError("Backup contact attribution scope failed its fingerprint check")
        total_bytes = 0
        for snapshot in run["snapshots"]:
            if approved_url(snapshot["url"], hosts) != snapshot["url"]:
                raise ValueError("Backup contact response URL differs from its approved source")
            if allow_unavailable_legacy and not is_derived_snapshot(snapshot):
                if (
                    snapshot.get("retention")
                    or not isinstance(snapshot.get("path"), str)
                    or not snapshot["path"].endswith(".body.txt")
                ):
                    raise ValueError("Contact response has an unsupported retention format")
                # Routine contact exports preserve the recorded source identity
                # but never reopen legacy website bodies. Full archival restore
                # validation remains strict by default.
                continue
            total_bytes += snapshot_path(store, row["id"], snapshot).stat().st_size
            if total_bytes > MAX_TOTAL_BYTES:
                raise ValueError("Backup contact discovery exceeded its total capture budget")
        if scope.get("basis") == "entity_domain":
            if scope.get("schema") != 2 or scope.get("attribution_ref") or scope.get("snapshots"):
                raise ValueError(
                    "Backup entity website scope has inconsistent attribution metadata"
                )
            continue
        if not (store.root / "attribution.sqlite3").is_file():
            raise ValueError("Backup contact discovery is missing its attribution evidence")
        with evidence_factory(store.root / "attribution.sqlite3") as evidence:
            original = checked_result(
                evidence, scope["attribution_ref"]["result_id"], row["root_domain"]
            )
            _verify_snapshots(evidence, original)
            for meta in scope["snapshots"]:
                snapshot = evidence.snapshot(meta["snapshot_id"])
                if snapshot.body_sha256 != meta["body_sha256"]:
                    raise ValueError("Backup contact attribution response failed its SHA-256 check")
    for row in store.all("SELECT * FROM contact_candidates" + predicate, args):
        validate_candidate(store, row)
    source_query = (
        "SELECT s.* FROM contact_sources s JOIN contact_candidates c ON c.id=s.candidate_id"
    )
    if entity_id is not None:
        source_query += " WHERE c.entity_id=?"
    for source in store.all(source_query, args):
        row = store.one("SELECT * FROM contact_candidates WHERE id=?", (source["candidate_id"],))
        run_row = store.one("SELECT * FROM contact_runs WHERE id=?", (source["run_id"],))
        if not row or not run_row:
            raise ValueError("Backup contact source is missing its candidate or retained run")
        _validate_sources(store, row, run_row, source)
