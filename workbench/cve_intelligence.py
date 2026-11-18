"""Pure source adapters for independent exploitation and impact signals.

No function in this module makes network requests or changes a case. Raw records
remain the evidence; normalized labels describe a CVE, never a recipient's state.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import re
from urllib.parse import urlsplit

ADAPTER_VERSION = "intelligence-0.7.0-v1"
SELECTION_POLICY = "cisa-first-assessment-date-v1"
SSVC_LABELS = {
    "active": "Active exploitation reported",
    "poc": "Public PoC / known exploitation method",
    "none": "No exploitation evidence reported in this assessment",
}


def stable_id(prefix, value):
    return (
        prefix
        + hashlib.sha256(
            json.dumps(
                value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        ).hexdigest()
    )


def _timestamp(value):
    """Missing or invalid dates sort last; retrieval time is never substituted."""
    try:
        value = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.timestamp()
    except (ValueError, TypeError, OverflowError):
        return float("-inf")


def _ssvc(cve_id, value, publisher, provider_role, path, revision):
    if not isinstance(value, dict):
        return None
    # Preserve unidentified records for review, but never merge another CVE's
    # assessment into this one.
    if value.get("id") and str(value["id"]).upper() != cve_id:
        raise ValueError("SSVC identifier does not match the requested CVE")
    options = value.get("options", [])
    choices = {}
    if isinstance(options, list):
        for option in options:
            if isinstance(option, dict):
                for key, raw in option.items():
                    choices[str(key).strip().casefold()] = raw
    raw_exploitation = choices.get("exploitation")
    exploitation = (
        raw_exploitation.strip().casefold() if isinstance(raw_exploitation, str) else None
    )
    supported = str(value.get("version", "")) == "2.0.3"
    normalized = exploitation if supported and exploitation in SSVC_LABELS else None
    record = {
        "publisher": publisher or "Unspecified contributor",
        "provider_role": provider_role,
        "role": value.get("role"),
        "scheme_version": value.get("version"),
        "assessed_at": value.get("timestamp"),
        "assessment_date_valid": _timestamp(value.get("timestamp")) != float("-inf"),
        "exploitation": normalized,
        "raw_exploitation": raw_exploitation,
        "label": SSVC_LABELS.get(normalized, "SSVC assessment requires adapter review"),
        "availability": "supplied" if normalized is not None else "unrecognized",
        "raw_options": deepcopy(options),
        "source_revision_id": revision,
        "source_path": path,
        "raw": deepcopy(value),
    }
    record["id"] = stable_id("ssvc-", record)
    return record


def extract_ssvc(cve_id, raw, source=None):
    source = source or {}
    revision = source.get("revision_id")
    assessments = []
    containers = raw.get("containers", {})
    if isinstance(containers, dict):
        paths = [("containers.cna", containers.get("cna"), "CNA")]
        paths += [
            (f"containers.adp[{i}]", item, "ADP")
            for i, item in enumerate(containers.get("adp", []))
        ]
        for path, container, role in paths:
            if not isinstance(container, dict):
                continue
            publisher = container.get("providerMetadata", {}).get("shortName") or container.get(
                "providerMetadata", {}
            ).get("orgId")
            for i, metric in enumerate(container.get("metrics", [])):
                if not isinstance(metric, dict):
                    continue
                other = metric.get("other")
                if isinstance(other, dict) and str(other.get("type", "")).casefold() == "ssvc":
                    item = _ssvc(
                        cve_id,
                        other.get("content"),
                        publisher,
                        role,
                        f"{path}.metrics[{i}].other.content",
                        revision,
                    )
                    if item:
                        assessments.append(item)
    for item in raw.get("vulnerabilities", []):
        cve = item.get("cve", {})
        if cve.get("id") != cve_id:
            raise ValueError("Returned CVE ID does not match the requested identifier")
        for i, metric in enumerate(cve.get("metrics", {}).get("ssvcV203", [])):
            record = _ssvc(
                cve_id,
                metric.get("ssvcData"),
                metric.get("source"),
                "NVD contributor",
                f"vulnerabilities[0].cve.metrics.ssvcV203[{i}].ssvcData",
                revision,
            )
            if record:
                assessments.append(record)
    return assessments


def select_ssvc(assessments, selected_id=None):
    """Explicit case choice wins; otherwise CISA first, then assessment date."""
    if selected_id:
        match = next((a for a in assessments if a["id"] == selected_id), None)
        if match is None:
            raise ValueError("Selected SSVC assessment is not in this source revision")
        return match
    if not assessments:
        return None
    return sorted(
        assessments,
        key=lambda a: (
            "cisa" not in a.get("publisher", "").casefold(),
            -_timestamp(a.get("assessed_at")),
            a["id"],
        ),
    )[0]


def ransomware(entry, source_revision_id=None, *, membership=None):
    raw = entry.get("knownRansomwareCampaignUse") if isinstance(entry, dict) else None
    if raw == "Known":
        status, label, availability = "known", "Known ransomware use", "supplied"
    elif raw == "Unknown":
        status, label, availability = "unknown", "Ransomware use unconfirmed by CISA", "supplied"
    elif raw is None:
        status = "not_supplied"
        label = (
            "No CISA assessment in this catalog"
            if membership is False
            else "Ransomware use not supplied"
        )
        availability = "not_in_catalog" if membership is False else "not_supplied"
    else:
        status, label, availability = (
            "unrecognized",
            "Ransomware assessment requires adapter review",
            "unrecognized",
        )
    return {
        "status": status,
        "raw": deepcopy(raw),
        "label": label,
        "availability": availability,
        "source_revision_id": source_revision_id,
    }


def validate_kev_catalog(raw):
    """A negative match requires a complete, internally consistent catalog."""
    if not isinstance(raw, dict) or not isinstance(raw.get("vulnerabilities"), list):
        raise ValueError("KEV catalog is incomplete")
    rows = raw["vulnerabilities"]
    count = raw.get("count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0 or count != len(rows):
        raise ValueError("KEV catalog count is absent or does not match the supplied entries")
    if (
        not isinstance(raw.get("catalogVersion"), str)
        or not raw["catalogVersion"].strip()
        or _timestamp(raw.get("dateReleased")) == float("-inf")
    ):
        raise ValueError("KEV catalog version or release date is invalid")
    seen = set()
    fields = (
        "cveID",
        "vendorProject",
        "product",
        "vulnerabilityName",
        "dateAdded",
        "shortDescription",
        "requiredAction",
        "dueDate",
    )
    for entry in rows:
        if not isinstance(entry, dict) or any(not isinstance(entry.get(k), str) for k in fields):
            raise ValueError("KEV catalog contains an incomplete vulnerability entry")
        identifier = entry["cveID"]
        if not re.fullmatch(r"CVE-\d{4}-\d{4,19}", identifier) or identifier in seen:
            raise ValueError("KEV catalog contains an invalid or duplicate CVE identifier")
        seen.add(identifier)
        if any(_timestamp(entry[key]) == float("-inf") for key in ("dateAdded", "dueDate")):
            raise ValueError("KEV catalog contains an invalid entry date")
    return raw


def reference_records(raw, source=None):
    source = source or {}
    records = []
    containers = raw.get("containers", {})
    groups = []
    if containers:
        groups = [("containers.cna", containers.get("cna", {}))]
        groups += [
            (f"containers.adp[{i}]", item) for i, item in enumerate(containers.get("adp", []))
        ]
    if raw.get("vulnerabilities"):
        groups += [("vulnerabilities[0].cve", raw["vulnerabilities"][0].get("cve", {}))]
    for path, container in groups:
        if not isinstance(container, dict):
            continue
        for i, value in enumerate(container.get("references", [])):
            if not isinstance(value, dict):
                continue
            try:
                url = urlsplit(value.get("url", ""))
                valid = url.scheme in ("http", "https") and bool(url.netloc)
            except (ValueError, TypeError):
                valid = False
            if valid:
                records.append(
                    {
                        **deepcopy(value),
                        "publisher": value.get("source")
                        or container.get("providerMetadata", {}).get("shortName")
                        or source.get("publisher"),
                        "source_revision_id": source.get("revision_id"),
                        "source_path": f"{path}.references[{i}]",
                    }
                )
    return records


def structured_impacts(raw, source=None):
    """Use explicit source impact fields; CVSS/CWE/SSVC never imply RCE or BEC."""
    source = source or {}
    results = []
    containers = raw.get("containers", {})
    for path, container in [
        ("containers.cna", containers.get("cna", {})),
        *[(f"containers.adp[{i}]", item) for i, item in enumerate(containers.get("adp", []))],
    ]:
        if not isinstance(container, dict):
            continue
        for i, impact in enumerate(container.get("impacts", [])):
            if not isinstance(impact, dict):
                continue
            for j, description in enumerate(impact.get("descriptions", [])):
                text = description.get("value") if isinstance(description, dict) else None
                if (
                    not isinstance(text, str)
                    or not text.strip()
                    or not str(description.get("lang", "")).lower().startswith("en")
                ):
                    continue
                record = {
                    "label": text,
                    "source_text": text,
                    "basis": "explicit_structured_data",
                    "conditions": deepcopy(container.get("affected", [])),
                    "source_revision_id": source.get("revision_id"),
                    "source_path": f"{path}.impacts[{i}].descriptions[{j}].value",
                    "publisher": container.get("providerMetadata", {}).get("shortName")
                    or source.get("publisher"),
                    "review": None,
                    "raw": deepcopy(impact),
                }
                record["id"] = stable_id("impact-", record)
                results.append(record)
    return results


def reviewed_impact(
    label, source_text, source, *, actor, reviewed_at, reason, conditions="", interpretation=False
):
    """Create a case-owned reviewed label while retaining the whole support text."""
    if not all(
        isinstance(v, str) and v.strip() for v in (label, source_text, actor, reviewed_at, reason)
    ):
        raise ValueError("An impact label requires source text, reviewer, time and a reason")
    if not source.get("revision_id") or _timestamp(reviewed_at) == float("-inf"):
        raise ValueError("An impact label requires a source revision and valid review time")
    record = {
        "label": label.strip(),
        "source_text": source_text,
        "basis": "analyst_interpretation" if interpretation else "reviewed_normalization",
        "conditions": deepcopy(conditions),
        "source_revision_id": source["revision_id"],
        "source_path": source.get("source_path"),
        "publisher": source.get("publisher"),
        "review": {"actor": actor, "reviewed_at": reviewed_at, "reason": reason},
    }
    record["id"] = stable_id("impact-", record)
    return record


def signal_labels(record, selected_ssvc_id=None):
    """Stable print/UI labels, preserving simultaneous and unknown signals."""
    labels = []
    if record.get("kev") is True:
        labels.append("Known exploited · CISA KEV")
    elif record.get("kev") is False:
        labels.append("Not listed in retrieved CISA KEV catalog")
    else:
        labels.append("CISA KEV status unavailable")
    labels.append(
        (
            record.get("ransomware")
            or ransomware(record.get("kev_details"), membership=record.get("kev"))
        )["label"]
    )
    selected = select_ssvc(
        record.get("ssvc_assessments", []),
        selected_ssvc_id or record.get("selected_ssvc_assessment_id"),
    )
    if selected:
        labels.append(
            selected["label"]
            + " · "
            + selected["publisher"]
            + " · "
            + str(selected.get("assessed_at") or "assessment date not supplied")
        )
    else:
        labels.append("No SSVC assessment supplied")
    for impact in record.get("impacts", []):
        labels.append("Potential impact: " + impact["label"])
    return labels
