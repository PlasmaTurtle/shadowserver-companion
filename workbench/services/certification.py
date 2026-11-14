"""Certification workflow: validate, stage a package, publish, then record it.

Capture reviewed content under the workspace lock, render outside it, then
recheck the case and all reviewed dependencies inside the publication transaction.
Interrupted publication retains the existing recoverable package protocol.
"""

from __future__ import annotations

import json
import shutil
from ..primitives import now, uid
from ..cases import Cases
from ..print_policy import PRINT_RENDERER_VERSION
from ..report_package import assemble_package
from ..report_operations import check_deadline, publication, phase
from ..report_execution import prepare_package
from ..artifact_registry import register_artifact
from ..reviews.queries import SectionReviewQueries


def certify_report(store, lead_id, case_id=None, *, build_snapshot, renderers):
    with store.lock:
        cases = Cases(store)
        case_id = case_id or cases.default_id(lead_id)
        with store.transaction() as db:
            case = dict(cases.require(db, case_id, editable=True))
            if case["entity_id"] != lead_id:
                raise ValueError("Case belongs to a different business")
        phase("Checking the reviewed report and its evidence")
        data = build_snapshot(store, lead_id, case_id, capture_sections=())
        certification = {
            "certified_by": store.settings()["analyst_name"] or data["draft"]["sender_name"],
            "certified_at": now(),
        }
        data["certification"] = certification
        report_id = uid()
        missing = [r["label"] for r in data["readiness"] if not r["ok"]]
        if missing:
            raise ValueError("Complete these items: " + "; ".join(missing))
        latest = store.one("SELECT max(revision) n FROM reports WHERE lead_id=?", (lead_id,))
        revision = (latest["n"] or 0) + 1
        certification.update(revision=revision, report_id=report_id)
        data["report_revision"] = revision
        from ..contact_records import ContactRecords

        # Contact research is an independent, dated internal evidence snapshot.
        # It neither changes reviewed recipient content nor starts discovery.
        contacts = ContactRecords(store).export_projection(lead_id)
        if contacts.get("runs") or contacts.get("contacts") or contacts.get("candidates"):
            data["contact_research"] = {**contacts, "packaged_at": certification["certified_at"]}
        from ..work_log import build_chronology
        from ..attribution_display import attribution_summaries

        audit_lead = cases.view(case_id)
        audit_lead["attribution_summaries"] = attribution_summaries(store, audit_lead)
        # Recovered automatic evaluation times stay explicitly distinct from
        # registry retrieval and human review timestamps.
        for group in audit_lead["domain_groups"]:
            card = next(
                (
                    s
                    for s in audit_lead["attribution_summaries"]
                    if s["root_domain"] == group["root_domain"]
                ),
                {},
            )
            if card.get("details", {}).get("evaluated_at") and not group["attribution"].get(
                "evaluated_at"
            ):
                group["attribution"]["evaluated_at"] = card["details"]["evaluated_at"]
        data["chronology"] = build_chronology(audit_lead, data["section_history"], certification)
        relative = f"reports/{lead_id}/v{revision:03}"
        target = store.path(relative)
        temporary = target.parent / (".build-" + uid())
        temporary.mkdir(parents=True)
    try:
        package = prepare_package(store, data, temporary, renderers, fallback=assemble_package)
        check_deadline()
        data = package.snapshot
        hashes = package.files
        manifest = {
            "schema_version": 5,
            "package_format": data.get("package_format", "shadowserver-report-package-v1"),
            "recipient_edition": data.get("composition", {}).get("recipient_edition", "full-v1"),
            "expected_version": case["version"],
            "renderer_version": PRINT_RENDERER_VERSION,
            "handling": data.get("handling"),
            "notification_id": case_id,
            "case_id": case_id,
            "entity_id": lead_id,
            "report_id": report_id,
            "revision": revision,
            "created_at": now(),
            "draft_revision": case["draft_revision"],
            **certification,
            "files": hashes,
        }
        (temporary / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        phase("Rechecking the reviewed case before publication")
        with store.transaction() as db:
            current_case = dict(
                cases.require(db, case_id, expected_version=case["version"], editable=True)
            )
            if (
                current_case["entity_id"] != lead_id
                or current_case["draft_revision"] != case["draft_revision"]
            ):
                raise ValueError(
                    "This case changed during report preparation. Reload and review before certifying."
                )
            latest = db.execute(
                "SELECT max(revision) n FROM reports WHERE lead_id=?", (lead_id,)
            ).fetchone()
            if (latest["n"] or 0) + 1 != revision:
                raise ValueError(
                    "A report revision was saved during preparation. Reload before certifying."
                )
            current = build_snapshot(
                store, lead_id, case_id, capture_sections=(), include_reviews=False
            )
            reviews = SectionReviewQueries(store).describe(
                current, cases.view(case_id), record_changes=False
            )
            if (
                any(not item["ok"] for item in current["readiness"])
                or any(item["status"] != "validated" for item in reviews)
                or {item["validation_id"] for item in reviews}
                != {item["validation_id"] for item in data["section_reviews"]}
                or (store.settings()["analyst_name"] or current["draft"]["sender_name"])
                != certification["certified_by"]
            ):
                raise ValueError(
                    "Reviewed content or its evidence changed during report preparation. Reload and review before certifying."
                )
            with publication():
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary.rename(target)
                db.execute(
                    "INSERT INTO reports(id,lead_id,revision,created_at,path,entity_id,case_id,certified_at,certified_by,certification_source) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        report_id,
                        lead_id,
                        revision,
                        now(),
                        relative,
                        lead_id,
                        case_id,
                        certification["certified_at"],
                        certification["certified_by"],
                        "analyst",
                    ),
                )
                register_artifact(db, store.root, "report", report_id)
                db.execute(
                    "UPDATE cases SET stage='pending_notification',certified_report_id=?,version=version+1,updated_at=? WHERE id=?",
                    (report_id, now(), case_id),
                )
                db.execute(
                    "UPDATE leads SET status='completed',new_observations=0,updated_at=? WHERE id=?",
                    (now(), lead_id),
                )
                store.log(
                    db,
                    "certified",
                    f"Certified report revision {revision} by {certification['certified_by']}",
                    lead_id,
                    case_id,
                )
        return store.one("SELECT * FROM reports WHERE id=?", (report_id,))
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
