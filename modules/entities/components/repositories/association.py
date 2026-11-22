"""Persist an already-authorized entity/domain group in the caller's transaction.

Accretion owns qualification/admission. This owner retains entity anchors and
source rows, preserving historical case references and manual profile decisions.
"""

import hashlib
import json

from modules.accretion.components.intake.identity import observed, signature
from modules.accretion.components.intake.versions import entry_fields
from modules.workspace.components.primitives import dump, now, uid
from .entities import EntityRepository


def _fresh_anchor(db, previous, anchor, stamp):
    if not previous:
        return True
    payload = json.loads(previous["payload"])
    if observed(anchor, stamp) < observed(payload, ""):
        return False
    return not (
        signature(payload) == signature(anchor)
        and db.execute(
            "SELECT 1 FROM case_entries WHERE entry_id=? LIMIT 1", (previous["id"],)
        ).fetchone()
    )


def record_group(
    db,
    root_domain,
    entries,
    attribution,
    *,
    import_id,
    source_hash,
    owner=None,
    owner_state="new",
    cve_records=None,
    demo=False,
):
    """Return (entity_id, inserted_rows); no provider, score or admission work."""
    anchor_index = next((i for i, e in enumerate(entries) if e["ip"] == attribution["ip"]), 0)
    anchor = entries[anchor_index]
    attribution_json, stamp = dump(attribution), now()
    existing = (
        db.execute(
            "SELECT * FROM leads WHERE id=? AND merged_into IS NULL",
            (owner,),
        ).fetchone()
        if owner and owner_state == "known"
        else None
    )
    if not existing:
        existing = db.execute(
            "SELECT l.* FROM leads l JOIN domain_groups g ON g.entity_id=l.id WHERE lower(g.root_domain)=?",
            (root_domain.casefold(),),
        ).fetchone()
    lead_id = existing["id"] if existing else uid()
    ids = [
        hashlib.sha256(
            f"{source_hash}:{e['source']['sheet']}:{e['source']['row']}".encode()
        ).hexdigest()
        for e in entries
    ]
    if not existing:
        db.execute(
            "INSERT INTO leads(id,domain,created_at,updated_at,attribution,attribution_entry_id,demo,company) VALUES(?,?,?,?,?,?,?,?)",
            (
                lead_id,
                root_domain,
                stamp,
                stamp,
                attribution_json,
                ids[anchor_index],
                int(demo),
                str(entry_fields(anchor)["hostname"]),
            ),
        )
    prior_group = db.execute(
        "SELECT e.id,e.payload,g.root_domain FROM domain_groups g JOIN entries e ON e.id=g.attribution_entry_id WHERE lower(g.root_domain)=?",
        (root_domain.casefold(),),
    ).fetchone()
    group_key = prior_group["root_domain"] if prior_group else root_domain
    fresh_group = _fresh_anchor(db, prior_group, anchor, stamp)
    if (
        fresh_group
        or not db.execute(
            "SELECT 1 FROM entity_domain_associations WHERE root_domain=? AND entity_id=? AND attribution_entry_id IS NOT NULL",
            (group_key, lead_id),
        ).fetchone()
    ):
        db.execute(
            "INSERT INTO entity_domain_associations(root_domain,entity_id,attribution_entry_id,attribution) VALUES(?,?,?,?) ON CONFLICT(root_domain,entity_id) DO UPDATE SET attribution_entry_id=excluded.attribution_entry_id,attribution=excluded.attribution",
            (group_key, lead_id, ids[anchor_index], attribution_json),
        )
    if fresh_group:
        db.execute(
            "INSERT INTO domain_groups VALUES(?,?,?,?) ON CONFLICT(root_domain) DO UPDATE SET attribution_entry_id=excluded.attribution_entry_id,attribution=excluded.attribution WHERE domain_groups.entity_id=excluded.entity_id",
            (group_key, lead_id, ids[anchor_index], attribution_json),
        )
    inserted = 0
    for entry_id, entry in zip(ids, entries):
        f = entry_fields(entry)
        cursor = db.execute(
            "INSERT INTO entries(id,lead_id,import_id,payload,ip,hostname,tag,version,observed_at,root_domain) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING",
            (
                entry_id,
                lead_id,
                import_id,
                dump(entry),
                entry["ip"],
                str(f["hostname"]),
                str(f["tag"]),
                str(f.get("version") or ""),
                str(f.get("timestamp") or ""),
                group_key,
            ),
        )
        inserted += cursor.rowcount
        db.execute(
            "INSERT INTO hostnames(name,root_domain) VALUES(?,?) ON CONFLICT(name) DO NOTHING",
            (str(f["hostname"]), group_key),
        )
    previous_primary = (
        db.execute(
            "SELECT id,payload FROM entries WHERE id=?", (existing["attribution_entry_id"],)
        ).fetchone()
        if existing
        else None
    )
    fresh_primary = _fresh_anchor(db, previous_primary, anchor, stamp)
    db.execute(
        "UPDATE leads SET attribution=?,attribution_entry_id=?,updated_at=?,new_observations=new_observations+? WHERE id=?",
        (
            attribution_json if fresh_primary else existing["attribution"],
            ids[anchor_index] if fresh_primary else existing["attribution_entry_id"],
            stamp,
            inserted if existing and existing["status"] == "completed" and fresh_primary else 0,
            lead_id,
        ),
    )
    if inserted or cve_records:
        draft = json.loads(existing["draft"]) if existing else {}
        if existing:
            draft["reviewed"] = False
            draft["cve_reviewed"] = False
        records = {r["id"]: r for r in draft.get("cve_records", [])}
        records.update({r["id"]: r for r in cve_records or []})
        draft["cve_records"] = list(records.values())
        db.execute(
            "UPDATE leads SET draft=?,draft_revision=draft_revision+? WHERE id=?",
            (dump(draft), int(bool(existing)), lead_id),
        )
    EntityRepository.validate_attribution_entry(db, lead_id)
    return lead_id, inserted
