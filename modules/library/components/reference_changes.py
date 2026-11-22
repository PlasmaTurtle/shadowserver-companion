"""Compare current local reference data with case-owned retained selections.

This read service never retrieves provider data, adopts a source, reopens a case,
or changes an existing report. Investigations owns the case membership query.
"""

import re
import sqlite3
from urllib.parse import quote

from modules.investigations.components.repositories.reference_usage import ReferenceUsage
from .cve_catalog.risk import RiskStore
from .cve_catalog.risk_policy import date
from .intelligence.metrics import select_nvd_metric


def _newer_or_invalid(pinned, current):
    if not pinned:
        return False
    try:
        return date(pinned) > date(current)
    except (ValueError, TypeError, AttributeError):
        return True


def _score(raw):
    metric = select_nvd_metric(raw)
    if metric is None:
        return None, None
    data = metric["cvssData"]
    return data["baseScore"], data.get("baseSeverity") or metric.get("baseSeverity")


def _pinned_nvd(record):
    raw = record.get("record") or {}
    if not isinstance(raw, dict):
        return None
    values = raw.get("vulnerabilities")
    if isinstance(values, list) and len(values) == 1 and isinstance(values[0], dict):
        cve = values[0].get("cve")
        if isinstance(cve, dict) and cve.get("id") == record.get("id"):
            return cve
    return None


def _comparison(pinned, current):
    if current is None:
        return (
            None,
            [],
            "Current local reference is unavailable; the retained selection is unchanged.",
        )
    previous = _pinned_nvd(pinned)
    if previous is None:
        return (
            None,
            [],
            "This selection has no comparable retained NVD record. Review its cited source in Investigations.",
        )
    if previous == current:
        return False, [], "The retained NVD record matches the current local reference."
    changes = []
    for field, label, keys in (
        ("status", "Record status", ("vulnStatus",)),
        ("assessments", "Severity and assessments", ("metrics",)),
        ("description", "Published description", ("descriptions",)),
        ("versions", "Affected products and versions", ("affected", "configurations")),
        ("references", "References and remediation links", ("references",)),
        (
            "kev",
            "Known exploitation metadata",
            ("cisaExploitAdd", "cisaActionDue", "cisaRequiredAction"),
        ),
    ):
        if any(previous.get(key) != current.get(key) for key in keys):
            changes.append({"field": field, "label": label})
    if not changes:
        changes.append(
            {"field": "metadata", "label": "Other source content or modification metadata"}
        )
    return (
        True,
        changes,
        "The retained reference differs from current local data. Review the changes in Investigations; no source has been adopted.",
    )


def _current_kev(risk, cve_id):
    result = {
        "available": False,
        "listed": None,
        "stale": None,
        "source": None,
        "record_sha256": None,
        "reason": "Local KEV membership is unavailable; update the risk catalog to compare it.",
    }
    try:
        value = risk.get(cve_id)["kev"]
        if value is not None:
            result.update(
                available=True,
                listed=value["listed"],
                stale=value["stale"],
                source=value["source"],
                record_sha256=value.get("record_sha256"),
                reason="Local KEV catalog is stale; update it before treating membership as current."
                if value["stale"]
                else "Compared with the current local KEV catalog.",
            )
    except (OSError, sqlite3.Error, ValueError):
        result["reason"] = (
            "Local KEV data is unavailable or failed its integrity check; membership is unknown."
        )
    return result


def _kev_comparison(pinned, current):
    # A historical default False is not evidence of absence. A negative result
    # requires a selection made from a complete catalog; explicit positives do not.
    previous = pinned.get("kev")
    if previous is not True and not (
        previous is False and pinned.get("kev_catalog_complete") is True
    ):
        previous = None
    if not current["available"]:
        return previous, None, current["reason"]
    if previous is None:
        return (
            None,
            None,
            "Retained KEV membership is unknown; review its cited source in Investigations. "
            + current["reason"],
        )
    changed = previous != current["listed"]
    reason = (
        "Known-exploited catalog membership differs from the retained selection; no source has been adopted."
        if changed
        else "Retained KEV membership matches the local catalog."
    )
    if current["stale"]:
        reason += " " + current["reason"]
    return previous, changed, reason


class ReferenceChanges:
    def __init__(self, store, catalog):
        self.usage, self.catalog = ReferenceUsage(store), catalog
        self.risk = RiskStore(store.root)

    def open_kev_changes(self, *, offset=0, limit=25):
        if not 0 <= offset <= 500000 or not 1 <= limit <= 100:
            raise ValueError("Invalid case reference page")
        result = {
            "items": [],
            "total": 0,
            "offset": offset,
            "limit": limit,
            "comparable": 0,
            "unknown": 0,
            "unreadable_cases": 0,
            "source": None,
            "notice": None,
        }
        try:
            feed = self.risk.extract("kev")
        except (ValueError, OSError, sqlite3.Error):
            result["notice"] = "The local KEV catalog could not be verified."
            return result
        if feed:
            result["source"] = feed["source"]
        if not feed or feed["stale"]:
            result["notice"] = "A current local KEV catalog is needed to check open work."
            return result
        current = {entry["cveID"] for entry in feed["data"]["vulnerabilities"]}
        with self.usage.open_kev_selections() as (rows, unreadable):
            result["unreadable_cases"] = unreadable
            for row in rows:
                identifier = row["cve_id"]
                if not isinstance(identifier, str) or not re.fullmatch(
                    r"CVE-\d{4}-\d{4,}", identifier
                ):
                    continue
                if (
                    row["listed"] is None
                    or _newer_or_invalid(row["retrieved_at"], feed["source"]["retrieved_at"])
                    or _newer_or_invalid(row["released_at"], feed["data"]["dateReleased"])
                ):
                    result["unknown"] += 1
                    continue
                result["comparable"] += 1
                previous, listed = bool(row["listed"]), identifier in current
                if previous == listed:
                    continue
                if offset <= result["total"] < offset + limit:
                    result["items"].append(
                        {
                            "case_id": row["id"],
                            "case_title": row["title"],
                            "cve_id": identifier,
                            "previous": previous,
                            "listed": listed,
                            "pinned_at": row["retrieved_at"],
                            "url": "#workspace/notifications/" + quote(row["id"], safe=""),
                        }
                    )
                result["total"] += 1
        return result

    def impact(self, cve_id, *, limit=25, offset=0, include_completed=False):
        cve_id = str(cve_id).upper()
        if len(cve_id) > 80 or not re.fullmatch(r"CVE-\d{4}-\d{4,}", cve_id):
            raise ValueError("Invalid CVE identifier")
        current = {
            "available": False,
            "id": cve_id,
            "status": None,
            "modified": None,
            "score": None,
            "severity": None,
            "record_sha256": None,
            "catalog_checked_at": None,
            "catalog_stale": None,
            "reason": "This CVE is not in the local reference catalog. Update the catalog in Library to compare it.",
        }
        record = None
        try:
            # Resolve optional CatalogAccess at request time, as Research does.
            # An unavailable sidecar must not prevent the application starting.
            captured = self.catalog.catalog.get(cve_id)
            if captured:
                record = captured["cve"]
                score, severity = _score(record)
                current.update(
                    available=True,
                    status=record.get("vulnStatus"),
                    modified=record.get("lastModified"),
                    score=score,
                    severity=severity,
                    record_sha256=captured["source"].get("record_sha256"),
                    catalog_checked_at=captured.get("catalog_checked_at"),
                    catalog_stale=captured.get("catalog_stale", True),
                    reason="Local reference data may be stale; update the catalog to check for newer source changes."
                    if captured.get("catalog_stale", True)
                    else "Compared with the current local reference catalog.",
                )
        except (OSError, sqlite3.Error, ValueError):
            current["reason"] = (
                "Local reference data is unavailable or failed its integrity check. Retained case selections remain unchanged."
            )
        current["kev"] = _current_kev(self.risk, cve_id)
        current["reason"] += " " + current["kev"]["reason"]
        cases = self.usage.cases(
            cve_id, limit=limit, offset=offset, include_completed=include_completed
        )
        for item in cases["items"]:
            pinned = item.pop("pinned")
            nvd_changed, changes, reason = _comparison(pinned, record)
            pinned_kev, kev_changed, kev_reason = _kev_comparison(pinned, current["kev"])
            if kev_changed:
                changes.append(
                    {"field": "kev_membership", "label": "Known-exploited catalog membership"}
                )
            changed = (
                True
                if nvd_changed is True or kev_changed is True
                else False
                if nvd_changed is False and kev_changed is False
                else None
            )
            item.update(
                pinned_revision_id=pinned.get("intelligence_revision_id"),
                pinned_source_revision_id=pinned.get("revision_id"),
                pinned_modified=pinned.get("date_updated"),
                pinned_status=pinned.get("state") or pinned.get("verification_status"),
                pinned_score=pinned.get("cvss"),
                pinned_kev=pinned_kev,
                nvd_changed=nvd_changed,
                kev_changed=kev_changed,
                changed=changed,
                changes=changes,
                reason=reason + " " + kev_reason,
            )
        return {
            "cve_id": cve_id,
            "current": current,
            "cases": cases,
            "review_required": True,
            "observations_url": "#eclipse?cve=" + quote(cve_id, safe=""),
            "observations_api_url": "/api/cve-catalog/records/"
            + quote(cve_id, safe="")
            + "/observations",
        }
