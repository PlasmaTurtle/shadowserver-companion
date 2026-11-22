"""Canonical assets, conditions and source events, independent of work queues.

All mutations use a caller-owned transaction. Imports and certified snapshots
are provenance, never rewritten by these projections. A source event can support
several conditions, but contributes only once to observation density.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
import math
import re

from .intake.domains import root_domain
from .intake.versions import entry_fields
from .intake.findings import version_is_placeholder
from modules.workspace.components.primitives import dump, now
from .awareness_identity import digest, hostname, timestamp, source_key, service_scope, asset_key
from modules.accretion.components import awareness_admission
from modules.entities.components import ownership


def available(db):
    return bool(
        db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='awareness_assets'"
        ).fetchone()
    )


def conditions(entry):
    """Each machine-readable condition owns an identity, not the whole tag set."""
    # Report-only condition overlays narrow a case; they never rename the
    # canonical source condition or change its underlying finding identity.
    raw = {
        **entry,
        "normalized": {
            k: v for k, v in (entry.get("normalized") or {}).items() if k != "case_condition_scope"
        },
    }
    fields = entry_fields(raw)
    tags = str(fields.get("tag") or entry.get("tag") or "")
    cves = set(re.findall(r"(?<![A-Za-z0-9])CVE-\d{4}-\d{4,}(?![A-Za-z0-9])", tags, re.I))
    result = [(value.upper(), "cve") for value in sorted(cves, key=str.upper)]
    other = re.sub(r"(?<![A-Za-z0-9])CVE-\d{4}-\d{4,}(?![A-Za-z0-9])", "", tags, flags=re.I)
    for value in sorted(set(re.split(r"[;,\s]+", other.casefold())) - {""}):
        if not re.fullmatch(r"[a-z][a-z0-9_.+/-]*", value):
            continue
        # Generic severity labels accompanying actual CVEs are attributes.
        if value in {"critical", "high", "medium", "low", "vulnerable", "cve"}:
            continue
        if value.startswith("eol"):
            # An EOL release line remains the same condition across patch changes.
            release = re.search(r"\d+(?:\.\d+)?", str(fields.get("version") or ""))
            product = (
                str(
                    fields.get("product")
                    or fields.get("application")
                    or fields.get("service")
                    or ""
                )
                .strip()
                .casefold()
            )
            base = (
                value
                if value not in {"eol", "end-of-life"}
                else value
                + ("-" + re.sub(r"[^a-z0-9.+_-]+", "-", product) if product else "-unspecified")
            )
            result.append((base + (":" + release.group() if release else ""), "eol"))
        elif not cves:
            result.append((value, "condition"))
    return sorted(set(result))


def finding_ids(entry, db=None, *, schema_ready=False):
    from modules.entities.components.ownership import entry_context, finding_id

    if is_dataclass(entry):
        entry = asdict(entry)
    key, _, _ = asset_key(entry)
    aid = digest(["asset", key])
    scope = service_scope(entry)
    episode = (
        entry_context(db, entry, schema_ready=schema_ready)["ownership_episode"]
        if db is not None
        else ""
    )
    return [finding_id(aid, condition, scope, episode) for condition, _ in conditions(entry)]


def _entity(db, entity_id):
    visited = set()
    while entity_id and entity_id not in visited:
        visited.add(entity_id)
        row = db.execute("SELECT id,merged_into FROM leads WHERE id=?", (entity_id,)).fetchone()
        if not row:
            raise ValueError("Entity does not exist")
        if not row["merged_into"]:
            return row["id"]
        entity_id = row["merged_into"]
    if entity_id:
        raise ValueError("Entity association contains a cycle")
    return None


def link_asset(db, name, entity_id, *, basis="manual"):
    name = hostname(name)
    if not name or not root_domain(name) or "." not in name:
        raise ValueError("Enter a valid hostname or domain")
    entity_id = _entity(db, entity_id)
    key, stamp = "hostname:" + name, now()
    prior = db.execute("SELECT * FROM awareness_assets WHERE asset_key=?", (key,)).fetchone()
    owner = ownership.hostname_owner(db, name)
    if owner and _entity(db, owner) != entity_id:
        raise ValueError(
            "This hostname belongs to another business. Use Transfer ownership after reviewing the affected records"
        )
    root = root_domain(name)
    if (
        name == root
        and db.execute(
            "SELECT 1 FROM awareness_assets WHERE root_domain=? AND entity_id IS NOT NULL AND entity_id<>? LIMIT 1",
            (root, entity_id),
        ).fetchone()
    ):
        raise ValueError("A hostname under this domain belongs to another entity")
    aid = prior["id"] if prior else digest(["asset", key])
    db.execute(
        """INSERT INTO awareness_assets VALUES(?,?,?,?,?,?,?,?)
      ON CONFLICT(asset_key) DO UPDATE SET entity_id=excluded.entity_id,association_basis=excluded.association_basis,updated_at=excluded.updated_at""",
        (aid, key, name, root, entity_id, str(basis)[:200], stamp, stamp),
    )
    if name == root:
        db.execute(
            "UPDATE awareness_assets SET entity_id=?,association_basis=?,updated_at=? WHERE root_domain=? AND entity_id IS NULL",
            (entity_id, str(basis)[:200], stamp, root),
        )
    from modules.entities.components.ownership import ensure_asset

    for asset in db.execute(
        "SELECT id,entity_id FROM awareness_assets WHERE root_domain=? AND entity_id=?",
        (root, entity_id),
    ).fetchall():
        ensure_asset(db, asset["id"], asset["entity_id"], basis=basis)
    return dict(db.execute("SELECT * FROM awareness_assets WHERE id=?", (aid,)).fetchone())


def merge_entities(db, source_id, target_id):
    target_id = _entity(db, target_id)
    db.execute(
        "UPDATE awareness_assets SET entity_id=?,association_basis='Explicit entity merge',updated_at=? WHERE entity_id=?",
        (target_id, now(), source_id),
    )
    from modules.entities.components.ownership import available as ownership_available

    if ownership_available(db):
        from modules.workspace.components.primitives import uid

        stamp = now()
        db.execute(
            "UPDATE asset_ownership_episodes SET entity_id=? WHERE entity_id=? AND ended_at IS NULL",
            (target_id, source_id),
        )
        db.execute(
            "INSERT INTO entity_lifecycle_events VALUES(?,?,?,?,?,?,?,?,?)",
            (
                uid(),
                "merge",
                source_id,
                target_id,
                "business_identity",
                "Explicit business identity merge",
                "Local operator",
                stamp,
                dump({"recorded_observation_owners_retained": True}),
            ),
        )


def _summary(fields):
    result = {}
    for key, value in fields.items():
        if not isinstance(key, str) or len(key) > 200:
            continue
        if isinstance(value, float) and not math.isfinite(value):
            value = None
        elif isinstance(value, str):
            value = value[:4096]
        elif value is not None and not isinstance(value, (int, float, bool)):
            value = str(value)[:4096]
        result[key] = value
    return result


def associate(
    db,
    entry,
    *,
    import_id,
    source_sha256="",
    entity_id=None,
    admitted=False,
    reason="",
    fallback="",
    workflow="unworked",
    admission_authority=None,
    admitted_conditions=None,
):
    """Retain all source conditions, admitting only an explicitly qualified scope.

    None keeps the historical whole-row API for non-funnel callers. An empty
    scope retains observed-only context; it cannot approve another condition.
    """
    if is_dataclass(entry):
        entry = asdict(entry)
    fields = entry_fields(entry)
    key, name, ip = asset_key(entry)
    if not key:
        return None
    raw_source = entry.get("source") or {}
    normalized = entry.get("normalized") or {}
    origin = (
        db.execute(
            "SELECT sha256,created_at,config FROM imports WHERE id=?", (import_id,)
        ).fetchone()
        if import_id
        else None
    )
    source_sha256 = (
        source_sha256 or normalized.get("source_sha256") or (origin["sha256"] if origin else "")
    )
    if origin and source_sha256 and source_sha256 != origin["sha256"]:
        actual = db.execute(
            "SELECT * FROM imports WHERE sha256=? ORDER BY created_at,id LIMIT 1", (source_sha256,)
        ).fetchone()
        if actual:
            import_id, origin = actual["id"], actual
    provenance = source_key(entry, source_sha256)
    stamp = now()
    aid = digest(["asset", key])
    owner = _entity(db, entity_id) if entity_id else ownership.hostname_owner(db, name)
    prior_asset = db.execute("SELECT * FROM awareness_assets WHERE id=?", (aid,)).fetchone()
    if prior_asset and prior_asset["entity_id"] and owner and prior_asset["entity_id"] != owner:
        # A conflicting assertion is retained unresolved; it cannot steal an asset.
        owner = prior_asset["entity_id"]
        admitted, reason = False, "association_conflict"
    root = root_domain(name) if name else ""
    db.execute(
        """INSERT INTO awareness_assets VALUES(?,?,?,?,?,?,?,?)
      ON CONFLICT(id) DO UPDATE SET entity_id=COALESCE(awareness_assets.entity_id,excluded.entity_id),
      association_basis=CASE WHEN awareness_assets.entity_id IS NULL THEN excluded.association_basis ELSE awareness_assets.association_basis END,
      updated_at=excluded.updated_at""",
        (
            aid,
            key,
            name,
            root,
            owner,
            "Qualified hostname association" if owner else "",
            stamp,
            stamp,
        ),
    )
    if owner and root and ownership.hostname_owner(db, root) == owner:
        # Root-domain evidence can connect earlier dark observations without
        # approving them; a shared address never supplies this relationship.
        db.execute(
            "UPDATE awareness_assets SET entity_id=?,association_basis='Saved root-domain association',updated_at=? WHERE root_domain=? AND entity_id IS NULL",
            (owner, stamp, root),
        )
    observed_at = timestamp(fields.get("timestamp"))
    if not observed_at and normalized.get("acquisition"):
        observed_at = timestamp(normalized["acquisition"].get("report_date"))
    if not observed_at and origin:
        observed_at = timestamp(
            json.loads(origin["config"]).get("acquisition", {}).get("report_date")
        )
    # Retrieval is not observation time. Equal undated measurements consolidate
    # conservatively and never manufacture another observation day on re-export.
    ownership.ensure_asset(db, aid, owner)
    owner_context = ownership.context(db, aid, name, observed_at, provenance, entity_id=owner)
    if owner_context["historical_review"]:
        admitted, reason = False, "ownership_history_review"
    event_time = observed_at or "undated"
    scope = service_scope(entry)
    condition_values = conditions(entry)
    if admitted_conditions is not None:
        admitted_conditions = frozenset(admitted_conditions)
        admitted = bool(admitted) and any(c in admitted_conditions for c, _ in condition_values)
    measurement = [
        aid,
        ip,
        scope,
        event_time,
        str(fields.get("version") or "").strip().casefold(),
        str(fields.get("product") or "").strip().casefold(),
    ]
    if owner_context["ownership_episode"]:
        measurement.append(owner_context["ownership_episode"])
    oid = digest(["observation", measurement])
    old_source = db.execute(
        "SELECT observation_id FROM awareness_sources WHERE import_id IS ? AND source_key=?",
        (import_id, provenance),
    ).fetchone()
    if old_source:
        oid = old_source[0]
    old = db.execute("SELECT * FROM awareness_observations WHERE id=?", (oid,)).fetchone()
    new_observation = old is None
    if old and normalized:
        previous = json.loads(old["normalized"])
        combined = {**previous, **normalized}
        if previous.get("accretion_cves") or normalized.get("accretion_cves"):
            combined["accretion_cves"] = {
                **previous.get("accretion_cves", {}),
                **normalized.get("accretion_cves", {}),
            }
        normalized = combined
    raw_fields = raw_source.get("fields") or fields
    summary_fields = _summary(raw_fields)
    clipped = [
        str(key)[:200]
        for key, value in raw_fields.items()
        if key not in summary_fields or summary_fields[key] != value
    ]
    normalized = {
        **normalized,
        "awareness_projection": {"complete": not clipped, "clipped_fields": clipped[:100]},
    }
    endpoint = digest([aid, ip, scope])
    db.execute(
        """INSERT INTO awareness_observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
      ON CONFLICT(id) DO UPDATE SET admitted=MAX(awareness_observations.admitted,excluded.admitted),
      reason=CASE WHEN MAX(awareness_observations.admitted,excluded.admitted)=1 THEN '' ELSE excluded.reason END,
      summary=CASE WHEN excluded.admitted=1 OR awareness_observations.admitted=0 THEN excluded.summary ELSE awareness_observations.summary END,
      source_key=CASE WHEN excluded.admitted=1 OR awareness_observations.admitted=0 THEN excluded.source_key ELSE awareness_observations.source_key END,
      normalized=CASE WHEN excluded.normalized<>'{}' AND (excluded.admitted=1 OR awareness_observations.admitted=0) THEN excluded.normalized ELSE awareness_observations.normalized END,
      last_recorded_at=excluded.last_recorded_at""",
        (
            oid,
            aid,
            observed_at,
            int(admitted),
            "" if admitted else str(reason)[:200],
            dump(summary_fields),
            dump(normalized),
            ip,
            endpoint,
            stamp,
            stamp,
            provenance,
        ),
    )
    ownership.record_observation(db, oid, owner_context)
    if import_id:
        row_number = raw_source.get("row")
        db.execute(
            "INSERT OR IGNORE INTO awareness_sources VALUES(?,?,?,?,?,?,?,?)",
            (
                import_id,
                provenance,
                oid,
                source_sha256,
                str(raw_source.get("sheet") or ""),
                int(row_number) if isinstance(row_number, int) else 0,
                str(entry.get("id") or normalized.get("observation_ref") or provenance),
                str(raw_source.get("workbook") or ""),
            ),
        )
    added = []
    ids = []
    for condition, kind in condition_values:
        fid = ownership.finding_id(aid, condition, scope, owner_context["ownership_episode"])
        ids.append(fid)
        prior = db.execute("SELECT * FROM awareness_findings WHERE id=?", (fid,)).fetchone()
        # Approval of another condition supported by this event is not approval
        # of a newly asserted CVE. Only the final qualification can promote it.
        effective_admission = bool(admitted) and (
            admitted_conditions is None or condition in admitted_conditions
        )
        effective_reason = (
            reason if effective_admission or not admitted else "outside_qualified_scope"
        )
        if prior is None:
            added.append(fid)
            owner_columns = ",ownership_episode,entity_id" if ownership.available(db) else ""
            owner_values = (
                (owner_context["ownership_episode"], owner_context["entity_id"])
                if owner_columns
                else ()
            )
            db.execute(
                "INSERT INTO awareness_findings(id,asset_id,condition,service_scope,kind,admitted,workflow,first_seen,last_seen,changed_at,last_fingerprint,latest_observation_id,handled_case_id,created_at,latest_source_key,reason"
                + owner_columns
                + ") VALUES("
                + ",".join("?" for _ in range(16 + len(owner_values)))
                + ")",
                (
                    fid,
                    aid,
                    condition,
                    scope,
                    kind,
                    int(effective_admission),
                    workflow,
                    observed_at,
                    observed_at,
                    stamp,
                    "",
                    oid,
                    "",
                    stamp,
                    provenance,
                    "" if effective_admission else str(effective_reason)[:200],
                )
                + owner_values,
            )
        else:
            prior_approved = bool(prior["admitted"])
            if awareness_admission.available(db):
                prior_approved = bool(
                    db.execute(
                        "SELECT 1 FROM awareness_memberships WHERE finding_id=? AND admission_state='admitted' LIMIT 1",
                        (fid,),
                    ).fetchone()
                )
            promoted = effective_admission and not prior_approved
            eligible = effective_admission or not prior["admitted"]
            latest = eligible and (promoted or observed_at > prior["last_seen"])
            if eligible and not promoted and observed_at == prior["last_seen"]:
                previous = db.execute(
                    "SELECT summary,normalized FROM awareness_observations WHERE id=?",
                    (prior["latest_observation_id"],),
                ).fetchone()
                previous_version = entry_fields(
                    {
                        "source": {"fields": json.loads(previous["summary"])},
                        "normalized": json.loads(previous["normalized"]),
                    }
                ).get("version")
                latest = (not version_is_placeholder(fields.get("version")), oid) >= (
                    not version_is_placeholder(previous_version),
                    prior["latest_observation_id"],
                )
            changed = promoted
            first_seen = (
                observed_at
                if promoted
                else min(prior["first_seen"], observed_at)
                if eligible
                else prior["first_seen"]
            )
            last_seen = (
                observed_at
                if promoted
                else max(prior["last_seen"], observed_at)
                if eligible
                else prior["last_seen"]
            )
            db.execute(
                """UPDATE awareness_findings SET admitted=MAX(admitted,?),first_seen=?,last_seen=?,
              changed_at=CASE WHEN ? THEN ? ELSE changed_at END,
              latest_observation_id=CASE WHEN ? THEN ? ELSE latest_observation_id END,
              latest_source_key=CASE WHEN ? THEN ? ELSE latest_source_key END,
              reason=CASE WHEN MAX(admitted,?)=1 THEN '' ELSE ? END,
              workflow=CASE WHEN workflow='unworked' AND ?<>'unworked' THEN ? ELSE workflow END WHERE id=?""",
                (
                    int(effective_admission),
                    first_seen,
                    last_seen,
                    changed,
                    stamp,
                    latest,
                    oid,
                    latest,
                    provenance,
                    int(effective_admission),
                    str(effective_reason)[:200],
                    workflow,
                    workflow,
                    fid,
                ),
            )
        if awareness_admission.available(db):
            db.execute(
                "INSERT INTO awareness_memberships(finding_id,observation_id,admission_state) SELECT ?,?,'observed' WHERE NOT EXISTS(SELECT 1 FROM awareness_memberships WHERE finding_id=? AND observation_id=?)",
                (fid, oid, fid, oid),
            )
            awareness_admission.record(
                db,
                finding_id=fid,
                observation_id=oid,
                import_id=import_id,
                source_key=provenance,
                admitted=effective_admission,
                fields=fields,
                reason=effective_reason,
                **(admission_authority or {}),
            )
        else:
            db.execute(
                "INSERT OR IGNORE INTO awareness_memberships(finding_id,observation_id) VALUES(?,?)",
                (fid, oid),
            )
    return {
        "asset_id": aid,
        "observation_id": oid,
        "finding_ids": ids,
        "new_observation": new_observation,
        "new_findings": added,
        "entity_id": owner_context["entity_id"],
    }


def recognize(db, entry, *, entity_id=None):
    key, _, ip = asset_key(entry)
    aid = digest(["asset", key])
    asset = db.execute("SELECT * FROM awareness_assets WHERE id=?", (aid,)).fetchone()
    endpoint = digest([aid, ip, service_scope(entry)])
    from modules.entities.components.ownership import (
        available as ownership_available,
        entry_context,
    )

    if ownership_available(db):
        episode = entry_context(db, entry)["ownership_episode"]
        prior = db.execute(
            "SELECT o.* FROM awareness_observations o JOIN awareness_observation_owners own ON own.observation_id=o.id WHERE o.endpoint_key=? AND o.admitted=1 AND own.ownership_episode=? ORDER BY o.observed_at DESC,o.id LIMIT 1",
            (endpoint, episode),
        ).fetchone()
    else:
        prior = db.execute(
            "SELECT * FROM awareness_observations WHERE endpoint_key=? AND admitted=1 ORDER BY observed_at DESC,id LIMIT 1",
            (endpoint,),
        ).fetchone()
    return {
        "asset_id": aid if asset else None,
        "entity_id": asset["entity_id"] if asset else None,
        "finding_ids": finding_ids(entry, db),
        "prior_observation": dict(prior) if prior else None,
        "endpoint_seen": bool(prior),
        "admitted": bool(prior),
        "owner_matches": not entity_id or bool(asset and asset["entity_id"] == entity_id),
    }


def actionable_scope(db, entries, *, entity_id=None):
    """Source-supported eligible conditions not already handled or ignored.

    Filter owns schema/admission; this read only removes settled finding scope.
    A new condition on a known entity remains eligible. No attribution or score
    is inferred from a catalog identifier or severity value.
    """
    candidates = []
    for index, entry in enumerate(entries):
        normalized = entry.get("normalized") or {}
        if not normalized.get("eligibility", {}).get("eligible"):
            continue
        profile = normalized.get("profile") or {}
        values = conditions(entry)
        identities = (
            finding_ids(entry, db, schema_ready=True) if entity_id else [None] * len(values)
        )
        for (condition, kind), identity in zip(values, identities):
            candidates.append(
                {
                    "entry_index": index,
                    "finding_id": identity,
                    "condition": condition,
                    "kind": kind,
                    "report_type": profile.get("id"),
                    "observation_kind": profile.get("observation_kind"),
                    "basis": "shadowserver_report",
                    "source": {key: entry["source"][key] for key in ("workbook", "sheet", "row")},
                }
            )
    settled = set()
    ids = list({value["finding_id"] for value in candidates if value["finding_id"]})
    for offset in range(0, len(ids), 500):
        batch = ids[offset : offset + 500]
        settled.update(
            row[0]
            for row in db.execute(
                "SELECT id FROM awareness_findings WHERE workflow IN ('handled','ignored') AND id IN ("
                + ",".join("?" for _ in batch)
                + ")",
                batch,
            )
        )
    return [value for value in candidates if value["finding_id"] not in settled]


def mark_handled(db, entry, case_id):
    active = (entry.get("normalized") or {}).get("active_conditions")
    pairs = zip(finding_ids(entry, db), conditions(entry))
    for fid, (condition, _) in pairs:
        if active is not None and condition not in active:
            continue
        db.execute(
            "UPDATE awareness_findings SET workflow='handled',handled_case_id=? WHERE id=?",
            (case_id, fid),
        )


def ignore_findings(db, ids):
    """Ignore unworked canonical findings without changing source evidence."""
    db.executemany(
        "UPDATE awareness_findings SET workflow='ignored' WHERE id=? AND workflow='unworked'",
        ((identity,) for identity in set(ids)),
    )


def settle_findings(db, ids):
    """Compare the complete admitted endpoint set after final group association.

    Comparing each row to one representative would oscillate the fingerprint
    whenever a load-balanced hostname has several IPs in the same scan.
    """
    for fid in set(ids):
        finding = db.execute("SELECT * FROM awareness_findings WHERE id=?", (fid,)).fetchone()
        if not finding or not finding["admitted"]:
            continue
        latest = finding["last_seen"]
        endpoints = {}
        # Start with the indexed asset/day range, not all historic memberships.
        # Sixty daily repeats do not require sixty expanding history rescans.
        day = latest[:10]
        query = (
            "SELECT o.*, "
            + awareness_admission.facts_sql(db)
            + " approved_facts FROM awareness_observations o INDEXED BY awareness_observations_asset CROSS JOIN awareness_memberships m WHERE o.asset_id=? AND "
            + awareness_admission.state_sql(db)
            + "='admitted' AND m.observation_id=o.id AND m.finding_id=? AND "
        )
        date_predicate = "o.observed_at>=? AND o.observed_at<?" if day else "o.observed_at=''"
        args = (
            (finding["asset_id"], fid, day + "T", day + "U") if day else (finding["asset_id"], fid)
        )
        for row in db.execute(query + date_predicate + " ORDER BY o.observed_at,o.id", args):
            fields = entry_fields(
                {
                    "source": {"fields": json.loads(row["summary"])},
                    "normalized": json.loads(row["normalized"]),
                }
            )
            if row["approved_facts"]:
                fields.update(json.loads(row["approved_facts"]))
            value = [
                row["ip"],
                str(fields.get("version") or "").casefold(),
                str(fields.get("severity") or "").casefold(),
            ]
            endpoints[
                (row["endpoint_key"], value[1], str(fields.get("product") or "").casefold())
            ] = (row["observed_at"], value)
        last_by_endpoint = {}
        for key, (observed_at, _) in endpoints.items():
            last_by_endpoint[key[0]] = max(last_by_endpoint.get(key[0], ""), observed_at)
        fingerprint = digest(
            sorted(
                value
                for key, (observed_at, value) in endpoints.items()
                if observed_at == last_by_endpoint[key[0]]
            )
        )
        changed = bool(finding["last_fingerprint"] and finding["last_fingerprint"] != fingerprint)
        db.execute(
            "UPDATE awareness_findings SET last_fingerprint=?,changed_at=CASE WHEN ? THEN ? ELSE changed_at END WHERE id=?",
            (fingerprint, changed, now(), fid),
        )


def counts(db, entity_id=None):
    modern = ownership.available(db)
    owner_join = (
        "LEFT JOIN awareness_observation_owners w ON w.observation_id=o.id" if modern else ""
    )
    owner = (
        "CASE WHEN w.observation_id IS NOT NULL THEN w.entity_id ELSE a.entity_id END"
        if modern
        else "a.entity_id"
    )
    owner = f"COALESCE((SELECT merged_into FROM leads WHERE id=({owner})),({owner}))"
    finding_owner = (
        "COALESCE((SELECT merged_into FROM leads WHERE id=f.entity_id),f.entity_id)"
        if modern
        else "a.entity_id"
    )
    where, args = (f" WHERE ({owner})=?", (entity_id,)) if entity_id else ("", ())
    approved, unknown = awareness_admission.observation_states_sql(db)
    observations = db.execute(
        f"SELECT count(*) total,COALESCE(sum({approved}),0) admitted,COALESCE(sum({unknown}),0) unknown,COALESCE(sum(o.admitted),0) known_aggregate,count(DISTINCT NULLIF(substr(o.observed_at,1,10),'')) days FROM awareness_observations o JOIN awareness_assets a ON a.id=o.asset_id "
        + owner_join
        + where,
        args,
    ).fetchone()
    findings = db.execute(
        "SELECT count(*) FROM awareness_findings f JOIN awareness_assets a ON a.id=f.asset_id"
        + (f" WHERE ({finding_owner})=?" if entity_id else ""),
        args,
    ).fetchone()[0]
    return {
        "observations": observations["total"],
        "approved_observations": observations["admitted"],
        "dark_matter_observations": observations["total"]
        - observations["admitted"]
        - observations["unknown"],
        "legacy_unknown_observation_count": observations["unknown"],
        "known_aggregate_qualified_observations": observations["known_aggregate"],
        "observation_days": observations["days"],
        "findings": findings,
    }
