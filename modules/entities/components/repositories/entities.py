"""Entity records and their complete observation/evidence projection."""

import json
from modules.investigations.components.repositories.artifacts import ArtifactRepository
from modules.workspace.components.repositories.records import Records
from modules.workspace.components.primitives import dump, now
from ..entity_review import review_summary, value_hash


class EntityRepository:
    def __init__(self, store):
        self.store = store
        self.artifacts = ArtifactRepository(store)

    @staticmethod
    def validate_attribution_entry(db, entity_id):
        row = db.execute(
            """SELECT 1 FROM leads l JOIN entries e ON e.id=l.attribution_entry_id
          WHERE l.id=? AND e.lead_id=l.id""",
            (entity_id,),
        ).fetchone()
        if not row:
            raise ValueError("Attribution entry must belong to the entity being qualified")

    def resolve_entity(self, entity_id, db=None):
        if db is None:
            with self.store.read_snapshot() as db:
                return self.resolve_entity(entity_id, db)
        row = Records(db).one("SELECT id,merged_into FROM leads WHERE id=?", (entity_id,))
        return (row["merged_into"] or row["id"]) if row else None

    @staticmethod
    def active(db, entity_id):
        return db.execute(
            "SELECT * FROM leads WHERE id=? AND merged_into IS NULL", (entity_id,)
        ).fetchone()

    @staticmethod
    def profiles(db, source_id, target_id):
        return {
            row["entity_id"]: json.loads(row["payload"])
            for row in db.execute(
                "SELECT * FROM entity_profiles WHERE entity_id IN (?,?)", (source_id, target_id)
            )
        }

    @staticmethod
    def save_profile(db, entity_id, values):
        db.execute(
            "INSERT INTO entity_profiles VALUES(?,?) ON CONFLICT(entity_id) DO UPDATE SET payload=excluded.payload",
            (entity_id, dump(values)),
        )

    @staticmethod
    def copy_profile_source(db, source_id, target_id, field):
        provenance = db.execute(
            "SELECT payload FROM entity_profile_sources WHERE entity_id=? AND field=?",
            (source_id, field),
        ).fetchone()
        if provenance:
            db.execute(
                "INSERT INTO entity_profile_sources VALUES(?,?,?) ON CONFLICT(entity_id,field) DO UPDATE SET payload=excluded.payload",
                (target_id, field, provenance[0]),
            )

    @staticmethod
    def profile(db, entity_id):
        row = db.execute(
            "SELECT payload FROM entity_profiles WHERE entity_id=?", (entity_id,)
        ).fetchone()
        return json.loads(row["payload"]) if row else {}

    @staticmethod
    def save_field_review(db, entity_id, field, value, status, actor):
        db.execute(
            """INSERT INTO entity_field_reviews VALUES(?,?,?,?,?,?)
            ON CONFLICT(entity_id,field) DO UPDATE SET status=excluded.status,
            value_hash=excluded.value_hash,reviewed_by=excluded.reviewed_by,
            reviewed_at=excluded.reviewed_at""",
            (entity_id, field, status, value_hash(value), actor, now()),
        )

    def field_review(self, db, entity, profile=None, hostnames=None):
        entity_id = entity["id"]
        if profile is None:
            profile = self.profile(db, entity_id)
        if hostnames is None:
            hostnames = db.execute(
                "SELECT h.name FROM hostnames h JOIN domain_groups g ON g.root_domain=h.root_domain WHERE g.entity_id=?",
                (entity_id,),
            ).fetchall()
        decisions = {
            row["field"]: row
            for row in db.execute(
                "SELECT * FROM entity_field_reviews WHERE entity_id=?", (entity_id,)
            )
        }
        return review_summary(entity, profile, hostnames, decisions)

    @staticmethod
    def update_working_drafts(db, entity_id, changes):
        """Only working drafts change; certified packages remain untouched."""
        rows = db.execute(
            "SELECT * FROM cases WHERE entity_id=? AND stage='in_progress'", (entity_id,)
        ).fetchall()
        for case in rows:
            draft = json.loads(case["draft"])
            draft.update(changes)
            db.execute(
                "UPDATE cases SET draft=?,draft_revision=draft_revision+1,version=version+1,updated_at=? WHERE id=?",
                (dump(draft), now(), case["id"]),
            )
        return [case["id"] for case in rows]

    @staticmethod
    def rename(db, entity_id, name, draft):
        db.execute(
            "UPDATE leads SET company=?,draft=?,draft_revision=draft_revision+1,updated_at=? WHERE id=?",
            (name, dump(draft), now(), entity_id),
        )

    @staticmethod
    def touch_profile(db, entity_id):
        db.execute(
            "UPDATE leads SET draft_revision=draft_revision+1,updated_at=? WHERE id=?",
            (now(), entity_id),
        )

    @staticmethod
    def transfer_records(db, source_id, target_id):
        """Move ownership and aliases together using the service's transaction."""
        if db.execute(
            "SELECT 1 FROM contact_discovery_locks WHERE entity_id IN (?,?)",
            (source_id, target_id),
        ).fetchone():
            raise ValueError("Finish or cancel contact discovery before combining these entities")
        from ..ownership import available

        if available(db):
            db.execute(
                "INSERT INTO entity_domain_associations SELECT root_domain,?,attribution_entry_id,attribution FROM entity_domain_associations WHERE entity_id=? ON CONFLICT(root_domain,entity_id) DO UPDATE SET attribution_entry_id=excluded.attribution_entry_id,attribution=excluded.attribution WHERE entity_domain_associations.attribution_entry_id IS NULL",
                (target_id, source_id),
            )
        count = db.execute("SELECT count(*) FROM entries WHERE lead_id=?", (source_id,)).fetchone()[
            0
        ]
        for table, column in (
            ("entries", "lead_id"),
            ("evidence", "lead_id"),
            ("domain_groups", "entity_id"),
            ("reports", "entity_id"),
            ("cases", "entity_id"),
            ("contact_runs", "entity_id"),
            ("contact_candidates", "entity_id"),
        ):
            db.execute(f"UPDATE {table} SET {column}=? WHERE {column}=?", (target_id, source_id))
        db.execute("UPDATE lead_queue SET entity_id=? WHERE entity_id=?", (target_id, source_id))
        db.execute(
            "INSERT OR IGNORE INTO entity_ip_associations SELECT ip,?,recorded_by,recorded_at FROM entity_ip_associations WHERE entity_id=?",
            (target_id, source_id),
        )
        db.execute("DELETE FROM entity_ip_associations WHERE entity_id=?", (source_id,))
        db.execute(
            "UPDATE leads SET merged_into=? WHERE merged_into=? OR id=?",
            (target_id, source_id, source_id),
        )
        return count

    @staticmethod
    def update_merge_target(db, target_id, draft, count):
        db.execute(
            "UPDATE leads SET draft=?,draft_revision=draft_revision+1,status='in_progress',new_observations=new_observations+?,updated_at=? WHERE id=?",
            (dump(draft), count, now(), target_id),
        )

    @staticmethod
    def invalidate_working_cases(db, entity_id):
        db.execute(
            "UPDATE cases SET draft_revision=draft_revision+1,version=version+1,updated_at=? WHERE entity_id=? AND stage='in_progress'",
            (now(), entity_id),
        )

    def lead(self, lead_id, db=None):
        if db is None:
            with self.store.read_snapshot() as db:
                return self.lead(lead_id, db)
        records = Records(db)
        lead_id = self.resolve_entity(lead_id, db)
        lead = records.one("SELECT * FROM leads WHERE id=?", (lead_id,))
        if not lead:
            return None
        profile = records.one("SELECT payload FROM entity_profiles WHERE entity_id=?", (lead_id,))
        lead["entity_profile"] = json.loads(profile["payload"]) if profile else {}
        lead["registry_profile_sources"] = {
            row["field"]: json.loads(row["payload"])
            for row in records.all(
                "SELECT field,payload FROM entity_profile_sources WHERE entity_id=?", (lead_id,)
            )
        }
        from modules.leads.components.repositories.lead_scopes import pending_counts

        lead["new_observations"] = (
            pending_counts(db, lead_id).get(lead_id, 0)
            if db.execute("SELECT 1 FROM cases WHERE entity_id=? LIMIT 1", (lead_id,)).fetchone()
            else 0
        )
        lead["draft"] = json.loads(lead["draft"])
        lead["attribution"] = json.loads(lead["attribution"])
        rows = records.all("SELECT * FROM entries WHERE lead_id=? ORDER BY rowid", (lead_id,))
        rows.sort(key=lambda row: row["id"] != lead["attribution_entry_id"])
        lead["entries"] = [{"id": row["id"], **json.loads(row["payload"])} for row in rows]
        lead["evidence"] = records.all(
            "SELECT * FROM evidence WHERE lead_id=? ORDER BY rowid", (lead_id,)
        )
        lead["hostnames"] = records.all(
            "SELECT h.name,h.root_domain FROM hostnames h JOIN domain_groups g ON g.root_domain=h.root_domain LEFT JOIN awareness_assets a ON a.hostname=h.name WHERE COALESCE(a.entity_id,g.entity_id)=? ORDER BY h.name",
            (lead_id,),
        )
        lead["associated_assets"] = records.all(
            "SELECT id,hostname,root_domain,association_basis,created_at,updated_at FROM awareness_assets WHERE entity_id=? AND hostname<>'' ORDER BY hostname",
            (lead_id,),
        )
        known_hosts = {h["name"] for h in lead["hostnames"]}
        lead["hostnames"].extend(
            {
                "name": a["hostname"],
                "root_domain": a["root_domain"],
                "association_basis": a["association_basis"],
            }
            for a in lead["associated_assets"]
            if a["hostname"] not in known_hosts
        )
        from .entity_awareness import detail as awareness_detail

        lead.update(awareness_detail(db, lead_id))
        lead["entity_review"] = self.field_review(
            db, lead, lead["entity_profile"], lead["hostnames"]
        )
        lead["merged_entities"] = records.all(
            "SELECT id,domain,company,draft_revision FROM leads WHERE merged_into=? ORDER BY updated_at",
            (lead_id,),
        )
        from ..ownership import available as ownership_available

        if ownership_available(db):
            groups = records.all(
                "SELECT a.*,g.entity_id=a.entity_id current_association FROM entity_domain_associations a LEFT JOIN domain_groups g ON g.root_domain=a.root_domain WHERE a.entity_id=? AND a.attribution_entry_id IS NOT NULL ORDER BY a.rowid",
                (lead_id,),
            )
        else:
            groups = records.all(
                "SELECT *,1 current_association FROM domain_groups WHERE entity_id=? ORDER BY rowid",
                (lead_id,),
            )
        groups.sort(key=lambda g: g["attribution_entry_id"] != lead["attribution_entry_id"])
        lead["domain_groups"] = [{**g, "attribution": json.loads(g["attribution"])} for g in groups]
        lead["reports"] = records.all(
            "SELECT * FROM reports WHERE entity_id=? ORDER BY created_at DESC", (lead_id,)
        )
        for report in lead["reports"]:
            report["files_available"] = self.artifacts.package_available(report)
        lead["shared_ip_associations"] = records.all(
            "SELECT e.ip,l.id entity_id,COALESCE(NULLIF(l.company,''),l.domain) entity_name,min(e.observed_at) first_seen,max(e.observed_at) last_seen FROM entries e JOIN leads l ON l.id=e.lead_id WHERE e.ip IN (SELECT ip FROM entries WHERE lead_id=?) AND e.lead_id<>? AND l.merged_into IS NULL GROUP BY e.ip,l.id ORDER BY e.ip,l.id",
            (lead_id, lead_id),
        )
        lead["history"] = records.all(
            "SELECT * FROM events WHERE lead_id IN (SELECT id FROM leads WHERE id=? OR merged_into=?) ORDER BY id DESC LIMIT 50",
            (lead_id, lead_id),
        )
        return lead
