"""Small durable progress snapshots and bounded intake statistics. No network I/O."""

from collections import Counter
import json
import sqlite3

from .primitives import dump, now


def catalog_readiness(root):
    from .cve_catalog.storage import CatalogStorage

    try:
        status = CatalogStorage(root).status()
    except (OSError, ValueError, sqlite3.Error):
        return {"state": "unavailable", "total": 0, "bootstrap_complete": False}
    state = (
        "missing"
        if not status["total"]
        else "partial"
        if not status["bootstrap_complete"]
        else "stale"
        if status["stale"]
        else "ready"
    )
    return {
        "state": state,
        **{key: status[key] for key in ("total", "bootstrap_complete", "last_success_at")},
    }


REASONS = {
    "missing_required_value": "Missing required fields",
    "outside_jurisdiction": "Outside jurisdiction",
    "invalid_hostname": "Invalid hostname",
    "invalid_ip": "Invalid IP address",
    "missing_version": "Missing version evidence",
    "placeholder_version": "Placeholder version",
    "malformed_cve_identifier": "Malformed CVE",
    "unsupported_finding": "Unrecognized finding",
    "unsupported_report_profile": "Unsupported report type",
    "below_critical": "Below outreach threshold",
    "unknown_severity": "Severity not established",
    "incident_review_required": "Incident report outside proactive outreach",
    "targeted_profile_review_required": "Outside selected outreach mode",
    "targeted_reason_required": "Targeted reason missing",
    "withdrawn_cve_only": "Withdrawn CVE",
    "provider_out_of_scope": "Historical ISP exclusion",
}


def publish(store, import_id, config, phase, detail, **counts):
    progress = config.setdefault("intake_progress", {})
    progress.update(phase=phase, detail=detail, updated_at=now(), **counts)
    with store.transaction() as db:
        db.execute(
            "UPDATE imports SET config=?,stage=? WHERE id=?",
            (dump(config), detail, import_id),
        )


def accepted_patterns(groups):
    cities, products = Counter(), Counter()
    for group in groups:
        for entry in group.entries:
            fields = entry.source.fields
            city = str(fields.get("city") or "").strip()
            if city:
                cities[city[:200]] += 1
            names = {
                str(p.get("product") or "").strip()[:200]
                for p in entry.normalized.get("products", [])
            } - {""}
            for name in names:
                products[name] += 1
    return {"cities": dict(cities.most_common(20)), "products": dict(products.most_common(20))}


def overview(store):
    # A fixed lookback bounds polling cost; repeated evaluations of one original
    # contribute only their most recent result to the recent-file statistics.
    rows = store.all("SELECT * FROM imports ORDER BY created_at DESC,rowid DESC LIMIT 60")
    active = store.one(
        "SELECT * FROM imports WHERE status IN ('running','queued') ORDER BY CASE status WHEN 'running' THEN 0 ELSE 1 END,created_at,id LIMIT 1"
    )
    current = active or (rows[0] if rows else None)
    reasons, products, cities = Counter(), Counter(), Counter()
    seen, accepted, source_rows = set(), 0, 0
    for row in rows:
        if row["sha256"] in seen or row["status"] in {"queued", "running", "error"}:
            continue
        seen.add(row["sha256"])
        config = json.loads(row["config"])
        reasons.update(json.loads(row["rejected"] or "{}"))
        patterns = config.get("intake_stats", {}).get("accepted_patterns", {})
        products.update(patterns.get("products", {}))
        cities.update(patterns.get("cities", {}))
        accepted += row["valid_rows"]
        source_rows += row["rows_read"]
        if len(seen) == 20:
            break
    result = {
        "catalog": catalog_readiness(store.root),
        "current": None,
        "queued": store.one("SELECT count(*) n FROM imports WHERE status='queued'")["n"],
        "recent": {
            "files": len(seen),
            "source_rows": source_rows,
            "admitted_rows": accepted,
            "failures": [
                {"key": key, "label": REASONS.get(key, key.replace("_", " ")), "count": value}
                for key, value in reasons.most_common(5)
            ],
            "products": [{"label": k, "count": v} for k, v in products.most_common(5)],
            "cities": [{"label": k, "count": v} for k, v in cities.most_common(5)],
        },
    }
    if current:
        config = json.loads(current["config"])
        jobs = {
            row["status"]: row["n"]
            for row in store.all(
                "SELECT status,count(*) n FROM jobs WHERE import_id=? GROUP BY status",
                (current["id"],),
            )
        }
        temperatures = {
            row["temperature"]: row["n"]
            for row in store.all(
                "SELECT COALESCE(json_extract(intake_score,'$.temperature'),'unscored') temperature,count(*) n FROM lead_queue WHERE import_id=? AND qualified=1 GROUP BY temperature",
                (current["id"],),
            )
        }
        progress = config.get("intake_progress", {})
        result["current"] = {
            **{
                key: current[key]
                for key in (
                    "id",
                    "name",
                    "status",
                    "stage",
                    "error",
                    "rows_read",
                    "valid_rows",
                    "groups_total",
                    "groups_done",
                    "qualified",
                )
            },
            "progress": progress,
            "catalog_at_scoring": config.get("catalog_at_scoring"),
            "stats": config.get("intake_stats", {}).get("accretion", {}),
            "jobs": jobs,
            "temperatures": temperatures,
            "rejections": json.loads(current["rejected"] or "{}"),
        }
    return result
