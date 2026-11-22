"""Verify restored attribution history before replacing the active workspace."""

from contextlib import closing
import json
import sqlite3

from attribution import EvidenceStore
from attribution.models import parse_json
from modules.attribution.components.attribution_bridge import same_domain


def _references(store):
    results, snapshots = set(), []
    inherited = []
    for table, domain_column in (
        ("leads", "domain"),
        ("domain_groups", "root_domain"),
        ("case_groups", "root_domain"),
    ):
        for row in store.all(f"SELECT {domain_column},attribution FROM {table}"):
            proof = json.loads(row["attribution"])
            if not isinstance(proof, dict):
                raise ValueError("Backup contains invalid saved attribution")
            if "approval_reuse" in proof:
                inherited.append((proof, row[domain_column]))
            if proof.get("result_id"):
                results.add((proof["result_id"], row[domain_column]))
            evidence = proof.get("evidence") or {}
            snapshot_id = proof.get("snapshot_id") or evidence.get("snapshot_id")
            if snapshot_id:
                snapshots.append((snapshot_id, proof.get("body_sha256")))
            snapshots.extend((sid, None) for sid in evidence.get("supporting_snapshot_ids", []))
    for row in store.all("SELECT domain,attribution_result_id,attempts FROM jobs"):
        if row["attribution_result_id"]:
            results.add((row["attribution_result_id"], row["domain"]))
        for attempt in json.loads(row["attempts"]):
            if attempt.get("result_id"):
                results.add((attempt["result_id"], row["domain"]))
            snapshots.extend((sid, None) for sid in attempt.get("snapshot_ids", []))
    for row in store.all(
        "SELECT r.result_id,j.domain FROM attribution_reviews r JOIN jobs j ON j.id=r.job_id"
    ):
        results.add((row["result_id"], row["domain"]))
    for row in store.all("SELECT result_id,root_domain FROM case_asset_attributions"):
        results.add((row["result_id"], row["root_domain"]))
    return results, snapshots, inherited


def validate_attribution_data(store):
    """Validate an isolated restored Store; legacy embedded proofs need no new IDs.

    EvidenceStore may migrate its database, so this must only be called on the
    staged replacement. Every captured response is hash-checked, including old
    results that are no longer the latest lookup for a domain.
    """
    try:
        expected_results, expected_snapshots, inherited = _references(store)
        path = store.root / "attribution.sqlite3"
        if not path.is_file():
            if expected_results or expected_snapshots:
                raise ValueError("Backup is missing its referenced attribution database")
            return
        with EvidenceStore(path) as evidence:
            from modules.attribution.components.attribution_approval_evidence import (
                valid_approval_reuse,
            )

            for proof, root in inherited:
                if not valid_approval_reuse(proof, root, evidence):
                    raise ValueError(
                        "Backup inherited attribution approval failed its integrity check"
                    )
            with closing(sqlite3.connect(path)) as db:
                if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Backup attribution database failed its integrity check")
                snapshot_ids = [row[0] for row in db.execute("SELECT id FROM snapshots")]
                result_rows = list(db.execute("SELECT id,payload FROM results"))
            digests = {}
            for snapshot_id in snapshot_ids:
                snapshot = evidence.snapshot(snapshot_id)
                if snapshot.snapshot_id != snapshot_id:
                    raise ValueError("Backup attribution response identity does not match")
                digests[snapshot_id] = snapshot.body_sha256
            results = {}
            for result_id, payload in result_rows:
                result = parse_json(payload)
                if result.get("result_id") != result_id:
                    raise ValueError("Backup attribution result identity does not match")
                results[result_id] = result["root_domain"]
                for item in result.get("evidence", []) + result.get("partial_evidence", []):
                    expected_snapshots.append((item["snapshot_id"], None))
                    expected_snapshots.extend(
                        (sid, None) for sid in item.get("supporting_snapshot_ids", [])
                    )
                for attempt in result.get("attempts", []):
                    expected_snapshots.extend(
                        (sid, None) for sid in attempt.get("snapshot_ids", [])
                    )
            for result_id, root_domain in expected_results:
                if not same_domain(results.get(result_id), root_domain):
                    raise ValueError(
                        "Backup attribution result is missing or belongs to another domain"
                    )
            for snapshot_id, expected_digest in expected_snapshots:
                if snapshot_id not in digests:
                    raise ValueError("Backup is missing a referenced attribution response")
                if expected_digest and digests[snapshot_id] != expected_digest:
                    raise ValueError(
                        "Backup attribution response differs from its recorded SHA-256"
                    )
    except (KeyError, TypeError, AttributeError, sqlite3.Error) as error:
        raise ValueError(f"Backup attribution history could not be verified: {error}") from error
