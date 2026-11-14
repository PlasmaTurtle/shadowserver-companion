"""Incoming findings and entity association, independent of notification work."""

from __future__ import annotations

from .intake.versions import entry_fields

from dataclasses import asdict
import hashlib
import ipaddress
import json

from .primitives import dump, now
from .lead_queue_migration import queue_id


def _owner(db, entity_id):
    row = db.execute(
        "SELECT id,company,domain FROM leads WHERE id=? AND merged_into IS NULL", (entity_id,)
    ).fetchone()
    return dict(row) if row else None


def association(db, root, entries):
    """Hostnames identify an entity. Shared IPs are dated associations only."""
    from .awareness import available, hostname, _owner as asset_owner
    from .ownership import available as ownership_available, entry_context

    names = {hostname(e.get("source", {}).get("fields", {}).get("hostname")) for e in entries}
    canonical = available(db)
    host_ids = set()
    for name in names or {root.casefold().rstrip(".")}:
        if canonical:
            owner = asset_owner(db, name)
            if owner:
                host_ids.add(owner)
        else:
            host_ids.update(
                r[0]
                for r in db.execute(
                    "SELECT entity_id FROM domain_groups WHERE lower(root_domain)=?",
                    (root.casefold(),),
                )
            )
    if ownership_available(db) and any(
        entry_context(db, entry)["historical_review"] for entry in entries
    ):
        return (
            None,
            "review",
            "Observation predates an ownership transfer or has no reported date",
            sorted(host_ids),
        )
    host_ids = {i for i in host_ids if _owner(db, i)}
    if len(host_ids) == 1:
        entity_id = next(iter(host_ids))
        return entity_id, "known", "Stored hostname association", [entity_id]
    if len(host_ids) > 1:
        return None, "review", "Hostname associations conflict", sorted(host_ids)
    return None, "new", "", []


def register_group(
    db, import_id, root, entries, *, entity_id=None, qualified=False, intake_score=None
):
    entries = [asdict(e) if not isinstance(e, dict) else e for e in entries]
    row_id = queue_id(import_id, root)
    prior = db.execute("SELECT * FROM lead_queue WHERE id=?", (row_id,)).fetchone()
    if prior:
        if intake_score and not json.loads(prior["intake_score"] or "{}"):
            db.execute(
                "UPDATE lead_queue SET intake_score=? WHERE id=?", (dump(intake_score), row_id)
            )
        if qualified and prior["qualified"] and prior["entity_id"] == entity_id:
            source_hash = db.execute(
                "SELECT sha256 FROM imports WHERE id=?", (import_id,)
            ).fetchone()["sha256"]
            if set(_entry_ids(source_hash, entries)) == set(entry_ids(db, prior)):
                return row_id
        if qualified and prior["status"] != "assigned" and not prior["superseded_by"]:
            db.execute(
                "UPDATE lead_queue SET payload=?,entity_id=?,qualified=1,updated_at=? WHERE id=?",
                (dump(entries), entity_id, now(), row_id),
            )
            from .lead_frontier import reconcile

            reconcile(db, row_id)
        return row_id
    matched, state, basis, candidates = association(db, root, entries)
    if intake_score is None:
        source = db.execute(
            "SELECT config,created_at FROM imports WHERE id=?", (import_id,)
        ).fetchone()
        config = json.loads(source["config"]) if source else {}
        if "accretion_policy" in config:
            from .accretion import score_lead

            intake_score = score_lead(
                entries,
                root_domain=root,
                association=(matched, state, basis, candidates),
                policy=config["accretion_policy"],
                as_of=config.get("accretion_scored_at") or source["created_at"],
            )
    stamp = now()
    db.execute(
        """INSERT INTO lead_queue(id,import_id,root_domain,payload,entity_id,qualified,
        association_state,association_basis,candidates,created_at,updated_at,intake_score)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            row_id,
            import_id,
            root,
            dump(entries),
            entity_id or matched,
            int(qualified),
            state,
            basis,
            dump(candidates),
            stamp,
            stamp,
            dump(intake_score or {}),
        ),
    )
    if qualified:
        from .lead_frontier import reconcile

        reconcile(db, row_id)
    return row_id


def entry_ids(db, row):
    source = db.execute("SELECT sha256 FROM imports WHERE id=?", (row["import_id"],)).fetchone()
    return _entry_ids(source["sha256"], json.loads(row["payload"]))


def _entry_ids(source_hash, entries):
    return [
        hashlib.sha256(
            f"{e.get('normalized', {}).get('source_sha256') or source_hash}:{e['source']['sheet']}:{e['source']['row']}".encode()
        ).hexdigest()
        for e in entries
    ]


def _has_pending(db, ids):
    # Keep the complete observation list; only readiness is an existence query.
    for start in range(0, len(ids), 500):
        batch = ids[start : start + 500]
        if db.execute(
            "SELECT 1 FROM entries e WHERE e.id IN ("
            + ",".join("?" for _ in batch)
            + ") AND NOT EXISTS(SELECT 1 FROM case_entries ce WHERE ce.entry_id=e.id) LIMIT 1",
            batch,
        ).fetchone():
            return True
    return False


def _pending_scope(db, ids):
    """Read unassigned IDs and roots in bounded batches, retaining source order."""
    pending = []
    for start in range(0, len(ids), 500):
        batch = ids[start : start + 500]
        rows = db.execute(
            "SELECT e.id,e.root_domain FROM entries e WHERE e.id IN ("
            + ",".join("?" for _ in batch)
            + ") AND NOT EXISTS(SELECT 1 FROM case_entries ce WHERE ce.entry_id=e.id)",
            batch,
        )
        roots = {row["id"]: row["root_domain"] for row in rows}
        pending.extend((identity, roots[identity]) for identity in batch if identity in roots)
    return pending


def _awareness_scope(db, entries):
    """Count source events once across the conditions selected for this lead."""
    from .awareness import available, conditions, finding_ids

    if not available(db):
        return None
    selected, labels = set(), set()
    for entry in entries:
        active = (entry.get("normalized") or {}).get("active_conditions")
        for fid, (condition, _) in zip(finding_ids(entry, db), conditions(entry)):
            if active is None or condition in active:
                selected.add(fid)
                labels.add(condition)
    if not selected:
        return None
    from .awareness_admission import state_sql

    state = state_sql(db)
    result = db.execute(
        "WITH selected AS (SELECT o.id,o.observed_at,max(" + state + "='admitted') approved,"
        "max(" + state + "='legacy_unknown') uncertain FROM awareness_memberships m "
        "JOIN awareness_observations o ON o.id=m.observation_id "
        "WHERE m.finding_id IN(SELECT value FROM json_each(?)) GROUP BY o.id) "
        "SELECT count(*) total,COALESCE(sum(approved),0) approved,"
        "COALESCE(sum(uncertain AND NOT approved),0) legacy_unknown,"
        "count(DISTINCT CASE WHEN approved THEN NULLIF(substr(observed_at,1,10),'') END) days,"
        "min(CASE WHEN approved THEN NULLIF(observed_at,'') END) first_seen,"
        "max(CASE WHEN approved THEN NULLIF(observed_at,'') END) last_seen FROM selected",
        (dump(sorted(selected)),),
    ).fetchone()
    return {**dict(result), "findings": len(selected), "labels": sorted(labels)}


class LeadQueue:
    def __init__(self, store):
        self.store = store

    def _project(self, db, row, *, detail=False):
        item = dict(row)
        entries = json.loads(item.pop("payload"))
        candidate_ids = json.loads(item.pop("candidates"))
        item["intake_score"] = json.loads(item["intake_score"]) or None
        item["delta"] = json.loads(item["delta"])
        job = db.execute(
            "SELECT id,status,error FROM jobs WHERE import_id=? AND domain=?",
            (row["import_id"], row["root_domain"]),
        ).fetchone()
        source = db.execute(
            "SELECT name,sha256 FROM imports WHERE id=?", (row["import_id"],)
        ).fetchone()
        entity = _owner(db, row["entity_id"]) if row["entity_id"] else None
        fields = [entry_fields(e) for e in entries]
        dates = sorted(str(f.get("timestamp") or "") for f in fields if f.get("timestamp"))
        ids = _entry_ids(source["sha256"], entries)
        pending = _has_pending(db, ids)
        scope = _awareness_scope(db, entries)
        # Explicit case creation through any supported route consumes queue scope.
        if row["qualified"] and ids and not pending:
            item["status"] = "assigned"
        item.update(
            domain=row["root_domain"],
            entity_name=(entity["company"] or entity["domain"]) if entity else "",
            hostnames=sorted({str(f.get("hostname") or "") for f in fields if f.get("hostname")}),
            ips=sorted({str(e.get("ip") or "") for e in entries if e.get("ip")}),
            findings=scope["labels"]
            if scope
            else sorted(
                {
                    str(f.get("tag") or f.get("version") or "")
                    for f in fields
                    if f.get("tag") or f.get("version")
                }
            ),
            observations=scope["approved"] if scope else len(entries),
            source_observation_count=scope["total"] if scope else len(entries),
            dark_matter_observations=scope["total"] - scope["approved"] - scope["legacy_unknown"]
            if scope
            else 0,
            legacy_unknown_observation_count=scope["legacy_unknown"] if scope else 0,
            reported_observation_count=scope["total"] if scope else len(entries),
            approved_observation_count=scope["approved"] if scope else len(entries),
            finding_count=scope["findings"] if scope else len(entries),
            observation_days=scope["days"] if scope else len({value[:10] for value in dates}),
            observed_from=(scope["first_seen"] if scope else None) or (dates[0] if dates else ""),
            observed_to=(scope["last_seen"] if scope else None) or (dates[-1] if dates else ""),
            attribution_status="qualified"
            if row["qualified"]
            else (job["status"] if job else "pending"),
            import_name=source["name"],
            job_id=job["id"] if job else None,
            can_start=bool(
                row["qualified"]
                and entity
                and not row["suppression_reason"]
                and not row["superseded_by"]
                and row["association_state"] != "review"
                and pending
                and item["status"] == "pending"
            ),
        )
        if detail:
            item["entries"] = [{"id": i, **e} for i, e in zip(ids, entries)]
            item["candidate_entities"] = [e for i in candidate_ids if (e := _owner(db, i))]
            item["active_cases"] = [
                dict(c)
                for c in db.execute(
                    "SELECT id,title,stage,version FROM cases WHERE entity_id=? AND stage IN ('in_progress','pending_notification') ORDER BY created_at DESC",
                    (row["entity_id"],),
                )
            ]
            item["attribution_error"] = job["error"] if job else ""
            item["shared_ip_associations"] = []
            for ip in item["ips"]:
                for match in db.execute(
                    "SELECT l.id entity_id,COALESCE(NULLIF(l.company,''),l.domain) entity_name,min(e.observed_at) first_seen,max(e.observed_at) last_seen FROM entries e JOIN leads l ON l.id=e.lead_id WHERE e.ip=? AND e.lead_id<>? AND l.merged_into IS NULL GROUP BY l.id",
                    (ip, row["entity_id"]),
                ):
                    item["shared_ip_associations"].append({"ip": ip, **dict(match)})
        return item

    def list(self, status="pending", q=""):
        if status and status not in {"pending", "deferred", "dismissed", "assigned", "all"}:
            raise ValueError("Unknown lead status")
        with self.store.read_snapshot() as db:
            where = " WHERE qualified=1 AND entity_id IS NOT NULL AND association_state<>'review' AND superseded_by='' AND suppression_reason='' AND payload<>'[]'"
            params = []
            if status in {"pending", "deferred", "dismissed"}:
                where += " AND status=?"
                params.append(status)
            rows = db.execute(
                "SELECT * FROM lead_queue"
                + where
                + " ORDER BY CAST(json_extract(intake_score, '$.aggregate') AS REAL) DESC,observation_day DESC,created_at DESC,id",
                params,
            ).fetchall()
            items = [self._project(db, r) for r in rows]
        if status and status != "all":
            items = [r for r in items if r["status"] == status]
        if q:
            query = q.casefold()
            items = [
                r
                for r in items
                if query
                in " ".join(
                    [r["domain"], r["entity_name"], *r["hostnames"], *r["ips"], *r["findings"]]
                ).casefold()
            ]
        return items

    def detail(self, lead_id):
        with self.store.read_snapshot() as db:
            row = db.execute("SELECT * FROM lead_queue WHERE id=?", (lead_id,)).fetchone()
            if not row:
                raise ValueError("Lead not found")
            return self._project(db, row, detail=True)

    @staticmethod
    def require(db, lead_id, revision):
        row = db.execute("SELECT * FROM lead_queue WHERE id=?", (lead_id,)).fetchone()
        if (
            not row
            or row["revision"] != revision
            or row["superseded_by"]
            or row["suppression_reason"]
        ):
            raise ValueError("This lead changed. Reload before saving.")
        return row

    def disposition(self, lead_id, revision, status):
        if status not in {"pending", "deferred", "dismissed"}:
            raise ValueError("Unknown lead disposition")
        with self.store.transaction() as db:
            row = self.require(db, lead_id, revision)
            if self._project(db, row)["status"] == "assigned":
                raise ValueError("This lead is already assigned to a notification")
            if status == "dismissed":
                from .lead_frontier import _retire

                _retire(db, row, "", "ignored")
            else:
                db.execute(
                    "UPDATE lead_queue SET status=?,revision=revision+1,updated_at=? WHERE id=?",
                    (status, now(), lead_id),
                )
            self.store.log(
                db, "lead_disposition", f"Lead {row['root_domain']}: {status}", row["entity_id"]
            )
        return self.detail(lead_id)

    def start(self, lead_id, revision, *, case_id=None, expected_case_version=None):
        from .cases import Cases
        from .repositories.reviews import SectionReviewRepository

        cases = Cases(self.store)
        with self.store.transaction() as db:
            row = self.require(db, lead_id, revision)
            current = self._project(db, row)
            if not current["can_start"]:
                raise ValueError("Resolve association and attribution before starting this lead")
            pending = _pending_scope(db, entry_ids(db, row))
            ids = [identity for identity, _ in pending]
            if case_id:
                if expected_case_version is None:
                    raise ValueError("The current notification version is required")
                case = cases.require(db, case_id, expected_case_version, editable=True)
                if case["entity_id"] != row["entity_id"]:
                    raise ValueError("Select a notification for this entity")
                frozen = SectionReviewRepository(self.store).active(case_id, db)
                if frozen:
                    raise ValueError("Reopen the frozen report sections before adding findings")
                roots = {}
                for identity, root in pending:
                    roots.setdefault(root, []).append(identity)
                added = sum(
                    cases.repository.extend_scope(db, case_id, root, scope, intake_lead_id=lead_id)
                    for root, scope in roots.items()
                )
                if added:
                    draft = json.loads(case["draft"])
                    draft.update(reviewed=False, cve_reviewed=False)
                    entity = db.execute(
                        "SELECT draft FROM leads WHERE id=?", (row["entity_id"],)
                    ).fetchone()
                    records = {r["id"]: r for r in draft.get("cve_records", [])}
                    for record in json.loads(entity["draft"]).get("cve_records", []):
                        records.setdefault(record["id"], record)
                    from .intelligence.identifiers import identifiers

                    reported = set(identifiers(cases.repository.reported_tags(db, case_id)))
                    from .intelligence.local import initial_records

                    draft["cve_records"] = initial_records(
                        self.store,
                        reported,
                        [r for k, r in records.items() if k in reported],
                        db=db,
                        preserve_existing=True,
                    )
                    cases.repository.replace_working_draft(db, case_id, draft)
            else:
                if cases.repository.open_for_entity(db, row["entity_id"]):
                    raise ValueError("Add these findings to the existing editable notification")
                case_id = cases._create(db, row["entity_id"], entry_ids=ids, intake_lead_id=lead_id)
            db.execute(
                "UPDATE lead_queue SET status='assigned',case_id=?,revision=revision+1,updated_at=? WHERE id=?",
                (case_id, now(), lead_id),
            )
            self.store.log(
                db,
                "lead_assigned",
                f"Assigned {row['root_domain']} findings to notification",
                row["entity_id"],
                case_id,
            )
        return {"entity_id": row["entity_id"], "case_id": case_id}

    def associate(self, lead_id, revision, entity_id):
        from .repositories.entities import EntityRepository

        repository = EntityRepository(self.store)
        with self.store.transaction() as db:
            row = self.require(db, lead_id, revision)
            target = _owner(db, entity_id)
            if not target:
                raise ValueError("Entity not found")
            if self._project(db, row)["status"] == "assigned":
                raise ValueError("This lead already belongs to a notification")
            source_id = row["entity_id"]
            if row["qualified"] and source_id and source_id != entity_id:
                source = _owner(db, source_id)
                if (
                    db.execute("SELECT 1 FROM cases WHERE entity_id=?", (source_id,)).fetchone()
                    or db.execute(
                        "SELECT count(*) FROM domain_groups WHERE entity_id=?", (source_id,)
                    ).fetchone()[0]
                    != 1
                ):
                    raise ValueError(
                        "This entity has other history. Combine entities explicitly to retain it."
                    )
                a = db.execute("SELECT demo FROM leads WHERE id=?", (source_id,)).fetchone()
                b = db.execute("SELECT demo FROM leads WHERE id=?", (entity_id,)).fetchone()
                if a["demo"] != b["demo"]:
                    raise ValueError("Demonstration and working entities cannot be combined")
                repository.transfer_records(db, source_id, entity_id)
                from .lead_frontier import merge_entity_memory

                merge_entity_memory(db, source_id, entity_id)
                db.execute(
                    "UPDATE lead_queue SET entity_id=? WHERE entity_id=?", (entity_id, source_id)
                )
                target_draft = json.loads(
                    db.execute("SELECT draft FROM leads WHERE id=?", (entity_id,)).fetchone()[
                        "draft"
                    ]
                )
                source_draft = json.loads(
                    db.execute("SELECT draft FROM leads WHERE id=?", (source_id,)).fetchone()[
                        "draft"
                    ]
                )
                records = {r["id"]: r for r in source_draft.get("cve_records", [])}
                records.update({r["id"]: r for r in target_draft.get("cve_records", [])})
                target_draft["cve_records"] = list(records.values())
                db.execute(
                    "UPDATE leads SET draft=?,draft_revision=draft_revision+1,updated_at=? WHERE id=?",
                    (dump(target_draft), now(), entity_id),
                )
                self.store.log(
                    db,
                    "entity_associated",
                    f"Associated {source['domain']} with {target['company'] or target['domain']}",
                    entity_id,
                )
            db.execute(
                "UPDATE lead_queue SET entity_id=?,association_state='known',association_basis='Analyst-selected entity',candidates=?,revision=revision+1,updated_at=? WHERE id=?",
                (entity_id, dump([entity_id]), now(), lead_id),
            )
            self.store.log(
                db, "lead_associated", f"Associated {row['root_domain']} with entity", entity_id
            )
            from .lead_frontier import reconcile

            current_id = reconcile(db, lead_id)
        self.store.export_all()
        return self.detail(current_id)


def save_ip_association(store, entity_id, ip, revision):
    address = ipaddress.ip_address(ip)
    if not address.is_global:
        raise ValueError("Use a public IP address")
    actor = store.settings().get("analyst_name") or "Local operator"
    with store.transaction() as db:
        row = db.execute(
            "SELECT * FROM leads WHERE id=? AND merged_into IS NULL", (entity_id,)
        ).fetchone()
        if not row or row["draft_revision"] != revision:
            raise ValueError("This entity changed. Reload before saving.")
        db.execute(
            "INSERT INTO entity_ip_associations VALUES(?,?,?,?) ON CONFLICT(ip,entity_id) DO NOTHING",
            (str(address), entity_id, actor, now()),
        )
        db.execute(
            "UPDATE leads SET draft_revision=draft_revision+1,updated_at=? WHERE id=?",
            (now(), entity_id),
        )
        store.log(db, "entity_ip_associated", f"Saved entity association for {address}", entity_id)
