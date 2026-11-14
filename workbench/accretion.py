"""Accretion's provisional, explainable intake ranking. No remote lookups.

Admission remains the intake/profile validator's responsibility. These snapshots
measure the information available at entry; they are detached from live catalog
and policy state and must not be rewritten when a case is certified.
"""

from .intake.versions import selected_version
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
import hashlib
from ipaddress import ip_address
import json
import math
import sqlite3

from .cve_catalog.storage import CatalogStorage, date as parse_date
from .cve_catalog.risk import RiskStore, digest
from .intake.domains import CVE_TAG as CVE, HOSTNAME, root_domain as registered_root

SCHEMA_VERSION = 1
POLICY_VERSION = 1
TEMPERATURES = ("cool", "warm", "hot", "blazing")
MAX_CVES = 100000
BATCH_SIZE = 500
_DEFAULT_POLICY = {
    "version": POLICY_VERSION,
    "quality_weights": {"data": 40, "finding": 40, "entity": 20},
    "urgency_weights": {"severity": 40, "kev": 35, "epss": 15, "priority": 10},
    "aggregate_weights": {"quality": 50, "urgency": 50},
    "temperature_thresholds": [40, 60, 80],
    "priority_cities": [],
    "priority_products": [],
    "provider_outreach_multiplier": 0.1,
}
_SEVERITY = {
    "critical": 9.5,
    "high": 8.0,
    "medium": 5.5,
    "low": 2.0,
    "info": 0.0,
    "informational": 0.0,
    "none": 0.0,
}


def policy_defaults():
    """Return an independent copy; weights are provisional, not scientific truth."""
    return deepcopy(_DEFAULT_POLICY)


def _number(value, maximum):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and 0 <= value <= maximum
    )


def normalize_policy(overrides=None):
    policy = policy_defaults()
    if overrides is None:
        return policy
    if not isinstance(overrides, Mapping) or set(overrides) - set(policy):
        raise ValueError("Unknown Accretion policy setting")
    for key, value in overrides.items():
        if key.endswith("_weights"):
            if not isinstance(value, Mapping) or set(value) - set(policy[key]):
                raise ValueError("Unknown Accretion weight")
            policy[key].update(value)
        else:
            policy[key] = deepcopy(value)
    if type(policy["version"]) is not int or policy["version"] != POLICY_VERSION:
        raise ValueError("Unsupported Accretion policy version")
    for key in ("quality_weights", "urgency_weights", "aggregate_weights"):
        values = list(policy[key].values())
        if not all(_number(v, 100) for v in values) or abs(sum(values) - 100) > 1e-8:
            raise ValueError("Accretion weights must be between 0 and 100 and total 100")
    thresholds = policy["temperature_thresholds"]
    if (
        not isinstance(thresholds, (list, tuple))
        or len(thresholds) != 3
        or not all(_number(v, 100) for v in thresholds)
        or not 0 < thresholds[0] < thresholds[1] < thresholds[2] < 100
    ):
        raise ValueError("Accretion requires three increasing temperature thresholds")
    policy["temperature_thresholds"] = list(thresholds)
    if not _number(policy["provider_outreach_multiplier"], 1):
        raise ValueError("Provider outreach multiplier must be between 0 and 1")
    for key in ("priority_cities", "priority_products"):
        values = policy[key]
        if (
            not isinstance(values, list)
            or len(values) > 100
            or any(not isinstance(v, str) or not v.strip() or len(v) > 200 for v in values)
        ):
            raise ValueError("Accretion priorities require at most 100 nonempty names")
        policy[key] = sorted({v.strip().casefold() for v in values})
    return policy


def _json(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def policy_hash(policy=None):
    return hashlib.sha256(_json(normalize_policy(policy)).encode()).hexdigest()


def _clock(as_of):
    if as_of is None:
        return datetime.now(timezone.utc)
    if isinstance(as_of, datetime):
        return (
            as_of.replace(tzinfo=timezone.utc)
            if as_of.tzinfo is None
            else as_of.astimezone(timezone.utc)
        )
    return parse_date(str(as_of))


def _stamp(as_of):
    return _clock(as_of).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _stale(checked, clock):
    try:
        return not checked or (clock - parse_date(checked)).total_seconds() > 172800
    except (TypeError, ValueError, OverflowError):
        return True


def _metric(raw):
    metrics = raw.get("metrics", {})
    if not isinstance(metrics, dict):
        return None, None
    for name in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        items = metrics.get(name, [])
        if not isinstance(items, list):
            continue
        items = [v for v in items if isinstance(v, dict)]
        items.sort(key=lambda v: v.get("type") != "Primary")
        for item in items:
            data = item.get("cvssData", {})
            value = data.get("baseScore") if isinstance(data, dict) else None
            if _number(value, 10):
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
    return None, None


def _empty_cve(identifier, status="missing"):
    return {
        "id": identifier,
        "status": status,
        "cvss": None,
        "severity": None,
        "source": {},
        "last_modified": None,
        "catalog_checked_at": None,
        "catalog_stale": True,
        "epss": None,
        "kev": None,
        "warnings": [],
    }


def _snapshot_cve(identifier, value):
    """Caller-supplied cached data cannot introduce nonfinite scores or wrong IDs."""
    if not value:
        return _empty_cve(identifier)
    if not isinstance(value, Mapping) or value.get("id") != identifier:
        item = _empty_cve(identifier, "invalid")
        item["warnings"].append("Cached CVE identity does not match its identifier")
        return item
    item = {**_empty_cve(identifier), **deepcopy(value)}
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
        item = _empty_cve(identifier, "invalid")
        item["warnings"].append("Cached CVE snapshot is not valid JSON evidence")
    return item


def vet_cves(workspace_root, cve_ids, *, as_of=None):
    """Bulk-read local CVE/risk snapshots, isolating a damaged record from its peers.

    Work is O(unique requested IDs), not O(catalog size); indexed lookups use
    bounded batches and one read transaction per database. No catalog is created.
    A missing/incomplete KEV feed cannot establish negative membership.
    """
    ids = sorted({str(v).upper() for v in cve_ids if CVE.fullmatch(str(v).upper())})
    if len(ids) > MAX_CVES:
        raise ValueError("Too many CVE identifiers for one Accretion batch")
    result = {identifier: _empty_cve(identifier) for identifier in ids}
    if not ids:
        return result
    clock = _clock(as_of)
    catalog = CatalogStorage(workspace_root)
    if catalog.db.is_file():
        try:
            with sqlite3.connect(catalog.db.as_uri() + "?mode=ro", uri=True, timeout=10) as db:
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


def _entry(value):
    value = asdict(value) if is_dataclass(value) else value
    if not isinstance(value, Mapping):
        raise ValueError("Accretion requires observation records")
    source = value.get("source", value)
    fields = source.get("fields", source)
    normalized = value.get("normalized") or {}
    return fields, normalized


def _ids(fields, normalized):
    ids = {v.upper() for v in CVE.findall(str(fields.get("tag") or ""))}
    ids.update(
        str(item.get("id")).upper()
        for item in normalized.get("findings", [])
        if isinstance(item, Mapping) and CVE.fullmatch(str(item.get("id")).upper())
    )
    return ids


def _present(value):
    return value is not None and str(value).strip().casefold() not in {
        "",
        "null",
        "none",
        "n/a",
        "unknown",
        "-",
    }


def _timestamp(value):
    try:
        return isinstance(value, (datetime, date)) or bool(parse_date(str(value)))
    except (TypeError, ValueError, OverflowError):
        return False


def _factor(identifier, label, value, weight, reason):
    return {
        "id": identifier,
        "label": label,
        "value": round(value, 6),
        "weight": weight,
        "points": round(value * weight, 3),
        "reason": reason,
    }


def _data(fields, normalized):
    try:
        valid_address = bool(ip_address(str(fields.get("ip") or "")))
        valid_root = bool(HOSTNAME.fullmatch(str(fields.get("hostname") or "")))
    except ValueError:
        valid_address = valid_root = False
    complete = all(_present(fields.get(key)) for key in ("ip", "hostname", "region", "tag"))
    value = 0.625 if complete and valid_address and valid_root else 0
    timed = _timestamp(normalized.get("scan_timestamp") or fields.get("timestamp"))
    if timed:
        value += 0.25
    source_hash = normalized.get("source_sha256")
    port = fields.get("port")
    try:
        endpoint = not isinstance(port, bool) and str(port).isdigit() and 1 <= int(port) <= 65535
    except (ValueError, TypeError, OverflowError):
        endpoint = False
    provenance = (
        isinstance(source_hash, str)
        and len(source_hash) == 64
        and all(c in "0123456789abcdef" for c in source_hash)
    )
    if endpoint or provenance:
        value += 0.125
    return value, (
        "Complete source identity"
        if complete and valid_address and valid_root
        else "Incomplete source identity"
    ) + ("; dated observation" if timed else "; observation time unknown") + (
        "; source or endpoint traceable" if endpoint or provenance else ""
    )


def _finding(fields, normalized, records):
    products = normalized.get("products") or []
    if any(
        isinstance(p, Mapping) and _present(p.get("product")) and _present(p.get("version"))
        for p in products
    ):
        return (
            1.0,
            "Explicit observed product and software version; applicability still requires evidence",
        )
    profile = normalized.get("profile") or {}
    if (
        profile.get("capability") == "eligible"
        and profile.get("version_requirement") in {"none", "not_required", "eol_only"}
        and not _ids(fields, normalized)
    ):
        return 0.85, "Supported finding profile does not require a software version"
    ids = _ids(fields, normalized)
    if any(records.get(identifier, {}).get("status") == "available" for identifier in ids):
        return (
            0.75,
            "Reported CVE resolves in the local catalog; affected-version match is not established",
        )
    if _present(normalized.get("raw_version", selected_version(fields, profile)["raw_version"])):
        return 0.75, "Observed version text retained; product applicability is not established"
    if ids:
        return 0.5, "CVE identifier reported; local reference is unavailable or unresolved"
    if profile.get("capability") == "eligible":
        return 0.5, "Recognized service or incident finding"
    return 0.0, "No supported finding detail"


def _entity(association, root):
    if isinstance(association, (tuple, list)) and len(association) >= 3:
        state, basis = association[1], association[2]
    elif isinstance(association, Mapping):
        state, basis = association.get("status", association.get("state")), association.get("basis")
    else:
        state, basis = None, None
    if state == "known" and basis in {
        "hostname",
        "saved_ip",
        "rdap",
        "root_domain",
        "Stored hostname association",
        "Saved entity IP association",
    }:
        return 1.0, "Existing explicit entity association: " + str(basis)
    if state == "review":
        return 0.0, "Entity association is ambiguous; shared IP does not establish ownership"
    return (
        (0.5, "Registrable domain is identifiable; organization attribution is not established")
        if root and HOSTNAME.fullmatch(root)
        else (0.0, "Entity identity unavailable")
    )


def score_lead(
    entries,
    *,
    root_domain=None,
    association=None,
    cve_records=None,
    policy=None,
    as_of=None,
    priority=None,
):
    """Score retained observations without mutating inputs or performing I/O."""
    policy = normalize_policy(policy)
    parsed = [_entry(entry) for entry in entries]
    if root_domain is None and parsed:
        root_domain = registered_root(str(parsed[0][0].get("hostname") or ""))
    ids, embedded = set(), {}
    for fields, normalized in parsed:
        ids.update(_ids(fields, normalized))
        embedded.update(normalized.get("accretion_cves") or {})
    records = cve_records if cve_records is not None else embedded
    vetted = [_snapshot_cve(identifier, records.get(identifier)) for identifier in sorted(ids)]
    records = {item["id"]: item for item in vetted}
    # Withdrawn findings remain visible in evidence; they must not lend their
    # old reported critical label to a different observation that opened a group.
    parsed = [
        (fields, normalized)
        for fields, normalized in parsed
        if (normalized.get("eligibility") or {}).get("reason") != "withdrawn_cve_only"
    ]
    active_ids = {
        identifier for fields, normalized in parsed for identifier in _ids(fields, normalized)
    }
    qweights, uweights = policy["quality_weights"], policy["urgency_weights"]
    data = max((_data(f, n) for f, n in parsed), default=(0.0, "No observations"))
    finding = max((_finding(f, n, records) for f, n in parsed), default=(0.0, "No observations"))
    entity = _entity(association, root_domain) if parsed else (0.0, "No observations")
    qfactors = [
        _factor(key, label, value[0], qweights[key], value[1])
        for key, label, value in (
            ("data", "Data", data),
            ("finding", "Finding", finding),
            ("entity", "Entity", entity),
        )
    ]
    priority = priority or {}
    if not isinstance(priority, Mapping) or not _number(priority.get("score", 0), 1):
        raise ValueError("Agency priority score must be between 0 and 1")
    priority_value = priority.get("score", 0) if parsed else 0
    priority_reason = str(priority.get("reason") or "No agency priority applied")[:1000]
    cities, products = set(policy["priority_cities"]), set(policy["priority_products"])
    matches = set()
    for fields, normalized in parsed:
        city = str(fields.get("city") or "").strip().casefold()
        if city and city in cities:
            matches.add("City priority: " + city)
        for product in normalized.get("products") or []:
            name = str(product.get("product") or "").strip().casefold()
            if name and name in products:
                matches.add("Product priority: " + name)
    if matches:
        priority_value, priority_reason = 1.0, "; ".join(sorted(matches))
    candidates = []
    for item in vetted:
        if item["status"] == "rejected" or item["id"] not in active_ids:
            continue
        score = item.get("cvss") if item.get("status") == "available" else None
        severity = score / 10 if _number(score, 10) else 0
        kev = item.get("kev") or {}
        epss = item.get("epss") or {}
        epss_score = epss.get("score")
        ransomware = (
            kev.get("listed") is True
            and str((kev.get("entry") or {}).get("knownRansomwareCampaignUse") or "").casefold()
            == "known"
        )
        finding_priority = max(priority_value, float(ransomware))
        finding_priority_reason = (
            f"{item['id']} CISA KEV records known ransomware use" if ransomware else priority_reason
        )
        factors = [
            _factor(
                "severity",
                "Severity",
                severity,
                uweights["severity"],
                f"{item['id']} local CVSS {score}"
                if _number(score, 10)
                else f"{item['id']} CVSS unknown",
            ),
            _factor(
                "kev",
                "Known exploitation",
                float(kev.get("listed") is True),
                uweights["kev"],
                f"{item['id']} listed in CISA KEV"
                if kev.get("listed") is True
                else f"{item['id']} not in captured KEV feed"
                if kev.get("listed") is False
                else "KEV membership unknown",
            ),
            _factor(
                "epss",
                "EPSS",
                epss_score if _number(epss_score, 1) else 0,
                uweights["epss"],
                f"{item['id']} EPSS probability {epss_score}"
                if _number(epss_score, 1)
                else "EPSS probability unknown",
            ),
            _factor(
                "priority",
                "Agency priority",
                finding_priority,
                uweights["priority"],
                finding_priority_reason,
            ),
        ]
        candidates.append((sum(v["points"] for v in factors), item["id"], "local_cve", factors))
    fallback_rows = [
        (f, n)
        for f, n in parsed
        if not any(
            records.get(identifier, {}).get("status") == "available"
            and _number(records[identifier].get("cvss"), 10)
            for identifier in _ids(f, n)
        )
    ]
    reported = max(
        (
            _SEVERITY.get(
                str(
                    (n.get("eligibility") or {}).get("severity") or f.get("severity") or ""
                ).casefold(),
                0,
            )
            for f, n in fallback_rows
        ),
        default=0,
    )
    fallback = [
        _factor(
            "severity",
            "Severity",
            reported / 10,
            uweights["severity"],
            "Reported severity; local CVSS not used",
        ),
        _factor(
            "kev",
            "Known exploitation",
            0,
            uweights["kev"],
            "No KEV claim in reported-severity fallback",
        ),
        _factor("epss", "EPSS", 0, uweights["epss"], "No EPSS claim in reported-severity fallback"),
        _factor(
            "priority", "Agency priority", priority_value, uweights["priority"], priority_reason
        ),
    ]
    candidates.append(
        (sum(v["points"] for v in fallback), "reported", "reported_severity", fallback)
    )
    best = max(candidates, key=lambda item: (item[0], item[2] == "local_cve", item[1]))
    ufactors = best[3]
    quality, urgency = (
        round(sum(f["points"] for f in qfactors), 1),
        round(sum(f["points"] for f in ufactors), 1),
    )
    aggregate = round(
        (
            quality * policy["aggregate_weights"]["quality"]
            + urgency * policy["aggregate_weights"]["urgency"]
        )
        / 100,
        1,
    )
    from .provider_policy import is_provider

    adjustments = []
    if parsed and (
        is_provider(root_domain) or all(is_provider(fields.get("hostname")) for fields, _ in parsed)
    ):
        multiplier = policy["provider_outreach_multiplier"]
        base = aggregate
        aggregate = round(base * multiplier, 1)
        adjustments.append(
            {
                "id": "provider_outreach",
                "label": "ISP outreach priority",
                "base_aggregate": base,
                "multiplier": multiplier,
                "points": round(aggregate - base, 1),
                "reason": "Provider-owned domain; reduced agency outreach priority. Evidence quality and vulnerability metrics are unchanged.",
            }
        )
    temperature = TEMPERATURES[
        sum(aggregate >= threshold for threshold in policy["temperature_thresholds"])
    ]
    warnings = sorted({warning for item in vetted for warning in item.get("warnings", [])})
    return {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "policy_hash": policy_hash(policy),
        "policy": policy,
        "scored_at": _stamp(as_of) if as_of is not None else None,
        "quality": quality,
        "urgency": urgency,
        "aggregate": aggregate,
        "ranking_adjustments": adjustments,
        "temperature": temperature,
        "factors": {"quality": qfactors, "urgency": ufactors},
        "strongest_finding": {"id": best[1], "basis": best[2], "score": round(best[0], 1)}
        if parsed
        else None,
        "cves": vetted,
        "warnings": warnings,
    }


def score_leads(
    groups,
    *,
    workspace_root=None,
    cve_records=None,
    associations=None,
    policy=None,
    as_of=None,
    priorities=None,
):
    """Score a batch after at most one local vetting call; never fetch remotely."""
    if isinstance(groups, Mapping):
        groups = {root: list(entries) for root, entries in groups.items()}
    else:
        groups = {group.hostname: list(group.entries) for group in groups}
    if cve_records is None and workspace_root is not None:
        ids = set()
        for entries in groups.values():
            for entry in entries:
                ids.update(_ids(*_entry(entry)))
        cve_records = vet_cves(workspace_root, ids, as_of=as_of)
    return {
        root: score_lead(
            entries,
            root_domain=root,
            association=(associations or {}).get(root),
            cve_records=cve_records,
            policy=policy,
            as_of=as_of,
            priority=(priorities or {}).get(root),
        )
        for root, entries in groups.items()
    }
