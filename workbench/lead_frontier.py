"""One current qualified lead per entity, with compact repeat-sighting memory.

Caller-owned transactions protect case evidence. Original imports remain intact;
retired queue copies and unreferenced unworked entries are discarded.
"""

import hashlib
import json

from .intake.identity import signature, observed
from .primitives import dump, now


def origin_entries(db, row):
    source = db.execute(
        "SELECT sha256,created_at FROM imports WHERE id=?", (row["import_id"],)
    ).fetchone()
    entries = json.loads(row["payload"])
    for entry in entries:
        normalized = entry.setdefault("normalized", {})
        normalized.setdefault("source_sha256", source["sha256"])
        normalized["observation_ref"] = hashlib.sha256(
            f"{normalized['source_sha256']}:{entry['source']['sheet']}:{entry['source']['row']}".encode()
        ).hexdigest()
    return entries, source["created_at"]


def _remember(db, row, entries, fallback, reason=""):
    """One representative per entity/finding; sixty scans need one summary."""
    from .dark_matter import record_observations

    from .awareness import associate, available, finding_ids
    from .awareness_admission import source_is_admitted

    canonical = available(db)
    for entry in entries:
        if canonical and not source_is_admitted(db, entry, finding_ids(entry, db)):
            associate(
                db,
                entry,
                import_id=row["import_id"],
                entity_id=row["entity_id"],
                admitted=True,
                fallback=fallback,
            )
        key, oid = signature(entry), entry["normalized"]["observation_ref"]
        stamp = observed(entry, fallback)
        prior = db.execute(
            "SELECT * FROM intake_observations WHERE entity_id=? AND signal_key=?",
            (row["entity_id"], key),
        ).fetchone()
        current = db.execute(
            "SELECT * FROM intake_observations WHERE observation_id=? ORDER BY recorded_at DESC LIMIT 1",
            (oid,),
        ).fetchone()
        if current is None:
            origin = db.execute(
                "SELECT id FROM imports WHERE sha256=? ORDER BY created_at DESC LIMIT 1",
                (entry["normalized"]["source_sha256"],),
            ).fetchone()
            record_observations(
                db,
                origin["id"] if origin else row["import_id"],
                entry["normalized"]["source_sha256"],
                [{"source": entry["source"], "disposition": "lead", "reason": ""}],
            )
            current = db.execute(
                "SELECT * FROM intake_observations WHERE observation_id=? ORDER BY recorded_at DESC LIMIT 1",
                (oid,),
            ).fetchone()
        if current is None:
            continue  # Isolated demo roots have no public-domain memory.
        days = set(json.loads(prior["seen_days"])) if prior else set()
        days.add(stamp[:10])
        first = min(prior["first_seen"] or stamp, stamp) if prior else stamp
        last = max(prior["last_seen"] or stamp, stamp) if prior else stamp
        selected = prior if prior and prior["last_seen"] > stamp else current
        handled = prior["handled_case_id"] if prior else ""
        db.execute(
            "DELETE FROM intake_observations WHERE (entity_id=? AND signal_key=?) OR observation_id=?",
            (row["entity_id"], key, oid),
        )
        db.execute(
            """INSERT INTO intake_observations
            (import_id,observation_id,root_domain,disposition,reason,observed_at,summary,recorded_at,
             entity_id,signal_key,first_seen,last_seen,seen_days,handled_case_id)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                selected["import_id"],
                selected["observation_id"],
                selected["root_domain"],
                "lead",
                reason,
                selected["observed_at"],
                selected["summary"],
                now(),
                row["entity_id"],
                key,
                first,
                last,
                dump(sorted(days)),
                handled,
            ),
        )


def _prune(db, entries, keep):
    for entry in entries:
        oid = entry["normalized"]["observation_ref"]
        if oid in keep:
            continue
        from .ownership import available as ownership_available

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


def _retire(db, row, successor, reason, keep=()):
    entries, _ = origin_entries(db, row)
    from .awareness import available, finding_ids

    if reason == "ignored" and available(db):
        for entry in entries:
            for fid in finding_ids(entry, db):
                db.execute(
                    "UPDATE awareness_findings SET workflow='ignored' WHERE id=? AND workflow='unworked'",
                    (fid,),
                )
    for entry in entries:
        db.execute(
            "UPDATE intake_observations SET disposition='lead',reason=? WHERE entity_id=? AND signal_key=?",
            (reason, row["entity_id"], signature(entry)),
        )
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


def _legacy_reconcile(db, lead_id):
    row = db.execute("SELECT * FROM lead_queue WHERE id=?", (lead_id,)).fetchone()
    if not row or not row["qualified"] or not row["entity_id"] or row["status"] == "assigned":
        return lead_id
    entries, fallback = origin_entries(db, row)
    if not entries:
        current = db.execute(
            "SELECT id FROM lead_queue WHERE entity_id=? AND qualified=1 AND status IN ('pending','deferred') AND superseded_by='' AND suppression_reason='' ORDER BY observation_day DESC,created_at DESC,id DESC LIMIT 1",
            (row["entity_id"],),
        ).fetchone()
        return current["id"] if current else lead_id
    day = max(observed(e, fallback)[:10] for e in entries)
    db.execute("UPDATE lead_queue SET observation_day=? WHERE id=?", (day, lead_id))
    incoming = {signature(e): e for e in sorted(entries, key=lambda e: observed(e, fallback))}
    prior_rows = db.execute(
        "SELECT * FROM lead_queue WHERE entity_id=? AND id<>? AND qualified=1 AND superseded_by='' AND suppression_reason='' AND status IN ('pending','deferred') ORDER BY observation_day,created_at,id",
        (row["entity_id"], lead_id),
    ).fetchall()
    prior_keys, candidates = set(), {}
    for old in prior_rows:
        old_entries, _ = origin_entries(db, old)
        prior_keys.update(signature(e) for e in old_entries)
        if old["observation_day"] == day:
            candidates.update({signature(e): e for e in old_entries})
    _remember(db, row, entries, fallback)
    # Legacy scopes and reports started outside Leads still own their findings.
    for old in db.execute(
        "SELECT e.payload,ce.case_id FROM entries e JOIN case_entries ce ON ce.entry_id=e.id WHERE e.lead_id=?",
        (row["entity_id"],),
    ):
        db.execute(
            "UPDATE intake_observations SET handled_case_id=? WHERE entity_id=? AND signal_key=?",
            (old["case_id"], row["entity_id"], signature(json.loads(old["payload"]))),
        )
    latest = db.execute(
        "SELECT id,observation_day FROM lead_queue WHERE entity_id=? AND qualified=1 ORDER BY observation_day DESC,created_at DESC,id DESC LIMIT 1",
        (row["entity_id"],),
    ).fetchone()
    if latest["observation_day"] > day:
        _retire(db, row, latest["id"], "superseded")
        for old in prior_rows:
            for entry in origin_entries(db, old)[0]:
                db.execute(
                    "UPDATE intake_observations SET disposition='lead',reason='' WHERE entity_id=? AND signal_key=?",
                    (row["entity_id"], signature(entry)),
                )
        return latest["id"]
    handled = {
        r["signal_key"]
        for r in db.execute(
            "SELECT signal_key FROM intake_observations WHERE entity_id=? AND handled_case_id<>''",
            (row["entity_id"],),
        )
    }
    # Keep complementary report types from the same observation day; select the
    # newest duplicate within that day even when files arrive out of order.
    for key, entry in incoming.items():
        if key not in candidates or observed(entry, fallback) >= observed(
            candidates[key], fallback
        ):
            candidates[key] = entry
    active = {key: value for key, value in candidates.items() if key not in handled}
    fingerprint = hashlib.sha256(dump(sorted(active)).encode()).hexdigest()
    ignored = (
        row["suppression_reason"] == "ignored"
        or db.execute(
            "SELECT 1 FROM lead_queue WHERE entity_id=? AND suppression_reason='ignored' AND signal_hash=? LIMIT 1",
            (row["entity_id"], fingerprint),
        ).fetchone()
    )
    keep = {e["normalized"]["observation_ref"] for e in active.values()}
    for old in prior_rows:
        _retire(db, old, lead_id, "superseded", keep)
    db.execute(
        "UPDATE lead_queue SET signal_hash=?,delta=? WHERE id=?",
        (
            fingerprint,
            dump(
                {
                    "new": len(set(active) - prior_keys),
                    "repeated": len(set(active) & prior_keys),
                    "retired": len(prior_keys - set(active)),
                }
            ),
            lead_id,
        ),
    )
    if not active or ignored:
        _retire(db, row, "", "ignored" if ignored else "unchanged_reported")
        return lead_id
    from .accretion import score_lead

    config = json.loads(
        db.execute("SELECT config FROM imports WHERE id=?", (row["import_id"],)).fetchone()[
            "config"
        ]
    )
    # Older releases treated shared IPs as identity conflicts. A genuine
    # hostname collision remains reviewable; IP overlap alone never is.
    state = row["association_state"]
    if state == "review" and row["association_basis"] != "Hostname associations conflict":
        state = "known"
    score = json.loads(row["intake_score"])
    incoming_ids = {e["normalized"]["observation_ref"] for e in entries}
    if score and config.get("accretion_policy") and keep != incoming_ids:
        score = score_lead(
            list(active.values()),
            root_domain=row["root_domain"],
            association=(row["entity_id"], state, row["association_basis"], []),
            policy=config["accretion_policy"],
            as_of=config.get("accretion_scored_at") or fallback,
        )

    db.execute(
        "UPDATE lead_queue SET payload=?,intake_score=?,association_state=?,candidates='[]',superseded_by='',suppression_reason='',revision=revision+1,updated_at=? WHERE id=?",
        (dump(list(active.values())), dump(score), state, now(), lead_id),
    )
    for key in active:
        db.execute(
            "UPDATE intake_observations SET disposition='lead',reason='' WHERE entity_id=? AND signal_key=?",
            (row["entity_id"], key),
        )
    for key in handled & candidates.keys():
        db.execute(
            "UPDATE intake_observations SET disposition='lead',reason='unchanged_reported' WHERE entity_id=? AND signal_key=?",
            (row["entity_id"], key),
        )
    _prune(db, entries, keep)
    return lead_id


def reconcile(db, lead_id):
    """One entity queue item, backed by stable individual condition identities."""
    from .awareness import available, conditions, finding_ids, settle_findings
    from .intake.versions import entry_fields

    if not available(db):
        return _legacy_reconcile(db, lead_id)
    row = db.execute("SELECT * FROM lead_queue WHERE id=?", (lead_id,)).fetchone()
    if not row or not row["qualified"] or not row["entity_id"] or row["status"] == "assigned":
        return lead_id
    entries, fallback = origin_entries(db, row)
    if not entries:
        current = db.execute(
            "SELECT id FROM lead_queue WHERE entity_id=? AND qualified=1 AND status IN ('pending','deferred') AND superseded_by='' AND suppression_reason='' ORDER BY observation_day DESC,created_at DESC,id DESC LIMIT 1",
            (row["entity_id"],),
        ).fetchone()
        return current["id"] if current else lead_id
    day = max((observed(e, fallback)[:10] for e in entries), default=fallback[:10])
    db.execute("UPDATE lead_queue SET observation_day=? WHERE id=?", (day, lead_id))
    _remember(db, row, entries, fallback)
    settle_findings(db, {fid for entry in entries for fid in finding_ids(entry, db)})
    prior_rows = db.execute(
        "SELECT * FROM lead_queue WHERE entity_id=? AND id<>? AND qualified=1 AND status IN ('pending','deferred') AND superseded_by='' AND suppression_reason='' ORDER BY observation_day,created_at,id",
        (row["entity_id"], lead_id),
    ).fetchall()
    candidates, prior_ids = {}, set()
    all_rows = [
        *prior_rows,
        db.execute("SELECT * FROM lead_queue WHERE id=?", (lead_id,)).fetchone(),
    ]
    for candidate in all_rows:
        source_entries, source_fallback = origin_entries(db, candidate)
        for entry in source_entries:
            ids = finding_ids(entry, db)
            if candidate["id"] != lead_id:
                prior_ids.update(ids)
            for fid, (condition, _) in zip(ids, conditions(entry)):
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
        if finding and finding["admitted"] and finding["workflow"] == "unworked":
            active[fid] = value
    winner = max(all_rows, key=lambda r: (r["observation_day"], r["created_at"], r["id"]))
    grouped = {}
    for fid, (_, endpoints) in active.items():
        for _, entry, condition in endpoints.values():
            oid = entry["normalized"]["observation_ref"]
            if oid not in grouped:
                copied = json.loads(dump(entry))
                copied["normalized"]["active_conditions"] = []
                copied["normalized"]["active_cves"] = []
                grouped[oid] = copied
            grouped[oid]["normalized"]["active_conditions"].append(condition)
            if condition.startswith("CVE-"):
                grouped[oid]["normalized"]["active_cves"].append(condition)
    keep = set(grouped)
    for old in all_rows:
        if old["id"] != winner["id"]:
            _retire(db, old, winner["id"], "superseded", keep)
    if not grouped:
        _retire(db, winner, "", "unchanged_reported")
        return winner["id"]
    fingerprint = hashlib.sha256(dump(sorted(active)).encode()).hexdigest()
    config = json.loads(
        db.execute("SELECT config FROM imports WHERE id=?", (winner["import_id"],)).fetchone()[
            "config"
        ]
    )
    score = json.loads(winner["intake_score"] or "{}")
    state = winner["association_state"]
    if state == "review" and winner["association_basis"] != "Hostname associations conflict":
        state = "known"
    winner_findings = {fid for e in origin_entries(db, winner)[0] for fid in finding_ids(e, db)}
    if config.get("accretion_policy") and set(active) != winner_findings:
        from .accretion import score_lead

        score = score_lead(
            list(grouped.values()),
            root_domain=winner["root_domain"],
            association=(winner["entity_id"], state, winner["association_basis"], []),
            policy=config["accretion_policy"],
            as_of=config.get("accretion_scored_at") or fallback,
        )
    db.execute(
        "UPDATE lead_queue SET payload=?,intake_score=?,association_state=?,candidates='[]',superseded_by='',suppression_reason='',signal_hash=?,delta=?,revision=revision+1,updated_at=? WHERE id=?",
        (
            dump(list(grouped.values())),
            dump(score),
            state,
            fingerprint,
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


def migrate_current_queue(db):
    rows = db.execute(
        "SELECT * FROM lead_queue WHERE qualified=1 ORDER BY created_at,id"
    ).fetchall()
    # Retain memory before retiring any old rows or pruning unworked entries.
    for row in rows:
        entries, fallback = origin_entries(db, row)
        day = max((observed(e, fallback)[:10] for e in entries), default=fallback[:10])
        db.execute("UPDATE lead_queue SET observation_day=? WHERE id=?", (day, row["id"]))
        if row["status"] == "dismissed":
            db.execute(
                "UPDATE lead_queue SET suppression_reason='ignored',signal_hash=? WHERE id=?",
                (
                    hashlib.sha256(
                        dump(sorted({signature(e) for e in entries})).encode()
                    ).hexdigest(),
                    row["id"],
                ),
            )
        _remember(db, row, entries, fallback)
    for row in db.execute(
        "SELECT id FROM lead_queue WHERE qualified=1 AND status<>'assigned' ORDER BY observation_day DESC,created_at DESC,id DESC"
    ).fetchall():
        reconcile(db, row["id"])


def merge_entity_memory(db, source_id, target_id):
    from .awareness import available, merge_entities

    if available(db):
        merge_entities(db, source_id, target_id)
    for row in db.execute(
        "SELECT * FROM intake_observations WHERE entity_id=?", (source_id,)
    ).fetchall():
        prior = db.execute(
            "SELECT * FROM intake_observations WHERE entity_id=? AND signal_key=?",
            (target_id, row["signal_key"]),
        ).fetchone()
        if prior:
            keep, drop = (prior, row) if prior["last_seen"] >= row["last_seen"] else (row, prior)
            days = sorted(set(json.loads(prior["seen_days"])) | set(json.loads(row["seen_days"])))
            db.execute(
                "DELETE FROM intake_observations WHERE import_id=? AND observation_id=?",
                (drop["import_id"], drop["observation_id"]),
            )
            db.execute(
                "UPDATE intake_observations SET entity_id=?,first_seen=?,last_seen=?,seen_days=?,handled_case_id=? WHERE import_id=? AND observation_id=?",
                (
                    target_id,
                    min(prior["first_seen"], row["first_seen"]),
                    max(prior["last_seen"], row["last_seen"]),
                    dump(days),
                    prior["handled_case_id"] or row["handled_case_id"],
                    keep["import_id"],
                    keep["observation_id"],
                ),
            )
        else:
            db.execute(
                "UPDATE intake_observations SET entity_id=? WHERE import_id=? AND observation_id=?",
                (target_id, row["import_id"], row["observation_id"]),
            )
    db.execute("DELETE FROM entity_contact_queue WHERE entity_id=?", (source_id,))
    for row in db.execute(
        "SELECT id FROM lead_queue WHERE entity_id=? AND status IN ('pending','deferred') AND qualified=1 ORDER BY observation_day DESC,created_at DESC,id DESC",
        (target_id,),
    ).fetchall():
        reconcile(db, row["id"])
