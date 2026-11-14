"""Durable intake dispositions for usable observations outside the lead queue.

Original files remain authoritative. This compact index records policy outcomes,
not extra evidence copies. Source identities deduplicate repeated imports; an
admission under any retained policy takes precedence in the current projection.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import hashlib
import heapq
import math
from ipaddress import ip_address
import json

from .intake.domains import HOSTNAME, EXTRACT_DOMAIN, root_domain
from .primitives import dump, now
from .intake.versions import selected_version

DISPOSITIONS = {"lead", "dark_matter"}
SUMMARY_FIELDS = (
    "hostname",
    "ip",
    "tag",
    "version",
    "component_version",
    "timestamp",
    "region",
    "city",
    "geo",
    "country",
    "protocol",
    "port",
    "product",
    "application",
    "service",
    "severity",
    "asn",
    "latitude",
    "longitude",
)
REASONS = {
    "superseded": "Replaced by a newer qualified finding",
    "unchanged_reported": "Finding already belongs to a notification",
    "ignored": "Ignored for outreach",
    "provider_out_of_scope": "Internet provider outside current outreach scope",
    "below_critical": "Below the critical outreach threshold",
    "unknown_severity": "Severity not established",
    "non_com_root_excluded": "Historical suffix filter (removed)",
    "numeric_root_excluded": "Historical numeric-root filter (removed)",
    "unsupported_report_profile": "Report type outside the supported outreach profiles",
    "missing_version": "Required version evidence absent",
    "placeholder_version": "Required version is a placeholder, not an observed release",
    "malformed_cve_identifier": "Malformed reported CVE identifier",
    "unsupported_finding": "Source tag does not identify a finding",
    "incident_review_required": "Incident finding outside proactive outreach",
    "targeted_profile_review_required": "Outside the selected outreach mode",
    "targeted_reason_required": "Targeted outreach reason absent",
    "api_narrative_date_review_required": "Historical narrative-date gate (removed)",
}


def schema(db):
    db.execute("""CREATE TABLE intake_observations(
        import_id TEXT NOT NULL REFERENCES imports(id),
        observation_id TEXT NOT NULL,
        root_domain TEXT NOT NULL,
        disposition TEXT NOT NULL CHECK(disposition IN ('lead','dark_matter')),
        reason TEXT NOT NULL DEFAULT '',
        observed_at TEXT NOT NULL DEFAULT '',
        summary TEXT NOT NULL,
        recorded_at TEXT NOT NULL,
        PRIMARY KEY(import_id,observation_id))""")
    db.execute(
        "CREATE INDEX intake_observations_root ON intake_observations(root_domain,disposition)"
    )
    db.execute(
        "CREATE INDEX intake_observations_identity ON intake_observations(observation_id,(disposition='lead') DESC,recorded_at DESC,import_id DESC)"
    )
    db.execute(
        "CREATE INDEX intake_observations_disposition ON intake_observations(disposition,recorded_at)"
    )


def _source(value):
    return asdict(value) if is_dataclass(value) else value if isinstance(value, dict) else {}


def usable_fields(fields, regions=None):
    """Reject malformed identifiers; workload preferences are not data corruption."""
    hostname = fields.get("hostname")
    if not isinstance(hostname, str) or len(hostname) > 253 or not HOSTNAME.fullmatch(hostname):
        return False
    domain = EXTRACT_DOMAIN(hostname)
    if not domain.suffix or not domain.domain:
        return False
    if not isinstance(fields.get("ip"), str):
        return False
    try:
        ip_address(fields["ip"])
    except ValueError:
        return False
    if not str(fields.get("tag") or "").strip() or not str(fields.get("region") or "").strip():
        return False
    if regions is not None and str(fields["region"]).casefold() not in regions:
        return False
    return True


def record_observations(db, import_id, source_sha256, rows, *, regions=None, recorded_at=None):
    """Persist bounded summaries in the caller's atomic import transaction."""
    stamp = recorded_at or now()
    region_set = {str(v).casefold() for v in regions} if regions is not None else None
    counts = {"lead": 0, "dark_matter": 0, "discarded": 0}
    batch = []
    from .awareness import available, associate

    canonical = available(db)
    statement = """INSERT INTO intake_observations
        (import_id,observation_id,root_domain,disposition,reason,observed_at,summary,recorded_at)
        VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(import_id,observation_id) DO UPDATE SET
        root_domain=excluded.root_domain,disposition=excluded.disposition,
        reason=excluded.reason,observed_at=excluded.observed_at,
        summary=excluded.summary,recorded_at=excluded.recorded_at"""
    for value in rows:
        source = _source(value.get("source"))
        fields = source.get("fields") or {}
        disposition = value.get("disposition")
        row = source.get("row")
        if (
            disposition not in DISPOSITIONS
            or not isinstance(row, int)
            or isinstance(row, bool)
            or row < 1
            or not isinstance(fields, dict)
            or not usable_fields(fields, region_set)
        ):
            counts["discarded"] += 1
            continue
        sheet = str(source.get("sheet") or "")
        identity = hashlib.sha256(f"{source_sha256}:{sheet}:{row}".encode()).hexdigest()
        summary = {key: fields[key] for key in SUMMARY_FIELDS if fields.get(key) is not None}
        clipped = []
        for key, item in summary.items():
            if isinstance(item, float) and not math.isfinite(item):
                summary[key] = None
                clipped.append(key)
            elif not isinstance(item, (str, int, float, bool)):
                summary[key] = str(item)[:4096]
                clipped.append(key)
            elif isinstance(item, str) and len(item) > 4096:
                summary[key] = item[:4096]
                clipped.append(key)
        summary.update(sheet=sheet[:500], row=row, clipped_fields=clipped)
        batch.append(
            (
                import_id,
                identity,
                root_domain(fields["hostname"]).casefold(),
                disposition,
                str(value.get("reason") or "")[:120],
                str(fields.get("timestamp") or "")[:100],
                dump(summary),
                stamp,
            )
        )
        if canonical:
            associate(
                db,
                {"source": source, "ip": fields.get("ip", "")},
                import_id=import_id,
                source_sha256=source_sha256,
                admitted=False,
                reason=value.get("reason") or "pending_qualification",
            )
        counts[disposition] += 1
        if len(batch) == 500:
            db.executemany(statement, batch)
            batch.clear()
    if batch:
        db.executemany(statement, batch)
    return counts


# The source-based identity survives policy re-evaluation. Successful rescue
# takes precedence; policy evaluations remain independently queryable in SQLite.
CURRENT = """WITH ranked AS (
    SELECT o.*,row_number() OVER(PARTITION BY observation_id
      ORDER BY (disposition='lead') DESC,recorded_at DESC,import_id DESC) position
    FROM intake_observations o
), current AS (SELECT * FROM ranked WHERE position=1) """


def current_records(db, observation_ids, *, limit=100000):
    """One current disposition per indexed source, with bounded batch reads."""
    identities = heapq.nsmallest(min(100000, max(0, limit)), observation_ids)
    result = {}
    for start in range(0, len(identities), 400):
        batch = identities[start : start + 400]
        query = (
            """WITH ranked AS (
            SELECT import_id,observation_id,root_domain,disposition,reason,recorded_at,
              row_number() OVER(PARTITION BY observation_id
                ORDER BY (disposition='lead') DESC,recorded_at DESC,import_id DESC) position
            FROM intake_observations WHERE observation_id IN ("""
            + ",".join("?" for _ in batch)
            + ") ) SELECT * FROM ranked WHERE position=1"
        )
        for row in db.execute(query, batch):
            result[row["observation_id"]] = dict(row)
    return result


def _public(row):
    item = dict(row)
    fields = json.loads(item.pop("summary"))
    item["entity_id"] = item.pop("associated_entity_id", None) or item.get("entity_id") or None
    item["sightings"] = len(json.loads(item.pop("seen_days", "[]"))) or 1
    for key in ("position", "path"):
        item.pop(key, None)
    item.update(
        hostname=fields.get("hostname", ""),
        ip=fields.get("ip", ""),
        tag=fields.get("tag", ""),
        version=selected_version(fields)["raw_version"] or "",
        city=fields.get("city", ""),
        region=fields.get("region", ""),
        sheet=fields.get("sheet", ""),
        row=fields.get("row"),
        clipped_fields=fields.get("clipped_fields", []),
        reason_label=REASONS.get(item["reason"], item["reason"].replace("_", " ").capitalize()),
        original_url=f"/api/imports/{item['import_id']}/original",
        observation_url=f"/api/eclipse/observations/{item['observation_id']}",
        entity_url=f"#entity/{item['entity_id']}" if item.get("entity_id") else None,
        association_basis="Saved root-domain association" if item.get("entity_id") else None,
    )
    return item


def browse(store, *, q="", limit=25, offset=0):
    """Bounded, read-only reference view, deliberately separate from lead work."""
    from .awareness import available

    with store.read_snapshot() as db:
        if available(db):
            return _canonical_browse(db, q=q, limit=limit, offset=offset)
    limit, offset = min(100, max(1, int(limit))), max(0, int(offset))
    query = str(q).strip()[:200]
    predicate = "c.disposition='dark_matter'"
    params = []
    if query:
        # Literal substring search; a supplied percent is not a wildcard.
        value = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        predicate += " AND (c.root_domain LIKE ? ESCAPE '\\' OR c.summary LIKE ? ESCAPE '\\')"
        params.extend((value, value))
    with store.read_snapshot() as db:
        # Aggregate all counters in one scan of the deduplicated projection.
        # Only the bounded page is materialized as Python observation records.
        aggregates = db.execute(
            CURRENT
            + "SELECT c.disposition,c.reason,count(*) total,sum(CASE WHEN "
            + predicate
            + " THEN 1 ELSE 0 END) matches FROM current c GROUP BY c.disposition,c.reason",
            params,
        ).fetchall()
        counts = {"lead": 0, "dark_matter": 0}
        total, reason_counts = 0, []
        for group in aggregates:
            counts[group["disposition"]] += group["total"]
            if group["matches"]:
                total += group["matches"]
                reason_counts.append({"reason": group["reason"], "total": group["matches"]})
        reason_counts = sorted(reason_counts, key=lambda r: (-r["total"], r["reason"]))[:12]
        evaluations = db.execute("SELECT count(*) FROM intake_observations").fetchone()[0]
        rows = db.execute(
            CURRENT
            + """SELECT c.*,i.name import_name,i.sha256 source_sha256,
                l.id associated_entity_id,COALESCE(NULLIF(l.company,''),l.domain,'') entity_name
                FROM current c JOIN imports i ON i.id=c.import_id
                LEFT JOIN domain_groups g ON g.root_domain=c.root_domain
                LEFT JOIN leads l ON l.id=g.entity_id AND l.merged_into IS NULL
                WHERE """
            + predicate
            + " ORDER BY c.observed_at DESC,c.observation_id LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
    return {
        "items": [_public(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "counts": {
            "dark_matter": counts.get("dark_matter", 0),
            "lead": counts.get("lead", 0),
            "observations": sum(counts.values()),
            "evaluations": evaluations,
        },
        "reasons": [
            {
                **r,
                "label": "Qualification provenance unavailable"
                if r["reason"] == "qualification_unknown"
                else REASONS.get(r["reason"], r["reason"].replace("_", " ").capitalize()),
            }
            for r in reason_counts
        ],
        "basis": "Usable in-jurisdiction observations retained outside the lead queue. Malformed rows remain in original evidence only. Saved root-domain matches can associate earlier observations; shared IPs never establish ownership.",
    }


def _canonical_browse(db, *, q="", limit=25, offset=0):
    """Admission is independent of whether an approved finding was worked."""
    limit, offset = min(100, max(1, int(limit))), max(0, int(offset))
    query = str(q).strip()[:200]
    from .awareness_admission import observation_states_sql

    approved, unknown = observation_states_sql(db)
    predicate, params = "NOT " + approved, []
    if query:
        value = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        predicate += " AND (a.root_domain LIKE ? ESCAPE '\\' OR o.summary LIKE ? ESCAPE '\\')"
        params.extend((value, value))
    base = " FROM awareness_observations o JOIN awareness_assets a ON a.id=o.asset_id "
    total = db.execute("SELECT count(*)" + base + "WHERE " + predicate, params).fetchone()[0]
    totals = db.execute(
        f"SELECT count(*) total,COALESCE(sum(o.admitted),0) known_aggregate,COALESCE(sum({approved}),0) admitted,COALESCE(sum({unknown}),0) unknown FROM awareness_observations o"
    ).fetchone()
    reason_sql = f"CASE WHEN {unknown} THEN 'qualification_unknown' ELSE o.reason END"
    reasons = [
        dict(row)
        for row in db.execute(
            f"SELECT {reason_sql} reason,count(*) total"
            + base
            + "WHERE "
            + predicate
            + f" GROUP BY {reason_sql} ORDER BY total DESC,reason LIMIT 12",
            params,
        )
    ]
    from .ownership import available as ownership_available

    modern = ownership_available(db)
    owner_join = (
        "LEFT JOIN awareness_observation_owners w ON w.observation_id=o.id" if modern else ""
    )
    recorded_owner = (
        "CASE WHEN w.observation_id IS NOT NULL THEN w.entity_id ELSE a.entity_id END"
        if modern
        else "a.entity_id"
    )
    observed_owner = (
        f"COALESCE((SELECT merged_into FROM leads WHERE id=({recorded_owner})),({recorded_owner}))"
    )
    rows = db.execute(
        f"""SELECT o.*,{unknown} qualification_unknown,a.hostname,a.root_domain,{observed_owner} entity_id,{recorded_owner} recorded_entity_id,a.entity_id current_entity_id,
      COALESCE(NULLIF(l.company,''),l.domain,'') entity_name,
      s.import_id,s.sheet,s.row_number,s.source_sha256,i.name import_name
      FROM awareness_observations o JOIN awareness_assets a ON a.id=o.asset_id
      {owner_join} LEFT JOIN leads l ON l.id=({observed_owner})
      LEFT JOIN awareness_sources s ON s.rowid=(SELECT min(x.rowid) FROM awareness_sources x WHERE x.observation_id=o.id AND x.source_key=o.source_key)
      LEFT JOIN imports i ON i.id=s.import_id WHERE """
        + predicate
        + " ORDER BY o.observed_at DESC,o.id LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    items = []
    for row in rows:
        fields = json.loads(row["summary"])
        item = {
            key: row[key]
            for key in (
                "import_id",
                "root_domain",
                "reason",
                "observed_at",
                "entity_id",
                "entity_name",
                "import_name",
                "source_sha256",
            )
        }
        item.update(
            observation_id=row["id"],
            recorded_entity_id=row["recorded_entity_id"],
            current_entity_id=row["current_entity_id"],
            disposition="qualification_unknown" if row["qualification_unknown"] else "dark_matter",
            admission_state="legacy_unknown" if row["qualification_unknown"] else "observed",
            known_aggregate_admitted=bool(row["admitted"]),
            hostname=row["hostname"],
            ip=row["ip"],
            tag=fields.get("tag", ""),
            version=selected_version(fields)["raw_version"] or "",
            city=fields.get("city", ""),
            region=fields.get("region", ""),
            sheet=row["sheet"] or "",
            row=row["row_number"],
            sightings=int(bool(row["observed_at"])),
            observation_count=1,
            clipped_fields=json.loads(row["normalized"])
            .get("awareness_projection", {})
            .get("clipped_fields", []),
            reason_label="Qualification provenance unavailable"
            if row["qualification_unknown"]
            else REASONS.get(row["reason"], row["reason"].replace("_", " ").capitalize()),
            original_url=f"/api/imports/{row['import_id']}/original" if row["import_id"] else None,
            observation_url=f"/api/eclipse/observations/{row['id']}",
            entity_url=f"#entity/{row['entity_id']}" if row["entity_id"] else None,
            association_basis="Saved asset association" if row["entity_id"] else None,
        )
        items.append(item)
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "counts": {
            "dark_matter": totals["total"] - totals["admitted"] - totals["unknown"],
            "lead": totals["admitted"],
            "qualification_unknown": totals["unknown"],
            "known_aggregate_qualified_observations": totals["known_aggregate"],
            "observations": totals["total"],
            "evaluations": db.execute("SELECT count(*) FROM awareness_sources").fetchone()[0],
        },
        "reasons": [
            {
                **r,
                "label": "Qualification provenance unavailable"
                if r["reason"] == "qualification_unknown"
                else REASONS.get(r["reason"], r["reason"].replace("_", " ").capitalize()),
            }
            for r in reasons
        ],
        "basis": "Each physical observation counts once as exact approved, known observed-only, or qualification unavailable. Historical aggregate qualification is retained separately; unavailable provenance does not establish approval or rejection. Attribution and workflow are separate.",
    }
