"""Read-only local CVE/risk snapshots and complete captured-evidence validation."""

from collections.abc import Mapping
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import sqlite3

from modules.library.components.cve_catalog.storage import CatalogStorage, date as parse_date
from modules.library.components.cve_catalog.risk import RiskStore, digest
from modules.library.components.intelligence.metrics import select_nvd_metric
from .intake.domains import CVE_TAG as CVE
from .scoring_matrix import is_score_number as _number, canonical_json as _json

MAX_CVES = 100000


BATCH_SIZE = 500


def score_clock(as_of):
    if as_of is None:
        return datetime.now(timezone.utc)
    if isinstance(as_of, datetime):
        return (
            as_of.replace(tzinfo=timezone.utc)
            if as_of.tzinfo is None
            else as_of.astimezone(timezone.utc)
        )
    return parse_date(str(as_of))


def score_stamp(as_of):
    return score_clock(as_of).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _stale(checked, clock):
    try:
        return not checked or (clock - parse_date(checked)).total_seconds() > 172800
    except (TypeError, ValueError, OverflowError):
        return True


def _metric(raw):
    item = select_nvd_metric(raw)
    if item is None:
        return None, None
    value = item["cvssData"]["baseScore"]
    severity = (
        "CRITICAL"
        if value >= 9
        else "HIGH"
        if value >= 7
        else "MEDIUM"
        if value >= 4
        else "LOW"
        if value > 0
        else "NONE"
    )
    return float(value), severity


def empty_cve(identifier, status="missing"):
    return {
        "id": identifier,
        "status": status,
        "cvss": None,
        "severity": None,
        "source": {},
        "last_modified": None,
        "catalog_checked_at": None,
        "captured_at": None,
        "catalog_stale": True,
        "epss": None,
        "kev": None,
        "warnings": [],
    }


def validated_cve(identifier, value):
    """Caller-supplied cached data cannot introduce nonfinite scores or wrong IDs."""
    if not value:
        return empty_cve(identifier)
    if not isinstance(value, Mapping) or value.get("id") != identifier:
        item = empty_cve(identifier, "invalid")
        item["warnings"].append("Cached CVE identity does not match its identifier")
        return item
    item = {**empty_cve(identifier), **deepcopy(value)}
    item["warnings"] = list(item.get("warnings") or [])
    if not _number(item.get("cvss"), 10):
        item["cvss"] = None
    epss = item.get("epss")
    if epss is not None and (not isinstance(epss, Mapping) or not _number(epss.get("score"), 1)):
        item["epss"] = None
        item["warnings"].append("Cached EPSS probability is invalid")
    kev = item.get("kev")
    if kev is not None and (not isinstance(kev, Mapping) or type(kev.get("listed")) is not bool):
        item["kev"] = None
        item["warnings"].append("Cached KEV membership is invalid")
    try:
        _json(item)
    except (TypeError, ValueError):
        item = empty_cve(identifier, "invalid")
        item["warnings"].append("Cached CVE snapshot is not valid JSON evidence")
    return item


def snapshot_order(item):
    """Prefer the latest whole capture; untimed/tied records have a stable order."""
    try:
        captured = parse_date(str(item.get("captured_at") or ""))
    except (TypeError, ValueError, OverflowError):
        captured = datetime.min.replace(tzinfo=timezone.utc)
    return captured, _json(item)


def vet_cves(workspace_root, cve_ids, *, as_of=None):
    """Bulk-read local CVE/risk snapshots, isolating a damaged record from its peers.

    Work is O(unique requested IDs), not O(catalog size); indexed lookups use
    bounded batches and one read transaction per database. No catalog is created.
    A missing/incomplete KEV feed cannot establish negative membership.
    """
    ids = sorted({str(v).upper() for v in cve_ids if CVE.fullmatch(str(v).upper())})
    if len(ids) > MAX_CVES:
        raise ValueError("Too many CVE identifiers for one Accretion batch")
    result = {identifier: empty_cve(identifier) for identifier in ids}
    if not ids:
        return result
    clock = score_clock(as_of)
    captured_at = score_stamp(clock)
    for item in result.values():
        item["captured_at"] = captured_at
    catalog = CatalogStorage(workspace_root)
    if catalog.db.is_file():
        try:
            with (
                closing(
                    sqlite3.connect(catalog.db.as_uri() + "?mode=ro", uri=True, timeout=10)
                ) as db,
                db,
            ):
                db.row_factory = sqlite3.Row
                db.execute("BEGIN")
                metadata = db.execute(
                    "SELECT value FROM metadata WHERE key='last_success_at'"
                ).fetchone()
                checked = json.loads(metadata[0]) if metadata else None
                for start in range(0, len(ids), BATCH_SIZE):
                    chunk = ids[start : start + BATCH_SIZE]
                    placeholders = ",".join("?" for _ in chunk)
                    rows = db.execute(
                        f"SELECT id,raw_json,raw_sha256,source_json,modified FROM records WHERE id IN ({placeholders})",
                        chunk,
                    )
                    for row in rows:
                        item = result[row["id"]]
                        item.update(
                            catalog_checked_at=checked, catalog_stale=_stale(checked, clock)
                        )
                        try:
                            if (
                                hashlib.sha256(row["raw_json"].encode()).hexdigest()
                                != row["raw_sha256"]
                            ):
                                raise ValueError("integrity")
                            raw, source = (
                                json.loads(row["raw_json"]),
                                json.loads(row["source_json"]),
                            )
                            if (
                                not isinstance(raw, dict)
                                or raw.get("id") != row["id"]
                                or not isinstance(source, dict)
                            ):
                                raise ValueError("identity")
                            _json(source)
                            rejected = str(raw.get("vulnStatus") or "").casefold() == "rejected"
                            score, severity = (None, None) if rejected else _metric(raw)
                            item.update(
                                status="rejected" if rejected else "available",
                                cvss=score,
                                severity=severity,
                                source={**source, "record_sha256": row["raw_sha256"]},
                                last_modified=row["modified"],
                            )
                        except (TypeError, ValueError, KeyError, AttributeError):
                            item.update(status="invalid")
                            item["warnings"].append("Local CVE record failed validation")
        except (OSError, sqlite3.Error, TypeError, ValueError):
            for item in result.values():
                if item["status"] == "missing":
                    item["status"] = "unavailable"
                item["warnings"].append("Local CVE catalog could not be read completely")
    else:
        for item in result.values():
            item["status"] = "unavailable"
    risk = RiskStore(workspace_root, clock=lambda: clock)
    if risk.db.is_file():
        try:
            with risk.connection() as db:
                epss_state, kev_state = risk._state("epss", db=db), risk._state("kev", db=db)
                kev_complete = bool(kev_state.get("last_success_at")) and db.execute(
                    "SELECT count(*) FROM kev"
                ).fetchone()[0] == kev_state.get("count")
                for start in range(0, len(ids), BATCH_SIZE):
                    chunk = ids[start : start + BATCH_SIZE]
                    placeholders = ",".join("?" for _ in chunk)
                    if kev_complete:
                        for identifier in chunk:
                            result[identifier]["kev"] = {
                                "listed": False,
                                "entry": None,
                                "source": risk.source("kev", kev_state),
                                "stale": kev_state["stale"],
                            }
                    for row in db.execute(
                        f"SELECT * FROM epss WHERE id IN ({placeholders})", chunk
                    ):
                        item = result[row["id"]]
                        try:
                            value = {
                                "cve": row["id"],
                                "epss": row["score"],
                                "percentile": row["percentile"],
                                "date": row["score_date"],
                                "model_version": row["model_version"],
                            }
                            if (
                                digest(value) != row["raw_sha256"]
                                or not _number(row["score"], 1)
                                or not _number(row["percentile"], 1)
                            ):
                                raise ValueError("integrity")
                            item["epss"] = {
                                "score": row["score"],
                                "percentile": row["percentile"],
                                "score_date": row["score_date"],
                                "model_version": row["model_version"],
                                "source": risk.source("epss", epss_state),
                                "stale": epss_state["stale"],
                                "record_sha256": row["raw_sha256"],
                            }
                        except (TypeError, ValueError):
                            item["warnings"].append("Local EPSS record failed validation")
                    for row in db.execute(f"SELECT * FROM kev WHERE id IN ({placeholders})", chunk):
                        item = result[row["id"]]
                        try:
                            if (
                                hashlib.sha256(row["raw_json"].encode()).hexdigest()
                                != row["raw_sha256"]
                            ):
                                raise ValueError("integrity")
                            entry = json.loads(row["raw_json"])
                            if not isinstance(entry, dict) or entry.get("cveID") != row["id"]:
                                raise ValueError("identity")
                            item["kev"] = {
                                "listed": True,
                                "entry": entry,
                                "source": risk.source("kev", kev_state),
                                "stale": kev_state["stale"],
                                "record_sha256": row["raw_sha256"],
                            }
                        except (TypeError, ValueError):
                            item["kev"] = None
                            item["warnings"].append("Local KEV record failed validation")
                if not kev_complete:
                    for item in result.values():
                        item["warnings"].append("Local KEV feed is unavailable or incomplete")
        except (OSError, sqlite3.Error, TypeError, ValueError, KeyError, AttributeError):
            for item in result.values():
                item["warnings"].append("Local risk catalog could not be read completely")
    for item in result.values():
        if item["status"] == "available" and item["catalog_stale"]:
            item["warnings"].append("Local CVE catalog is stale")
        for provider in ("epss", "kev"):
            if item[provider] and item[provider].get("stale"):
                item["warnings"].append("Local " + provider.upper() + " snapshot is stale")
    return result
