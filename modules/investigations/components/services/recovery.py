"""Recover published packages after interruption without rewriting their bytes.

The Store composition facade invokes these after schema initialization. Recovery
uses the same review state and package-integrity rules as normal publication.
"""

import hashlib
import sqlite3
from modules.workspace.components.primitives import uid, now
from ..package_files import parsed_manifest
from ..artifact_registry import register_artifact
from ..repositories.report_publication import activate_report
import modules.workspace.components.compact_json as compact_json


def recover_reports(store):
    """Recover a completed package if the process stopped just before its DB commit."""
    for path in (store.root / "reports").glob("*/v*/manifest.json"):
        relative = path.parent.relative_to(store.root).as_posix()
        if store.one("SELECT id FROM reports WHERE path=?", (relative,)):
            continue
        try:
            manifest, _ = store.package_inventory({"path": relative})
            lead_id = manifest.get("entity_id") or manifest["notification_id"]
            if not store.one("SELECT id FROM leads WHERE id=?", (lead_id,)):
                continue
            from ..cases import Cases

            case_id = manifest.get("case_id") or Cases(store).default_id(
                store.resolve_entity(lead_id)
            )
            can_activate = True
            if manifest.get("schema_version", 0) >= 3 and case_id:
                from ..report_snapshot import snapshot
                from ..reviews.queries import SectionReviewQueries

                current = snapshot(
                    store,
                    store.resolve_entity(lead_id),
                    case_id,
                    include_reviews=False,
                    capture_sections=(),
                )
                lead = Cases(store).view(case_id)
                reviews = SectionReviewQueries(store).describe(current, lead, record_changes=False)
                saved = compact_json.loads(
                    (path.parent / "snapshot.json").read_text(encoding="utf-8")
                )
                can_activate = all(r["status"] == "validated" for r in reviews) and {
                    r["validation_id"] for r in reviews
                } == {r.get("validation_id") for r in saved.get("section_reviews", [])}
            with store.transaction() as db:
                db.execute(
                    "INSERT OR IGNORE INTO reports(id,lead_id,revision,created_at,path,entity_id,case_id,certified_by,certified_at,certification_source) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        manifest.get("report_id") or uid(),
                        lead_id,
                        manifest["revision"],
                        manifest["created_at"],
                        relative,
                        store.resolve_entity(lead_id),
                        case_id,
                        manifest.get("certified_by", ""),
                        manifest.get("certified_at"),
                        "analyst" if manifest.get("certified_by") else "legacy_finalized",
                    ),
                )
                recovered = db.execute(
                    "SELECT id FROM reports WHERE path=?", (relative,)
                ).fetchone()
                if recovered is None:
                    continue
                register_artifact(db, store.root, "report", recovered["id"])
                if manifest.get("schema_version", 0) >= 5:
                    current_case = db.execute(
                        "SELECT version FROM cases WHERE id=?", (case_id,)
                    ).fetchone()
                    # Schema 5 records the exact pre-publication state. Apply
                    # the same readiness/operator gate as normal publication;
                    # intact orphan bytes remain registered if activation is stale.
                    certifying_actor = (
                        store.settings(db)["analyst_name"] or current["draft"]["sender_name"]
                    )
                    can_activate = bool(
                        can_activate
                        and current_case
                        and current_case["version"] == manifest.get("expected_version")
                        and all(item["ok"] for item in current["readiness"])
                        and certifying_actor == manifest.get("certified_by")
                    )
                if case_id and manifest.get("report_id") and can_activate:
                    activate_report(
                        db,
                        case_id=case_id,
                        entity_id=store.resolve_entity(lead_id),
                        report_id=manifest["report_id"],
                        draft_revision=manifest.get("draft_revision", -1),
                        expected_version=(
                            manifest.get("expected_version")
                            if manifest.get("schema_version", 0) >= 5
                            else None
                        ),
                        updated_at=now(),
                    )
                store.log(db, "recovered", "Recovered a completed report package", lead_id)
        except (OSError, ValueError, KeyError, TypeError, sqlite3.IntegrityError):
            continue


def recover_closings(store):
    """Complete an interrupted rename/commit only if its case has not changed."""
    for path in (store.root / "closures").glob("*/*/manifest.json"):
        relative = path.parent.relative_to(store.root).as_posix()
        if store.one("SELECT id FROM case_closures WHERE path=?", (relative,)):
            continue
        try:
            manifest, _ = parsed_manifest(path.parent)
            if (
                path.parent.name != manifest["closure_id"]
                or path.parent.parent.name != manifest["case_id"]
            ):
                continue
            if not store.closure_available({"path": relative}):
                continue
            raw = (path.parent / "snapshot.json").read_bytes()
            data = compact_json.loads(raw)
            if data["case_id"] != manifest["case_id"]:
                continue
            with store.transaction() as db:
                case = db.execute("SELECT * FROM cases WHERE id=?", (data["case_id"],)).fetchone()
                if (
                    not case
                    or case["stage"] == "closed"
                    or case["version"] != manifest["expected_version"]
                ):
                    continue
                db.execute(
                    "INSERT INTO case_closures VALUES(?,?,?,?,?,?,?,?)",
                    (
                        manifest["closure_id"],
                        data["case_id"],
                        data["created_at"],
                        data["closed_by"],
                        data["disposition"],
                        data["conclusion"],
                        relative,
                        hashlib.sha256(raw).hexdigest(),
                    ),
                )
                register_artifact(db, store.root, "closure", manifest["closure_id"])
                db.execute(
                    "UPDATE cases SET stage='closed',closed_at=?,disposition=?,next_action='',follow_up_date=NULL,version=version+1,updated_at=? WHERE id=?",
                    (data["created_at"], data["disposition"], now(), data["case_id"]),
                )
                store.log(
                    db,
                    "closure_recovered",
                    "Recovered finalized internal closing report",
                    case["entity_id"],
                    case["id"],
                )
        except (OSError, ValueError, KeyError, TypeError, sqlite3.IntegrityError):
            continue
