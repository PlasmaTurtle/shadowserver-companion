"""Reviewed ownership transfers and explicit finding reactivation."""

from contextlib import closing
from dataclasses import asdict
import hashlib
import json

from ..primitives import dump, now, uid
from ..repositories.entities import EntityRepository
from ..ownership import available, ensure_asset


def _token(value):
    return hashlib.sha256(dump(value).encode()).hexdigest()


def _reason(value):
    value = str(value or "").strip()
    if not value or len(value) > 5000:
        raise ValueError("Explain the correction in 1–5,000 characters")
    return value


class EntityLifecycle:
    def __init__(self, store):
        self.store = store
        self.repository = EntityRepository(store)

    def _entity(self, db, entity_id):
        if not available(db):
            raise ValueError(
                "Upgrade the workspace before changing ownership or restoring findings"
            )
        row = self.repository.active(db, entity_id)
        if not row:
            raise ValueError("The business changed or was combined. Reload before continuing")
        return row

    def _transfer_plan(self, db, entity_id, hostname, target_id):
        from ..awareness import hostname as normalize
        from ..intake.domains import root_domain

        source, target = self._entity(db, entity_id), self._entity(db, target_id)
        name = normalize(hostname)
        root = root_domain(name)
        if not name or not root or source["id"] == target["id"]:
            raise ValueError("Select a valid hostname and a different active business")
        if source["demo"] != target["demo"]:
            raise ValueError("Demonstration and working assets cannot be transferred together")
        assets = [
            dict(r)
            for r in db.execute(
                "SELECT * FROM awareness_assets WHERE "
                + ("root_domain=?" if name == root else "hostname=?")
                + " ORDER BY id",
                (name,),
            )
        ]
        group = db.execute("SELECT * FROM domain_groups WHERE root_domain=?", (root,)).fetchone()
        if not assets and not (name == root and group and group["entity_id"] == entity_id):
            raise ValueError("This hostname is not associated with the source business")
        if any(r["entity_id"] not in (None, entity_id) for r in assets) or (
            name == root and group and group["entity_id"] != entity_id
        ):
            raise ValueError(
                "An affected hostname already belongs to another business. Review the individual associations first"
            )
        affected_names = {r["hostname"] for r in assets} | {name}
        queues = []
        for row in db.execute(
            "SELECT * FROM lead_queue WHERE entity_id=? AND status IN('pending','deferred') AND superseded_by='' AND suppression_reason='' ORDER BY id",
            (entity_id,),
        ):
            entries = json.loads(row["payload"])
            affected = [
                e
                for e in entries
                if normalize(e.get("source", {}).get("fields", {}).get("hostname"))
                in affected_names
                or (
                    name == root
                    and root_domain(
                        normalize(e.get("source", {}).get("fields", {}).get("hostname"))
                    )
                    == root
                )
            ]
            if affected:
                queues.append(
                    {
                        "id": row["id"],
                        "revision": row["revision"],
                        "root_domain": row["root_domain"],
                        "affected_observations": len(affected),
                        "remaining_observations": len(entries) - len(affected),
                    }
                )
        cases = [
            dict(r)
            for r in db.execute(
                """SELECT DISTINCT c.id,c.title,c.stage,c.version,c.entity_id,c.certified_report_id FROM cases c JOIN case_entries ce ON ce.case_id=c.id
            JOIN entries e ON e.id=ce.entry_id WHERE c.entity_id=? AND """
                + ("e.root_domain=?" if name == root else "e.hostname=?")
                + " ORDER BY c.id",
                (entity_id, name),
            )
        ]
        plan = {
            "source_entity_id": entity_id,
            "source_name": source["company"] or source["domain"],
            "source_revision": source["draft_revision"],
            "target_entity_id": target_id,
            "target_name": target["company"] or target["domain"],
            "target_revision": target["draft_revision"],
            "hostname": name,
            "scope": "domain" if name == root else "hostname",
            "assets": assets,
            "pending_leads": queues,
            "retained_cases": cases,
            "effective": "On confirmation",
            "historical_evidence": "Existing observations, notification identity, attribution and certified reports remain with the recorded business. New qualifying observations create a separate finding episode. Undated or earlier observations require review.",
        }
        plan["review_token"] = _token(plan)
        return plan

    def transfer_plan(self, entity_id, hostname, target_id):
        with self.store.read_snapshot() as db:
            return self._transfer_plan(db, entity_id, hostname, target_id)

    def transfer(
        self, entity_id, hostname, target_id, source_revision, target_revision, review_token, reason
    ):
        from ..awareness import digest, hostname as normalize
        from ..intake.domains import root_domain
        from ..lead_frontier import reconcile

        reason = _reason(reason)
        actor = self.store.settings().get("analyst_name") or "Local operator"
        with self.store.transaction() as db:
            plan = self._transfer_plan(db, entity_id, hostname, target_id)
            if (plan["source_revision"], plan["target_revision"], plan["review_token"]) != (
                source_revision,
                target_revision,
                review_token,
            ):
                raise ValueError(
                    "An affected association, lead or notification changed. Reload the transfer review"
                )
            stamp, event_id = now(), uid()
            name, root = plan["hostname"], root_domain(plan["hostname"])
            # A root marker allows a future, previously unseen hostname to enter the new episode.
            if not any(a["hostname"] == name for a in plan["assets"]):
                aid = digest(["asset", "hostname:" + name])
                db.execute(
                    "INSERT INTO awareness_assets VALUES(?,?,?,?,?,?,?,?)",
                    (
                        aid,
                        "hostname:" + name,
                        name,
                        root,
                        entity_id,
                        "Explicit domain association",
                        stamp,
                        stamp,
                    ),
                )
                ensure_asset(db, aid, entity_id)
                plan["assets"].append(
                    dict(db.execute("SELECT * FROM awareness_assets WHERE id=?", (aid,)).fetchone())
                )
            db.execute(
                "INSERT OR IGNORE INTO entity_domain_associations(root_domain,entity_id) VALUES(?,?)",
                (root, target_id),
            )
            if name == root:
                db.execute(
                    "UPDATE domain_groups SET entity_id=? WHERE root_domain=? AND entity_id=?",
                    (target_id, root, entity_id),
                )
            for asset in plan["assets"]:
                ensure_asset(db, asset["id"], asset["entity_id"])
                # Resolve the display fallback before changing current ownership.
                # Earlier unknown evidence stays explicitly unknown after this boundary.
                db.execute(
                    "INSERT INTO awareness_observation_owners SELECT o.id,?,COALESCE(ep.episode,''),?,? FROM awareness_observations o LEFT JOIN asset_ownership_episodes ep ON ep.asset_id=o.asset_id AND ep.ended_at IS NULL WHERE o.asset_id=? AND NOT EXISTS(SELECT 1 FROM awareness_observation_owners w WHERE w.observation_id=o.id)",
                    (
                        asset["entity_id"],
                        "association_before_transfer"
                        if asset["entity_id"]
                        else "unresolved_at_transfer",
                        stamp,
                        asset["id"],
                    ),
                )
                db.execute(
                    "UPDATE asset_ownership_episodes SET ended_at=? WHERE asset_id=? AND ended_at IS NULL",
                    (stamp, asset["id"]),
                )
                db.execute(
                    "INSERT INTO asset_ownership_episodes VALUES(?,?,?,?,NULL,?,?)",
                    (asset["id"], event_id, target_id, stamp, "explicit_transfer", event_id),
                )
                db.execute(
                    "UPDATE awareness_assets SET entity_id=?,association_basis='Explicit ownership transfer',updated_at=? WHERE id=?",
                    (target_id, stamp, asset["id"]),
                )
            names = {a["hostname"] for a in plan["assets"]}
            for pending in plan["pending_leads"]:
                row = db.execute("SELECT * FROM lead_queue WHERE id=?", (pending["id"],)).fetchone()
                kept = [
                    e
                    for e in json.loads(row["payload"])
                    if normalize(e.get("source", {}).get("fields", {}).get("hostname")) not in names
                ]
                if kept:
                    db.execute(
                        "UPDATE lead_queue SET payload=?,revision=revision+1,updated_at=? WHERE id=?",
                        (dump(kept), stamp, row["id"]),
                    )
                    reconcile(db, row["id"])
                else:
                    db.execute(
                        "UPDATE lead_queue SET payload='[]',status='dismissed',suppression_reason='ownership_transferred',revision=revision+1,updated_at=? WHERE id=?",
                        (stamp, row["id"]),
                    )
            db.execute(
                "INSERT INTO entity_lifecycle_events VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    event_id,
                    "transfer",
                    entity_id,
                    target_id,
                    name,
                    reason,
                    actor,
                    stamp,
                    dump(plan),
                ),
            )
            for owner in (entity_id, target_id):
                self.repository.touch_profile(db, owner)
                self.store.log(
                    db,
                    "asset_ownership_transferred",
                    f"{name}: {plan['source_name']} → {plan['target_name']}. {reason}",
                    owner,
                )
        self.store.export_all()
        return {
            "event_id": event_id,
            "effective_at": stamp,
            "source_entity_id": entity_id,
            "target_entity_id": target_id,
            "retained_cases": plan["retained_cases"],
        }

    def _reactivation_plan(self, db, entity_id, finding_id):
        entity = self._entity(db, entity_id)
        finding = db.execute(
            """SELECT f.*,a.hostname,a.entity_id current_entity_id FROM awareness_findings f
            JOIN awareness_assets a ON a.id=f.asset_id WHERE f.id=? AND f.entity_id IN(SELECT id FROM leads WHERE id=? OR merged_into=?)""",
            (finding_id, entity_id, entity_id),
        ).fetchone()
        if (
            not finding
            or finding["current_entity_id"] != entity_id
            or finding["workflow"] != "ignored"
            or not finding["admitted"]
        ):
            raise ValueError(
                "Only an approved, dismissed finding still owned by this business can be restored"
            )
        from ..awareness_admission import state_sql

        observations = [
            dict(r)
            for r in db.execute(
                """SELECT DISTINCT o.id,o.observed_at,o.ip,o.summary,o.normalized,s.import_id,s.source_key,s.source_sha256,s.sheet,s.row_number,s.entry_id
            FROM awareness_memberships m JOIN awareness_observations o ON o.id=m.observation_id
            JOIN awareness_sources s ON s.observation_id=o.id JOIN imports i ON i.id=s.import_id
            WHERE m.finding_id=? AND EXISTS(SELECT 1 FROM awareness_admission_events ae WHERE ae.finding_id=m.finding_id AND ae.observation_id=o.id AND ae.import_id=s.import_id AND ae.source_key=s.source_key AND ae.state='admitted') AND """
                + state_sql(db)
                + "='admitted' AND substr(o.observed_at,1,10)=substr(?,1,10) ORDER BY o.observed_at DESC,o.id,i.created_at DESC,s.import_id",
                (finding_id, finding["last_seen"]),
            )
        ]
        # Repeated deliveries are one event; keep a retained source copy for each.
        sources = list({r["id"]: r for r in reversed(observations)}.values())
        if not sources:
            raise ValueError("No retained approved source supports this finding")
        for source in sources:
            current = db.execute(
                "SELECT q.status FROM lead_queue q JOIN awareness_assets a ON a.root_domain=q.root_domain WHERE q.import_id=? AND a.id=? LIMIT 1",
                (source["import_id"], finding["asset_id"]),
            ).fetchone()
            if current and current["status"] == "assigned":
                raise ValueError(
                    "This source is already assigned to a notification. Review that notification instead"
                )
        plan = {
            "entity_id": entity_id,
            "entity_revision": entity["draft_revision"],
            "finding": dict(finding),
            "sources": sources,
            "restored_observations": len(sources),
            "admission_unchanged": True,
        }
        plan["review_token"] = _token(plan)
        return plan

    def reactivation_plan(self, entity_id, finding_id):
        with self.store.read_snapshot() as db:
            plan = self._reactivation_plan(db, entity_id, finding_id)
            return {
                **plan,
                "sources": [
                    {k: v for k, v in s.items() if k not in ("summary", "normalized")}
                    for s in plan["sources"]
                ],
            }

    def _restore_entry(self, db, source, entity_id, root):
        row = db.execute("SELECT * FROM entries WHERE id=?", (source["entry_id"],)).fetchone()
        if row:
            if row["lead_id"] != entity_id:
                raise ValueError("The source belongs to another business")
            entry = json.loads(row["payload"])
        else:
            origin = db.execute(
                "SELECT * FROM imports WHERE id=?", (source["import_id"],)
            ).fetchone()
            path = self.store.path(origin["path"])
            digest = hashlib.sha256()
            try:
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
            except OSError as error:
                raise ValueError(
                    "The retained original source is unavailable; restore it before reactivating this finding"
                ) from error
            if (
                digest.hexdigest() != origin["sha256"]
                or origin["sha256"] != source["source_sha256"]
            ):
                raise ValueError(
                    "The retained original source does not match its recorded checksum"
                )
            from ..intake import read_entries

            original = None
            with closing(read_entries(path, source["sheet"])) as rows:
                for candidate in rows:
                    if candidate.sheet == source["sheet"] and candidate.row == source["row_number"]:
                        original = candidate
                        break
            if original is None:
                raise ValueError("The retained source row could not be found")
            entry = {
                "source": asdict(original),
                "ip": source["ip"],
                "private_ip": False,
                "normalized": json.loads(source["normalized"]),
            }
            from ..intake.versions import entry_fields

            fields = entry_fields(entry)
            db.execute(
                "INSERT INTO entries(id,lead_id,import_id,payload,ip,hostname,tag,version,observed_at,root_domain) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    source["entry_id"],
                    entity_id,
                    source["import_id"],
                    dump(entry),
                    source["ip"],
                    str(fields.get("hostname") or ""),
                    str(fields.get("tag") or ""),
                    str(fields.get("version") or ""),
                    source["observed_at"],
                    root,
                ),
            )
        entry.setdefault("normalized", {}).update(
            observation_ref=source["source_key"], source_sha256=source["source_sha256"]
        )
        return entry

    def reactivate(self, entity_id, finding_id, expected_revision, review_token, reason):
        from ..lead_queue_migration import queue_id
        from ..lead_frontier import reconcile
        from ..intake.domains import root_domain

        reason = _reason(reason)
        actor = self.store.settings().get("analyst_name") or "Local operator"
        with self.store.transaction() as db:
            plan = self._reactivation_plan(db, entity_id, finding_id)
            if (plan["entity_revision"], plan["review_token"]) != (expected_revision, review_token):
                raise ValueError("This finding changed. Reload the restoration review")
            root = root_domain(plan["finding"]["hostname"])
            grouped = {}
            for source in plan["sources"]:
                grouped.setdefault(source["import_id"], []).append(
                    self._restore_entry(db, source, entity_id, root)
                )
            db.execute(
                "UPDATE awareness_findings SET workflow='unworked',handled_case_id='' WHERE id=? AND workflow='ignored'",
                (finding_id,),
            )
            stamp, event_id = now(), uid()
            for import_id, entries in grouped.items():
                row_id = queue_id(import_id, root)
                row = db.execute("SELECT payload FROM lead_queue WHERE id=?", (row_id,)).fetchone()
                if row:
                    combined = {
                        e.get("normalized", {}).get("observation_ref", dump(e)): e
                        for e in json.loads(row["payload"])
                    }
                    combined.update({e["normalized"]["observation_ref"]: e for e in entries})
                    entries = list(combined.values())
                    db.execute(
                        "UPDATE lead_queue SET payload=?,entity_id=?,qualified=1,status='pending',association_state='known',association_basis='Explicit finding reactivation',superseded_by='',suppression_reason='',revision=revision+1,updated_at=? WHERE id=?",
                        (dump(entries), entity_id, stamp, row_id),
                    )
                else:
                    db.execute(
                        "INSERT INTO lead_queue(id,import_id,root_domain,payload,entity_id,qualified,association_state,association_basis,created_at,updated_at) VALUES(?,?,?,?,?,1,'known','Explicit finding reactivation',?,?)",
                        (row_id, import_id, root, dump(entries), entity_id, stamp, stamp),
                    )
                row_id = reconcile(db, row_id)
            db.execute(
                "INSERT INTO entity_lifecycle_events VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    event_id,
                    "reactivation",
                    entity_id,
                    None,
                    finding_id,
                    reason,
                    actor,
                    stamp,
                    dump(
                        {
                            "finding_id": finding_id,
                            "sources": [s["id"] for s in plan["sources"]],
                            "restored_observations": len(plan["sources"]),
                            "admission_unchanged": True,
                        }
                    ),
                ),
            )
            self.repository.touch_profile(db, entity_id)
            self.store.log(
                db,
                "finding_reactivated",
                f"Restored {plan['finding']['condition']} for {plan['finding']['hostname']}. {reason}",
                entity_id,
            )
        self.store.export_all()
        return {
            "event_id": event_id,
            "pending_lead_id": row_id,
            "finding_id": finding_id,
            "admission_unchanged": True,
        }
