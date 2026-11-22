"""Rank coherent urgency candidates without reading evidence or running workflow."""

from collections.abc import Mapping

from .scoring_matrix import SEVERITY, factor as _factor, is_score_number as _number, report_base


def strongest_finding(parsed, records, policy, priority):
    """Return the strongest complete candidate; rows carry their active CVE IDs."""
    uweights = policy["urgency_weights"]
    active_ids = {identifier for _, _, ids in parsed for identifier in ids}
    priority = priority or {}
    if not isinstance(priority, Mapping) or not _number(priority.get("score", 0), 1):
        raise ValueError("Agency priority score must be between 0 and 1")
    priority_value = priority.get("score", 0) if parsed else 0
    priority_reason = str(priority.get("reason") or "No agency priority applied")[:1000]
    cities, products = set(policy["priority_cities"]), set(policy["priority_products"])
    matches = set()
    for fields, normalized, _ in parsed:
        if str(fields.get("hostname") or "").casefold().rstrip(".").endswith(".gov"):
            matches.add("Government domain (.gov)")
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
    for item in records.values():
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
        for f, n, row_ids in parsed
        if not any(
            records.get(identifier, {}).get("status") == "available"
            and _number(records[identifier].get("cvss"), 10)
            for identifier in row_ids
        )
    ]
    reported = max(
        (
            SEVERITY.get(
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
    for _, normalized, _ in parsed:
        base = report_base(normalized.get("profile") or {}, policy)
        if base is None:
            continue
        factors = [
            _factor("severity", "Report type", base["value"], uweights["severity"], base["reason"]),
            *fallback[1:],
        ]
        candidates.append((sum(v["points"] for v in factors), base["id"], "report_type", factors))
    return max(candidates, key=lambda item: (item[0], item[2] == "local_cve", item[1]))
