"""Rank explicitly reported references by distinct identified entities."""

from collections import defaultdict
from itertools import groupby
import json
from operator import itemgetter

from modules.accretion.components.intake.versions import version_sources
from modules.accretion.components.report_profiles import products_from_version, resolve_profile
from modules.library.components.cve_catalog.products import meaningful
from modules.library.components.intelligence.identifiers import CVE, identifiers
from .observatory_queries import observation_ownership
from .observatory_view import _revision

LABEL_LIMIT = 200  # Library search accepts reference text up to this length.


def _source_values(fields, normalized, *, report_type="", clipped=()):
    # Fields belong to the retained source, including when its case has a narrower scope.
    tag = fields.get("tag")
    if "tag" in clipped:
        # A clipped numeric suffix could otherwise manufacture a shorter CVE.
        cves = {
            item["id"].upper()
            for item in normalized.get("findings", [])
            if isinstance(item, dict)
            and item.get("source_field") == "tag"
            and isinstance(item.get("id"), str)
            and CVE.fullmatch(item["id"])
        }
    else:
        cves = set(identifiers([tag]))
    names = set()
    for key in ("product", "application", "service"):
        if key not in clipped and meaningful(fields.get(key)):
            names.add(fields[key].strip())
            break
    pairs = normalized.get("products")
    if pairs is None:
        profile = normalized.get("profile") or resolve_profile(fields, configured_type=report_type)
        pairs = []
        if profile.get("version_semantics") == "software":
            for version in version_sources(fields, profile):
                key = version["source_field"]
                if key not in clipped:
                    pairs.extend(
                        products_from_version(version["raw_version"], "", source_field=key)[
                            "products"
                        ]
                    )
    names.update(
        pair["product"].strip()
        for pair in pairs
        if isinstance(pair, dict) and meaningful(pair.get("product"))
    )
    return cves, names


def _archive_values(record):
    return _source_values(record["raw_fields"], {}, report_type=record["report_type"])


def _canonical_values(db, archive):
    # A canonical measurement may have several contributing source rows. Read
    # their original fields without case-condition or catalog overlays.
    base, owner, _ = observation_ownership(db)
    rows = db.execute(
        f"""SELECT o.id, l.id AS entity_id, coalesce(nullif(l.company,''),l.domain) AS entity_name,
                  o.summary, o.normalized, o.source_key AS primary_key,
                  s.source_key, e.payload
           {base} JOIN leads l ON l.id={owner} AND l.merged_into IS NULL
           LEFT JOIN awareness_sources s ON s.observation_id=o.id
           LEFT JOIN entries e ON e.id=s.entry_id
           ORDER BY o.id"""
    )
    for (_, entity_id, entity_name), members in groupby(
        rows, itemgetter("id", "entity_id", "entity_name")
    ):
        cves, names, partial = set(), set(), False
        for member in members:
            key = member["source_key"] or member["primary_key"]
            entry = json.loads(member["payload"]) if member["payload"] else {}
            source_fields = (entry.get("source") or {}).get("fields")
            if isinstance(source_fields, dict):
                found = _source_values(source_fields, entry.get("normalized") or {})
            elif key and key != member["primary_key"]:
                record = archive.get(key)
                if record is None:
                    partial = True
                    continue
                found = _archive_values(record)
            else:
                fields, normalized = json.loads(member["summary"]), json.loads(member["normalized"])
                info = normalized.get("awareness_projection") or {}
                clipped = set(info.get("clipped_fields") or ())
                if not info or not info.get("complete"):
                    clipped.update(
                        k for k, v in fields.items() if isinstance(v, str) and len(v) == 4096
                    )
                relevant = clipped & {
                    "tag",
                    "product",
                    "application",
                    "service",
                    "version",
                    "component_version",
                    "device_version",
                }
                record = archive.get(key) if relevant and key else None
                if record:
                    found = _archive_values(record)
                else:
                    found = _source_values(fields, normalized, clipped=clipped)
                    partial |= bool(relevant)
            cves.update(found[0])
            names.update(found[1])
        yield entity_id, entity_name, cves, names, partial


def _collect(store):
    members = {"cves": defaultdict(set), "products": defaultdict(set)}
    entities, products = {}, {}
    warnings = set()
    with store.read_snapshot() as db:
        for entity_id, entity_name, cves, names, partial in _canonical_values(
            db, store.dark_matter
        ):
            entities[entity_id] = entity_name
            if partial:
                warnings.add("Some source labels for identified entities are incomplete.")
            for kind, values in (("cves", cves), ("products", names)):
                for value in values:
                    if len(value) > LABEL_LIMIT:
                        warnings.add(
                            f"Reference labels longer than {LABEL_LIMIT} characters were omitted."
                        )
                        continue
                    if kind == "products":
                        key = value.casefold()
                        products[key] = min(products.get(key, value), value)
                    else:
                        key = value
                    members[kind][key].add(entity_id)
    rankings = {}
    for kind, values in members.items():
        rankings[kind] = [
            {
                "value": products[key] if kind == "products" else key,
                "entity_count": len(values[key]),
            }
            for key in sorted(values, key=lambda key: (-len(values[key]), key))
        ]
    return {
        "members": members,
        "entities": entities,
        "rankings": rankings,
        "warnings": sorted(warnings),
    }


def _snapshot(eclipse):
    with eclipse._view_lock:
        revision = _revision(eclipse)
        if eclipse._observed_reference_cache and eclipse._observed_reference_cache[0] == revision:
            return eclipse._observed_reference_cache
        # Exact archived source recovery and canonical ownership use separate stores.
        for _ in range(2):
            data = _collect(eclipse.store)
            after = _revision(eclipse)
            if revision == after:
                eclipse._observed_reference_cache = revision, data
                return revision, data
            revision = after
        raise ValueError("Workspace evidence changed during the read")


def _coverage(revision, data):
    return {
        "revision": revision,
        "coverage_complete": not data["warnings"],
        "warnings": list(data["warnings"]),
    }


def observed_references(eclipse, *, limit, cve_offset, product_offset):
    if not (1 <= limit <= 100 and min(cve_offset, product_offset) >= 0):
        raise ValueError("Invalid observed-reference page")
    revision, data = _snapshot(eclipse)
    result = _coverage(revision, data)
    for kind, offset in (("cves", cve_offset), ("products", product_offset)):
        rows = data["rankings"][kind]
        result[kind] = {
            "items": [row.copy() for row in rows[offset : offset + limit]],
            "total": len(rows),
            "offset": offset,
            "limit": limit,
        }
    return result


def reference_entities(eclipse, *, kind, value, limit, offset):
    if (
        kind not in ("cves", "products")
        or not 0 < len(value) <= LABEL_LIMIT
        or not 1 <= limit <= 100
        or offset < 0
    ):
        raise ValueError("Invalid entity reference page")
    revision, data = _snapshot(eclipse)
    key = value.upper() if kind == "cves" else value.casefold()
    names = data["entities"]
    matched = sorted(
        data["members"][kind].get(key, ()),
        key=lambda entity_id: (names[entity_id].casefold(), entity_id),
    )
    return {
        **_coverage(revision, data),
        "items": [
            {"id": entity_id, "name": names[entity_id]}
            for entity_id in matched[offset : offset + limit]
        ],
        "total": len(matched),
        "offset": offset,
        "limit": limit,
    }
