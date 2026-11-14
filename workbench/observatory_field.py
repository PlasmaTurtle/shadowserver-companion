"""Revision-pinned FIELD objects and bounded, progressively loaded constellations.

The index counts canonical findings and observations once per filtered revision.
Only requested bodies and their visible satellites become public graph records.
History controls density; meaningful changes and observation dates control order.
"""

from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone

from .observatory_intelligence import MAX_TIMELINE, Support, _condition_support, stable_id

OVERVIEW_ASSETS_PER_OBJECT = 6
MAX_PAGE_ASSETS = 240
DARK_REASON_LIMIT = 8


class FieldRevisionChanged(ValueError):
    pass


def _dark_history(rows):
    """Count actual excluded source events once, independent of outreach state."""
    from .dark_matter import REASONS

    dark = {
        row["id"]: row
        for row in rows
        if row.get("admitted") is not True
        and (row.get("admitted") is False or row.get("dark_matter") is True)
    }
    counts = Counter(
        str(row.get("intake_reason") or "").strip() or "Not admitted" for row in dark.values()
    )
    reasons = [
        {
            "reason": reason,
            "label": REASONS.get(reason, reason.replace("_", " ").capitalize()),
            "count": count,
        }
        for reason, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    omitted = max(0, len(reasons) - DARK_REASON_LIMIT)
    if omitted:
        tail = reasons[DARK_REASON_LIMIT - 1 :]
        reasons = [
            *reasons[: DARK_REASON_LIMIT - 1],
            {
                "reason": "other",
                "label": "Other recorded reasons",
                "count": sum(item["count"] for item in tail),
            },
        ]
        omitted = len(tail)
    dates = [
        row.get("observed_at")
        for row in dark.values()
        if _stamp(row.get("observed_at")) != float("-inf")
    ]
    return {
        "dark_matter_reasons": reasons,
        "dark_matter_reason_groups": len(counts),
        "dark_matter_reasons_omitted": omitted,
        "dark_matter_counted_observations": len(dark),
        "dark_matter_first_seen": min(dates, key=_stamp, default=""),
        "dark_matter_last_seen": max(dates, key=_stamp, default=""),
        "dark_matter_undated_observations": len(dark) - len(dates),
    }


def _stamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).timestamp()
    except TypeError, ValueError, OverflowError:
        return float("-inf")


def _dark_discovery_key(row):
    port = str(row.get("port") or "").strip()
    if port.isascii() and port.isdigit() and len(port) < 8:
        port = str(int(port))
    return (
        row.get("asset_id") or row["id"],
        str(row.get("reported_tag") or row.get("tag") or "").strip().casefold(),
        str(row.get("protocol") or "").strip().casefold(),
        port,
        str(row.get("product") or "").strip().casefold(),
    )


def _dark_discoveries(rows):
    """First local acquisition of each unresolved asset/condition/service.

    Build from retained base history, before filtering. A repeat observation's
    later import is not another discovery, even inside a narrowed date window.
    """
    first = {}
    for row in rows:
        if row.get("finding_ids"):
            continue
        key = _dark_discovery_key(row)
        stamp = next(
            (
                value
                for value in (row.get("first_indexed_at"), row.get("imported_at"))
                if _stamp(value) != float("-inf")
            ),
            "",
        )
        if _stamp(stamp) != float("-inf") and (
            key not in first or _stamp(stamp) < _stamp(first[key])
        ):
            first[key] = stamp
    return first


def _recency(rows, canonical, *, historical, dark_discoveries=None):
    """Keep per-condition change dates separate from co-observed conditions."""
    local_dates, indexed_dates, risk_dates, kev_dates = [], [], [], []
    has_findings = False
    for row in rows:
        findings = [canonical[fid] for fid in row.get("finding_ids", []) if fid in canonical]
        has_findings = has_findings or bool(findings)
        if not findings:
            discovery = (dark_discoveries or {}).get(_dark_discovery_key(row), "")
            local_dates.append(discovery)
            if discovery:
                indexed_dates.append(discovery)
        for item in findings:
            local_dates.append(item.get("changed_at") or item.get("fresh_at") or "")
            if item.get("first_indexed_at"):
                indexed_dates.append(item["first_indexed_at"])
            if item.get("risk_changed"):
                risk_dates.append(item.get("risk_updated_at") or "")
            for finding in item.get("catalog_findings", []):
                added = (((finding.get("risk") or {}).get("kev") or {}).get("entry") or {}).get(
                    "dateAdded"
                )
                if added:
                    kev_dates.append(added)
    local = max(local_dates, key=_stamp, default="")
    risk = max(risk_dates, key=_stamp, default="")
    fresh = max((local, risk), key=_stamp)
    basis = (
        "Latest saved vulnerability or KEV change"
        if _stamp(risk) > _stamp(local)
        else "Latest local finding change"
    )
    if not has_findings:
        basis = (
            "Latest first local discovery among retained assets, conditions and services"
            if _stamp(fresh) != float("-inf")
            else "Local discovery date unavailable; ordered by last reported observation"
        )
    elif _stamp(fresh) == float("-inf"):
        basis = "Local finding change date unavailable; ordered by last reported observation"
    if historical:
        fresh = max((row.get("observed_at") or "" for row in rows), key=_stamp, default="")
        basis = "Latest reported observation within the selected historical period"
    return {
        "fresh_at": fresh,
        "recency_basis": basis,
        "first_indexed_at": min(indexed_dates, key=_stamp, default=""),
        "latest_indexed_at": max(indexed_dates, key=_stamp, default=""),
        "local_changed_at": local,
        "risk_updated_at": risk,
        "kev_added_at": max(kev_dates, key=_stamp, default=""),
    }


def build_index(snapshot, selection, *, historical=False):
    selected = selection["_selected"]
    canonical = {row["finding_id"]: row for row in snapshot["findings"] if row.get("finding_id")}
    dark_discoveries = snapshot.get("_dark_discovery_cache")
    if dark_discoveries is None:
        dark_discoveries = _dark_discoveries(snapshot["observations"])
        snapshot["_dark_discovery_cache"] = dark_discoveries
    kinds = (
        {"entity"}
        if selection["filters"]["lens"] == "organization"
        else {"cve", "finding"}
        if selection["filters"]["lens"] == "vulnerability"
        else {selection["filters"]["lens"]}
    )
    assets, objects, rows_by_asset, object_rows = {}, {}, defaultdict(list), defaultdict(list)
    links_by_asset = defaultdict(set)
    edge_stats = {}
    metadata = selection.pop("_metadata")
    timeline = defaultdict(lambda: {"observations": 0, "assets": set(), "entities": set()})
    for row in selected:
        asset_id, asset, dimensions = metadata[row["id"]]
        if asset_id not in assets:
            assets[asset_id] = Support(*asset, identity=asset_id)
        assets[asset_id].add(row, asset_id)
        rows_by_asset[asset_id].append(row)
        allowed = set(row.get("finding_ids", []))
        for identity, kind, key, label in dimensions:
            if kind not in kinds:
                continue
            supported = _condition_support(row, kind, key)
            if kind in {"cve", "finding"}:
                supported = {
                    **supported,
                    "finding_ids": [
                        fid for fid in supported.get("finding_ids", []) if fid in allowed
                    ],
                }
                if row.get("finding_ids") and not supported["finding_ids"]:
                    continue
                # An approved condition does not approve a different endpoint.
                admitted = bool(row.get("admitted") and supported.get("admitted"))
                supported.update(admitted=admitted, dark_matter=not admitted)
            if identity not in objects:
                objects[identity] = Support(kind, key, label, identity=identity)
            objects[identity].add(supported, asset_id)
            object_rows[identity].append(supported)
            links_by_asset[asset_id].add(identity)
            pair = (asset_id, identity)
            if pair not in edge_stats:
                edge_stats[pair] = {
                    "source": asset_id,
                    "target": identity,
                    "type": "observed_with",
                    "observation_count": 0,
                    "observation_ids": [],
                    "first_seen": "",
                    "last_seen": "",
                }
            edge = edge_stats[pair]
            edge["observation_count"] += 1
            if len(edge["observation_ids"]) < 5:
                edge["observation_ids"].append(row["id"])
            day = row.get("observed_day") or ""
            if day:
                edge["first_seen"] = min(edge["first_seen"] or day, day)
                edge["last_seen"] = max(edge["last_seen"], day)
        if row.get("observed_day"):
            bucket = timeline[row["observed_day"]]
            bucket["observations"] += 1
            bucket["assets"].add(asset_id)
            if row.get("entity_id"):
                bucket["entities"].add(row["entity_id"])
    # Unresolved assets remain navigable even without a named entity/CVE hub.
    for identity, support in assets.items():
        if not links_by_asset[identity]:
            objects[identity] = support
            object_rows[identity] = rows_by_asset[identity]
    recency, dark_history = {}, {}
    for identity, rows in {**rows_by_asset, **object_rows}.items():
        dates = _recency(rows, canonical, historical=historical, dark_discoveries=dark_discoveries)
        latest = max((row.get("observed_at") or "" for row in rows), key=_stamp, default="")
        recency[identity] = {**dates, "last_seen": latest}
        dark_history[identity] = _dark_history(rows)

    def order(identity):
        item = recency[identity]
        stamp = _stamp(item["fresh_at"])
        if stamp == float("-inf"):
            stamp = _stamp(item["last_seen"])
        # Repeat scan dates must not reshuffle objects with equal local change
        # dates. They add historical density without claiming a new discovery.
        return (-stamp, identity)

    focus = selection["filters"].get("focus")
    if focus in objects:
        objects = {focus: objects[focus]}
    elif focus in assets:
        objects = {focus: assets[focus]}
    ordered = sorted(objects, key=order)
    dated_recency = [
        recency[identity]["fresh_at"]
        if _stamp(recency[identity]["fresh_at"]) != float("-inf")
        else recency[identity]["last_seen"]
        for identity in ordered
        if recency[identity]["fresh_at"] or recency[identity]["last_seen"]
    ]
    ordered_assets = {
        identity: sorted(value.assets, key=order) for identity, value in objects.items()
    }
    counts = deepcopy(selection["counts"])
    findings = {fid for row in selected for fid in row.get("finding_ids", [])}
    counts.update(
        rows=counts["observations"],
        qualified_rows=counts["admitted_observations"],
        lead_rows=counts["admitted_observations"],
        dark_matter_rows=counts["dark_matter_observations"],
        dark_matter_findings=sum(
            not canonical.get(fid, {}).get("admitted", False) for fid in findings
        ),
        delivered_rows=sum(row.get("status") == "delivered" for row in selected),
        observation_days=len(timeline),
        distinct_ips=len({row.get("ip") for row in selected if row.get("ip_valid")}),
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
    selection["coverage"]["timeline_omitted_days"] = max(0, len(timeline) - MAX_TIMELINE)
    if len(timeline) > MAX_TIMELINE:
        selection["coverage"]["warnings"].append(
            f"Timeline displays the latest {MAX_TIMELINE} observed days; aggregate counts include the full selected period."
        )
    return {
        "selection": {key: value for key, value in selection.items() if key != "_selected"},
        "objects": objects,
        "assets": assets,
        "ordered": ordered,
        "ordered_assets": ordered_assets,
        "edges": edge_stats,
        "counts": counts,
        "recency": recency,
        "dark_history": dark_history,
        "recency_range": {
            "newest": max(dated_recency, key=_stamp, default=""),
            "oldest": min(dated_recency, key=_stamp, default=""),
        },
        "canonical": canonical,
        "timeline": [
            {
                "day": day,
                "count": data["observations"],
                "observation_count": data["observations"],
                "asset_count": len(data["assets"]),
                "entity_count": len(data["entities"]),
            }
            for day, data in sorted(timeline.items())[-MAX_TIMELINE:]
        ],
        "total_edges": sum(
            len(value.assets) for value in objects.values() if value.kind != "asset"
        ),
        "total_nodes": len(set(objects) | set(assets)),
    }


def _public(index, support, *, field_object=False, loaded_assets=0):
    result = support.public()
    result.update(index["recency"][support.id])
    result.update(deepcopy(index["dark_history"][support.id]))
    approved = any(index["canonical"].get(fid, {}).get("admitted") for fid in support.findings)
    if support.kind == "asset":
        loaded_assets = 1
        # The containing entity can have other assets' dark observations.
        # An asset's own cloud must not borrow those observations or reasons.
        result.update(
            density_count=support.count,
            admitted_density=support.admitted,
            dark_matter_density=support.dark_matter,
        )
    result.update(
        field_object=field_object,
        admitted=bool(approved or support.admitted),
        dark_matter=not bool(approved or support.admitted),
        total_assets=len(support.assets),
        loaded_assets=loaded_assets,
        omitted_assets=max(0, len(support.assets) - loaded_assets),
        density_basis="Distinct matching canonical source observations for this object",
        density_band="purple"
        if result["density_count"] > 1000
        else "red"
        if result["density_count"] > 200
        else "yellow"
        if result["density_count"] > 50
        else "normal",
    )
    return result


def page(index, revision, *, offset, limit, asset_offset, asset_limit, compact, entity_names):
    selection = index["selection"]
    focus = selection["filters"].get("focus")
    identifiers = index["ordered"][offset : offset + limit]
    object_ids = set(identifiers)
    satellite_ids, object_assets = set(), {}
    focused_assets = None
    for identity in identifiers:
        support = index["objects"][identity]
        if support.kind == "asset":
            object_assets[identity] = []
            continue
        candidates = index["ordered_assets"][identity]
        if focus == identity:
            chosen = candidates[asset_offset : asset_offset + asset_limit]
            focused_assets = {
                "offset": asset_offset,
                "limit": asset_limit,
                "total_assets": len(candidates),
                "next_offset": asset_offset + len(chosen)
                if asset_offset + len(chosen) < len(candidates)
                else None,
                "has_more": asset_offset + len(chosen) < len(candidates),
            }
        else:
            chosen = candidates[:OVERVIEW_ASSETS_PER_OBJECT]
        # At most240satellites are materialized; every body exposes omissions.
        selected = []
        for asset_id in chosen:
            if asset_id in satellite_ids or len(satellite_ids) < MAX_PAGE_ASSETS:
                satellite_ids.add(asset_id)
                selected.append(asset_id)
        object_assets[identity] = selected
    nodes = []
    for rank, identity in enumerate(identifiers, offset + 1):
        node = _public(
            index,
            index["objects"][identity],
            field_object=True,
            loaded_assets=len(object_assets[identity]),
        )
        node["field_rank"] = rank
        node["organizations"] = [
            {
                "id": owner,
                "name": entity_names.get(owner, owner),
                "scope": {**node["scope"], "entity_id": owner},
            }
            for owner in node.get("entity_ids", [])
        ]
        nodes.append(node)
    for identity in sorted(satellite_ids - object_ids):
        nodes.append(_public(index, index["assets"][identity]))
    edges = []
    for target in identifiers:
        if index["objects"][target].kind == "asset":
            continue
        for source in object_assets[target]:
            edges.append(
                {
                    "id": stable_id("edge", (source, target)),
                    **deepcopy(index["edges"][(source, target)]),
                }
            )
    visible_rows = {}
    for identity in sorted(satellite_ids | (object_ids & set(index["assets"]))):
        for row in index["assets"][identity].samples.values():
            visible_rows[row["id"]] = compact(row)
    end = offset + len(identifiers)
    return {
        "counts": deepcopy(index["counts"]),
        "observations": list(visible_rows.values()),
        "graph": {
            "nodes": nodes,
            "edges": edges,
            "recency_range": deepcopy(index["recency_range"]),
            "limits": {
                "max_nodes": limit + MAX_PAGE_ASSETS,
                "max_edges": max(asset_limit, limit * OVERVIEW_ASSETS_PER_OBJECT),
                "total_nodes": index["total_nodes"],
                "total_edges": index["total_edges"],
                "nodes_truncated": max(0, index["total_nodes"] - len(nodes)),
                "edges_truncated": max(0, index["total_edges"] - len(edges)),
            },
        },
        "field": {
            "revision": revision,
            "offset": offset,
            "limit": limit,
            "total_objects": len(index["ordered"]),
            "next_offset": end if end < len(index["ordered"]) else None,
            "has_more": end < len(index["ordered"]),
            "counts_exact": True,
            "objects_complete": selection["coverage"]["complete"],
            "object_count_basis": "Objects indexed in the selected canonical observations",
            "order": "recent_change",
            "asset_page": focused_assets,
        },
    }
