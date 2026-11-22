"""Pinned report inventory and explicit, offline observation adapters.

The upstream inventory describes available fields; it is not a required-field
schema. Full-row ingestion works for every report. Only implemented adapters may
place observations into notification work, and severity is never inferred from
an EOL tag, KEV flag, version age, or presence of a CVE.
"""

from __future__ import annotations

from functools import lru_cache
import hashlib
from ipaddress import ip_address
import json
from pathlib import Path
import re

PROFILE_VERSION = "0.9.92-2"
_DATA = Path(__file__).resolve().parents[3] / "modules/accretion/schemas"
_CVE = re.compile(r"(?<![A-Z0-9-])CVE-\d{4}-\d{4,}(?![A-Z0-9-])", re.I)
_PRODUCT = re.compile(
    r"(?P<product>[A-Za-z][A-Za-z0-9_.+\-]*)\s*[/=:]\s*(?P<version>[0-9][^\s;,]*)"
)
_SPACED = re.compile(r"^\s*(?P<product>[A-Za-z][A-Za-z0-9_.+\-]*)\s+(?P<version>[0-9][^\s;,]*)\s*$")
# These are reviewed observation adapters, not every report in the inventory.
# Reachability reports outside this set remain research-only even if an input
# happens to contain a critical severity or HTTP-like columns.
_ADAPTER_FAMILIES = {
    "http_vulnerable": ("vulnerability", "software", "cve_or_version"),
    "smtp_vulnerable": ("vulnerability", "software", "eol_only"),
    "exchange": ("vulnerability", "software", "eol_only"),
    "badsecrets": ("weak_secret", "unspecified", "eol_only"),
    "isakmp": ("vulnerability", "protocol", "eol_only"),
    "rdp": ("exposure", "protocol", "eol_only"),
    "mongodb": ("exposure", "software", "eol_only"),
    "msrpc": ("exposure", "protocol", "eol_only"),
    "http": ("exposure", "software", "eol_only"),
    "gtp": ("exposure", "protocol", "eol_only"),
}
_ADAPTERS = {
    prefix + family: {
        "family": family,
        "observation_kind": semantics[0],
        "version_semantics": semantics[1],
        "version_requirement": semantics[2],
        "notification_mode": "targeted"
        if family in {"rdp", "msrpc", "http", "gtp"}
        else "critical_or_targeted",
    }
    for family, semantics in _ADAPTER_FAMILIES.items()
    for prefix in ("scan_", "scan6_")
    if not (family == "gtp" and prefix == "scan6_")
}
for _profile, _family in (
    ("population_isakmp", "isakmp"),
    ("population6_isakmp", "isakmp"),
    ("population_ntrip", "ntrip"),
):
    _ADAPTERS[_profile] = {
        "family": _family,
        "observation_kind": "exposure",
        "version_semantics": "protocol",
        "version_requirement": "eol_only",
        "notification_mode": "targeted",
    }
_ADAPTERS["population_ntrip"]["version_fields"] = ["ntrip_version", "version"]
for _family in ("compromised_website", "compromised_iot"):
    for _suffix in ("", "6"):
        _ADAPTERS[_family + _suffix] = {
            "family": _family,
            "observation_kind": "compromise_indicator",
            "version_semantics": "software",
            "version_requirement": "eol_only",
            "notification_mode": "targeted",
        }


def supported_profiles():
    """Canonical report IDs supported by the notification adapters."""
    return sorted(_ADAPTERS)


def _identity_token(value):
    return re.sub(r"[\s-]+", "_", str(value).strip().casefold())


@lru_cache(maxsize=1)
def _profile_aliases():
    aliases = {}
    for key, definition in inventory().items():
        aliases[_identity_token(key)] = key
        if definition.get("name"):
            aliases[_identity_token(definition["name"])] = key
            aliases[_identity_token(definition["name"]) + "_report"] = key
    aliases.update(
        {
            "http_vulnerable": "scan_http_vulnerable",
            "http_vulnerable_ipv6": "scan6_http_vulnerable",
            "open_mongodb_service": "scan_mongodb",
            "accessible_gprs_tunnel": "scan_gtp",
            "accessible_ntrip": "population_ntrip",
            "accessible_isakmp": "population_isakmp",
            "ipv6_accessible_isakmp": "population6_isakmp",
            "ipv6_open_mongodb_service": "scan6_mongodb",
            "accessible_ms_rpc_service": "scan_msrpc",
            "ipv6_accessible_ms_rpc_service": "scan6_msrpc",
            "ipv6_vulnerable_exchange_server": "scan6_exchange",
            "ipv6_vulnerable_exchange_server_report": "scan6_exchange",
            "open_mongodb_service_report": "scan_mongodb",
            "ipv6_open_mongodb_service_report": "scan6_mongodb",
            "accessible_ms_rpc_service_report": "scan_msrpc",
            "ipv6_accessible_ms_rpc_service_report": "scan6_msrpc",
        }
    )
    return aliases


@lru_cache(maxsize=1)
def inventory():
    raw = (_DATA / "shadowserver-reports.json").read_bytes()
    meta = json.loads((_DATA / "shadowserver-reports.meta.json").read_text(encoding="utf-8"))
    if hashlib.sha256(raw).hexdigest() != meta["sha256"]:
        raise ValueError("Bundled Shadowserver inventory fingerprint mismatch")
    return json.loads(raw)


@lru_cache(maxsize=1)
def _metadata():
    meta = json.loads((_DATA / "shadowserver-reports.meta.json").read_text(encoding="utf-8"))
    definitions = inventory()
    meta.update(
        {
            "inventory_count": len(definitions),
            "distinct_field_count": len(
                {f for d in definitions.values() for f in d.get("fields", [])}
            ),
            "adapter_version": PROFILE_VERSION,
        }
    )
    return meta


def inventory_metadata():
    return dict(_metadata())


@lru_cache(maxsize=128)
def _filename_profile(filename):
    """Resolve fixed file identity once; row schema details remain uncached."""
    for key in sorted(inventory(), key=len, reverse=True):
        report_token = re.escape(key.casefold()).replace("_", "[-_]")
        if re.search(r"(?:^|[^a-z0-9_])" + report_token + r"(?:[^a-z0-9_]|$)", filename):
            return key
    return ""


def resolve_profile(fields, filename="", configured_type="auto"):
    """Return a versioned profile without coercing unknown reports to HTTP.

    Prefer the explicit import setting/row identity, then a recognized filename.
    Headers cannot distinguish accessible HTTP from vulnerable HTTP, so an
    unrecognized filename needs a deliberate report-profile selection. Saved
    normalized profiles remain part of their original retained observations.
    """
    definitions = inventory()
    selected, basis = "", "unclassified"
    explicit = (
        configured_type if configured_type not in ("", None, "auto") else fields.get("report_type")
    )
    if explicit:
        selected, basis = (
            str(explicit),
            "configured" if configured_type not in ("", None, "auto") else "reported",
        )
        selected = _profile_aliases().get(_identity_token(selected), selected)
    else:
        selected = _filename_profile(str(filename).casefold())
        if selected:
            basis = "filename"
    definition = definitions.get(selected, {})
    supported = selected in _ADAPTERS
    return {
        "id": selected or "unclassified",
        "name": definition.get("name") or selected or "Unclassified report",
        "capability": "eligible" if supported else "retained",
        "capability_label": "Supported for notification" if supported else "Retained for research",
        "selection_basis": basis,
        "adapter_version": PROFILE_VERSION if supported else None,
        "inventory_commit": _metadata()["commit"],
        "inventory_sha256": _metadata()["sha256"],
        "source_url": definition.get("url"),
        "declared_fields": definition.get("fields", []),
        "required_for_notification": ["tag", "hostname", "ip", "region"] if supported else [],
        "endpoint_roles": {
            "reported_service": {
                "ip": "ip",
                "hostname": "hostname",
                "protocol": "protocol",
                "port": "port",
            }
        }
        if supported
        else {},
        "severity_rule": "reported severity field only" if supported else None,
        **(_ADAPTERS[selected] if supported else {}),
        "schema_observation": {
            "unknown_columns": sorted(set(fields) - set(definition.get("fields", []))),
            "missing_notification_columns": sorted(
                {"tag", "hostname", "ip", "region"} - set(fields)
            )
            if supported
            else [],
        },
    }


def has_independent_finding(fields, profile):
    """Report/EOL evidence can survive withdrawal of every associated CVE."""
    return bool(
        re.search(r"(?:^|[;,:\s])eol(?:$|[-;,:\s])", str(fields.get("tag") or ""), re.I)
    ) or profile.get("observation_kind") in {"weak_secret", "exposure", "compromise_indicator"}


def notification_eligibility(fields, profile, config, *, catalog_records=None):
    """Profile/severity gate; structural/jurisdiction rules remain separate.

    An eligible critical group can retain other observations as context; this
    function does not relabel the severity of those observations.
    """
    raw_severity = fields.get("severity")
    supplied = str(raw_severity).strip().casefold() if raw_severity is not None else ""
    severity = (
        supplied
        if supplied in {"critical", "high", "medium", "low", "info", "informational"}
        else None
    )
    # Catalog scores are a separate admission source, never a rewrite of the
    # reported severity or proof that an observed software version is affected.
    # Ignore arbitrary input columns named CVSS/KEV: only vetted local records
    # explicitly linked by a reported CVE identifier may contribute here.
    reported_cves = sorted({c.upper() for c in _CVE.findall(str(fields.get("tag") or ""))})
    catalog_scores, withdrawn = {}, set()
    for cve_id in reported_cves:
        record = (catalog_records or {}).get(cve_id, {})
        score = record.get("cvss")
        if record.get("status") == "rejected":
            withdrawn.add(cve_id)
        elif (
            record.get("status") == "available"
            and isinstance(score, (int, float))
            and not isinstance(score, bool)
            and 0 <= score <= 10
        ):
            catalog_scores[cve_id] = score
    # KEV is an independent, verified reason for proactive attention. Only the
    # vetted local snapshot can supply it; a source row's arbitrary KEV flag
    # never bypasses admission. Withdrawn or damaged CVE records cannot rescue.
    catalog_kev = sorted(
        cve_id
        for cve_id in reported_cves
        if (catalog_records or {}).get(cve_id, {}).get("status")
        in {"available", "missing", "unavailable"}
        and ((catalog_records or {}).get(cve_id, {}).get("kev") or {}).get("listed") is True
    )
    independent_finding = has_independent_finding(fields, profile)
    catalog_complete = bool(reported_cves) and all(
        cve_id in catalog_scores or cve_id in withdrawn for cve_id in reported_cves
    )
    catalog_critical = sorted(cve_id for cve_id, score in catalog_scores.items() if score >= 9)
    admission_severity = severity
    admission_basis = "reported" if severity else "unknown"
    admission_cves = []
    if catalog_scores and catalog_complete and not independent_finding:
        # Complete local coverage controls CVE-only admission in both directions.
        # Partial coverage cannot establish that the unknown findings are minor.
        score = max(catalog_scores.values())
        admission_severity = (
            "critical"
            if score >= 9
            else "high"
            if score >= 7
            else "medium"
            if score >= 4
            else "low"
            if score > 0
            else "informational"
        )
        admission_basis = "local_catalog_cvss"
        admission_cves = sorted(
            cve_id for cve_id, value in catalog_scores.items() if value == score
        )
    elif catalog_critical and severity != "critical":
        admission_severity = "critical"
        admission_basis = "local_catalog_cvss"
        admission_cves = catalog_critical
    # A withdrawn-only CVE row has no surviving finding to justify outreach.
    # Retain independently reported EOL/service evidence and unknown CVEs.
    withdrawn_only = (
        bool(reported_cves) and not independent_finding and len(withdrawn) == len(reported_cves)
    )
    admission_signal = "known_exploitation" if catalog_kev else None
    if catalog_kev:
        admission_basis = "local_kev"
        admission_cves = catalog_kev
    if withdrawn_only:
        admission_severity = None
        admission_basis = "local_catalog_status"
        admission_cves = sorted(withdrawn)
    targeted = config.get("outreach_mode") == "targeted" or config.get("critical_only") is False
    reason = None
    if profile.get("capability") != "eligible":
        reason = "unsupported_report_profile"
    elif (
        not targeted
        and profile.get("notification_mode") == "targeted"
        and profile.get("observation_kind") != "compromise_indicator"
    ):
        reason = "targeted_profile_review_required"
    elif targeted and not str(config.get("targeted_reason") or "").strip():
        reason = "targeted_reason_required"
    elif withdrawn_only:
        reason = "withdrawn_cve_only"
    elif (
        not targeted
        and admission_severity != "critical"
        and not catalog_kev
        and profile.get("observation_kind") != "compromise_indicator"
    ):
        reason = "unknown_severity" if admission_severity is None else "below_critical"
    return {
        "eligible": reason is None,
        "reason": reason,
        "severity": severity,
        "raw_severity": raw_severity,
        "severity_basis": "reported" if severity else "unknown",
        "admission_severity": admission_severity,
        "admission_basis": admission_basis,
        "admission_signal": admission_signal,
        "admission_cves": admission_cves,
        "admission_catalog_complete": catalog_complete,
        "outreach_mode": "targeted" if targeted else "critical",
        "override_reason": str(config.get("targeted_reason") or "").strip() if targeted else None,
        "included_as_context": False,
    }


def products_from_version(value, service_ref, *, source_field="version"):
    """Extract explicit product/version pairs; retain every unmatched fragment.

    Never attach a lone bare version to all products from a multi-product tag.
    Source strings are preserved in raw_version regardless of parse coverage.
    """
    if value is None or value == "":
        return {"raw_version": value, "products": [], "unresolved_fragments": []}
    text = str(value)
    products, covered = [], []
    for match in _PRODUCT.finditer(text):
        products.append(
            {
                "product": match["product"],
                "version": match["version"],
                "raw": match.group(),
                "service_ref": service_ref,
                "source_field": source_field,
                "parse_basis": "explicit_product_version",
            }
        )
        covered.append(match.span())
    if not products:
        for part in re.split(r"[;,]", text):
            match = _SPACED.fullmatch(part)
            if match:
                products.append(
                    {
                        "product": match["product"],
                        "version": match["version"],
                        "raw": part,
                        "service_ref": service_ref,
                        "source_field": source_field,
                        "parse_basis": "explicit_product_version",
                    }
                )
        if products:
            fragments = [
                p for p in re.split(r"[;,]", text) if p.strip() and not _SPACED.fullmatch(p)
            ]
        else:
            fragments = [text]
    else:
        cursor, fragments = 0, []
        for start, end in covered:
            fragment = text[cursor:start].strip(" ;,")
            if fragment:
                fragments.append(fragment)
            cursor = end
        fragment = text[cursor:].strip(" ;,")
        if fragment:
            fragments.append(fragment)
    return {"raw_version": value, "products": products, "unresolved_fragments": fragments}


def observation_envelope(source, profile, eligibility, *, source_sha256=None, acquisition=None):
    """Identify a source occurrence independently of its display filename.

    Persisted intake always supplies the original file digest. The content-based
    fallback serves standalone in-memory callers and is explicitly labeled; it
    never claims to identify a complete source file. Historical envelopes are
    read unchanged, and no stored occurrence is rewritten here.
    """
    if source_sha256 is not None:
        if not re.fullmatch(r"[0-9a-f]{64}", str(source_sha256)):
            raise ValueError("Observation source requires a SHA-256 digest")
        source_identity = source_sha256
        identity_basis = "file_sha256_sheet_row"
    else:
        from modules.accretion.components.intake.records import json_default

        source_identity = hashlib.sha256(
            json.dumps(
                source.fields,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
                default=json_default,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        identity_basis = "inline_row_content_sheet_row"
    identity = hashlib.sha256(f"{source_identity}:{source.sheet}:{source.row}".encode()).hexdigest()
    fields = source.fields
    try:
        address = ip_address(str(fields.get("ip") or ""))
        nonpublic_ip = not address.is_global or address.is_multicast
    except ValueError:
        nonpublic_ip = None
    from modules.accretion.components.intake.versions import selected_version, version_sources

    selected = selected_version(fields, profile)
    sources = version_sources(fields, profile)
    version = {
        "raw_version": selected["raw_version"],
        "version_source_field": selected["source_field"],
        "version_sources": sources,
        "products": [],
        "unresolved_fragments": [],
    }
    if profile.get("version_semantics") in {"protocol", "unspecified"}:
        # A protocol revision (for example ISAKMP/IKE 10 or MS-RPC 5) is
        # evidence, but is not a detected software product/version pair.
        version["products"] = []
        version["unresolved_fragments"] = (
            [str(selected["raw_version"])] if selected["raw_version"] not in (None, "") else []
        )
    else:
        for source_version in sources:
            parsed = products_from_version(
                source_version["raw_version"], identity, source_field=source_version["source_field"]
            )
            version["products"].extend(parsed["products"])
            version["unresolved_fragments"].extend(parsed["unresolved_fragments"])
    return {
        "schema_version": 2,
        "observation_ref": identity,
        "identity_basis": identity_basis,
        "source_sha256": source_sha256,
        "acquisition": dict(acquisition or {}),
        "profile": profile,
        "eligibility": eligibility,
        "nonpublic_ip": nonpublic_ip,
        "scan_timestamp": fields.get("timestamp"),
        "service": {
            "id": identity,
            "ip": fields.get("ip"),
            "hostname": fields.get("hostname"),
            "protocol": fields.get("protocol"),
            "port": fields.get("port"),
        },
        "findings": [
            {"id": cve, "service_ref": identity, "source_field": "tag"}
            for cve in sorted({c.upper() for c in _CVE.findall(str(fields.get("tag") or ""))})
        ],
        **version,
    }
