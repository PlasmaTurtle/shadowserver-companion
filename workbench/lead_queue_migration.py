"""Independent intake dispositions and pinned notification identity (schema 10)."""

import hashlib
import json


def queue_id(import_id, domain):
    return hashlib.sha256((import_id + "\0" + domain).encode()).hexdigest()[:32]


def schema_ten(db):
    db.execute("""CREATE TABLE lead_queue (
      id TEXT PRIMARY KEY, import_id TEXT NOT NULL REFERENCES imports(id),
      root_domain TEXT NOT NULL, payload TEXT NOT NULL,
      entity_id TEXT REFERENCES leads(id), qualified INTEGER NOT NULL DEFAULT 0,
      association_state TEXT NOT NULL CHECK(association_state IN ('new','known','review')),
      association_basis TEXT NOT NULL DEFAULT '', candidates TEXT NOT NULL DEFAULT '[]',
      status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','deferred','dismissed','assigned')),
      revision INTEGER NOT NULL DEFAULT 0, case_id TEXT REFERENCES cases(id),
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
      UNIQUE(import_id,root_domain))""")
    db.execute("CREATE INDEX lead_queue_status ON lead_queue(status,updated_at)")
    db.execute("CREATE INDEX lead_queue_entity ON lead_queue(entity_id,status)")
    db.execute("""CREATE TABLE entity_ip_associations (
      ip TEXT NOT NULL, entity_id TEXT NOT NULL REFERENCES leads(id),
      recorded_by TEXT NOT NULL, recorded_at TEXT NOT NULL,
      PRIMARY KEY(ip,entity_id))""")
    db.execute("ALTER TABLE cases ADD COLUMN entity_snapshot TEXT NOT NULL DEFAULT '{}'")
    for case in db.execute("SELECT id,entity_id,draft FROM cases").fetchall():
        entity = db.execute(
            "SELECT company,domain FROM leads WHERE id=?", (case["entity_id"],)
        ).fetchone()
        profile = db.execute(
            "SELECT payload FROM entity_profiles WHERE entity_id=?", (case["entity_id"],)
        ).fetchone()
        snapshot = {
            "entity_id": case["entity_id"],
            "company": entity["company"],
            "domain": entity["domain"],
            "entity_profile": json.loads(profile["payload"]) if profile else {},
        }
        db.execute(
            "UPDATE cases SET entity_snapshot=? WHERE id=?", (json.dumps(snapshot), case["id"])
        )
    # Preserve existing scopes; only previously unassigned observations enter the queue.
    groups = {}
    for job in db.execute("SELECT j.*,i.created_at FROM jobs j JOIN imports i ON i.id=j.import_id"):
        groups[(job["import_id"], job["domain"])] = (job["payload"], job["created_at"])
    for row in db.execute(
        "SELECT e.*,i.created_at FROM entries e JOIN imports i ON i.id=e.import_id ORDER BY e.rowid"
    ):
        key = (row["import_id"], row["root_domain"])
        if key not in groups:
            rows = db.execute(
                "SELECT payload FROM entries WHERE import_id=? AND root_domain=? ORDER BY rowid",
                key,
            ).fetchall()
            groups[key] = (json.dumps([json.loads(r["payload"]) for r in rows]), row["created_at"])
    for (import_id, root), (payload, stamp) in groups.items():
        owner = db.execute(
            "SELECT entity_id FROM domain_groups WHERE root_domain=?", (root,)
        ).fetchone()
        entries = db.execute(
            "SELECT id FROM entries WHERE import_id=? AND root_domain=?", (import_id, root)
        ).fetchall()
        remaining = any(
            not db.execute("SELECT 1 FROM case_entries WHERE entry_id=?", (e["id"],)).fetchone()
            for e in entries
        )
        state = "pending" if not entries or remaining else "assigned"
        db.execute(
            """INSERT INTO lead_queue(id,import_id,root_domain,payload,entity_id,qualified,
          association_state,association_basis,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                queue_id(import_id, root),
                import_id,
                root,
                payload,
                owner["entity_id"] if owner else None,
                int(bool(entries)),
                "known" if owner else "new",
                "Stored hostname association" if owner else "",
                state,
                stamp,
                stamp,
            ),
        )
