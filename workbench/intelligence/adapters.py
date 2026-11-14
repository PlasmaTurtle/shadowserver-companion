"""Pure provider normalization. No retrieval, persistence or case adoption."""

import math
from datetime import datetime
from urllib.parse import urlsplit
from ..cve_intelligence import (
    extract_ssvc,
    reference_records,
    structured_impacts,
    validate_kev_catalog,
)


def _number(value, maximum, label):
    result = float(value)
    if not math.isfinite(result) or not 0 <= result <= maximum:
        raise ValueError("Invalid " + label + " in source response")
    return result


def _description(values):
    return next(
        (
            x["value"]
            for x in values
            if isinstance(x, dict)
            and str(x.get("lang", "")).lower().split("-")[0] == "en"
            and isinstance(x.get("value"), str)
            and x["value"].strip()
        ),
        "",
    )


def _empty():
    return {
        "state": "UNKNOWN",
        "verification_status": "unavailable",
        "description": "",
        "cvss": None,
        "cvss_assessments": [],
        "epss": None,
        "epss_percentile": None,
        "kev": None,
        "references": [],
        "affected": [],
        "language": "en",
        "ssvc_assessments": [],
        "reference_records": [],
        "impacts": [],
    }


def _assessment(value, source, severity=None):
    return {
        "source": source or "Unspecified contributor",
        "version": str(value.get("version", "")),
        "score": _number(value["baseScore"], 10, "CVSS score"),
        "severity": value.get("baseSeverity") or severity or "Not supplied",
        "vector": value.get("vectorString", ""),
    }


def _legacy_score(result):
    if result["cvss_assessments"]:
        first = result["cvss_assessments"][0]
        result.update(
            cvss=first["score"],
            cvss_version=first["version"],
            cvss_source=first["source"],
            vector=first["vector"],
        )
    return result


def summarize(cve_id, raw):
    """Normalize CVE Program records, including existing saved 0.3.0 records."""
    meta = raw.get("cveMetadata", {})
    if meta.get("cveId") != cve_id:
        raise ValueError("Returned CVE ID does not match the requested identifier")
    state = meta.get("state")
    if state not in ("PUBLISHED", "REJECTED", "RESERVED"):
        raise ValueError("CVE record has an unsupported state")
    result = {
        **_empty(),
        "state": state,
        "verification_status": state.lower(),
        "source": "CVE Program",
        "description_source": "CVE Program",
        "date_published": meta.get("datePublished", ""),
        "date_updated": meta.get("dateUpdated", ""),
    }
    if state != "PUBLISHED":
        return result
    containers = raw.get("containers", {})
    cna = containers.get("cna", {})
    result["description"] = _description(cna.get("descriptions", []))
    if not result["description"]:
        raise ValueError("Published CVE record is missing its English description")
    result["affected"] = cna.get("affected", [])
    result["description_contributor"] = cna.get("providerMetadata", {}).get("shortName", "")
    for container in [cna, *containers.get("adp", [])]:
        for ref in container.get("references", []):
            if isinstance(ref.get("url"), str) and urlsplit(ref["url"]).scheme in ("http", "https"):
                if ref["url"] not in result["references"]:
                    result["references"].append(ref["url"])
        for metric in container.get("metrics", []):
            for key in ("cvssV4_0", "cvssV3_1", "cvssV3_0", "cvssV2_0"):
                value = metric.get(key)
                if isinstance(value, dict) and "baseScore" in value:
                    result["cvss_assessments"].append(
                        _assessment(
                            value, container.get("providerMetadata", {}).get("shortName", "CNA")
                        )
                    )
    result.update(
        ssvc_assessments=extract_ssvc(cve_id, raw),
        reference_records=reference_records(raw),
        impacts=structured_impacts(raw),
    )
    return _legacy_score(result)


def summarize_nvd(cve_id, raw):
    values = raw.get("vulnerabilities")
    if not isinstance(values, list):
        raise ValueError("NVD response is missing its vulnerabilities array")
    if not values:
        return {
            **_empty(),
            "state": "NOT_FOUND",
            "verification_status": "not_found",
            "source": "NVD",
        }
    if len(values) != 1 or values[0].get("cve", {}).get("id") != cve_id:
        raise ValueError("Returned CVE ID does not match the requested identifier")
    item = values[0]["cve"]
    status = str(item.get("vulnStatus", "")).strip()
    state = (
        "REJECTED"
        if status.lower() == "rejected"
        else "RESERVED"
        if status.lower() == "reserved"
        else "PUBLISHED"
    )
    result = {
        **_empty(),
        "state": state,
        "verification_status": state.lower(),
        "source": "NVD",
        "description_source": "NVD",
        "description_contributor": item.get("sourceIdentifier", ""),
        "nvd_status": status,
        "date_published": item.get("published", ""),
        "date_updated": item.get("lastModified", ""),
    }
    if state != "PUBLISHED":
        return result
    result["description"] = _description(item.get("descriptions", []))
    if not result["description"]:
        raise ValueError("NVD record is missing its English description")
    for key in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        for metric in item.get("metrics", {}).get(key, []):
            value = metric.get("cvssData", {})
            if "baseScore" in value:
                result["cvss_assessments"].append(
                    _assessment(value, metric.get("source", ""), metric.get("baseSeverity"))
                )
    result["references"] = list(
        dict.fromkeys(
            x["url"]
            for x in item.get("references", [])
            if isinstance(x.get("url"), str) and urlsplit(x["url"]).scheme in ("http", "https")
        )
    )
    # NVD's CISA convenience fields are retained as source content. Only the
    # retrieved CISA catalog establishes a negative KEV membership result.
    result["nvd_cisa_fields"] = {k: v for k, v in item.items() if k.startswith("cisa")}
    # Current NVD records include CNA affected data alongside CPE configurations.
    result["affected"] = item.get("affected", [])
    result.update(
        ssvc_assessments=extract_ssvc(cve_id, raw),
        reference_records=reference_records(raw),
        impacts=structured_impacts(raw),
    )
    return _legacy_score(result)


def _validate_risk_response(key, raw):
    if key.startswith("epss:"):
        expected_id = key.split(":", 1)[1]
        if (
            not isinstance(raw, dict)
            or not isinstance(raw.get("data"), list)
            or len(raw["data"]) > 1
            or raw.get("status", "OK") != "OK"
        ):
            raise ValueError("EPSS response is incomplete or ambiguous")
        for item in raw["data"]:
            if not isinstance(item, dict) or item.get("cve") != expected_id:
                raise ValueError("EPSS identifier does not match the requested CVE")
            _number(item["epss"], 1, "EPSS probability")
            if item.get("percentile") is not None:
                _number(item["percentile"], 1, "EPSS percentile")
            if not isinstance(item.get("date"), str):
                raise ValueError("EPSS score date is missing")
            datetime.strptime(item["date"], "%Y-%m-%d")
    elif key.startswith("program:"):
        summarize(key.split(":", 1)[1], raw)
    else:
        validate_kev_catalog(raw)
    return raw
