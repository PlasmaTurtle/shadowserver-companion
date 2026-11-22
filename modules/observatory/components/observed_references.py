"""Rank reported reference labels across canonical measurements and retained archive rows."""

from collections import Counter
from itertools import groupby
import json
from operator import itemgetter

from modules.accretion.components.intake.versions import version_sources
from modules.accretion.components.report_profiles import products_from_version, resolve_profile
from modules.library.components.cve_catalog.products import meaningful
from modules.library.components.intelligence.identifiers import CVE, identifiers
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


def _canonical_values(db, archive, represented):
    # A canonical measurement may have several contributing source rows. Read
    # their original fields without case-condition or catalog overlays.
    rows = db.execute(
        """SELECT o.id, o.summary, o.normalized, o.source_key AS primary_key,
                  s.source_key, e.payload
           FROM awareness_observations o
           LEFT JOIN awareness_sources s ON s.observation_id=o.id
           LEFT JOIN entries e ON e.id=s.entry_id
           ORDER BY o.id"""
    )
    for _, members in groupby(rows, itemgetter("id")):
        cves, names, partial = set(), set(), False
        for member in members:
            key = member["source_key"] or member["primary_key"]
            if key:
                represented.add(key)
            if member["primary_key"]:
                represented.add(member["primary_key"])
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
        yield cves, names, partial


def _collect(store, archive_limit):
    cve_counts, product_counts, labels = Counter(), Counter(), {}
    observations = with_cves = with_products = partial = overlong = 0

    def add(cves, names):
        nonlocal observations, with_cves, with_products, overlong
        observations += 1
        if any(len(value) > LABEL_LIMIT for value in cves | names):
            overlong += 1
            cves = {value for value in cves if len(value) <= LABEL_LIMIT}
            names = {value for value in names if len(value) <= LABEL_LIMIT}
        with_cves += bool(cves)
        with_products += bool(names)
        cve_counts.update(cves)
        keys = set()
        for name in names:
            key = name.casefold()
            labels[key] = min(labels.get(key, name), name)
            keys.add(key)
        product_counts.update(keys)

    represented = set()
    archive = store.dark_matter
    with store.read_snapshot() as db:
        for cves, names, incomplete in _canonical_values(db, archive, represented):
            add(cves, names)
            partial += incomplete
    scanned = 0
    for record in archive.iter_records(limit=archive_limit):
        scanned += 1
        if record["record_id"] not in represented:
            add(*_archive_values(record))

    warnings = []
    if scanned == archive_limit and archive.query(fields=[], limit=1)["total"] > scanned:
        warnings.append(
            f"Counts include the first {scanned:,} unpromoted archive records and all retained canonical observations."
        )
    if partial:
        warnings.append(
            f"Complete source labels were unavailable for {partial:,} canonical observations. Counts include their verified labels."
        )
    if overlong:
        warnings.append(
            f"Reference labels longer than {LABEL_LIMIT} characters were omitted from {overlong:,} observations."
        )
    cves = sorted(cve_counts.items(), key=lambda item: (-item[1], item[0]))
    products = [
        (labels[key], n)
        for key, n in sorted(product_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    return observations, warnings, (cves, with_cves), (products, with_products)


def observed_references(eclipse, *, limit, cve_offset, product_offset, archive_limit):
    if not (1 <= limit <= 100 and min(cve_offset, product_offset) >= 0):
        raise ValueError("Invalid observed-reference page")
    with eclipse._view_lock:
        revision = _revision(eclipse)
        if (
            not eclipse._observed_reference_cache
            or eclipse._observed_reference_cache[0] != revision
        ):
            # The archive and canonical workspace are independent SQLite databases.
            # If either advanced during the read, retry against the new revision.
            for _ in range(2):
                data = _collect(eclipse.store, archive_limit)
                after = _revision(eclipse)
                if revision == after:
                    eclipse._observed_reference_cache = revision, data
                    break
                revision = after
            else:
                raise ValueError("Workspace observations changed during the read")
        _, (total, warnings, cves, products) = eclipse._observed_reference_cache

    def page(ranking, offset):
        values, covered = ranking
        return {
            "items": [{"value": value, "count": n} for value, n in values[offset : offset + limit]],
            "total": len(values),
            "observations_with_value": covered,
            "limit": limit,
            "offset": offset,
        }

    return {
        "revision": revision,
        "observation_count": total,
        "coverage_complete": not warnings,
        "warnings": list(warnings),
        "cves": page(cves, cve_offset),
        "products": page(products, product_offset),
    }
