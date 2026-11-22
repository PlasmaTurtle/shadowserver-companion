"""One revision-scoped Observatory read model, with bounded presentation payloads.

Canonical events are cached once per committed workspace/reference revision.
Filtering and exact counts precede presentation limits. Rich provenance remains
behind the observation detail endpoint; imports and notification evidence are
never modified by this read path.
"""

from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from .observatory_intelligence import (
    project,
    MAX_TIMELINE,
    stable_id,
    location_key,
    product_names,
    validate_query,
)

SAMPLE_LIMIT = 200
ATLAS_LIMIT = 1800
PULSE_LIMIT = 12
FACET_LIMIT = 100


def _revision(eclipse):
    reference = Path(str(eclipse.store.root) + "-reference") / "nvd"
    from .analytical_index import revision

    with eclipse.store.read_snapshot() as db:
        analytical_revision = revision(db)
        jurisdiction = eclipse._jurisdiction(db)
    paths = [reference / "catalog.sqlite3", reference / "risk.sqlite3"]
    parts = [("jurisdiction", jurisdiction), ("dark_matter", eclipse.store.dark_matter.revision())]
    if analytical_revision is None:
        paths.insert(0, eclipse.store.db)
    else:
        stat = eclipse.store.db.stat()
        parts.append(("workspace", stat.st_dev, stat.st_ino, analytical_revision))
    for path in paths:
        for filename in (path, Path(str(path) + "-wal")):
            try:
                stat = filename.stat()
                parts.append((filename.name, stat.st_ino, stat.st_size, stat.st_mtime_ns))
            except OSError:
                parts.append((filename.name, None))
    return hashlib.sha256(repr(parts).encode()).hexdigest()[:24]


def _base(eclipse):
    revision = _revision(eclipse)
    if eclipse._view_base and eclipse._view_base[0] == revision:
        return eclipse._view_base
    # Metadata and source membership use Eclipse's single SQLite read snapshot.
    # Retry once if an intake/reference commit overlaps that snapshot. If writes
    # continue, expose this pinned response rather than mixing later projections.
    for attempt in range(2):
        before = _revision(eclipse)
        snapshot = eclipse._build(events=True)[0]
        # Deduplicate the expensive catalog/risk document fragments once. The
        # analytical cache only requires risk facts, not publisher feed bodies.
        for row in [*snapshot["observations"], *snapshot["findings"]]:
            row["catalog_findings"] = [
                {
                    "id": item.get("id"),
                    "severity": item.get("severity"),
                    "score": item.get("score"),
                    "kev": item.get("kev"),
                    "modified": item.get("modified"),
                    "risk": {
                        "kev": {
                            "entry": {
                                "knownRansomwareCampaignUse": (
                                    ((item.get("risk") or {}).get("kev") or {}).get("entry") or {}
                                ).get("knownRansomwareCampaignUse"),
                                "dateAdded": (
                                    ((item.get("risk") or {}).get("kev") or {}).get("entry") or {}
                                ).get("dateAdded"),
                            }
                        }
                    },
                }
                for item in row.get("catalog_findings", [])
            ]
            row.pop("catalog_basis", None)
            row.pop("intelligence_basis", None)
        after = _revision(eclipse)
        if before == after:
            break
    revision = (
        after if before == after else hashlib.sha256((before + after).encode()).hexdigest()[:24]
    )
    snapshot["revision"] = revision
    snapshot["_dimension_cache"] = {}
    eclipse._view_base = (revision, snapshot)
    eclipse._view_results.clear()
    eclipse._field_results.clear()
    return eclipse._view_base


# Keep scalar facts and a tiny source locator. Catalog full records, risk feed
# entries, condition maps and source copies do not belong in every UI mark.
_SUMMARY_KEYS = frozenset(
    """id finding_id observation_id asset_id record_kind finding_kind
ip ip_valid nonpublic_ip hostname domain tag version product protocol port asn city region country
latitude longitude location_basis observed_at observed_day first_seen last_seen changed_at fresh_at
admitted status workflow intake_disposition dark_matter intake_reason disposition_reason
observation_count reported_observation_count approved_observation_count legacy_unknown_observation_count admission_state reported_first_seen reported_last_seen approved_first_seen approved_last_seen current_entity_id recorded_entity_id sightings density_id density_count density_band admitted_density dark_matter_density legacy_unknown_density qualification_density_basis density_days
temperature entity_id entity_name case_id case_stage lead_id delivered_at detail_url source_available original_url
kev ransomware_known catalog_severity risk_changed risk_updated_at risk_change_reasons
entity_association_basis lifetime_first_seen lifetime_last_seen observation_admitted catalog_product_id current_changed_at current_risk_updated_at freshness_basis first_indexed_at""".split()
)


def compact(row):
    result = {key: value for key, value in row.items() if key in _SUMMARY_KEYS}
    result["finding_ids"] = row.get("finding_ids", [])
    source = row.get("source") or {}
    result["source"] = {
        key: source.get(key) for key in ("import_id", "workbook", "sheet", "row", "source_key")
    }
    return result


def locator(row):
    return {
        key: row.get(key)
        for key in (
            "id",
            "observation_id",
            "hostname",
            "ip",
            "observed_day",
            "observed_at",
            "entity_id",
            "tag",
            "admitted",
            "dark_matter",
            "detail_url",
            "finding_ids",
        )
    }


def _temperature(row):
    value = row.get("temperature") or ""
    if isinstance(value, dict):
        value = value.get("id") or value.get("label") or ""
    return {"blazing": 4, "hot": 3, "warm": 2, "cool": 1, "cold": 0}.get(str(value).casefold(), 0)


def _rank(row):
    return (
        -_temperature(row),
        not bool(row.get("risk_changed")),
        str(row.get("fresh_at") or row.get("observed_at") or ""),
        str(row.get("id") or ""),
    )


def _findings(selected, snapshot, *, historical=False):
    canonical = {
        row["finding_id"]: row for row in snapshot.get("findings", []) if row.get("finding_id")
    }
    support = defaultdict(list)
    for row in selected:
        for identity in row.get("finding_ids", []):
            support[identity].append(row)
    findings = []
    for identity, rows in support.items():
        original = canonical.get(identity)
        if original is None:
            continue
        # Choose a representative *inside* the selected observation period.
        # Prefer admitted support so rejected endpoints never replace approved
        # evidence; workflow/reference values remain explicitly current.
        approved = [
            row
            for row in rows
            if row.get("finding_admission_states", {}).get(
                identity, "admitted" if row.get("admitted") else "observed"
            )
            == "admitted"
        ]
        unknown = [
            row
            for row in rows
            if row.get("finding_admission_states", {}).get(identity) == "legacy_unknown"
        ]
        candidates = approved or rows
        latest = max(candidates, key=lambda row: (row.get("observed_at") or "", row["id"]))
        days = sorted({row["observed_day"] for row in rows if row.get("observed_day")})
        approved_days = sorted({row["observed_day"] for row in approved if row.get("observed_day")})
        result = {**latest}
        for key in (
            "finding_id",
            "finding_kind",
            "tag",
            "admitted",
            "status",
            "workflow",
            "dark_matter",
            "intake_disposition",
            "intake_reason",
            "disposition_reason",
            "case_id",
            "case_stage",
            "lead_id",
            "delivered_at",
            "fresh_at",
            "changed_at",
            "temperature",
            "catalog_severity",
            "catalog_findings",
            "kev",
            "ransomware_known",
            "risk_changed",
            "risk_change_reasons",
            "risk_updated_at",
        ):
            result[key] = original.get(key)
        result.update(
            id=identity,
            finding_ids=[identity],
            record_kind="finding",
            observation_id=latest["id"],
            observation_admitted=latest.get("admitted"),
            first_seen=days[0] if days else "",
            last_seen=days[-1] if days else "",
            lifetime_first_seen=original.get("first_seen"),
            lifetime_last_seen=original.get("last_seen"),
            observation_count=len(rows),
            reported_observation_count=len(rows),
            approved_observation_count=len(approved),
            legacy_unknown_observation_count=len(unknown),
            admission_state="admitted" if approved else "legacy_unknown" if unknown else "observed",
            admitted=bool(approved),
            dark_matter=not bool(approved) and not bool(unknown),
            intake_disposition="lead"
            if approved
            else "qualification_unknown"
            if unknown
            else "dark_matter",
            status=original.get("status")
            if approved
            else "qualification_unknown"
            if unknown
            else "excluded",
            reported_first_seen=days[0] if days else "",
            reported_last_seen=days[-1] if days else "",
            approved_first_seen=approved_days[0] if approved_days else "",
            approved_last_seen=approved_days[-1] if approved_days else "",
            sightings=len(days),
            detail_url="/api/eclipse/observations/" + latest["id"] + "?finding_id=" + identity,
        )
        result.update((latest.get("finding_approved_fields") or {}).get(identity, {}))
        if original.get("observation_id") == latest["id"]:
            result["source"] = original.get("source", latest.get("source"))
            result["source_available"] = original.get(
                "source_available", latest.get("source_available")
            )
            result["original_url"] = original.get("original_url", latest.get("original_url"))
        result["current_changed_at"] = original.get("changed_at")
        result["current_risk_updated_at"] = original.get("risk_updated_at")
        if historical:
            # We cannot reconstruct an old local risk/workflow assessment from
            # a current catalog. Historical ordering uses observation chronology,
            # never an endpoint change acquired after the selected cutoff.
            result["fresh_at"] = days[0] if days else ""
            result["changed_at"] = None
            result["freshness_basis"] = (
                "First observation inside the selected historical scope; current assessment is separate."
            )
        else:
            result["freshness_basis"] = "Current canonical material-change acquisition time."
        findings.append(result)
    # Stable sorting: priority, material risk change, freshness, identifier.
    findings.sort(key=lambda row: (row.get("fresh_at") or "", row["id"]), reverse=True)
    findings.sort(key=lambda row: (-_temperature(row), not bool(row.get("risk_changed"))))
    return findings


def _summary(rows, *, identity, label, scope):
    days = sorted({row["observed_day"] for row in rows if row.get("observed_day")})
    latest = max(rows, key=lambda row: (row.get("observed_at") or "", row["id"]))
    top = max((row for row in rows if row.get("admitted")), key=_temperature, default={})
    finding_ids = {fid for row in rows for fid in row.get("finding_ids", [])}
    return {
        "id": identity,
        "label": label,
        "scope": scope,
        "summary": True,
        "finding_count": len(finding_ids),
        "observation_count": len(rows),
        "density_count": len(rows),
        "admitted_density": sum(bool(row.get("admitted")) for row in rows),
        "dark_matter_density": sum(bool(row.get("dark_matter")) for row in rows),
        "legacy_unknown_density": sum(
            bool(row.get("legacy_unknown_observation_count")) for row in rows
        ),
        "qualification_density_basis": "Observations with incomplete qualification provenance overlap physical admission counts; do not add these categories.",
        "entity_count": len({row["entity_id"] for row in rows if row.get("entity_id")}),
        "asset_count": len({row["asset_id"] for row in rows if row.get("asset_id")}),
        "day_count": len(days),
        "observed_days": days,
        "first_seen": days[0] if days else "",
        "last_seen": days[-1] if days else "",
        "temperature": top.get("temperature"),
        "risk_changed": any(row.get("risk_changed") for row in rows),
        "fresh_at": max((row.get("fresh_at") or "" for row in rows), default=""),
        "admitted": any(row.get("admitted") for row in rows),
        "dark_matter": all(row.get("dark_matter") for row in rows),
        "observation_ids": [row["id"] for row in rows[-5:]],
        "rows": [locator(rows[-1])],
        "latest": latest,
    }


def _entity_map_location(entity, latest, location_resolver):
    """Prefer a complete saved city/state; otherwise use the newest report's city/state."""
    location = entity.get("map_location") or {}
    if str(location.get("city") or "").strip() and str(location.get("region") or "").strip():
        return location
    city, region, country = (latest.get(key) or "" for key in ("city", "region", "country"))
    latitude, longitude, basis, _, source_url = (
        location_resolver({"city": city, "region": region, "country": country})
        if location_resolver
        else (None, None, "unplaced", "", "")
    )
    placed = basis == "city_area"
    source = latest.get("source") or {}
    return {
        "city": city,
        "region": region,
        "country": country,
        "latitude": latitude,
        "longitude": longitude,
        "location_basis": "reported_asset_city_area" if placed else "unplaced",
        "approximate": placed,
        "location_source": "City/state in the latest selected associated hostname/IP report",
        "location_source_url": source_url,
        "location_temporal_basis": "latest_selected_report",
        "location_hostname": latest.get("hostname") or "",
        "location_ip": latest.get("ip") or "",
        "location_observed_at": latest.get("observed_at") or "",
        "location_observed_day": latest.get("observed_day") or "",
        "location_observation_id": latest["id"],
        "location_source_locator": {
            **locator(latest),
            "source": {
                key: source.get(key)
                for key in ("import_id", "workbook", "sheet", "row", "sha256", "source_key")
            },
        },
        "unplaced_reason": ""
        if placed
        else (
            "No complete saved entity city/state, and the latest selected hostname/IP report "
            "has no unambiguous supported city-area match."
        ),
    }


def _entity_atlas(selected, entities, findings=None, *, location_resolver=None):
    """One city-area marker per selected entity, retaining explicit location provenance."""
    grouped, unresolved = defaultdict(list), set()
    for row in selected:
        identity = row.get("entity_id")
        if identity in entities:
            grouped[identity].append(row)
        else:
            unresolved.add(row.get("asset_id") or row["id"])
    finding_rows = {row["id"]: row for row in findings or []}
    placed, unplaced = [], []
    for identity, rows in grouped.items():
        entity = entities[identity]
        summary = _summary(
            rows,
            identity="entity-location:" + identity,
            label=entity.get("name") or entity.get("domain") or identity,
            scope={"entity_id": identity},
        )
        latest = summary.pop("latest")
        location = _entity_map_location(entity, latest, location_resolver)
        latest_by_finding = {}
        for row in rows:
            for finding_id in row.get("finding_ids", []):
                previous = latest_by_finding.get(finding_id)
                if previous is None or (row.get("observed_at") or "", row["id"]) > (
                    previous.get("observed_at") or "",
                    previous["id"],
                ):
                    latest_by_finding[finding_id] = row
        # These are unique findings and cases, not repeated scan observations.
        statuses = Counter()
        for finding_id, latest_finding_row in latest_by_finding.items():
            finding = finding_rows.get(finding_id, latest_finding_row)
            statuses[finding.get("status") or "unknown"] += 1
        cases = {}
        for row in sorted(rows, key=lambda row: (row.get("observed_at") or "", row["id"])):
            if row.get("case_id"):
                cases[row["case_id"]] = row.get("case_stage") or "unknown"
        locations = {
            location_key(row)
            for row in rows
            if row.get("latitude") is not None and row.get("longitude") is not None
        }
        summary.update(
            type="entity-location",
            entity_id=identity,
            entity_ids=[identity],
            entity_name=summary["label"],
            entity_count=1,
            domain=entity.get("domain", ""),
            case_ids=sorted(cases),
            workflow_summary={
                "findings_by_status": dict(sorted(statuses.items())),
                "cases_by_stage": dict(sorted(Counter(cases.values()).items())),
                "case_count": len(cases),
            },
            location_count=len(locations),
            reported_location_count=len(locations),
            rows=[locator(latest)],
            observation_ids=[latest["id"]],
            latitude=location.get("latitude"),
            longitude=location.get("longitude"),
            city=location.get("city", ""),
            region=location.get("region", ""),
            country=location.get("country", ""),
            location_basis=location.get("location_basis", "unplaced"),
            approximate=bool(location.get("approximate")),
            location_source=location.get(
                "location_source", "Current saved entity profile city/state"
            ),
            location_source_url=location.get("location_source_url", ""),
            location_temporal_basis=location.get(
                "location_temporal_basis", "current_saved_profile"
            ),
            unplaced_reason=location.get(
                "unplaced_reason", "Save an entity city and state to place this entity."
            ),
            basis="Current saved entity profile city/state, shown as an approximate city area. "
            "This is not a verified street address. Date filters apply to supporting evidence; "
            "the saved entity location is current.",
        )
        if location.get("location_temporal_basis") == "latest_selected_report":
            summary.update(
                {key: value for key, value in location.items() if key.startswith("location_")}
            )
            summary["basis"] = (
                "City/state from the latest selected associated hostname/IP report, shown as an "
                "approximate city area because the saved entity city/state is incomplete. "
                "This reported network location is not a verified business address."
            )
        if summary["latitude"] is None or summary["longitude"] is None:
            summary["basis"] = summary["unplaced_reason"]
            unplaced.append(summary)
        else:
            placed.append(summary)

    def order(row):
        return (
            -_temperature(row),
            not row.get("risk_changed"),
            -row["finding_count"],
            row["id"],
        )

    placed.sort(key=order)
    unplaced.sort(key=order)
    return {
        "unit": "entities",
        "nodes": placed[:ATLAS_LIMIT],
        "unplaced_entities_list": unplaced[:ATLAS_LIMIT],
        "total_entities": len(grouped),
        "mapped_entities": len(placed),
        "unplaced_entities": len(unplaced),
        "unplaced_count": len(unplaced),
        "unresolved_asset_count": len(unresolved),
        "total_nodes": len(placed),
        "omitted_nodes": max(0, len(placed) - ATLAS_LIMIT),
        "omitted_unplaced_entities": max(0, len(unplaced) - ATLAS_LIMIT),
        "location_temporal_basis": "current_saved_profile_or_latest_selected_report",
    }


def _aggregates(selected, entity_names, *, entities=None, findings=None, location_resolver=None):
    assets, products, locations, organizations = (
        defaultdict(list),
        defaultdict(list),
        defaultdict(list),
        defaultdict(list),
    )
    for row in selected:
        assets[row.get("asset_id") or row["id"]].append(row)
        for name in product_names(row):
            products[name.casefold()].append(row)
        locations[location_key(row)].append(row)
        if row.get("entity_id"):
            organizations[row["entity_id"]].append(row)
    lanes = []
    for identity, rows in assets.items():
        latest = max(rows, key=lambda row: (row.get("observed_at") or "", row["id"]))
        label = latest.get("hostname") or latest.get("ip") or "Unresolved asset"
        summary = _summary(
            rows,
            identity=stable_id("asset", (identity,)),
            label=label,
            scope={"asset_id": identity},
        )
        summary.pop("latest")
        summary.update(
            asset_id=identity,
            entity_id=latest.get("entity_id"),
            entity_name=latest.get("entity_name"),
            type="asset",
            latitude=latest.get("latitude"),
            longitude=latest.get("longitude"),
            location_basis=latest.get("location_basis"),
            city=latest.get("city"),
            region=latest.get("region"),
            country=latest.get("country"),
            location_scope={"location_key": location_key(latest)},
        )
        lane = {
            key: value
            for key, value in summary.items()
            if key not in {"rows", "day_keys", "observed_days"}
        }
        lane["_asset_rows"] = rows
        lanes.append(lane)

    def ordered(items):
        return sorted(
            items,
            key=lambda item: (
                -_temperature(item),
                not item.get("risk_changed"),
                -(item.get("finding_count") or 0),
                item["id"],
            ),
        )

    lanes = ordered(lanes)
    for lane in lanes[:PULSE_LIMIT]:
        bins = defaultdict(list)
        for row in lane["_asset_rows"]:
            if row.get("observed_day"):
                bins[row["observed_day"]].append(row)
        lane["bins"] = [
            {
                "day": day,
                "observation_count": len(items),
                "finding_count": len({fid for row in items for fid in row.get("finding_ids", [])}),
                "observation_ids": [row["id"] for row in items[:3]],
                "rows": [locator(row) for row in items[:1]],
            }
            for day, items in sorted(bins.items())
        ]
    for lane in lanes:
        lane.pop("_asset_rows")
    product_rows = []
    for key, rows in products.items():
        name = next(name for name in product_names(rows[0]) if name.casefold() == key)
        entry = _summary(
            rows, identity=stable_id("product", key), label=name, scope={"product_name": name}
        )
        entry.pop("latest")
        entry["versions"] = sorted(
            {str(row.get("version") or "") for row in rows if row.get("version")}
        )[:30]
        product_rows.append(entry)
    location_rows = []
    for identity, rows in locations.items():
        sample = rows[0]
        label = (
            ", ".join(str(sample.get(key) or "") for key in ("city", "region") if sample.get(key))
            or "Unplaced"
        )
        if label == "Unplaced" and sample.get("latitude") is not None:
            label = f"{sample['latitude']:.3f}, {sample['longitude']:.3f}"
        entry = _summary(rows, identity=identity, label=label, scope={"location_key": identity})
        entry.pop("latest")
        entry.update(
            {
                key: sample.get(key)
                for key in ("city", "region", "country", "latitude", "longitude", "location_basis")
            }
        )
        location_rows.append(entry)
    organization_rows = []
    for identity, rows in organizations.items():
        entry = _summary(
            rows,
            identity=identity,
            label=entity_names.get(identity) or rows[0].get("entity_name") or rows[0].get("domain"),
            scope={"entity_id": identity},
        )
        entry.pop("latest")
        entry.update(
            entity_id=identity,
            domain=rows[0].get("domain"),
            case_ids=sorted({row["case_id"] for row in rows if row.get("case_id")}),
            lead_ids=sorted({row["lead_id"] for row in rows if row.get("lead_id")}),
        )
        organization_rows.append(entry)
    return {
        "atlas": _entity_atlas(
            selected,
            entities
            if entities is not None
            else {
                identity: {"id": identity, "name": name} for identity, name in entity_names.items()
            },
            findings,
            location_resolver=location_resolver,
        ),
        "pulse": {
            "lanes": lanes[:PULSE_LIMIT],
            "undated": sum(not row.get("observed_day") for row in selected),
            "total_lanes": len(lanes),
            "omitted_lanes": max(0, len(lanes) - PULSE_LIMIT),
        },
        "products": ordered(product_rows)[:FACET_LIMIT],
        "product_total": len(product_rows),
        "locations": ordered(location_rows)[:FACET_LIMIT],
        "location_total": len(location_rows),
        "organizations": ordered(organization_rows)[:FACET_LIMIT],
        "organization_total": len(organization_rows),
    }


def _response(cached, finding_records, limit, offset, records_only):
    items = deepcopy(finding_records[offset : offset + limit])
    records = {
        "items": items,
        "total": len(finding_records),
        "limit": limit,
        "offset": offset,
        "kind": cached["records"].get("kind", "findings"),
    }
    if records_only:
        return {
            "revision": cached["revision"],
            "filters": deepcopy(cached["filters"]),
            "records": records,
            "counts": deepcopy(cached["snapshot"]["counts"]),
        }
    result = deepcopy(cached)
    result["records"] = records
    result["snapshot"]["findings"] = [
        item for item in items if item.get("record_kind") == "finding"
    ]
    return result


def _field_view(
    eclipse,
    revision,
    base,
    filters,
    *,
    field_limit,
    field_offset,
    field_asset_limit,
    field_asset_offset,
):
    from .observatory_field import build_index, page

    key = json.dumps(filters, sort_keys=True)
    index = eclipse._field_results.get(key)
    if index is None:
        snapshot = base
        if filters.get("product_id"):
            from modules.library.components.catalog_outreach import decorate_product_selection

            snapshot = {
                **base,
                "observations": [dict(row) for row in base["observations"]],
                "findings": [dict(row) for row in base["findings"]],
            }
            decorate_product_selection(eclipse.store.root, snapshot, filters["product_id"])
        selection = project(snapshot, selection_only=True, **filters)
        index = build_index(snapshot, selection, historical=bool(filters.get("date_to")))
        index["catalog_selection"] = snapshot.get("catalog_selection")
        index["entity_names"] = {item["id"]: item["name"] for item in base["entities"]}
        index["networks"] = sorted(
            {str(row.get("asn")) for row in base["observations"] if row.get("asn")}
        )
        if filters.get("date_to"):
            timeline = project(snapshot, selection_only=True, **{**filters, "date_to": ""})
            bins = defaultdict(int)
            for row in timeline["_selected"]:
                if row.get("observed_day"):
                    bins[row["observed_day"]] += 1
            index["full_timeline"] = [
                {"day": day, "count": count, "observation_count": count}
                for day, count in sorted(bins.items())[-MAX_TIMELINE:]
            ]
            index["timeline_undated"] = timeline["counts"]["undated_rows"]
        else:
            index["full_timeline"] = index["timeline"]
            index["timeline_undated"] = selection["counts"]["undated_rows"]
        if len(eclipse._field_results) >= 6:
            eclipse._field_results.pop(next(iter(eclipse._field_results)))
        eclipse._field_results[key] = index
    result = page(
        index,
        revision,
        offset=field_offset,
        limit=field_limit,
        asset_offset=field_asset_offset,
        asset_limit=field_asset_limit,
        compact=compact,
        entity_names=index["entity_names"],
    )
    selection = index["selection"]
    dark_records = filters.get("intake") == "dark_matter" or filters.get("status") == "excluded"
    records = {
        "items": [],
        "total": result["counts"]["observations" if dark_records else "findings"],
        "limit": 0,
        "offset": 0,
        "kind": "observations" if dark_records else "findings",
    }
    return {
        "schema_version": 1,
        "revision": revision,
        "filters": deepcopy(selection["filters"]),
        "snapshot": {
            "schema_version": 4,
            "revision": revision,
            "generated_at": base["generated_at"],
            "observations": result["observations"],
            "findings": [],
            "entities": deepcopy(base["entities"]),
            "networks": index["networks"],
            "counts": result["counts"],
            "warnings": deepcopy(selection["coverage"]["warnings"]),
            "coverage_complete": selection["coverage"]["complete"],
            "sampled": len(result["observations"]) < result["counts"]["observations"],
            "sample_count": len(result["observations"]),
            "timeline": {
                "bins": deepcopy(index["full_timeline"]),
                "undated": index["timeline_undated"],
            },
            "catalog_selection": index["catalog_selection"],
            "handling": base["handling"],
            "jurisdiction": deepcopy(base["jurisdiction"]),
            "status_basis": base["status_basis"],
            "density_basis": base["density_basis"],
        },
        "intelligence": {
            "revision": revision,
            "filters": deepcopy(selection["filters"]),
            "counts": result["counts"],
            "graph": result["graph"],
            "field": result["field"],
            "semantics": deepcopy(selection["semantics"]),
            "coverage": deepcopy(selection["coverage"]),
            "timeline": deepcopy(index["timeline"]),
            "patterns": [],
        },
        "records": records,
    }


def view(
    eclipse,
    *,
    limit=20,
    offset=0,
    records_only=False,
    field_only=False,
    field_limit=24,
    field_offset=0,
    field_revision="",
    field_asset_limit=120,
    field_asset_offset=0,
    **filters,
):
    if not 1 <= limit <= 100 or not 0 <= offset <= 10000000:
        raise ValueError("Invalid Observatory page")
    validate_query(**filters)
    if not (
        1 <= field_limit <= 60
        and 0 <= field_offset <= 10000000
        and 1 <= field_asset_limit <= 240
        and 0 <= field_asset_offset <= 10000000
    ):
        raise ValueError("Invalid FIELD page")
    with eclipse._view_lock:
        if field_only and field_revision and field_revision != _revision(eclipse):
            from .observatory_field import FieldRevisionChanged

            raise FieldRevisionChanged(
                "The field changed; reload its first page before continuing."
            )
        revision, base = _base(eclipse)
        if field_only:
            if field_revision and revision != field_revision:
                from .observatory_field import FieldRevisionChanged

                raise FieldRevisionChanged(
                    "The field changed; reload its first page before continuing."
                )
            return _field_view(
                eclipse,
                revision,
                base,
                filters,
                field_limit=field_limit,
                field_offset=field_offset,
                field_asset_limit=field_asset_limit,
                field_asset_offset=field_asset_offset,
            )
        cache_key = json.dumps(filters, sort_keys=True)
        if cache_key in eclipse._view_results:
            cached, finding_records = eclipse._view_results[cache_key]
            return _response(cached, finding_records, limit, offset, records_only)
        snapshot = base
        if filters.get("product_id"):
            from modules.library.components.catalog_outreach import decorate_product_selection

            snapshot = {
                **base,
                "observations": [dict(row) for row in base["observations"]],
                "findings": [dict(row) for row in base["findings"]],
            }
            decorate_product_selection(eclipse.store.root, snapshot, filters["product_id"])
        intelligence = project(snapshot, include_selection=True, **filters)
        selected = intelligence.pop("_selected")
        if filters.get("date_to"):
            before_cutoff = project(snapshot, include_selection=False, **{**filters, "date_to": ""})
            full_timeline = before_cutoff["timeline"]
            timeline_undated = before_cutoff["counts"]["undated_rows"]
        else:
            full_timeline = intelligence["timeline"]
            timeline_undated = intelligence["counts"]["undated_rows"]
        findings = _findings(selected, snapshot, historical=bool(filters.get("date_to")))
        dark_records = filters.get("intake") == "dark_matter" or filters.get("status") == "excluded"
        record_rows = findings
        if dark_records:
            # Unadmitted events need not contain a recognized condition, and a
            # dark endpoint can support a previously approved finding. Both
            # remain inspectable without manufacturing another finding.
            record_rows = [
                {
                    **row,
                    "record_kind": "observation",
                    "observation_id": row["id"],
                    "detail_url": "/api/eclipse/observations/" + row["id"],
                }
                for row in selected
                if row.get("admitted") is not True
            ]
            record_rows.sort(
                key=lambda row: (row.get("observed_at") or "", row["id"]), reverse=True
            )
            for row in record_rows:
                if row.get("observation_admitted") and len(row.get("finding_ids", [])) == 1:
                    row["detail_url"] += "?finding_id=" + row["finding_ids"][0]
                else:
                    row["detail_url"] += "?intake=dark_matter"
        entity_names = {item["id"]: item["name"] for item in base["entities"]}
        intelligence.update(
            _aggregates(
                selected,
                entity_names,
                entities={item["id"]: item for item in base["entities"]},
                findings=findings,
                location_resolver=eclipse._location,
            )
        )
        for node in intelligence["graph"]["nodes"]:
            node["organizations"] = [
                {
                    "id": identity,
                    "name": entity_names.get(identity, identity),
                    "scope": {**(node.get("scope") or {}), "entity_id": identity},
                }
                for identity in node.get("entity_ids", [])
            ]
        intelligence["revision"] = revision
        counts = dict(intelligence["counts"])
        counts.update(
            record_count=len(record_rows),
            findings=len(findings),
            dark_matter_findings=sum(row.get("dark_matter") is True for row in findings),
            legacy_unknown_findings=sum(
                row.get("admission_state") == "legacy_unknown" for row in findings
            ),
            legacy_unknown_observation_count=sum(
                bool(row.get("legacy_unknown_observation_count")) for row in selected
            ),
            qualification_density_basis="Observations with incomplete qualification provenance overlap physical admission counts; do not add these categories.",
            rows=len(selected),
            qualified_rows=sum(row.get("admitted") is True for row in selected),
            delivered_rows=sum(row.get("status") == "delivered" for row in selected),
            lead_rows=sum(row.get("admitted") is True for row in selected),
            dark_matter_rows=sum(row.get("dark_matter") is True for row in selected),
            observation_days=len(
                {row["observed_day"] for row in selected if row.get("observed_day")}
            ),
            distinct_ips=len({row["ip"] for row in selected if row.get("ip_valid")}),
            review_rows=0,
            unclassified_rows=0,
        )
        for alias, key in (
            ("finding_count", "findings"),
            ("entity_count", "entities"),
            ("asset_count", "assets"),
            ("observation_count", "observations"),
            ("dark_matter_count", "dark_matter_findings"),
            ("unplaced_count", "unplaced_rows"),
        ):
            counts[alias] = counts[key]
        intelligence["counts"] = counts
        samples = sorted(
            selected, key=lambda row: (row.get("observed_at") or "", row["id"]), reverse=True
        )[:SAMPLE_LIMIT]
        records = {
            "items": [compact(row) for row in record_rows[offset : offset + limit]],
            "total": len(record_rows),
            "limit": limit,
            "offset": offset,
            "kind": "observations" if dark_records else "findings",
        }
        result = {
            "schema_version": 1,
            "revision": revision,
            "filters": intelligence["filters"],
            "snapshot": {
                "schema_version": 4,
                "revision": revision,
                "generated_at": base["generated_at"],
                "observations": [compact(row) for row in samples],
                "findings": [
                    row for row in records["items"] if row.get("record_kind") == "finding"
                ],
                "entities": base["entities"],
                "networks": sorted(
                    {str(row.get("asn")) for row in base["observations"] if row.get("asn")}
                ),
                "counts": counts,
                "warnings": intelligence["coverage"]["warnings"],
                "coverage_complete": intelligence["coverage"]["complete"],
                "sampled": len(samples) < len(selected),
                "sample_count": len(samples),
                "timeline": {
                    "bins": [
                        {**item, "count": item["observation_count"]} for item in full_timeline
                    ],
                    "undated": timeline_undated,
                },
                "catalog_selection": snapshot.get("catalog_selection"),
                "handling": base["handling"],
                "jurisdiction": base["jurisdiction"],
                "status_basis": base["status_basis"],
                "density_basis": base["density_basis"],
            },
            "intelligence": intelligence,
            "records": records,
        }
        if len(eclipse._view_results) >= 12:
            eclipse._view_results.pop(next(iter(eclipse._view_results)))
        eclipse._view_results[cache_key] = (result, [compact(row) for row in record_rows])
        return _response(result, eclipse._view_results[cache_key][1], limit, offset, records_only)
