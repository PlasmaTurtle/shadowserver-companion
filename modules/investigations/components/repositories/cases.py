"""Case projections read one snapshot and retain the complete scoped observations.

This repository cannot invoke case commands or recovery. A supplied connection
lets a service read its own uncommitted writes without opening another snapshot.
"""

import json
from modules.workspace.components.primitives import dump, now, uid
from modules.workspace.components.repositories.records import Records
from modules.entities.components.repositories.entities import EntityRepository
from .artifacts import ArtifactRepository
from modules.accretion.components.repositories.intake_scores import pin_case_score


class CaseRepository:
    def __init__(self, store):
        self.store = store
        self.entities = EntityRepository(store)
        self.artifacts = ArtifactRepository(store)

    @staticmethod
    def get(db, case_id):
        return db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()

    def default_id(self, entity_id, db=None):
        if db is None:
            with self.store.read_snapshot() as db:
                return self.default_id(entity_id, db)
        row = Records(db).one(
            """SELECT id FROM cases WHERE entity_id=?
          ORDER BY CASE stage WHEN 'in_progress' THEN 0 WHEN 'pending_notification' THEN 1
          WHEN 'notification_completed' THEN 2 ELSE 3 END,created_at DESC,rowid DESC LIMIT 1""",
            (entity_id,),
        )
        return row["id"] if row else None

    def view(self, case_id, db=None):
        if db is None:
            with self.store.read_snapshot() as db:
                return self.view(case_id, db)
        records = Records(db)
        case = records.one("SELECT * FROM cases WHERE id=?", (case_id,))
        if not case:
            raise ValueError("Notification case not found")
        lead = self.entities.lead(case["entity_id"], db)
        lead["entity_hostnames"] = lead["hostnames"]
        lead["entity_revision"] = lead["draft_revision"]
        # Entity maintenance is independent of the identity used by this report.
        identity = json.loads(case.get("entity_snapshot") or "{}")
        source_entity_id = identity.get("entity_id", case["entity_id"])
        lead["current_entity"] = {
            "company": lead["company"],
            "domain": lead["domain"],
            "entity_profile": lead["entity_profile"],
        }
        for key in ("company", "domain", "entity_profile"):
            if key in identity:
                lead[key] = identity[key]
        lead["case_id"] = case_id
        case["intake_score"] = json.loads(case.get("intake_score") or "{}") or None
        lead["intake_score"] = case["intake_score"]
        lead["case"] = case
        from ..outreach_policy import get_policy
        from modules.entities.components.finding_history import entity_finding_history

        lead["outreach_policy"] = get_policy(db, case_id)
        lead["finding_history"] = entity_finding_history(db, case["entity_id"])
        lead["draft"] = json.loads(case["draft"])
        lead["draft_revision"] = case["draft_revision"]
        lead["status"] = "in_progress" if case["stage"] == "in_progress" else "completed"
        groups = records.all("SELECT * FROM case_groups WHERE case_id=? ORDER BY rowid", (case_id,))
        lead["domain_groups"] = [
            {**g, "entity_id": source_entity_id, "attribution": json.loads(g["attribution"])}
            for g in groups
        ]
        primary = groups[0]["attribution_entry_id"] if groups else None
        rows = records.all(
            """SELECT e.* FROM case_entries ce JOIN entries e ON e.id=ce.entry_id
          WHERE ce.case_id=? ORDER BY ce.rowid""",
            (case_id,),
        )
        rows.sort(key=lambda row: row["id"] != primary)
        from ..case_conditions import overlay

        lead["entries"] = overlay(
            db, case_id, [{**json.loads(r["payload"]), "id": r["id"]} for r in rows]
        )
        lead["attribution_entry_id"] = primary
        lead["attribution"] = json.loads(groups[0]["attribution"]) if groups else {}
        lead["hostnames"] = list(
            {
                r["hostname"]: {"name": r["hostname"], "root_domain": r["root_domain"]}
                for r in rows
            }.values()
        )
        lead["evidence"] = [
            {**record, "lead_id": source_entity_id}
            for record in records.all(
                "SELECT * FROM evidence WHERE case_id=? ORDER BY rowid", (case_id,)
            )
        ]
        lead["reports"] = records.all(
            "SELECT * FROM reports WHERE case_id=? ORDER BY revision DESC", (case_id,)
        )
        for report in lead["reports"]:
            report["files_available"] = self.artifacts.package_available(report)
            report["work_log_available"] = self.artifacts.work_log_available(report)
        lead["history"] = records.all(
            "SELECT * FROM events WHERE case_id=? ORDER BY id DESC", (case_id,)
        )
        lead["attempts"] = records.all(
            "SELECT * FROM contact_attempts WHERE case_id=? ORDER BY occurred_at,recorded_at,rowid",
            (case_id,),
        )
        lead["closure"] = records.one("SELECT * FROM case_closures WHERE case_id=?", (case_id,))
        if lead["closure"]:
            lead["closure"]["files_available"] = self.artifacts.closure_available(lead["closure"])
        lead["cases"] = records.all(
            "SELECT id,title,stage,created_at,delivered_at,closed_at FROM cases WHERE entity_id=? ORDER BY created_at DESC,rowid DESC",
            (case["entity_id"],),
        )
        from ..observation_scope import apply_scope

        lead["scope_root_by_id"] = {row["id"]: row["root_domain"] for row in rows}
        return apply_scope(lead)

    @staticmethod
    def open_for_entity(db, entity_id):
        return db.execute(
            "SELECT * FROM cases WHERE entity_id=? AND stage IN ('in_progress','pending_notification') ORDER BY created_at,rowid",
            (entity_id,),
        ).fetchall()

    @staticmethod
    def creation_entries(db, entity_id):
        rows = db.execute(
            """SELECT e.* FROM entries e WHERE lead_id=? AND NOT EXISTS
          (SELECT 1 FROM case_entries ce WHERE ce.entry_id=e.id) ORDER BY e.rowid""",
            (entity_id,),
        ).fetchall()
        if not rows:
            rows = db.execute(
                "SELECT * FROM entries WHERE lead_id=? ORDER BY rowid", (entity_id,)
            ).fetchall()
        return rows

    @staticmethod
    def create_scope(db, case_id, entity_id, title, stamp, draft, rows, *, intake_lead_id=None):
        db.execute(
            "INSERT INTO cases(id,entity_id,title,created_at,updated_at,draft) VALUES(?,?,?,?,?,?)",
            (
                case_id,
                entity_id,
                title,
                stamp,
                stamp,
                dump(draft),
            ),
        )
        for row in rows:
            db.execute("INSERT INTO case_entries VALUES(?,?)", (case_id, row["id"]))
        for root in dict.fromkeys(r["root_domain"] for r in rows):
            from modules.entities.components.ownership import group_for_entity

            group = group_for_entity(db, root, entity_id)
            db.execute(
                "INSERT INTO case_entries VALUES(?,?) ON CONFLICT DO NOTHING",
                (case_id, group["attribution_entry_id"]),
            )
            db.execute(
                "INSERT INTO case_groups VALUES(?,?,?,?)",
                (
                    case_id,
                    root,
                    group["attribution_entry_id"],
                    group["attribution"],
                ),
            )

        from ..case_conditions import pin

        pin(db, case_id, intake_lead_id)
        pin_case_score(db, case_id, entry_ids=[row["id"] for row in rows], lead_id=intake_lead_id)

    @staticmethod
    def pin_entity(db, case_id, entity, profile):
        prior = db.execute("SELECT entity_snapshot FROM cases WHERE id=?", (case_id,)).fetchone()
        identity = json.loads(prior["entity_snapshot"]) if prior else {}
        snapshot = {
            # Entity merges change current ownership, not the report's source identity.
            "entity_id": identity.get("entity_id", entity["id"]),
            "company": entity["company"],
            "domain": entity["domain"],
            "entity_profile": profile,
        }
        db.execute("UPDATE cases SET entity_snapshot=? WHERE id=?", (dump(snapshot), case_id))

    @staticmethod
    def inherit_outreach_hold(db, entity_id, case_id):
        """Copy the latest explicit business hold inside the caller's transaction."""
        prior_policy = db.execute(
            """SELECT p.* FROM case_outreach_policy p JOIN cases c ON c.id=p.case_id
            WHERE c.entity_id=? AND c.id!=? ORDER BY p.changed_at DESC,p.rowid DESC LIMIT 1""",
            (entity_id, case_id),
        ).fetchone()
        if not prior_policy or prior_policy["state"] == "active":
            return None
        db.execute(
            "INSERT INTO case_outreach_policy VALUES(?,?,?,?,?,?)",
            (
                case_id,
                prior_policy["state"],
                prior_policy["reason"],
                prior_policy["review_on"],
                prior_policy["changed_by"],
                prior_policy["changed_at"],
            ),
        )
        return prior_policy["case_id"]

    @staticmethod
    def reported_tags(db, case_id):
        from ..case_conditions import overlay
        from modules.accretion.components.intake.versions import entry_fields

        entries = [
            {**json.loads(row["payload"]), "id": row["id"]}
            for row in db.execute(
                "SELECT e.id,e.payload FROM entries e JOIN case_entries ce ON ce.entry_id=e.id WHERE ce.case_id=?",
                (case_id,),
            )
        ]
        return [entry_fields(entry).get("tag", "") for entry in overlay(db, case_id, entries)]

    @staticmethod
    def set_initial_draft(db, case_id, draft):
        db.execute("UPDATE cases SET draft=? WHERE id=?", (dump(draft), case_id))

    @staticmethod
    def open_for_group(db, entity_id, root):
        return db.execute(
            """SELECT c.* FROM cases c WHERE entity_id=? AND stage IN ('in_progress','pending_notification')
          ORDER BY EXISTS(SELECT 1 FROM case_groups g WHERE g.case_id=c.id AND g.root_domain=?) DESC,c.created_at DESC,c.rowid DESC LIMIT 1""",
            (entity_id, root),
        ).fetchone()

    @staticmethod
    def has_cases(db, entity_id):
        return (
            db.execute("SELECT 1 FROM cases WHERE entity_id=?", (entity_id,)).fetchone() is not None
        )

    @staticmethod
    def extend_scope(db, case_id, root, entry_ids, *, intake_lead_id=None):
        prior_ids = {
            r["entry_id"]
            for r in db.execute("SELECT entry_id FROM case_entries WHERE case_id=?", (case_id,))
        }
        added = 0
        for entry_id in entry_ids:
            added += db.execute(
                "INSERT INTO case_entries VALUES(?,?) ON CONFLICT DO NOTHING",
                (case_id, entry_id),
            ).rowcount
        if not added:
            return 0
        from modules.entities.components.ownership import group_for_entity

        entity_id = db.execute("SELECT entity_id FROM cases WHERE id=?", (case_id,)).fetchone()[0]
        group = group_for_entity(db, root, entity_id)
        db.execute(
            "INSERT INTO case_entries VALUES(?,?) ON CONFLICT DO NOTHING",
            (case_id, group["attribution_entry_id"]),
        )
        db.execute(
            """INSERT INTO case_groups VALUES(?,?,?,?) ON CONFLICT(case_id,root_domain)
          DO UPDATE SET attribution_entry_id=excluded.attribution_entry_id,attribution=excluded.attribution""",
            (
                case_id,
                root,
                group["attribution_entry_id"],
                group["attribution"],
            ),
        )
        from ..case_conditions import pin

        new_ids = (set(entry_ids) | {group["attribution_entry_id"]}) - prior_ids
        pin(db, case_id, intake_lead_id, entry_ids=new_ids)
        pin_case_score(db, case_id, entry_ids=entry_ids, lead_id=intake_lead_id)
        return added

    @staticmethod
    def replace_working_draft(db, case_id, draft):
        db.execute(
            "UPDATE cases SET stage='in_progress',certified_report_id=NULL,draft=?,draft_revision=draft_revision+1,version=version+1,updated_at=? WHERE id=?",
            (dump(draft), now(), case_id),
        )

    @staticmethod
    def has_work(db, case_id):
        scoped = db.execute("SELECT draft FROM cases WHERE id=?", (case_id,)).fetchone()
        if scoped and json.loads(scoped["draft"]).get("observation_scope"):
            return True
        return (
            db.execute(
                "SELECT 1 FROM reports WHERE case_id=? UNION ALL SELECT 1 FROM contact_attempts WHERE case_id=? UNION ALL SELECT 1 FROM evidence WHERE case_id=? UNION ALL SELECT 1 FROM section_validations WHERE case_id=? UNION ALL SELECT 1 FROM case_asset_attributions WHERE case_id=? UNION ALL SELECT 1 FROM case_outreach_policy WHERE case_id=? UNION ALL SELECT 1 FROM outreach_preparations WHERE case_id=? LIMIT 1",
                (case_id, case_id, case_id, case_id, case_id, case_id, case_id),
            ).fetchone()
            is not None
        )

    @staticmethod
    def combine_scope(db, target_id, source_id):
        old_ids = {
            row[0]
            for row in db.execute("SELECT entry_id FROM case_entries WHERE case_id=?", (target_id,))
        }
        db.execute(
            "INSERT INTO case_entries SELECT ?,entry_id FROM case_entries WHERE case_id=? ON CONFLICT DO NOTHING",
            (target_id, source_id),
        )
        for row in db.execute(
            "SELECT * FROM case_entry_conditions WHERE case_id=?", (source_id,)
        ).fetchall():
            prior = db.execute(
                "SELECT conditions FROM case_entry_conditions WHERE case_id=? AND entry_id=?",
                (target_id, row["entry_id"]),
            ).fetchone()
            if prior:
                conditions = sorted(set(json.loads(prior[0])) | set(json.loads(row["conditions"])))
                db.execute(
                    "UPDATE case_entry_conditions SET conditions=? WHERE case_id=? AND entry_id=?",
                    (dump(conditions), target_id, row["entry_id"]),
                )
            elif row["entry_id"] not in old_ids:
                db.execute(
                    "INSERT INTO case_entry_conditions VALUES(?,?,?)",
                    (target_id, row["entry_id"], row["conditions"]),
                )
        db.execute("DELETE FROM case_entry_conditions WHERE case_id=?", (source_id,))
        db.execute(
            "UPDATE awareness_findings SET handled_case_id=? WHERE handled_case_id=?",
            (target_id, source_id),
        )

        db.execute(
            "INSERT INTO case_groups SELECT ?,root_domain,attribution_entry_id,attribution FROM case_groups WHERE case_id=? ON CONFLICT DO NOTHING",
            (target_id, source_id),
        )
        db.execute("UPDATE events SET case_id=? WHERE case_id=?", (target_id, source_id))
        db.execute("DELETE FROM case_groups WHERE case_id=?", (source_id,))
        db.execute("DELETE FROM case_entries WHERE case_id=?", (source_id,))
        pin_case_score(db, target_id, source_case_id=source_id)
        db.execute("DELETE FROM cases WHERE id=?", (source_id,))

    @staticmethod
    def scoped_attributions(db, case_id):
        entries = {}
        for row in db.execute(
            "SELECT e.payload,e.root_domain FROM entries e JOIN case_entries ce ON ce.entry_id=e.id "
            "WHERE ce.case_id=? ORDER BY e.rowid",
            (case_id,),
        ):
            entries.setdefault(row["root_domain"], []).append(json.loads(row["payload"]))
        return {
            row["root_domain"]: {
                "proof": json.loads(row["attribution"]),
                "entries": entries.get(row["root_domain"], []),
            }
            for row in db.execute(
                "SELECT root_domain,attribution FROM case_groups WHERE case_id=?", (case_id,)
            )
        }

    @staticmethod
    def save_scope_attribution(db, case_id, root, proof):
        db.execute(
            "UPDATE case_groups SET attribution=? WHERE case_id=? AND root_domain=?",
            (dump(proof), case_id, root),
        )

    @staticmethod
    def save_plan(db, case_id, values):
        keys = (
            "next_action",
            "follow_up_date",
            "contact_name",
            "contact_role",
            "contact_email",
            "contact_phone",
        )
        db.execute(
            "UPDATE cases SET "
            + ",".join(k + "=?" for k in keys)
            + ",version=version+1,updated_at=? WHERE id=?",
            (*(values[k] for k in keys), now(), case_id),
        )

    @staticmethod
    def report(db, case_id, report_id):
        return (
            db.execute(
                "SELECT * FROM reports WHERE id=? AND case_id=?", (report_id, case_id)
            ).fetchone()
            if report_id
            else None
        )

    @staticmethod
    def record_contact(db, case_id, report_id, values, success):
        keys = (
            "channel",
            "outcome",
            "recipient",
            "destination",
            "notes",
            "recorded_by",
            "information_source",
        )
        db.execute(
            """INSERT INTO contact_attempts(id,case_id,report_id,occurred_at,recorded_at,channel,outcome,recipient,destination,notes,recorded_by,information_source)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                uid(),
                case_id,
                report_id,
                values["occurred_at"],
                now(),
                *(values[k] for k in keys),
            ),
        )
        if success:
            db.execute(
                "UPDATE cases SET stage='notification_completed',delivered_at=COALESCE(delivered_at,?),next_action='Prepare closing report',follow_up_date=NULL WHERE id=?",
                (values["occurred_at"], case_id),
            )
            db.execute(
                "UPDATE reports SET sent_at=COALESCE(sent_at,?),delivery_note=? WHERE id=?",
                (values["occurred_at"], values["notes"], report_id),
            )
        db.execute("UPDATE cases SET version=version+1,updated_at=? WHERE id=?", (now(), case_id))

    def list(self, stage="", entity_id="", q="", due_before=None, *, db=None, case_ids=None):
        clauses, args = [], []
        if case_ids is not None:
            if not case_ids:
                return []
            clauses.append("c.id IN (SELECT value FROM json_each(?))")
            args.append(json.dumps(list(case_ids)))
        if stage:
            clauses.append("c.stage=?")
            args.append(stage)
        if entity_id:
            clauses.append("c.entity_id=?")
            args.append(entity_id)
        if q:
            clauses.append(
                "(l.company LIKE ? OR l.domain LIKE ? OR c.title LIKE ? OR EXISTS(SELECT 1 FROM case_entries ce JOIN entries e ON e.id=ce.entry_id WHERE ce.case_id=c.id AND e.hostname LIKE ?))"
            )
            args.extend(["%" + q + "%"] * 4)
        if due_before:
            clauses.append("c.stage!='closed' AND c.follow_up_date<=?")
            args.append(due_before.isoformat())
        selected = """SELECT c.*,c.rowid case_order,l.company,l.domain,l.demo
          FROM cases c JOIN leads l ON l.id=c.entity_id"""
        if clauses:
            selected += " WHERE " + " AND ".join(clauses)
        # Decode decisions once for the selected cases. Repeated json_each
        # scans per observation make a large, heavily excluded scope quadratic.
        sql = (
            """WITH selected AS MATERIALIZED ("""
            + selected
            + """),
          excluded AS MATERIALIZED (
            SELECT c.id case_id,s.key entry_id FROM selected c
            JOIN json_each(c.draft,'$.observation_scope') s
            WHERE json_extract(s.value,'$.decision')='exclude'
          ), counts AS MATERIALIZED (
            SELECT c.id case_id,count(*) source_observations,
              sum(x.entry_id IS NULL) included_source_observations,
              sum(x.entry_id IS NULL AND (cc.conditions IS NULL OR json_array_length(cc.conditions)>0)) observations,
              count(DISTINCT CASE WHEN x.entry_id IS NULL AND
                (cc.conditions IS NULL OR json_array_length(cc.conditions)>0) THEN e.ip END) assets
            FROM selected c JOIN case_entries ce ON ce.case_id=c.id
            JOIN entries e ON e.id=ce.entry_id
            LEFT JOIN case_entry_conditions cc ON cc.case_id=c.id AND cc.entry_id=ce.entry_id
            LEFT JOIN excluded x ON x.case_id=c.id AND x.entry_id=ce.entry_id
            GROUP BY c.id
          ) SELECT c.id,c.entity_id,c.title,c.stage,c.created_at,c.updated_at,c.next_action,c.follow_up_date,c.delivered_at,c.closed_at,c.disposition,c.intake_score,c.company,c.domain,c.demo,
            COALESCE(n.source_observations,0) source_observations,
            COALESCE(n.included_source_observations,0) included_source_observations,
            COALESCE(n.observations,0) observations,COALESCE(n.assets,0) assets
          FROM selected c LEFT JOIN counts n ON n.case_id=c.id
          ORDER BY c.updated_at DESC,c.case_order DESC"""
        )
        reader = Records(db) if db is not None else self.store
        rows = reader.all(sql, args)
        for row in rows:
            row["intake_score"] = json.loads(row["intake_score"]) or None
        return rows
