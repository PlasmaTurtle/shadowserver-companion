"""Current asset associations and immutable observation ownership episodes."""

import hashlib
import json
from modules.workspace.components.primitives import dump, now
from modules.accretion.components.awareness_identity import hostname, timestamp
from modules.tools.components.network_identity import root_domain


def available(db):
    return bool(
        db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='awareness_observation_owners'"
        ).fetchone()
    ) and any(
        r[1] == "ownership_episode" for r in db.execute("PRAGMA table_info(awareness_findings)")
    )


def hostname_owner(db, name):
    """Resolve exact and root hostname ownership in an initialized Workspace."""
    if not name:
        return None
    exact = db.execute(
        "SELECT entity_id FROM awareness_assets WHERE asset_key=? AND entity_id IS NOT NULL",
        ("hostname:" + name,),
    ).fetchone()
    if exact:
        return exact[0]
    root = root_domain(name)
    manual = db.execute(
        "SELECT entity_id FROM awareness_assets WHERE asset_key=? AND entity_id IS NOT NULL",
        ("hostname:" + root,),
    ).fetchone()
    if manual:
        return manual[0]
    known = db.execute(
        "SELECT g.entity_id FROM domain_groups g JOIN leads l ON l.id=g.entity_id WHERE g.root_domain=? AND l.merged_into IS NULL",
        (root,),
    ).fetchone()
    return known[0] if known else None


class OwnershipChanged(ValueError):
    """A concurrent ownership change invalidated a qualification snapshot."""


def _association_context(db, root, entries):
    names = [hostname(e.get("source", {}).get("fields", {}).get("hostname")) for e in entries]
    host_ids = {
        owner
        for name in set(names) or {root.casefold().rstrip(".")}
        if (owner := hostname_owner(db, name))
    }
    episodes = set()
    for name, entry in zip(names, entries):
        observed = entry_context(db, entry, schema_ready=True)
        episodes.add((name, observed["active_ownership_episode"]))
        if observed["historical_review"]:
            return (
                None,
                "review",
                "Observation predates an ownership transfer or has no reported date",
                sorted(host_ids),
            ), episodes
    host_ids = {
        identity
        for identity in host_ids
        if db.execute(
            "SELECT 1 FROM leads WHERE id=? AND merged_into IS NULL", (identity,)
        ).fetchone()
    }
    if len(host_ids) == 1:
        entity_id = next(iter(host_ids))
        return (entity_id, "known", "Stored hostname association", [entity_id]), episodes
    if len(host_ids) > 1:
        return (None, "review", "Hostname associations conflict", sorted(host_ids)), episodes
    return (None, "new", "", []), episodes


def association(db, root, entries):
    """Current hostname ownership, with replay and dated transfer safeguards.

    Workspace initializes the complete schema before this API is called. Shared
    IP addresses never establish ownership; historical/undated transferred rows
    require review even when the current hostname has one unambiguous owner.
    """
    current, _ = _association_context(db, root, entries)
    return current


def _qualification_token(root, current, episodes):
    return hashlib.sha256(
        dump(
            {
                "root_domain": root.casefold().rstrip("."),
                "entity_id": current[0],
                "state": current[1],
                "candidates": current[3],
                "active_episodes": sorted(episodes),
            }
        ).encode()
    ).hexdigest()


def check_qualification_context(db, root, entries, expected_token):
    """Recheck the bound owner/episodes and return the current association tuple.

    Evidence refreshes do not change this token. A transfer away and back does;
    the caller must restart qualification rather than rebind captured evidence.
    """
    current, episodes = _association_context(db, root, entries)
    if _qualification_token(root, current, episodes) != expected_token:
        raise OwnershipChanged(
            "Ownership changed while this group was qualifying; retry qualification"
        )
    return current


def qualification_context(db, root, entries):
    """Return current local ownership plus its saved proof reference.

    The caller owns the read snapshot. Attribution alone validates the saved
    proof; reading this context performs no provider or evidence-store work.
    """
    current, episodes = _association_context(db, root, entries)
    owner, state, basis, candidates = current
    saved = None
    if state == "known":
        saved = db.execute(
            "SELECT attribution FROM entity_domain_associations WHERE lower(root_domain)=? AND entity_id=?",
            (root.casefold(), owner),
        ).fetchone()
    try:
        proof = json.loads(saved["attribution"]) if saved else None
    except (ValueError, TypeError):
        proof = None
    return {
        "entity_id": owner,
        "state": state,
        "basis": basis,
        "candidates": candidates,
        "saved_proof": proof,
        "ownership_token": _qualification_token(root, current, episodes),
    }


def finding_id(asset_id, condition, scope, episode=""):
    values = ["finding", asset_id, condition, scope]
    if episode:
        values.append(episode)
    return hashlib.sha256(dump(values).encode()).hexdigest()


def context(
    db, asset_id, name="", observed_at="", source_key="", *, entity_id=None, schema_ready=False
):
    """A replay keeps its recorded owner; undated/old new rows need review after transfer."""
    observed_at = timestamp(observed_at)
    result = {
        "entity_id": entity_id,
        "ownership_episode": "",
        "active_ownership_episode": "",
        "historical_review": False,
    }
    if not schema_ready and not available(db):
        return result
    if source_key:
        prior = db.execute(
            """SELECT own.* FROM awareness_sources s
            JOIN awareness_observation_owners own ON own.observation_id=s.observation_id
            WHERE s.source_key=? ORDER BY s.import_id LIMIT 1""",
            (source_key,),
        ).fetchone()
        if prior:
            current = db.execute(
                "SELECT episode FROM asset_ownership_episodes WHERE asset_id=? AND ended_at IS NULL",
                (asset_id,),
            ).fetchone()
            return {
                "entity_id": prior["entity_id"],
                "ownership_episode": prior["ownership_episode"],
                "active_ownership_episode": current["episode"] if current else "",
                "historical_review": bool(
                    prior["basis"] == "ownership_history_review"
                    or (current and current["episode"] != prior["ownership_episode"])
                ),
            }
    episode = db.execute(
        "SELECT * FROM asset_ownership_episodes WHERE asset_id=? AND ended_at IS NULL", (asset_id,)
    ).fetchone()
    if episode is None and name:
        # A previously unseen hostname inherits a dated domain association, never an IP association.
        root = root_domain(name)
        episode = db.execute(
            """SELECT ep.* FROM asset_ownership_episodes ep JOIN awareness_assets a ON a.id=ep.asset_id
            WHERE a.asset_key=? AND ep.ended_at IS NULL ORDER BY ep.started_at DESC LIMIT 1""",
            ("hostname:" + root,),
        ).fetchone()
    if episode:
        result.update(
            entity_id=episode["entity_id"],
            ownership_episode=episode["episode"],
            active_ownership_episode=episode["episode"],
        )
        if episode["episode"] and (
            not observed_at or observed_at < timestamp(episode["started_at"])
        ):
            result["historical_review"] = True
            previous = db.execute(
                "SELECT * FROM asset_ownership_episodes WHERE asset_id=? AND ended_at IS NOT NULL",
                (episode["asset_id"],),
            ).fetchall()
            if not previous and name:
                # New child hostnames have no local past interval. Resolve the
                # root's past interval, not its present owner's identity.
                previous = db.execute(
                    "SELECT ep.* FROM asset_ownership_episodes ep JOIN awareness_assets a ON a.id=ep.asset_id WHERE a.asset_key=? AND ep.ended_at IS NOT NULL",
                    ("hostname:" + root_domain(name),),
                ).fetchall()
            eligible = [
                r
                for r in previous
                if not observed_at
                or not r["started_at"]
                or timestamp(r["started_at"]) <= observed_at
            ]
            prior = max(eligible, key=lambda r: timestamp(r["ended_at"]), default=None)
            if prior:
                result.update(entity_id=prior["entity_id"], ownership_episode=prior["episode"])
            else:
                result["entity_id"] = None
            if not observed_at:
                result["entity_id"] = None
    return result


def record_observation(db, observation_id, owner):
    if available(db) and (owner.get("entity_id") is not None or owner.get("historical_review")):
        db.execute(
            "INSERT INTO awareness_observation_owners SELECT ?,?,?,?,? WHERE NOT EXISTS(SELECT 1 FROM awareness_observation_owners WHERE observation_id=?)",
            (
                observation_id,
                owner.get("entity_id"),
                owner.get("ownership_episode", ""),
                "ownership_history_review"
                if owner.get("historical_review")
                else "observation_association",
                now(),
                observation_id,
            ),
        )


def ensure_asset(db, asset_id, entity_id, *, basis="association"):
    if not available(db):
        return
    existing = db.execute(
        "SELECT 1 FROM asset_ownership_episodes WHERE asset_id=? LIMIT 1", (asset_id,)
    ).fetchone()
    if not existing:
        inherited = db.execute(
            "SELECT ep.* FROM awareness_assets a JOIN awareness_assets root ON root.asset_key='hostname:'||a.root_domain JOIN asset_ownership_episodes ep ON ep.asset_id=root.id WHERE a.id=? AND root.id<>a.id AND ep.ended_at IS NULL AND ep.episode<>''",
            (asset_id,),
        ).fetchone()
        if inherited:
            db.execute(
                "INSERT INTO asset_ownership_episodes VALUES(?,?,?,?,NULL,?,?)",
                (
                    asset_id,
                    inherited["episode"],
                    inherited["entity_id"],
                    inherited["started_at"],
                    "domain_association",
                    inherited["event_id"],
                ),
            )
        else:
            db.execute(
                "INSERT OR IGNORE INTO asset_ownership_episodes(asset_id,episode,entity_id,started_at,ended_at,basis,event_id) VALUES(?,'',?,'',NULL,?,'')",
                (asset_id, entity_id, basis),
            )
    # The initial association may qualify previously unowned evidence, but a transfer never does.
    row = db.execute(
        "SELECT episode FROM asset_ownership_episodes WHERE asset_id=? AND ended_at IS NULL",
        (asset_id,),
    ).fetchone()
    if row and not row["episode"] and entity_id:
        db.execute(
            "UPDATE asset_ownership_episodes SET entity_id=? WHERE asset_id=? AND episode='' AND entity_id IS NULL",
            (entity_id, asset_id),
        )
        db.execute(
            "UPDATE awareness_findings SET entity_id=? WHERE asset_id=? AND ownership_episode='' AND entity_id IS NULL",
            (entity_id, asset_id),
        )
        # Existing unknown ownership is explicitly unknown; never relabel recorded observations.


def entry_context(db, entry, *, schema_ready=False):
    from modules.accretion.components.awareness_identity import (
        asset_key,
        digest,
        timestamp,
        source_key,
    )
    from modules.accretion.components.intake.versions import entry_fields

    key, name, _ = asset_key(entry)
    fields = entry_fields(entry)
    normalized = entry.get("normalized") or {}
    observed = timestamp(fields.get("timestamp")) or timestamp(
        (normalized.get("acquisition") or {}).get("report_date")
    )
    return context(
        db,
        digest(["asset", key]),
        name,
        observed,
        source_key(entry, normalized.get("source_sha256", "")),
        schema_ready=schema_ready,
    )


def group_for_entity(db, root, entity_id):
    if available(db):
        row = db.execute(
            "SELECT * FROM entity_domain_associations WHERE root_domain=? AND entity_id=? AND attribution_entry_id IS NOT NULL",
            (root, entity_id),
        ).fetchone()
    else:
        row = db.execute(
            "SELECT * FROM domain_groups WHERE root_domain=? AND entity_id=?", (root, entity_id)
        ).fetchone()
    if not row:
        raise ValueError(
            "This business needs its own approved attribution before starting a notification for this domain"
        )
    return row
