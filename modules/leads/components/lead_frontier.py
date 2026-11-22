"""One current qualified lead per entity, selected from canonical findings.

Caller-owned transactions protect case evidence. Original imports remain intact;
retired queue copies and unreferenced unworked entries are discarded.
"""

import hashlib
import json

from modules.accretion.components.intake.identity import observed
from modules.accretion.components.awareness_identity import source_key
from modules.workspace.components.primitives import dump, now


def origin_entries(db, row):
    source = db.execute(
        "SELECT sha256,created_at FROM imports WHERE id=?", (row["import_id"],)
    ).fetchone()
    entries = json.loads(row["payload"])
    for entry in entries:
        normalized = entry.setdefault("normalized", {})
        normalized.setdefault("source_sha256", source["sha256"])
        normalized.setdefault("observation_ref", source_key(entry, normalized["source_sha256"]))
    return entries, source["created_at"]


def _prune(db, entries, keep):
    for entry in entries:
        oid = entry["normalized"]["observation_ref"]
        if oid in keep:
            continue
        from modules.entities.components.ownership import available as ownership_available

        if (
            ownership_available(db)
            and db.execute(
                "SELECT 1 FROM entity_domain_associations WHERE attribution_entry_id=? LIMIT 1",
                (oid,),
            ).fetchone()
        ):
            continue
        # Include non-FK pointers and deferred constraints. Migration deliberately
        # disables enforcement, so catching IntegrityError is not sufficient.
        if db.execute(
            """SELECT 1 FROM case_entries WHERE entry_id=?
            UNION SELECT 1 FROM domain_groups WHERE attribution_entry_id=?
            UNION SELECT 1 FROM leads WHERE attribution_entry_id=?
            UNION SELECT 1 FROM case_asset_attributions WHERE entry_id=? LIMIT 1""",
            (oid, oid, oid, oid),
        ).fetchone():
            continue
        db.execute("DELETE FROM entries WHERE id=?", (oid,))


def _retire(db, row, successor, reason, keep=(), *, entries=None):
    if entries is None:
        entries, _ = origin_entries(db, row)
    from modules.accretion.components.awareness import finding_ids, ignore_findings

    if reason == "ignored":
        ignore_findings(db, {fid for entry in entries for fid in finding_ids(entry, db)})
    db.execute(
        "UPDATE lead_queue SET payload='[]',intake_score='{}',status='dismissed',superseded_by=?,suppression_reason=?,revision=revision+1,updated_at=? WHERE id=?",
        (successor, reason, now(), row["id"]),
    )
    # Retiring duplicate work must not erase an analyst decision's source-row
    # mapping. The current acceptance may still be in progress (status review),
    # before its decision row is inserted by the same transaction.
    db.execute(
        "UPDATE jobs SET payload='[]' WHERE import_id=? AND domain=? AND status!='review' "
        "AND NOT EXISTS(SELECT 1 FROM attribution_reviews r WHERE r.job_id=jobs.id AND r.decision='accept')",
        (row["import_id"], row["root_domain"]),
    )
    _prune(db, entries, set(keep))


def _select_scope(db, all_rows, parsed_candidates, fallbacks, *, proposed_id=None):
    """Select pending conditions without publishing or evaluating them."""
    from modules.accretion.components.awareness import (
        conditions,
        finding_ids,
    )
    from modules.accretion.components.intake.versions import entry_fields, project_conditions

    candidates, candidate_findings, proposed = {}, {}, set()
    for candidate in all_rows:
        source_entries = parsed_candidates[candidate["id"]]
        source_fallback = fallbacks[candidate["id"]]
        candidate_findings[candidate["id"]] = set()
        for entry in source_entries:
            ids = finding_ids(entry, db)
            selected = entry.get("normalized", {}).get("active_conditions")
            for fid, (condition, _) in zip(ids, conditions(entry)):
                if selected is not None and condition not in selected:
                    continue
                candidate_findings[candidate["id"]].add(fid)
                if candidate["id"] == proposed_id:
                    proposed.add(fid)
                stamp = observed(entry, source_fallback)
                fields = entry_fields(entry)
                endpoint = (
                    str(entry.get("ip") or fields.get("ip") or ""),
                    str(fields.get("version") or ""),
                    str(fields.get("product") or ""),
                )
                day = stamp[:10]
                if fid not in candidates or day > candidates[fid][0]:
                    candidates[fid] = (day, {})
                if day == candidates[fid][0]:
                    endpoints = candidates[fid][1]
                    if endpoint not in endpoints or stamp >= endpoints[endpoint][0]:
                        endpoints[endpoint] = (stamp, entry, condition)
    for _, endpoints in candidates.values():
        latest_by_ip = {}
        for endpoint, (stamp, _, _) in endpoints.items():
            latest_by_ip[endpoint[0]] = max(latest_by_ip.get(endpoint[0], ""), stamp)
        for endpoint in list(endpoints):
            if endpoints[endpoint][0] < latest_by_ip[endpoint[0]]:
                del endpoints[endpoint]
    # New imports update current awareness; handled/ignored finding identity is
    # independent of the newest row's version, location, and report delivery.
    active = {}
    for fid, value in candidates.items():
        finding = db.execute(
            "SELECT admitted,workflow FROM awareness_findings WHERE id=?", (fid,)
        ).fetchone()
        if (
            finding
            and finding["workflow"] == "unworked"
            and (finding["admitted"] or fid in proposed)
        ) or (not finding and fid in proposed):
            active[fid] = value
    winner = max(all_rows, key=lambda r: (r["observation_day"], r["created_at"], r["id"]))
    grouped = {}
    for fid, (_, endpoints) in active.items():
        for _, entry, condition in endpoints.values():
            oid = entry["normalized"]["observation_ref"]
            if oid not in grouped:
                copied = project_conditions(json.loads(dump(entry)), [])
                grouped[oid] = copied
            grouped[oid]["normalized"]["active_conditions"].append(condition)
            if condition.startswith("CVE-"):
                grouped[oid]["normalized"]["active_cves"].append(condition)
    imported = db.execute(
        "SELECT config,created_at FROM imports WHERE id=?", (winner["import_id"],)
    ).fetchone()
    config = json.loads(imported["config"])
    selected_entries = list(grouped.values())
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "winner": winner["id"],
                "root": winner["root_domain"],
                "entries": sorted(
                    selected_entries, key=lambda entry: entry["normalized"]["observation_ref"]
                ),
                "policy": config.get("accretion_policy"),
                "as_of": config.get("accretion_scored_at") or imported["created_at"],
            },
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        ).encode()
    ).hexdigest()
    return {
        "winner": winner,
        "rows": all_rows,
        "parsed": parsed_candidates,
        "entries": selected_entries,
        "active": set(active),
        "candidate_findings": candidate_findings,
        "fingerprint": fingerprint,
        "policy": config.get("accretion_policy"),
        "as_of": config.get("accretion_scored_at") or imported["created_at"],
    }


def _scope(db, row, entries, fallback, *, proposed=False):
    prior_rows = (
        [
            dict(value)
            for value in db.execute(
                "SELECT * FROM lead_queue WHERE entity_id=? AND id<>? AND qualified=1 AND status IN ('pending','deferred') AND superseded_by='' AND suppression_reason='' ORDER BY observation_day,created_at,id",
                (row["entity_id"], row["id"]),
            ).fetchall()
        ]
        if row["entity_id"]
        else []
    )
    current = {
        **dict(row),
        "observation_day": max(
            (observed(e, fallback)[:10] for e in entries), default=fallback[:10]
        ),
    }
    parsed, fallbacks = {current["id"]: entries}, {current["id"]: fallback}
    for candidate in prior_rows:
        parsed[candidate["id"]], fallbacks[candidate["id"]] = origin_entries(db, candidate)
    return _select_scope(
        db,
        [*prior_rows, current],
        parsed,
        fallbacks,
        proposed_id=current["id"] if proposed else None,
    )


def preview_scope(db, import_id, root, entries, *, entity_id=None):
    """Preview the entity's pending work including one completely qualified lead.

    Incoming rows must already be projected to Qualify's active conditions. They
    need no canonical entity or finding writes before Evaluate can rank them.
    """
    from ..helpers.queue_identity import queue_id

    identity = queue_id(import_id, root)
    prior = db.execute("SELECT * FROM lead_queue WHERE id=?", (identity,)).fetchone()
    source = db.execute("SELECT sha256,created_at FROM imports WHERE id=?", (import_id,)).fetchone()
    copied = json.loads(dump(entries))
    for entry in copied:
        normalized = entry.setdefault("normalized", {})
        normalized.setdefault("source_sha256", source["sha256"])
        normalized.setdefault("observation_ref", source_key(entry, normalized["source_sha256"]))
    row = {
        "id": identity,
        "entity_id": entity_id,
        "import_id": import_id,
        "root_domain": root,
        "created_at": prior["created_at"] if prior else now(),
        "association_state": "known" if entity_id else "new",
        "association_basis": "Qualified lead",
        "intake_score": prior["intake_score"] if prior else "{}",
    }
    return _scope(db, row, copied, source["created_at"], proposed=True)


def preview_current(db, lead_id):
    """Read the scope of already-qualified queue work after an explicit edit."""
    row = db.execute("SELECT * FROM lead_queue WHERE id=?", (lead_id,)).fetchone()
    if not row or not row["qualified"] or not row["entity_id"] or row["status"] == "assigned":
        return None
    entries, fallback = origin_entries(db, row)
    if not entries:
        return None
    return _scope(db, row, entries, fallback)


def reconcile(db, lead_id, *, scope=None, score=None):
    """Publish selected qualified work with an existing Evaluate result."""
    from modules.accretion.components.awareness import finding_ids, settle_findings

    row = db.execute("SELECT * FROM lead_queue WHERE id=?", (lead_id,)).fetchone()
    if not row or not row["qualified"] or row["status"] == "assigned":
        return lead_id
    scope = scope or preview_current(db, lead_id)
    if scope is None:
        if row and row["entity_id"]:
            current = db.execute(
                "SELECT id FROM lead_queue WHERE entity_id=? AND qualified=1 AND status IN ('pending','deferred') AND superseded_by='' AND suppression_reason='' ORDER BY observation_day DESC,created_at DESC,id DESC LIMIT 1",
                (row["entity_id"],),
            ).fetchone()
            if current:
                return current["id"]
        return lead_id
    winner, all_rows, parsed = scope["winner"], scope["rows"], scope["parsed"]
    if scope["entries"]:
        score = score if score is not None else json.loads(winner["intake_score"] or "{}")
        if score.get("evaluation_scope", {}).get("fingerprint") != scope["fingerprint"]:
            raise ValueError("Changed pending lead scope must pass Evaluate before publication")
    entries = parsed.get(lead_id, [])
    settle_findings(db, {fid for entry in entries for fid in finding_ids(entry, db)})
    incoming = next(value for value in all_rows if value["id"] == lead_id)
    db.execute(
        "UPDATE lead_queue SET observation_day=? WHERE id=?", (incoming["observation_day"], lead_id)
    )
    keep = {entry["normalized"]["observation_ref"] for entry in scope["entries"]}
    for old in all_rows:
        if old["id"] != winner["id"]:
            _retire(db, old, winner["id"], "superseded", keep, entries=parsed[old["id"]])
    if not scope["entries"]:
        _retire(db, winner, "", "unchanged_reported", entries=parsed[winner["id"]])
        return winner["id"]
    state = winner["association_state"]
    if state == "review" and winner["association_basis"] != "Hostname associations conflict":
        state = "known"
    prior_ids = set().union(
        *(values for identity, values in scope["candidate_findings"].items() if identity != lead_id)
    )
    active = scope["active"]
    db.execute(
        "UPDATE lead_queue SET payload=?,intake_score=?,association_state=?,candidates='[]',superseded_by='',suppression_reason='',signal_hash=?,delta=?,revision=revision+1,updated_at=? WHERE id=?",
        (
            dump(scope["entries"]),
            dump(score),
            state,
            hashlib.sha256(dump(sorted(active)).encode()).hexdigest(),
            dump(
                {
                    "new": len(set(active) - prior_ids),
                    "repeated": len(set(active) & prior_ids),
                    "retired": len(prior_ids - set(active)),
                }
            ),
            now(),
            winner["id"],
        ),
    )
    _prune(db, entries, keep)
    return winner["id"]


def merge_entity_scope(db, source_id, target_id):
    """Merge finding ownership; return qualified work for the caller to evaluate."""
    from modules.accretion.components.awareness import merge_entities

    merge_entities(db, source_id, target_id)
    db.execute("DELETE FROM entity_contact_queue WHERE entity_id=?", (source_id,))
    return [
        row["id"]
        for row in db.execute(
            "SELECT id FROM lead_queue WHERE entity_id=? AND status IN ('pending','deferred') AND qualified=1 ORDER BY observation_day DESC,created_at DESC,id DESC",
            (target_id,),
        ).fetchall()
    ]
