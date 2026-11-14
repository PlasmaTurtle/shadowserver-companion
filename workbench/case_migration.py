"""Schema 4: notification work belongs to a case; business identity persists."""

import json
import hashlib
from pathlib import Path
from uuid import uuid4
from . import compact_json
from .package_integrity import read_manifest


def report_snapshot(db, report):
    """Use the saved report's content, never a later working draft, during upgrade."""
    try:
        workspace = Path(db.execute("PRAGMA database_list").fetchone()["file"]).resolve().parent
        folder = (workspace / report["path"]).resolve()
        if not folder.is_relative_to(workspace):
            return None
        raw = (folder / "snapshot.json").read_bytes()
        manifest = json.loads(read_manifest(folder))
        if hashlib.sha256(raw).hexdigest() != manifest["files"]["snapshot.json"]:
            return None
        value = compact_json.loads(raw)
        if not isinstance(value.get("draft"), dict) or not value.get("qualified_lead", {}).get(
            "validated_leads"
        ):
            return None
        return value
    except OSError, ValueError, KeyError, TypeError:
        return None


def attach_current(db, case_id, groups):
    for group in groups:
        db.execute(
            "INSERT INTO case_entries SELECT ?,id FROM entries WHERE root_domain=?",
            (case_id, group["root_domain"]),
        )
        db.execute(
            "INSERT INTO case_groups VALUES(?,?,?,?)",
            (case_id, group["root_domain"], group["attribution_entry_id"], group["attribution"]),
        )


def attach_snapshot(db, case_id, saved):
    # Modern historical packets distinguish the full retained source scope
    # from recipient inventory. Reconstruct both without rewriting the packet.
    if saved.get("scope_source_entries") and saved.get("scope_source_groups"):
        for entry in saved["scope_source_entries"]:
            db.execute(
                "INSERT INTO case_entries VALUES(?,?) ON CONFLICT DO NOTHING",
                (case_id, entry["id"]),
            )
        for group in saved["scope_source_groups"]:
            db.execute(
                "INSERT INTO case_groups VALUES(?,?,?,?)",
                (
                    case_id,
                    group["root_domain"],
                    group["attribution_entry_id"],
                    json.dumps(group["attribution"], ensure_ascii=False),
                ),
            )
        return
    qualified = saved["qualified_lead"]
    for index, group in enumerate(qualified["validated_leads"]):
        root = group["hostname"]
        entries = group["entries"]
        for entry in entries:
            # IDs are stable across the older workbench schema migrations.
            db.execute(
                "INSERT INTO case_entries VALUES(?,?) ON CONFLICT DO NOTHING",
                (case_id, entry["id"]),
            )
        attribution = qualified["whois"][index]
        db.execute(
            "INSERT INTO case_groups VALUES(?,?,?,?)",
            (case_id, root, entries[0]["id"], json.dumps(attribution, ensure_ascii=False)),
        )


def schema_four(db):
    statements = (
        """CREATE TABLE cases(
          id TEXT PRIMARY KEY NOT NULL, entity_id TEXT NOT NULL REFERENCES leads(id),
          title TEXT NOT NULL, stage TEXT NOT NULL DEFAULT 'in_progress'
            CHECK(stage IN ('in_progress','pending_notification','notification_completed','closed')),
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          draft TEXT NOT NULL DEFAULT '{}', draft_revision INTEGER NOT NULL DEFAULT 0 CHECK(draft_revision>=0),
          version INTEGER NOT NULL DEFAULT 0 CHECK(version>=0),
          certified_report_id TEXT REFERENCES reports(id) DEFERRABLE INITIALLY DEFERRED,
          next_action TEXT NOT NULL DEFAULT '', follow_up_date TEXT,
          contact_name TEXT NOT NULL DEFAULT '', contact_role TEXT NOT NULL DEFAULT '',
          contact_email TEXT NOT NULL DEFAULT '', contact_phone TEXT NOT NULL DEFAULT '',
          delivered_at TEXT, closed_at TEXT, disposition TEXT,
          FOREIGN KEY(certified_report_id,id) REFERENCES reports(id,case_id) DEFERRABLE INITIALLY DEFERRED)""",
        "ALTER TABLE reports ADD COLUMN case_id TEXT REFERENCES cases(id)",
        "ALTER TABLE reports ADD COLUMN certified_at TEXT",
        "ALTER TABLE reports ADD COLUMN certified_by TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE reports ADD COLUMN certification_source TEXT NOT NULL DEFAULT 'legacy_finalized' CHECK(certification_source IN ('analyst','legacy_finalized'))",
        "CREATE UNIQUE INDEX reports_identity_case ON reports(id,case_id)",
        "ALTER TABLE evidence ADD COLUMN case_id TEXT REFERENCES cases(id)",
        "ALTER TABLE events ADD COLUMN case_id TEXT REFERENCES cases(id)",
        """CREATE TABLE case_entries(
          case_id TEXT NOT NULL REFERENCES cases(id), entry_id TEXT NOT NULL REFERENCES entries(id),
          PRIMARY KEY(case_id,entry_id), UNIQUE(entry_id,case_id))""",
        """CREATE TABLE case_groups(
          case_id TEXT NOT NULL REFERENCES cases(id), root_domain TEXT NOT NULL,
          attribution_entry_id TEXT NOT NULL, attribution TEXT NOT NULL,
          PRIMARY KEY(case_id,root_domain),
          FOREIGN KEY(attribution_entry_id,root_domain) REFERENCES entries(id,root_domain) DEFERRABLE INITIALLY DEFERRED,
          FOREIGN KEY(case_id,attribution_entry_id) REFERENCES case_entries(case_id,entry_id) DEFERRABLE INITIALLY DEFERRED)""",
        """CREATE TABLE contact_attempts(
          id TEXT PRIMARY KEY NOT NULL, case_id TEXT NOT NULL REFERENCES cases(id),
          report_id TEXT, occurred_at TEXT NOT NULL, recorded_at TEXT NOT NULL,
          channel TEXT NOT NULL CHECK(channel IN ('phone','email','mail','in_person','other')),
          outcome TEXT NOT NULL CHECK(outcome IN ('contact_research','no_answer','voicemail','callback_requested','email_sent','bounced','delivered','acknowledged','recipient_update','other')),
          recipient TEXT NOT NULL DEFAULT '', destination TEXT NOT NULL DEFAULT '',
          notes TEXT NOT NULL DEFAULT '', recorded_by TEXT NOT NULL,
          information_source TEXT NOT NULL DEFAULT 'administrative'
            CHECK(information_source IN ('administrative','recipient_reported','analyst_verified')),
          FOREIGN KEY(report_id,case_id) REFERENCES reports(id,case_id),
          CHECK(outcome NOT IN ('delivered','acknowledged') OR (report_id IS NOT NULL AND length(trim(recipient))>0)))""",
        """CREATE TABLE case_closures(
          id TEXT PRIMARY KEY NOT NULL, case_id TEXT NOT NULL UNIQUE REFERENCES cases(id),
          created_at TEXT NOT NULL, closed_by TEXT NOT NULL, disposition TEXT NOT NULL
            CHECK(disposition IN ('notified','unable_to_contact','out_of_scope','duplicate','other')),
          conclusion TEXT NOT NULL, path TEXT NOT NULL UNIQUE, snapshot_sha256 TEXT NOT NULL)""",
        "CREATE INDEX cases_entity_stage ON cases(entity_id,stage,created_at)",
        "CREATE INDEX cases_follow_up ON cases(stage,follow_up_date)",
        "CREATE INDEX reports_case ON reports(case_id,created_at)",
        "CREATE INDEX evidence_case ON evidence(case_id)",
        "CREATE INDEX events_case ON events(case_id,id)",
        "CREATE INDEX attempts_case_time ON contact_attempts(case_id,occurred_at,recorded_at)",
    )
    for statement in statements:
        db.execute(statement)
    # Legacy report revisions cannot establish separate historical campaigns.
    # Preserve each original notification's revisions together, and retain a
    # distinct working draft when the prior application had reopened it.
    for lead in db.execute("SELECT * FROM leads ORDER BY rowid").fetchall():
        entity_id = lead["merged_into"] or lead["id"]
        reports = db.execute(
            "SELECT * FROM reports WHERE lead_id=? ORDER BY revision", (lead["id"],)
        ).fetchall()
        if lead["merged_into"] and not reports:
            continue  # The archived pre-merge draft is not another open notification.
        saved = report_snapshot(db, reports[-1]) if reports else None
        draft = saved["draft"] if saved else json.loads(lead["draft"])
        stage = (
            ("notification_completed" if reports[-1]["sent_at"] else "pending_notification")
            if reports
            else "in_progress"
        )
        case_id = uuid4().hex
        db.execute(
            """INSERT INTO cases(id,entity_id,title,stage,created_at,updated_at,draft,draft_revision,
          certified_report_id,contact_name,contact_role,contact_email,delivered_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                case_id,
                entity_id,
                f"Notification · {lead['domain']}",
                stage,
                lead["created_at"],
                lead["updated_at"],
                json.dumps(draft, ensure_ascii=False),
                saved.get("draft_revision", 0) if saved else lead["draft_revision"],
                reports[-1]["id"] if reports else None,
                draft.get("contact_name", ""),
                draft.get("contact_title", ""),
                draft.get("contact_email", ""),
                reports[-1]["sent_at"] if reports else None,
            ),
        )
        db.execute("UPDATE reports SET case_id=? WHERE lead_id=?", (case_id, lead["id"]))
        db.execute("UPDATE evidence SET case_id=? WHERE lead_id=?", (case_id, lead["id"]))
        db.execute("UPDATE events SET case_id=? WHERE lead_id=?", (case_id, lead["id"]))
        roots = db.execute(
            "SELECT * FROM domain_groups WHERE root_domain=?"
            if lead["merged_into"]
            else "SELECT * FROM domain_groups WHERE entity_id=?",
            (lead["domain"] if lead["merged_into"] else lead["id"],),
        ).fetchall()
        if saved:
            attach_snapshot(db, case_id, saved)
        else:
            attach_current(db, case_id, roots)
            if reports:
                db.execute(
                    "INSERT INTO events(lead_id,case_id,action,detail,created_at) VALUES(?,?,?,?,?)",
                    (
                        entity_id,
                        case_id,
                        "migration_note",
                        "Report snapshot unavailable during upgrade; case observations reflect the legacy workspace. Restore the original report package to inspect its exact scope.",
                        lead["updated_at"],
                    ),
                )
        # Record what the old application actually knew; do not invent a named
        # certifier, delivery recipient, or independently verified remediation.
        for report in reports:
            if report["sent_at"]:
                db.execute(
                    """INSERT INTO contact_attempts(id,case_id,report_id,occurred_at,recorded_at,channel,outcome,
                  recipient,notes,recorded_by) VALUES(?,?,?,?,?,'other','other',?,?,?)""",
                    (
                        uuid4().hex,
                        case_id,
                        report["id"],
                        report["sent_at"],
                        report["sent_at"],
                        draft.get("contact_name", ""),
                        "Legacy delivery record: " + report["delivery_note"],
                        "Legacy record",
                    ),
                )
        if (
            reports
            and lead["merged_into"] is None
            and lead["status"] in ("new", "in_progress", "deferred")
        ):
            new_id = uuid4().hex
            db.execute(
                """INSERT INTO cases(id,entity_id,title,created_at,updated_at,draft,draft_revision)
              VALUES(?,?,?,?,?,?,?)""",
                (
                    new_id,
                    entity_id,
                    f"Working notification · {lead['domain']}",
                    lead["updated_at"],
                    lead["updated_at"],
                    lead["draft"],
                    lead["draft_revision"],
                ),
            )
            attach_current(db, new_id, roots)
            db.execute("UPDATE evidence SET case_id=? WHERE case_id=?", (new_id, case_id))
