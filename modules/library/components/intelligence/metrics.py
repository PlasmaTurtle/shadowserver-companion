"""Pure NVD CVSS selection shared by catalog, intelligence and scoring readers.

Prefer the newest supplied CVSS family, then its Primary assessment. Preserve
provider order among otherwise equal candidates and never alter provider data.
"""

NVD_CVSS_FAMILIES = ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2")


def nvd_metrics(cve):
    """Yield (family, original wrapper) for structurally usable assessments."""
    metrics = cve.get("metrics") or {}
    if not isinstance(metrics, dict):
        return
    for family in NVD_CVSS_FAMILIES:
        values = metrics.get(family) or []
        for item in values if isinstance(values, list) else []:
            if isinstance(item, dict) and isinstance(item.get("cvssData"), dict):
                yield family, item


def valid_nvd_score(metric):
    value = metric["cvssData"].get("baseScore")
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 10


def select_nvd_metric(cve):
    """Return a valid original metric wrapper, or None when no score is supplied."""
    candidates = [(family, item) for family, item in nvd_metrics(cve) if valid_nvd_score(item)]
    if not candidates:
        return None
    family = candidates[0][0]
    preferred = [item for name, item in candidates if name == family]
    return next((item for item in preferred if item.get("type") == "Primary"), preferred[0])
