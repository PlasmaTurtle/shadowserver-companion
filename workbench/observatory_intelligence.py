"""Bounded offline relationships between reported observations, never inferred ownership.

Every graph edge is a co-occurrence in a preserved source row. Aggregation is
linear in the indexed rows and identifier occurrences; it never creates an
entity-pair clique. Rendering limits do not change aggregate support counts.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
import hashlib
from ipaddress import ip_address
import json
import math
import re
from urllib.parse import quote

MAX_ROWS = 100000
MAX_INDEX_NODES = 100000
MAX_LABEL = 180
MAX_FIELD = 4096
MAX_IDENTIFIERS = 8
MAX_PATTERNS = 24
MAX_TIMELINE = 366
LENSES = {"organization", "ip", "service", "vulnerability", "version"}
STATUSES = {"qualified", "delivered", "review", "pending", "excluded", "unqualified"}
CVE = re.compile(r"(?<![a-z0-9-])CVE-\d{4}-\d{4,}(?![a-z0-9-])", re.I)
SEMANTICS = {
    "graph": "Edges mean identifiers occur together in preserved observations. Shared values do not establish common ownership or compromise.",
    "timeline": "First seen and returning describe dated observations in the indexed local sources, not actual onset, continuous exposure, or remediation. Missing days are not negative scans.",
    "workflow": "Notification and attribution states are current saved work, not historical scan status.",
    "geography": "Missing geography remains in every denominator. City-area points are approximate and are not asset positions.",
    "support": "Counts cover the selected indexed observations; observation IDs and examples are bounded provenance samples, not the complete support set.",
}


def _text(value):
    return "" if value is None else str(value)


def stable_id(kind, key):
    encoded = json.dumps(key, ensure_ascii=False, separators=(",", ":")).encode()
    return kind + ":" + hashlib.sha256(encoded).hexdigest()[:24]


def _label(value):
    value = _text(value)
    return value if len(value) <= MAX_LABEL else value[: MAX_LABEL - 1] + "…"


def _day(value):
    try:
        return date.fromisoformat(_text(value)[:10]).isoformat()
    except (ValueError, TypeError):
        return ""


def _ip(value):
    try:
        return ip_address(_text(value).strip()).compressed
    except ValueError:
        return ""


def _example(row):
    source = row.get("source") or {}
    identity = quote(_text(row["id"]), safe="")
    imported = quote(_text(source.get("import_id")), safe="")
    return {
        "observation_id": row["id"],
        "detail_url": "/api/eclipse/observations/" + identity,
        "source": {
            "import_id": source.get("import_id"),
            "workbook": _label(source.get("workbook")),
            "sheet": _label(source.get("sheet")),
            "row": source.get("row"),
            "sha256": _text(source.get("sha256"))[:64],
        },
        "source_available": row.get("source_available") is True,
        "original_url": f"/api/imports/{imported}/original"
        if imported and row.get("source_available") is True
        else None,
        "entity_id": row.get("entity_id"),
        "lead_id": row.get("lead_id"),
        "case_id": row.get("case_id"),
        "observed_day": _day(row.get("observed_day")),
    }


class Support:
    __slots__ = (
        "id",
        "kind",
        "key",
        "label",
        "count",
        "assets",
        "entities",
        "days",
        "samples",
        "findings",
        "admitted",
        "dark_matter",
        "density",
        "density_admitted",
        "density_dark",
        "canonical_asset",
        "temperature",
        "temperature_rank",
        "risk_changed",
    )

    def __init__(self, kind, key, label, *, identity=None):
        self.id = identity or stable_id(kind, key)
        self.kind, self.key, self.label = kind, key, label
        self.count = 0
        self.assets, self.entities, self.days = set(), set(), set()
        self.samples = {}
        self.findings = set()
        self.admitted = self.dark_matter = self.density = 0
        self.density_admitted = self.density_dark = 0
        self.canonical_asset = ""
        self.temperature = None
        self.temperature_rank = -1
        self.risk_changed = False

    def add(self, row, asset_id):
        self.count += 1
        temperature = row.get("temperature")
        name = (
            (temperature.get("id") or temperature.get("label"))
            if isinstance(temperature, dict)
            else temperature
        )
        rank = {"blazing": 4, "hot": 3, "warm": 2, "cool": 1, "cold": 0}.get(
            str(name or "").casefold(), -1
        )
        if row.get("admitted") and rank > self.temperature_rank:
            self.temperature, self.temperature_rank = temperature, rank
        self.risk_changed |= bool(row.get("risk_changed"))
        self.findings.update(
            row.get("finding_ids") or ([row["finding_id"]] if row.get("finding_id") else [])
        )
        self.admitted += int(row.get("admitted", row.get("status") in {"qualified", "delivered"}))
        self.dark_matter += int(row.get("dark_matter") is True)
        self.density = max(self.density, row.get("density_count") or 0)
        self.density_admitted = max(self.density_admitted, row.get("admitted_density") or 0)
        self.density_dark = max(self.density_dark, row.get("dark_matter_density") or 0)
        self.canonical_asset = row.get("asset_id") or self.canonical_asset
        self.assets.add(asset_id)
        if row.get("entity_id"):
            self.entities.add(row["entity_id"])
        day = _day(row.get("observed_day"))
        if day:
            self.days.add(day)
        identity = row["id"]
        if len(self.samples) < 5 or identity < max(self.samples):
            self.samples[identity] = row
            if len(self.samples) > 5:
                del self.samples[max(self.samples)]

    def public(self):
        ids = sorted(self.samples)
        result = {
            "id": self.id,
            "scope": {"entity_id": self.key}
            if self.kind == "entity"
            else {"ip": self.key}
            if self.kind == "ip"
            else {"cve": self.key}
            if self.kind == "cve"
            else {"condition": self.key}
            if self.kind == "finding"
            else {"service": self.key}
            if self.kind == "service"
            else {"asset_id": self.canonical_asset}
            if self.kind == "asset" and self.canonical_asset
            else {"version": self.key[1], "service": self.key[0]}
            if self.kind == "version"
            and isinstance(self.key, tuple)
            and not self.key[0].startswith("unknown product")
            else {},
            "type": self.kind,
            "key": _label(self.key),
            "label": _label(self.label),
            "observation_count": self.count,
            "finding_count": len(self.findings),
            "admitted_observations": self.admitted,
            "dark_matter_observations": self.dark_matter,
            "density_count": self.density
            if self.kind in {"asset", "entity"} and self.density
            else self.count,
            "admitted_density": self.density_admitted
            if self.kind in {"asset", "entity"} and self.density
            else self.admitted,
            "dark_matter_density": self.density_dark
            if self.kind in {"asset", "entity"} and self.density
            else self.dark_matter,
            "asset_id": self.canonical_asset if self.kind == "asset" else None,
            "asset_count": len(self.assets),
            "entity_count": len(self.entities),
            "entity_ids": sorted(self.entities)[:12],
            "temperature": self.temperature,
            "risk_changed": self.risk_changed,
            "observation_ids": ids,
            "first_seen": min(self.days) if self.days else "",
            "last_seen": max(self.days) if self.days else "",
            "day_count": len(self.days),
            "examples": [_example(self.samples[i]) for i in ids[:3]],
            "basis": "Source row without a reported hostname or valid IP; kept separate from other unidentified rows"
            if self.kind == "asset" and self.key[0] == "unidentified observation"
            else "Canonical asset; endpoint and service details retain their observation dates"
            if self.kind == "asset" and self.canonical_asset
            else "Exact reported endpoint tuple (hostname, IP, protocol, port, product)"
            if self.kind == "asset"
            else "Saved entity association on these observations"
            if self.kind == "entity"
            else "Exact identifier reported in these source rows",
        }
        if any(len(str(value)) > 300 for value in result["scope"].values()):
            result["scope"] = {}
        return result


def location_key(row):
    return stable_id(
        "location",
        tuple(
            row.get(key) or ""
            for key in ("city", "region", "country", "latitude", "longitude", "location_basis")
        ),
    )


def product_names(row):
    pairs = row.get("product_versions") or []
    names = list(
        dict.fromkeys(
            str(item.get("product") or "").strip()
            for item in pairs
            if isinstance(item, dict) and item.get("product")
        )
    )
    return names or ([str(row["product"]).strip()] if row.get("product") else [])


def _dimensions(row):
    host = _text(row.get("hostname")).strip().casefold().rstrip(".")
    address = _ip(row.get("ip"))
    protocol = _text(row.get("protocol")).strip().upper()
    port = _text(row.get("port")).strip()
    if port.isascii() and port.isdigit():
        port = str(int(port)) if len(port) < 8 else port
    product = _text(row.get("product") or row.get("service")).strip()
    service = " | ".join((protocol, port, product.casefold()))
    service_label = " · ".join(v for v in (protocol, port, product) if v)
    asset_key = (
        (row["asset_id"],)
        if row.get("asset_id")
        else (host, address, protocol, port, product.casefold())
    )
    if not host and not address and not row.get("asset_id"):
        asset_key = ("unidentified observation", row["id"])
    asset_label = " · ".join(v for v in (host, address, service_label) if v)
    asset = ("asset", asset_key, asset_label or "Endpoint identifiers not reported")
    values = []
    if row.get("entity_id"):
        values.append(("entity", row["entity_id"], row.get("entity_name") or "Named entity"))
    if address:
        values.append(("ip", address, address))
    if service_label:
        values.append(("service", service, service_label))
    version = _text(row.get("version")).strip()
    if version:
        # An unlabelled version number is never treated as one software product.
        context = service if product else "unknown product at " + stable_id("asset", asset_key)
        values.append(
            ("version", (context, version), (service_label or host or address) + " · " + version)
        )
    tags = _text(row.get("tag"))
    # Read one boundary character so a clipped long identifier cannot become
    # a different, shorter CVE at the field budget boundary.
    cves = sorted(
        {
            match.group().upper()
            for match in CVE.finditer(tags[: MAX_FIELD + 1])
            if match.end() <= MAX_FIELD
        }
    )
    extra = row.get("reported_cves") or []
    if isinstance(extra, list):
        cves = sorted(
            set(cves)
            | {
                v.upper()
                for v in extra[:MAX_IDENTIFIERS]
                if isinstance(v, str) and CVE.fullmatch(v)
            }
        )
    token_truncated = (
        len(tags) > MAX_FIELD
        or len(cves) > MAX_IDENTIFIERS
        or (isinstance(extra, list) and len(extra) > MAX_IDENTIFIERS)
    )
    values.extend(("cve", c, c) for c in cves[:MAX_IDENTIFIERS])
    tokens = re.split(r"[;,|]", tags[:MAX_FIELD])
    if len(tags) > MAX_FIELD and tags[MAX_FIELD] not in ";,|":
        tokens = tokens[:-1]  # Never join unrelated values by a clipped prefix.
    findings = sorted(
        {t.strip().casefold() for t in tokens if t.strip() and not CVE.fullmatch(t.strip())}
    )
    remaining = max(0, MAX_IDENTIFIERS - len(cves))
    token_truncated |= len(findings) > remaining
    values.extend(("finding", t, t) for t in findings[:remaining])
    return asset, values, token_truncated


def _dimension_metadata(row, cache):
    """Repeated sightings share immutable identifier parsing and stable IDs.

    The cache is private to one canonical revision (or one direct project call).
    Workflow/admission/risk restrictions are applied to copies afterwards.
    """
    fields = (
        "asset_id",
        "hostname",
        "ip",
        "protocol",
        "port",
        "product",
        "service",
        "version",
        "tag",
        "entity_id",
        "entity_name",
    )
    extra = row.get("reported_cves") or []
    extra = extra if isinstance(extra, list) else []
    key = (
        tuple(_text(row.get(field)) for field in fields),
        tuple(_text(value) for value in extra[:MAX_IDENTIFIERS]),
        len(extra),
        row.get("id")
        if not (row.get("asset_id") or row.get("hostname") or _ip(row.get("ip")))
        else "",
    )
    cached = cache.get(key)
    if cached is None:
        asset, dimensions, truncated = _dimensions(row)
        cached = (
            stable_id(asset[0], asset[1]),
            asset,
            dimensions,
            truncated,
            {(kind, value): stable_id(kind, value) for kind, value, _ in dimensions},
        )
        cache[key] = cached
    return cached


def _condition_support(row, kind, key):
    """An admitted source event does not approve every condition attached to it."""
    admissions = row.get("condition_admissions") or {}
    if kind not in {"cve", "finding"} or key not in admissions:
        return row
    source_admitted = row.get("admitted", row.get("status") in {"qualified", "delivered"})
    admitted = bool(source_admitted and admissions[key])
    identity = (row.get("condition_findings") or {}).get(key)
    condition_reason = (
        (row.get("condition_workflows") or {}).get(key, {}).get("intake_reason")
        if source_admitted and not admissions[key]
        else None
    )
    return {
        **row,
        **({"intake_reason": condition_reason} if condition_reason is not None else {}),
        "admitted": admitted,
        "dark_matter": not admitted,
        "finding_ids": [identity] if identity else [],
    }


def _placed(row):
    values = (row.get("latitude"), row.get("longitude"))
    return (
        all(
            isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
            for v in values
        )
        and -90 <= values[0] <= 90
        and -180 <= values[1] <= 180
    )


def validate_query(
    *,
    lens="vulnerability",
    date_from="",
    date_to="",
    status="",
    intake="",
    max_nodes=180,
    max_edges=300,
    ip="",
    network="",
    intelligence="all",
    product_id="",
    **filters,
):
    if lens not in LENSES:
        raise ValueError("Unknown Observatory lens")
    if status and status not in STATUSES:
        raise ValueError("Unknown observation status")
    if intake not in {"", "lead", "dark_matter", "unclassified"}:
        raise ValueError("Unknown intake disposition")
    if intelligence not in {"all", "critical", "critical_kev", "kev", "ransomware"}:
        raise ValueError("Unknown saved intelligence filter")
    if product_id and not re.fullmatch(r"product:[a-f0-9]{24}", product_id):
        raise ValueError("Invalid catalog product")
    if (
        network
        and network != "__unknown"
        and not (
            network.isascii()
            and network.isdigit()
            and len(network) <= 10
            and int(network) <= 4294967295
        )
    ):
        raise ValueError("Use a reported ASN or the unknown-network filter")
    for value in (date_from, date_to):
        if value and (_day(value) != value):
            raise ValueError("Use an ISO observation date (YYYY-MM-DD)")
    if date_from and date_to and date_from > date_to:
        raise ValueError("Observation date range is reversed")
    if not 2 <= max_nodes <= 300 or not 1 <= max_edges <= 600:
        raise ValueError("Graph limits exceed the supported bounds")
    if ip and not _ip(ip):
        raise ValueError("Use a valid reported IP address")
    if any(len(_text(value)) > 300 for value in filters.values()):
        raise ValueError("Observation filter is too long")


def project(
    snapshot,
    *,
    lens="vulnerability",
    q="",
    entity_id="",
    asset_id="",
    city="",
    region="",
    country="",
    location_key="",
    product_name="",
    version="",
    ip="",
    cve="",
    condition="",
    service="",
    date_from="",
    date_to="",
    status="",
    intake="",
    unplaced=False,
    include_undated=False,
    network="",
    intelligence="all",
    product_id="",
    focus="",
    max_nodes=180,
    max_edges=300,
    include_selection=False,
    selection_only=False,
):
    """Build one deterministic selection from verified local source projections."""
    filters = dict(
        lens=lens,
        q=q,
        entity_id=entity_id,
        asset_id=asset_id,
        city=city,
        region=region,
        country=country,
        location_key=location_key,
        product_name=product_name,
        version=version,
        ip=ip,
        cve=cve,
        condition=condition,
        service=service,
        date_from=date_from,
        date_to=date_to,
        status=status,
        intake=intake,
        unplaced=unplaced,
        include_undated=include_undated,
        network=network,
        intelligence=intelligence,
        product_id=product_id,
        focus=focus,
    )
    validate_query(**filters, max_nodes=max_nodes, max_edges=max_edges)
    original = snapshot.get("observations") or []
    rows = {r["id"]: r for r in original if r.get("id")}
    indexed = list(rows.values())
    omitted = 0
    query = q.strip().casefold()
    cve = cve.upper() or (q.strip().upper() if CVE.fullmatch(q.strip()) else "")
    condition = condition.strip()
    condition = condition.upper() if CVE.fullmatch(condition) else condition.casefold()
    selected_condition = cve or condition
    ip_filter = _ip(ip) if ip else ""
    asset_filter = asset_id
    selected, metadata, earliest, first_identifier_day = [], {}, {}, {}
    truncated_identifiers = 0
    dimension_cache = snapshot.get("_dimension_cache")
    if dimension_cache is None:
        dimension_cache = {}
    for row in indexed:
        source_admitted = (
            row.get("admitted", row.get("status") in {"qualified", "delivered"}) is True
        )
        source_dark = row.get("dark_matter") is True or row.get("admitted") is False
        # Asset/entity identity is stable across the canonical event history;
        # other predicates remain below earliest-date collection so date/IP
        # changes cannot falsely turn returning assets into first sightings.
        if entity_id and row.get("entity_id") != entity_id:
            continue
        if asset_filter and row.get("asset_id") != asset_filter:
            continue
        asset_id, asset, dimensions, truncated, identities = _dimension_metadata(
            row, dimension_cache
        )
        if cve and condition and cve != condition:
            continue
        if selected_condition:
            # An exact condition selection restricts risk and membership, not
            # merely the source row that happened to contain that condition.
            dimensions = [
                item
                for item in dimensions
                if item[0] not in {"cve", "finding"} or item[1] == selected_condition
            ]
            found = (row.get("condition_workflows") or {}).get(selected_condition)
            if found:
                admitted = source_admitted and bool(found["admitted"])
                row = {
                    **row,
                    **found,
                    "observation_admitted": source_admitted,
                    "admitted": admitted,
                    "status": found.get("status") if admitted else "excluded",
                    "finding_ids": [found["finding_id"]],
                    "admitted_finding_ids": [found["finding_id"]] if admitted else [],
                    "unadmitted_finding_ids": [] if admitted else [found["finding_id"]],
                    "dark_matter": not admitted,
                    "intake_disposition": "lead" if admitted else "dark_matter",
                    "intake_reason": found.get("intake_reason", row.get("intake_reason", ""))
                    if source_admitted
                    else row.get("intake_reason", ""),
                    "disposition_reason": found.get(
                        "disposition_reason", row.get("disposition_reason", "")
                    )
                    if source_admitted
                    else row.get("disposition_reason", ""),
                }
            row = {
                **row,
                "tag": selected_condition,
                "reported_cves": [selected_condition] if CVE.fullmatch(selected_condition) else [],
                "catalog_findings": [
                    item
                    for item in row.get("catalog_findings", [])
                    if item.get("id") == selected_condition
                ],
                "catalog_product_cves": [selected_condition]
                if CVE.fullmatch(selected_condition)
                else [],
            }
            if not CVE.fullmatch(selected_condition):
                row.update(kev=None, ransomware_known=None, catalog_severity="UNKNOWN")

        condition_scope = (
            "approved"
            if intake == "lead" or status in {"qualified", "delivered"}
            else "dark"
            if intake == "dark_matter" or status == "excluded"
            else ""
        )
        if condition_scope and row.get("condition_admissions"):
            dimensions = [
                (kind, key, label)
                for kind, key, label in dimensions
                if kind not in {"cve", "finding"}
                or (bool(row["condition_admissions"].get(key)) and source_admitted)
                == (condition_scope == "approved")
            ]
        # Qualification/workflow belongs to a condition, not to the source row
        # containing it. Restrict memberships before aggregate counting.
        condition_states = row.get("condition_workflows") or {}
        if source_dark:
            condition_states = {
                key: {**value, "admitted": False, "status": "excluded"}
                for key, value in condition_states.items()
            }
        if condition_states and (status or intake or selected_condition or intelligence != "all"):
            eligible = dict(condition_states)
            if selected_condition:
                eligible = {
                    key: value for key, value in eligible.items() if key == selected_condition
                }
            if status:
                eligible = {
                    key: value for key, value in eligible.items() if value.get("status") == status
                }
            if intake in {"lead", "dark_matter"}:
                eligible = {
                    key: value
                    for key, value in eligible.items()
                    if bool(value.get("admitted")) == (intake == "lead")
                }
            if intelligence != "all":

                def risk_matches(item):
                    if intelligence == "critical":
                        return item.get("severity") == "CRITICAL"
                    if intelligence == "critical_kev":
                        return item.get("severity") == "CRITICAL" and item.get("kev") is True
                    if intelligence == "kev":
                        return item.get("kev") is True
                    return (((item.get("risk") or {}).get("kev") or {}).get("entry") or {}).get(
                        "knownRansomwareCampaignUse"
                    ) == "Known"

                risk_conditions = {
                    item["id"] for item in row.get("catalog_findings", []) if risk_matches(item)
                }
                if product_id:
                    risk_conditions &= set(row.get("catalog_product_cves") or [])
                eligible = {key: value for key, value in eligible.items() if key in risk_conditions}
            unmatched_dark_source = (
                bool(row.get("dark_matter"))
                and (intake == "dark_matter" or status == "excluded")
                and not selected_condition
                and intelligence == "all"
            )
            if not eligible and not unmatched_dark_source:
                continue
            allowed_ids = [value["finding_id"] for value in eligible.values()]
            dimensions = [
                item
                for item in dimensions
                if item[0] not in {"cve", "finding"} or item[1] in eligible
            ]
            row = {
                **row,
                "observation_admitted": source_admitted,
                "finding_ids": allowed_ids,
                "admitted_finding_ids": [
                    v["finding_id"] for v in eligible.values() if v.get("admitted")
                ],
                "unadmitted_finding_ids": [
                    v["finding_id"] for v in eligible.values() if not v.get("admitted")
                ],
            }
            if status:
                row["status"] = status
            if intake:
                row["intake_disposition"] = intake
            if len(eligible) == 1:
                state = next(iter(eligible.values()))
                row.update(
                    {
                        key: state.get(key)
                        for key in ("status", "workflow", "case_id", "case_stage", "delivered_at")
                    }
                )
                row["admitted"] = bool(state["admitted"])
                row["dark_matter"] = not state["admitted"]
                if source_admitted and not state["admitted"]:
                    row["intake_reason"] = state.get("intake_reason", row.get("intake_reason", ""))
                    row["disposition_reason"] = state.get(
                        "disposition_reason", row.get("disposition_reason", "")
                    )
        dimension_ids = [
            (identities[(kind, key)], kind, key, label) for kind, key, label in dimensions
        ]
        metadata[row["id"]] = (asset_id, asset, dimension_ids)
        day = _day(row.get("observed_day"))
        if day and (asset_id not in earliest or day < earliest[asset_id]):
            earliest[asset_id] = day
        if day:
            for identity, _, _, _ in dimension_ids:
                if identity not in first_identifier_day or day < first_identifier_day[identity]:
                    first_identifier_day[identity] = day
        truncated_identifiers += int(truncated)
        if entity_id and row.get("entity_id") != entity_id:
            continue
        if asset_filter and row.get("asset_id") != asset_filter:
            continue
        if city and _text(row.get("city")).casefold() != city.casefold():
            continue
        if region and _text(row.get("region")).casefold() != region.casefold():
            continue
        if country and _text(row.get("country")).casefold() != country.casefold():
            continue
        if location_key and globals()["location_key"](row) != location_key:
            continue
        if product_name and product_name.casefold() not in {
            name.casefold() for name in product_names(row)
        }:
            continue
        if version and str(row.get("version") or "").casefold() != version.casefold():
            continue
        if product_id and row.get("catalog_product_id") != product_id:
            continue
        if ip_filter and _ip(row.get("ip")) != ip_filter:
            continue
        if cve and not any(k == "cve" and value == cve.upper() for _, k, value, _ in dimension_ids):
            continue
        if condition and not any(
            k in {"cve", "finding"} and value == condition for _, k, value, _ in dimension_ids
        ):
            continue
        if service and not any(
            k == "service"
            and service.casefold() in (_text(value).casefold(), _text(label).casefold(), ident)
            for ident, k, value, label in dimension_ids
        ):
            continue
        if intake and row.get("intake_disposition", "unclassified") != intake:
            if not (intake == "dark_matter" and row.get("unadmitted_finding_ids")):
                continue
        if status and row.get("status") != status:
            if not (status == "excluded" and row.get("unadmitted_finding_ids")):
                continue
        if unplaced and _placed(row):
            continue
        if network and (
            (network == "__unknown" and row.get("asn"))
            or (network != "__unknown" and _text(row.get("asn")) != str(int(network)))
        ):
            continue
        if intelligence == "kev" and not cve and row.get("kev") is not True:
            continue
        if (product_id or cve) and intelligence == "kev":
            from .catalog_outreach import matches_scope

            if not matches_scope(row, "kev", product=True):
                continue
        if intelligence in {"critical", "critical_kev"}:
            from .catalog_outreach import matches_scope

            if not matches_scope(row, intelligence, product=bool(product_id or cve)):
                continue
        if intelligence == "ransomware":
            if product_id or cve:
                product_cves = set(row.get("catalog_product_cves") or [])
                if not any(
                    item.get("id") in product_cves
                    and (((item.get("risk") or {}).get("kev") or {}).get("entry") or {}).get(
                        "knownRansomwareCampaignUse"
                    )
                    == "Known"
                    for item in (row.get("catalog_findings") or [])
                ):
                    continue
            elif row.get("ransomware_known") is not True:
                continue
        if not (include_undated and not day) and (
            (date_from and (not day or day < date_from)) or (date_to and (not day or day > date_to))
        ):
            continue
        if focus and focus not in {asset_id, *(v[0] for v in dimension_ids)}:
            continue
        if (
            query
            and query
            not in " ".join(
                _text(row.get(k))[:MAX_FIELD]
                for k in (
                    "hostname",
                    "ip",
                    "domain",
                    "entity_name",
                    "tag",
                    "version",
                    "product",
                    "protocol",
                    "port",
                    "city",
                    "region",
                    "country",
                )
            ).casefold()
        ):
            continue
        if condition_scope == "dark" and row.get("unadmitted_finding_ids"):
            selected.append(
                {
                    **row,
                    "admitted": False,
                    "dark_matter": True,
                    "finding_ids": row["unadmitted_finding_ids"],
                }
            )
        elif condition_scope == "approved" and row.get("admitted_finding_ids"):
            selected.append(
                {
                    **row,
                    "admitted": True,
                    "dark_matter": False,
                    "finding_ids": row["admitted_finding_ids"],
                }
            )
        else:
            selected.append(row)

    # Halo density uses the same selected historical scope in every view.
    # A CVE/period filter must not borrow future or unrelated observation counts.
    scoped_density = defaultdict(lambda: [0, 0, 0])
    for row in selected:
        scope = row.get("density_id") or row.get("asset_id") or row["id"]
        counts = scoped_density[scope]
        counts[0] += 1
        counts[1] += int(row.get("admitted", row.get("status") in {"qualified", "delivered"}))
        counts[2] += int(row.get("dark_matter") is True)
    selected = [
        {
            **row,
            "density_count": scoped_density[
                row.get("density_id") or row.get("asset_id") or row["id"]
            ][0],
            "admitted_density": scoped_density[
                row.get("density_id") or row.get("asset_id") or row["id"]
            ][1],
            "dark_matter_density": scoped_density[
                row.get("density_id") or row.get("asset_id") or row["id"]
            ][2],
        }
        for row in selected
    ]
    if selection_only:
        # FIELD pages share the same predicates and canonical membership as
        # traditional views, without constructing every graph/pattern first.
        dated = sum(bool(_day(row.get("observed_day"))) for row in selected)
        mapped = sum(_placed(row) for row in selected)
        return {
            "filters": filters,
            "semantics": SEMANTICS,
            "_selected": selected,
            "_metadata": metadata,
            "counts": {
                "total_rows": len(original),
                "selected_rows": len(selected),
                "dated_rows": dated,
                "undated_rows": len(selected) - dated,
                "mapped_rows": mapped,
                "unplaced_rows": len(selected) - mapped,
                "entities": len({r["entity_id"] for r in selected if r.get("entity_id")}),
                "assets": len({metadata[r["id"]][0] for r in selected}),
                "observations": len(selected),
                "findings": len({fid for r in selected for fid in r.get("finding_ids", [])}),
                "admitted_observations": sum(r.get("admitted") is True for r in selected),
                "dark_matter_observations": sum(r.get("dark_matter") is True for r in selected),
            },
            "coverage": {
                "complete": bool(snapshot.get("coverage_complete", True))
                and not truncated_identifiers,
                "warnings": list(snapshot.get("warnings", []))
                + (
                    [
                        "Some identifier fields exceed the relationship index; complete originals remain in observation details."
                    ]
                    if truncated_identifiers
                    else []
                ),
                "indexed_rows": len(indexed),
                "omitted_rows": omitted,
                "identifier_limited_rows": truncated_identifiers,
                "omitted_identifier_occurrences": 0,
            },
        }
    assets, hubs, bins = {}, {}, {}
    omitted_identifiers = 0
    for row in selected:
        asset_id, asset, dimensions = metadata[row["id"]]
        if asset_id not in assets:
            assets[asset_id] = Support(*asset)
        assets[asset_id].add(row, asset_id)
        for identity, kind, key, label in dimensions:
            if identity not in hubs:
                if len(hubs) >= MAX_INDEX_NODES:
                    omitted_identifiers += 1
                    continue
                hubs[identity] = Support(kind, key, label)
            hubs[identity].add(_condition_support(row, kind, key), asset_id)
        day = _day(row.get("observed_day"))
        if day:
            if day not in bins:
                bins[day] = {"rows": 0, "assets": set(), "entities": set()}
            entry = bins[day]
            entry["rows"] += 1
            entry["assets"].add(asset_id)
            if row.get("entity_id"):
                entry["entities"].add(row["entity_id"])

    kinds = (
        {"entity"}
        if lens == "organization"
        else {"cve", "finding"}
        if lens == "vulnerability"
        else {lens}
    )
    candidates = [v for v in hubs.values() if v.kind in kinds]

    def rank(value):
        return (
            -value.temperature_rank,
            not value.risk_changed,
            -len(value.entities),
            -len(value.assets),
            -value.count,
            value.id,
        )

    candidates.sort(key=rank)
    hub_budget = min(max(1, max_nodes // 3), 60)
    chosen_hubs = candidates[:hub_budget]
    if focus in hubs and hubs[focus].kind in kinds and hubs[focus] not in chosen_hubs:
        chosen_hubs = [hubs[focus], *chosen_hubs[: max(0, hub_budget - 1)]]
    neighbors = set().union(*(v.assets for v in chosen_hubs)) if chosen_hubs else set()
    chosen_assets = sorted(
        assets.values(), key=lambda v: (v.id != focus, v.id not in neighbors, *rank(v))
    )[: max_nodes - len(chosen_hubs)]
    node_ids = {v.id for v in chosen_assets + chosen_hubs}
    edge_stats, all_edge_ids = {}, set()
    for row in selected:
        asset_id, _, dimensions = metadata[row["id"]]
        for identity, kind, key, _ in dimensions:
            if kind not in kinds or identity not in hubs:
                continue
            pair = (asset_id, identity)
            all_edge_ids.add(pair)
            if asset_id in node_ids and identity in node_ids:
                if pair not in edge_stats:
                    edge_stats[pair] = Support("edge", pair, "")
                edge_stats[pair].add(_condition_support(row, kind, key), asset_id)
    edges = []
    for (source, target), value in sorted(edge_stats.items(), key=lambda v: (-v[1].count, v[0]))[
        :max_edges
    ]:
        public = value.public()
        edges.append(
            {
                k: public[k]
                for k in ("id", "observation_count", "observation_ids", "first_seen", "last_seen")
            }
            | {
                "source": source,
                "target": target,
                "type": "observed_with",
                "basis": "The endpoint and this identifier are recorded together in the supporting source rows",
            }
        )
    graph = {
        "nodes": [v.public() for v in sorted(chosen_assets + chosen_hubs, key=lambda v: v.id)],
        "edges": edges,
        "limits": {
            "max_nodes": max_nodes,
            "max_edges": max_edges,
            "total_nodes": len(assets) + len(candidates),
            "total_edges": len(all_edge_ids),
            "nodes_truncated": max(0, len(assets) + len(candidates) - len(node_ids)),
            "edges_truncated": max(0, len(all_edge_ids) - len(edges)),
        },
    }
    timeline = []
    days = sorted(bins)
    for day in days[-MAX_TIMELINE:]:
        value = bins[day]
        new = sum(earliest.get(identity) == day for identity in value["assets"])
        timeline.append(
            {
                "day": day,
                "observation_count": value["rows"],
                "asset_count": len(value["assets"]),
                "new_assets": new,
                "returning_assets": len(value["assets"]) - new,
                "entity_count": len(value["entities"]),
            }
        )
    patterns_by_type = defaultdict(list)
    latest_day = days[-1] if days else ""
    history_precedes_latest = bool(earliest and min(earliest.values()) < latest_day)
    for value in hubs.values():
        if (
            value.kind in {"cve", "finding"}
            and history_precedes_latest
            and first_identifier_day.get(value.id) == latest_day
        ):
            patterns_by_type["first_seen_finding"].append(value)
        if value.kind not in {"ip", "cve", "service", "version"} or len(value.assets) < 2:
            continue
        if value.kind != "ip" and len(value.entities) < 2:
            continue
        patterns_by_type["shared_" + value.kind].append(value)
    for value in assets.values():
        if len(value.days) >= 2:
            patterns_by_type["recurrent_asset"].append(value)
    for bucket in patterns_by_type.values():
        bucket.sort(
            key=lambda value: (
                -value.temperature_rank,
                not value.risk_changed,
                -len(value.entities),
                -len(value.days),
                -value.count,
                value.id,
            )
        )
    patterns = []
    for index in range(MAX_PATTERNS):
        for kind in sorted(patterns_by_type):
            if index >= len(patterns_by_type[kind]) or len(patterns) >= MAX_PATTERNS:
                continue
            value = patterns_by_type[kind][index]
            if kind == "recurrent_asset":
                title = "Observed on multiple days · "
                basis = "This canonical asset has observations on distinct reported scan dates; endpoint or service details may differ. Gaps do not establish remediation or continuous exposure."
            elif kind == "first_seen_finding":
                title = "First observed on latest selected date · "
                basis = "This finding first appears on the latest selected scan date in the indexed local sources. This is not a verified onset date."
            else:
                title = (
                    "Shared reported "
                    + {"cve": "CVE", "ip": "IP", "service": "service", "version": "version"}[
                        value.kind
                    ]
                    + " · "
                )
                basis = "The same reported identifier appears on multiple observed endpoints; shared infrastructure is not an ownership conclusion."
            # Only chosen cards materialize bounded provenance DTOs. Large
            # collections of recurrent assets remain compact Support objects.
            patterns.append(
                value.public()
                | {
                    "node_id": value.id,
                    "id": stable_id("pattern", (kind, value.id)),
                    "type": kind,
                    "title": title + _label(value.label),
                    "basis": basis,
                }
            )
    mapped = sum(_placed(row) for row in selected)
    dated = sum(bool(_day(row.get("observed_day"))) for row in selected)
    warnings = list(snapshot.get("warnings") or [])
    if omitted:
        warnings.append(
            f"Indexed {MAX_ROWS:,} observations by stable source ID; {omitted:,} observations are outside this bounded projection."
        )
    if truncated_identifiers or omitted_identifiers:
        warnings.append(
            "Some identifier fields exceed the bounded relationship index; complete original fields remain in observation details."
        )
    if len(days) > MAX_TIMELINE:
        warnings.append(
            f"Timeline displays the latest {MAX_TIMELINE} observed days; aggregate counts include the full selected period."
        )
    result = {
        "schema_version": 1,
        "filters": filters,
        "semantics": SEMANTICS,
        "counts": {
            "total_rows": len(original),
            "selected_rows": len(selected),
            "dated_rows": dated,
            "undated_rows": len(selected) - dated,
            "mapped_rows": mapped,
            "unplaced_rows": len(selected) - mapped,
            "entities": len({r["entity_id"] for r in selected if r.get("entity_id")}),
            "assets": len(assets),
            "observations": len(selected),
            "findings": len(
                {finding for row in selected for finding in row.get("finding_ids", [])}
            ),
            "admitted_observations": sum(row.get("admitted") is True for row in selected),
            "dark_matter_observations": sum(row.get("dark_matter") is True for row in selected),
        },
        "graph": graph,
        "timeline": timeline,
        "patterns": patterns,
        "coverage": {
            "complete": bool(snapshot.get("coverage_complete", True))
            and not (omitted or truncated_identifiers or omitted_identifiers),
            "warnings": warnings,
            "indexed_rows": len(indexed),
            "omitted_rows": omitted,
            "identifier_limited_rows": truncated_identifiers,
            "omitted_identifier_occurrences": omitted_identifiers,
            "timeline_omitted_days": max(0, len(days) - MAX_TIMELINE),
        },
    }
    if include_selection:
        result["_selected"] = selected
    return result
