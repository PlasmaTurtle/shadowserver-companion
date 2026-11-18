"""Offline, saved-evidence-only flags for queue and map filtering."""

import hashlib
import json
from collections.abc import Iterable
from .intelligence_models import CVERecord, IntelligenceFlags
from .intelligence.identifiers import identifiers
from .cve_state import excluded_cves


def flags(records: Iterable[CVERecord]) -> IntelligenceFlags:
    records = list(records)
    known = any(r.get("kev") is True for r in records)
    ransomware = any(
        (r.get("ransomware") or {}).get("status") == "known"
        or (r.get("kev_details") or {}).get("knownRansomwareCampaignUse") == "Known"
        for r in records
    )
    return {
        "kev": True if known else None,
        "ransomware_known": True if ransomware else None,
        "intelligence_basis": "Saved vulnerability source records; does not establish recipient compromise",
    }


def bank_index(store, db=None, identities=None) -> dict[str, CVERecord]:
    from .evidence_registry import available

    if db is None:
        with store.read_snapshot() as snapshot:
            return bank_index(store, snapshot, identities)
    table = "evidence_revisions" if available(db) else "cache"
    digest_column = ",v.payload_sha256" if table == "evidence_revisions" else ""
    if identities is None:
        batches = [("p.key GLOB 'intelligence-latest:*'", ())]
    else:
        keys = sorted({"intelligence-latest:" + key for key in identities})
        batches = [
            (
                "p.key IN (" + ",".join("?" for _ in keys[start : start + 500]) + ")",
                keys[start : start + 500],
            )
            for start in range(0, len(keys), 500)
        ]
    result = {}
    for condition, args in batches:
        rows = db.execute(
            f"SELECT v.payload{digest_column} FROM cache p JOIN {table} v ON v.key='intelligence-version:' || json_extract(p.payload,'$.revision_id') WHERE {condition}",
            args,
        )
        for row in rows:
            if (
                digest_column
                and hashlib.sha256(row["payload"].encode()).hexdigest() != row["payload_sha256"]
            ):
                raise ValueError("Saved intelligence revision failed its payload digest")
            record = json.loads(row["payload"])
            if record.get("id"):
                result[record["id"]] = record
    return result


def notification_records(draft):
    """Retained sources excluded from a notification do not restore its urgency."""
    exclusions = excluded_cves(draft)
    return [record for record in draft.get("cve_records", []) if record.get("id") not in exclusions]


def decorate_rows(store, rows, *, kind, db=None):
    from .repositories.records import Records

    reader = Records(db) if db is not None else store
    if kind == "cases":
        # A single entity/notification view must not deserialize every saved
        # draft in the workspace. Bound placeholders for large all-case views.
        ids = list(dict.fromkeys(row["id"] for row in rows))
        saved = {}
        for start in range(0, len(ids), 500):
            batch = ids[start : start + 500]
            for record in reader.all(
                "SELECT id,draft FROM cases WHERE id IN (" + ",".join("?" for _ in batch) + ")",
                batch,
            ):
                saved[record["id"]] = notification_records(json.loads(record["draft"]))
        for row in rows:
            row.update(flags(saved.get(row["id"], [])))
    else:
        requested = {
            cve for row in rows for cve in identifiers([row.get("tags", row.get("tag", ""))])
        }
        bank = bank_index(store, db, requested)
        for row in rows:
            row.update(
                flags(
                    bank[c] for c in identifiers([row.get("tags", row.get("tag", ""))]) if c in bank
                )
            )
    return rows
