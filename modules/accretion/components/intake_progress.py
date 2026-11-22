"""Small durable progress snapshots and bounded intake statistics. No network I/O."""

from collections import Counter
from datetime import datetime
import json
import sqlite3

from modules.workspace.components.primitives import dump, now


def catalog_readiness(root):
    from modules.library.components.cve_catalog.storage import CatalogStorage

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
    "unusable_certificate_hostname": "Certificate name cannot identify a reported host",
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


def preserve_export_obligation(db, import_id, config):
    """Progress snapshots cannot clear another accepted decision's durable work."""
    row = db.execute(
        "SELECT json_extract(config,'$.intake_progress.exports_pending') pending FROM imports WHERE id=?",
        (import_id,),
    ).fetchone()
    if row and row["pending"]:
        config.setdefault("intake_progress", {})["exports_pending"] = True


def publish(store, import_id, config, phase, detail, **counts):
    progress = config.setdefault("intake_progress", {})
    progress.update(phase=phase, detail=detail, updated_at=now(), **counts)
    with store.transaction() as db:
        preserve_export_obligation(db, import_id, config)
        db.execute(
            "UPDATE imports SET config=json_set(config,'$.intake_progress',json(?)),stage=? "
            "WHERE id=? AND status!='paused'",
            (dump(progress), detail, import_id),
        )


def accepted_patterns(groups):
    cities, products = Counter(), Counter()
    for group in groups:
        for entry in group.observations:
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


RETRY_LABELS = {
    "website_budget_exhausted": "Website time limit reached; resume at the next hostname",
    "capture_browser_startup": "Capture browser could not start",
    "website_capture_error": "Website capture tool failed",
    "website_unavailable": "Website could not be loaded",
    "website_identity_review": "Website identity needs review",
    "attribution_deferred": "Attribution deferred",
    "ownership_changed": "Ownership changed during qualification",
    "association_conflict": "Conflicting ownership evidence",
    "association_evidence_changed": "Referral changed the evidence available for publication",
    "website_deconflicted_destination": "Website redirected to a referred hostname",
}


def retry_label(reason, *, attempts=None):
    """Summarize typed reasons and recognize a precise legacy local startup failure."""
    if reason == "website_capture_error" and attempts:
        last = attempts[-1]
        if (
            isinstance(last, dict)
            and last.get("method") == "website"
            and last.get("status") == "tool_error"
            and last.get("message") == "Capture browser could not start"
        ):
            reason = "capture_browser_startup"
    return RETRY_LABELS.get(reason, "Qualification needs another attempt")


def stage_totals(published, excluded, deferred_at_associate=0):
    """Each terminal Associate disposition followed successful Qualify and Evaluate."""
    return {
        "qualified": published + excluded + deferred_at_associate,
        "evaluated": published + excluded + deferred_at_associate,
        "published": published,
        "excluded_by_associate": excluded,
    }


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
        jobs, retries, group_reasons = Counter(), Counter(), Counter()
        deferred_at_associate = 0
        for row in store.all(
            "SELECT status,error reason,count(*) n "
            "FROM jobs WHERE import_id=? GROUP BY status,reason",
            (current["id"],),
        ):
            jobs[row["status"]] += row["n"]
            if row["status"] == "deferred":
                retries[retry_label(row["reason"])] += row["n"]
                if row["reason"] == "association_evidence_changed":
                    deferred_at_associate += row["n"]
            elif row["reason"]:
                group_reasons[row["reason"]] += row["n"]
        temperatures = {
            row["temperature"]: row["n"]
            for row in store.all(
                "SELECT COALESCE(json_extract(intake_score,'$.temperature'),'unscored') temperature,count(*) n FROM lead_queue WHERE import_id=? AND qualified=1 GROUP BY temperature",
                (current["id"],),
            )
        }
        progress = {
            **config.get("intake_progress", {}),
            # Older snapshots counted every checked group here. Only a completed
            # qualified job commits the successful association transaction.
            "associated_groups": jobs.get("qualified", 0),
        }
        stats = config.get("intake_stats", {}).get("accretion", {})
        if progress.get("filter_complete") and "filtered_rows" in stats:
            progress["filtered_rows"] = stats["filtered_rows"]
        start = progress.get("started_at")
        end = now() if current["status"] == "running" else progress.get("updated_at")
        elapsed = None
        if start and end:
            try:
                elapsed = max(
                    0,
                    int(
                        (
                            datetime.fromisoformat(end) - datetime.fromisoformat(start)
                        ).total_seconds()
                    ),
                )
            except (TypeError, ValueError):
                pass
        result["current"] = {
            "stage_totals": stage_totals(
                jobs["qualified"], group_reasons["association_deconflicted"], deferred_at_associate
            ),
            "elapsed_seconds": elapsed,
            "group_rejections": dict(group_reasons),
            "eligibility_checks": config.get("intake_stats", {}).get("eligibility", {}),
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
            "stats": stats,
            "jobs": jobs,
            "retry_reasons": dict(retries.most_common()),
            "temperatures": temperatures,
            "rejections": json.loads(current["rejected"] or "{}"),
        }
    return result
