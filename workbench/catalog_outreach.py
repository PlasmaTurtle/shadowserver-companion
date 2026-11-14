"""Local reference joins for observed findings, with no casework mutations."""

from collections import defaultdict
from contextlib import closing
import re
import sqlite3
from urllib.parse import quote

from .cve_catalog import Catalog
from .intelligence.identifiers import identifiers


SCOPES = {"critical", "critical_kev", "kev", "all"}


def reported_cves(row):
    explicit = row.get("reported_cves") or []
    return identifiers([row.get("tag", ""), *(explicit if isinstance(explicit, list) else [])])


def _name(value):
    return " ".join(re.sub(r"[_\W]+", " ", str(value).casefold()).split())


def _reported_product_names(row):
    """Match explicit intake product pairs without inferring applicability."""
    names = {_name(row.get("product", ""))}
    for pair in row.get("product_versions") or []:
        if isinstance(pair, dict) and pair.get("product"):
            names.add(_name(pair["product"]))
    names.discard("")
    return names


def _endpoint(row):
    return tuple(
        str(row.get(key) or "").strip().casefold()
        for key in ("hostname", "ip", "protocol", "port", "product")
    )


def decorate_product_selection(root, snapshot, product_id):
    if not re.fullmatch(r"product:[a-f0-9]{24}", product_id):
        raise ValueError("Invalid catalog product")
    catalog = Catalog(root)
    identity = catalog.product_identity(product_id)
    if not identity:
        raise ValueError("Product is not in this local index")
    values = catalog.product_cve_ids(product_id, scope="all")
    names = {
        _name(item.get("product", "")) for item in [identity, *(identity.get("aliases") or [])]
    }
    names.update(
        _name(str(item.get("vendor", "")) + " " + str(item.get("product", "")))
        for item in [identity, *(identity.get("aliases") or [])]
    )
    names.discard("")
    for row in [*snapshot.get("observations", []), *snapshot.get("findings", [])]:
        reported_matches = set(reported_cves(row)) & values
        if reported_matches or _reported_product_names(row) & names:
            row["catalog_product_id"] = product_id
            row["catalog_product_cves"] = sorted(reported_matches)
    snapshot["catalog_selection"] = {
        "product_id": product_id,
        "label": " ".join(str(identity.get(key) or "") for key in ("vendor", "product")).strip(),
    }
    return snapshot


def reference_summaries(root, cve_ids):
    """Bounded SQL batches; never parse the full catalog or create an unused DB."""
    catalog = Catalog(root)
    values = sorted(set(cve_ids))
    result = {}
    if not values or not catalog.db.is_file():
        return result
    try:
        with closing(sqlite3.connect(catalog.db.as_uri() + "?mode=ro", uri=True, timeout=2)) as db:
            db.row_factory = sqlite3.Row
            for start in range(0, len(values), 500):
                batch = values[start : start + 500]
                query = (
                    "SELECT id,severity,score,status,modified FROM records WHERE id IN ("
                    + ",".join("?" for _ in batch)
                    + ")"
                )
                for row in db.execute(query, batch):
                    result[row["id"]] = dict(row)
    except OSError, ValueError, sqlite3.Error:
        return {}
    return result


def matches_scope(row, scope, *, product=False):
    if scope == "all":
        return True
    entries = row.get("catalog_findings") or []
    if product:
        members = set(row.get("catalog_product_cves") or [])
        entries = [item for item in entries if item.get("id") in members]
    # Critical+KEV must refer to the SAME CVE, not two unrelated findings on a host.
    if scope == "critical_kev":
        return any(
            item.get("severity") == "CRITICAL" and item.get("kev") is True for item in entries
        )
    if scope == "critical":
        return any(item.get("severity") == "CRITICAL" for item in entries)
    return any(item.get("kev") is True for item in entries) if product else row.get("kev") is True


def material_risk_changes(baseline, findings):
    """Compare saved intake assessments with current local intelligence only."""
    baseline = baseline if isinstance(baseline, dict) else {}
    ranks = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
    reasons, stamps = [], []
    for finding in findings:
        previous = baseline.get(finding.get("id"))
        if not isinstance(previous, dict) or previous.get("status") not in (None, "available"):
            continue
        prior_kev = previous.get("kev")
        prior_listed = prior_kev.get("listed") if isinstance(prior_kev, dict) else prior_kev
        current_kev = (finding.get("risk") or {}).get("kev") or {}
        if prior_listed is False and finding.get("kev") is True:
            reasons.append(f"{finding['id']} is now listed in KEV; it was unlisted at intake.")
            stamps.append(
                (current_kev.get("entry") or {}).get("dateAdded")
                or (current_kev.get("source") or {}).get("retrieved_at")
            )
        old_severity = str(previous.get("severity") or "").upper()
        new_severity = str(finding.get("severity") or "").upper()
        if (
            old_severity in ranks
            and new_severity in ranks
            and ranks[new_severity] > ranks[old_severity]
        ):
            reasons.append(
                f"{finding['id']} severity increased from {old_severity.title()} to {new_severity.title()}."
            )
            stamps.append(finding.get("modified"))
    return {
        "risk_changed": bool(reasons),
        "risk_change_reasons": reasons,
        "risk_updated_at": max((str(value) for value in stamps if value), default=None),
    }


def decorate_entity(root, entity):
    """Enrich a bounded entity projection without changing its stored assessment."""
    findings = entity.get("awareness_findings") or []
    for finding in findings:
        finding["tag"] = finding["condition"]
    decorate_observations(root, findings)
    for finding in findings:
        finding.pop("tag", None)
    entity.setdefault("awareness", {})["risk_changed_findings"] = sum(
        bool(f.get("risk_changed")) for f in findings
    )
    return entity


def decorate_observations(root, rows):
    values = sorted({value for row in rows for value in reported_cves(row)})
    summaries = reference_summaries(root, values)
    for row in rows:
        row.update(risk_changed=False, risk_change_reasons=[], risk_updated_at=None)
    if not values:
        for row in rows:
            row.pop("_intake_cve_assessments", None)
        return rows
    risks = {}
    try:
        from .cve_catalog.risk import RiskStore

        risks = RiskStore(root).batch(values)
    except ImportError, AttributeError, OSError, ValueError, sqlite3.Error:
        pass
    for row in rows:
        findings = []
        for identifier in reported_cves(row):
            summary = summaries.get(identifier)
            if summary and summary["status"] == "Rejected":
                continue
            risk = risks.get(identifier) or {}
            if not summary and not any(risk.values()):
                continue
            kev = risk.get("kev") or {}
            findings.append(
                {
                    **(
                        summary
                        or {
                            "id": identifier,
                            "severity": "UNKNOWN",
                            "score": None,
                            "status": "Not in local catalog",
                        }
                    ),
                    "kev": kev.get("listed"),
                    "epss": risk.get("epss"),
                    "risk": risk,
                }
            )
        row["catalog_findings"] = findings
        row.update(
            material_risk_changes(
                row.pop("_intake_cve_assessments", row.get("intake_cve_assessments")), findings
            )
        )
        row["catalog_severity"] = (
            "CRITICAL"
            if any(item["severity"] == "CRITICAL" for item in findings)
            else next(
                (
                    level
                    for level in ("HIGH", "MEDIUM", "LOW", "NONE")
                    if any(item["severity"] == level for item in findings)
                ),
                "UNKNOWN",
            )
        )
        if (
            findings
            and all(item.get("kev") is not None for item in findings)
            and len(findings) == len(reported_cves(row))
        ):
            row["kev"] = any(item.get("kev") is True for item in findings)
        elif any(item.get("kev") is True for item in findings):
            row["kev"] = True
        if any(
            (((item.get("risk") or {}).get("kev") or {}).get("entry") or {}).get(
                "knownRansomwareCampaignUse"
            )
            == "Known"
            for item in findings
        ):
            row["ransomware_known"] = True
        row["catalog_basis"] = (
            "Current local reference joined to explicitly reported CVE identifiers; report evidence is unchanged."
        )
    return rows


class CatalogOutreach:
    def __init__(self, eclipse, manager):
        self.eclipse, self.manager = eclipse, manager

    def observations(self, *, cve_id="", product_id="", scope="all", limit=50, offset=0):
        if scope not in SCOPES or not 1 <= limit <= 100 or not 0 <= offset <= 500000:
            raise ValueError("Invalid outreach selection")
        product_ids, product_names = set(), set()
        catalog = self.manager.catalog
        if product_id:
            if not re.fullmatch(r"product:[a-f0-9]{24}", product_id):
                raise ValueError("Invalid catalog product")
            identity = catalog.product_identity(product_id)
            if not identity:
                raise ValueError("Product is not in this local index")
            for item in [identity, *(identity.get("aliases") or [])]:
                product_names.add(_name(item.get("product", "")))
                product_names.add(
                    _name(str(item.get("vendor", "")) + " " + str(item.get("product", "")))
                )
            product_names.discard("")
            product_ids = catalog.product_cve_ids(product_id, scope=scope)
        snapshot = self.eclipse.snapshot()
        selected = []
        source_rows = snapshot.get("observations", [])
        candidates = snapshot.get("findings", source_rows)
        for row in candidates:
            reported = set(reported_cves(row))
            matches = reported & ({cve_id} if cve_id else product_ids)
            named = bool(product_id and _reported_product_names(row) & product_names)
            if not matches and not named:
                continue
            if cve_id and not matches_scope(
                {**row, "catalog_product_cves": [cve_id]}, scope, product=True
            ):
                continue
            # A product-name match is deliberately a research lead, not a new CVE assertion.
            basis = (
                "Reported CVE"
                if cve_id
                else "Reported CVE associated with this product"
                if matches
                else "Reported product; applicability unresolved"
            )
            selected.append(
                {
                    **row,
                    "matched_cves": sorted(matches),
                    "basis": basis,
                    "finding_kind": "reported" if matches else "product_candidate",
                    "entity_url": "#entity/" + quote(str(row["entity_id"]), safe="")
                    if row.get("entity_id")
                    else None,
                    "case_url": "#workspace/notifications/" + quote(str(row["case_id"]), safe="")
                    if row.get("case_id")
                    else None,
                }
            )
        selected.sort(key=lambda row: (row.get("observed_day") or "", row["id"]), reverse=True)
        selected_ids = {row.get("finding_id") for row in selected if row.get("finding_id")}
        supporting = [
            row for row in source_rows if selected_ids.intersection(row.get("finding_ids") or [])
        ]
        if not selected_ids:
            supporting = selected
        entity_support = defaultdict(set)
        for row in supporting:
            if row.get("entity_id"):
                entity_support[row["entity_id"]].add(row.get("observation_id") or row["id"])
        entities, versions = {}, defaultdict(list)
        for row in selected:
            versions[row.get("version") or "Not reported"].append(row)
            if not row.get("entity_id"):
                continue
            identity = row["entity_id"]
            item = entities.setdefault(
                identity,
                {
                    "id": identity,
                    "name": row.get("entity_name") or row.get("domain"),
                    "domain": row.get("domain"),
                    "observations": 0,
                    "findings": 0,
                    "endpoints": set(),
                    "case_ids": set(),
                    "pending": False,
                    "notified": False,
                },
            )
            item["observations"] = len(entity_support[identity])
            item["findings"] += 1
            item["endpoints"].add(_endpoint(row))
            if row.get("case_id"):
                item["case_ids"].add(row["case_id"])
            item["notified"] |= bool(row.get("delivered_at"))
            item["pending"] |= not row.get("delivered_at") and row.get("status") != "excluded"
        entity_rows = [
            {**item, "endpoints": len(item["endpoints"]), "case_ids": sorted(item["case_ids"])}
            for item in entities.values()
        ]
        return {
            "counts": {
                "observations": len({r.get("observation_id") or r["id"] for r in supporting}),
                "findings": len(selected),
                "dark_matter": sum(row.get("dark_matter") is True for row in supporting),
                "endpoints": len({_endpoint(row) for row in selected}),
                "entities": len(entities),
                "pending_entities": sum(item["pending"] for item in entity_rows),
                "notified_entities": sum(item["notified"] for item in entity_rows),
                "unassociated": sum(not row.get("entity_id") for row in selected),
                "reported": sum(row["finding_kind"] == "reported" for row in selected),
                "product_candidates": sum(
                    row["finding_kind"] == "product_candidate" for row in selected
                ),
            },
            "items": selected[offset : offset + limit],
            "total": len(selected),
            "limit": limit,
            "offset": offset,
            "versions": [
                {
                    "version": version,
                    "count": len(rows),
                    "entities": len({row["entity_id"] for row in rows if row.get("entity_id")}),
                }
                for version, rows in sorted(versions.items())
            ],
            "entities": sorted(
                entity_rows, key=lambda item: (not item["pending"], str(item["name"]).casefold())
            ),
            "coverage_complete": snapshot.get("coverage_complete", True),
            "warnings": snapshot.get("warnings", []),
            "basis": "Unique canonical findings with distinct supporting observations and current workflow. Product associations do not confirm version applicability.",
        }
