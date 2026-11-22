"""Reports HTTP adapters."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from fastapi import HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from ..reporting import snapshot, finalize, render_pdf
from ..reviews.policy import assert_current
from modules.investigations.components.api_models import (
    Delivery,
)
from ..package_integrity import LegacyUnvalidatedEvidence, write_export, write_recipient_export
from ..report_operations import register_operations, check_deadline, phase
from ..report_execution import prepare_pdf


def register(app, *, store, cases, get_lead):
    operations = register_operations(app)

    @app.get("/api/report-operations")
    def operation_list(case_id: str | None = None, limit: int = 20):
        return {
            "operations": operations.list(case_id, limit),
            "warning": operations.history_warning,
        }

    @app.get("/api/report-operations/{operation_id}")
    def operation_status(operation_id: str):
        return operations.get(operation_id)

    @app.post("/api/report-operations/{operation_id}/cancel")
    def cancel_operation(operation_id: str):
        return operations.cancel(operation_id)

    @app.get("/api/leads/{lead_id}/preview.pdf")
    def preview_pdf(lead_id: str, case_id: str | None = None):
        with operations.run(case_id or cases.default_id(lead_id), "preview"):
            lead = get_lead(lead_id, case_id)
            if lead["case"]["certified_report_id"]:
                report = store.one(
                    "SELECT * FROM reports WHERE id=?", (lead["case"]["certified_report_id"],)
                )
                if not store.package_available(report):
                    raise HTTPException(409, "Report package has missing or changed files")
                return FileResponse(
                    store.path(report["path"]) / "notification.pdf", media_type="application/pdf"
                )
            phase("Preparing saved report content")
            data = snapshot(
                store,
                lead_id,
                lead["case_id"],
                capture_sections=(),
                include_validation_history=False,
            )
            assert_current(data["section_reviews"])
            if not next(r["ok"] for r in data["readiness"] if r["key"] == "evidence_integrity"):
                raise HTTPException(
                    409,
                    "Screenshot evidence is missing or changed. Restore it before previewing the report.",
                )
            handle, path = tempfile.mkstemp(suffix=".pdf")
            os.close(handle)
            try:
                prepare_pdf(data, Path(path), store.root, draft=True, fallback=render_pdf)
                check_deadline()
            except Exception:
                Path(path).unlink(missing_ok=True)
                raise
            return FileResponse(
                path,
                media_type="application/pdf",
                background=BackgroundTask(Path(path).unlink, missing_ok=True),
            )

    @app.post("/api/leads/{lead_id}/finalize")
    def complete(lead_id: str, case_id: str | None = None):
        with operations.run(case_id or cases.default_id(lead_id), "certification"):
            lead = get_lead(lead_id, case_id)
            report = finalize(store, lead_id, lead["case_id"])
            report["supporting_appendix_available"] = (
                lead["draft"].get("include_appendix", True) is False
            )
            return report

    @app.get("/api/reports")
    def reports():
        rows = store.all(
            "SELECT r.*,l.domain,l.company,l.demo FROM reports r JOIN leads l ON l.id=r.entity_id ORDER BY r.created_at DESC"
        )
        for row in rows:
            row["files_available"] = False
            row["work_log_available"] = False
            row["supporting_appendix_available"] = False
            try:
                manifest, _ = store.package_inventory(row)
                row["files_available"] = True
                row["work_log_available"] = {"work-log.pdf", "chronology.json"} <= manifest[
                    "files"
                ].keys()
                row["supporting_appendix_available"] = {
                    "supporting-appendix.pdf",
                    "supporting-appendix.docx",
                } <= manifest["files"].keys()
            except (ValueError, OSError, KeyError, TypeError):
                pass
        return rows

    @app.get("/api/reports/{report_id}/{format}")
    def report_file(report_id: str, format: str, include_appendix: bool = False):
        item = store.one("SELECT * FROM reports WHERE id=?", (report_id,))
        if not item or format not in (
            "pdf",
            "docx",
            "json",
            "zip",
            "recipient-zip",
            "work-log",
            "chronology",
            "appendix-pdf",
            "appendix-docx",
        ):
            raise HTTPException(404, "Report not found")
        folder = store.path(item["path"])
        try:
            manifest, manifest_bytes = store.package_inventory(item)
        except (ValueError, OSError, KeyError, TypeError) as error:
            raise HTTPException(
                409, "Report package has missing or changed files. Restore the package from backup."
            ) from error
        if format in ("work-log", "chronology"):
            name = "work-log.pdf" if format == "work-log" else "chronology.json"
            if name not in manifest["files"]:
                raise HTTPException(
                    404, "This older package does not contain a certification work log"
                )
            return FileResponse(
                folder / name,
                filename=name,
                media_type="application/pdf" if format == "work-log" else "application/json",
            )
        if format in ("appendix-pdf", "appendix-docx"):
            name = "supporting-appendix." + format.removeprefix("appendix-")
            if name not in manifest["files"]:
                raise HTTPException(
                    404, "This report does not contain a separate supporting appendix"
                )
            return FileResponse(folder / name, filename=name)
        if format in ("zip", "recipient-zip"):
            handle, path = tempfile.mkstemp(suffix=".zip")
            os.close(handle)
            try:
                with ZipFile(path, "w", ZIP_DEFLATED) as archive:
                    if format == "recipient-zip":
                        write_recipient_export(
                            archive,
                            folder,
                            manifest,
                            manifest_bytes,
                            include_appendix=include_appendix,
                        )
                    else:
                        write_export(archive, folder, manifest, manifest_bytes)
            except LegacyUnvalidatedEvidence as error:
                Path(path).unlink(missing_ok=True)
                raise HTTPException(409, str(error)) from error
            except (ValueError, OSError, KeyError, TypeError) as error:
                Path(path).unlink(missing_ok=True)
                raise HTTPException(409, "Report package could not be safely exported") from error
            return FileResponse(
                path,
                filename=f"{'recipient' if format == 'recipient-zip' else 'internal-record'}-{item['lead_id'][:8]}-v{item['revision']}.zip",
                background=BackgroundTask(Path(path).unlink, missing_ok=True),
            )
        name = "snapshot.json" if format == "json" else "notification." + format
        return FileResponse(
            folder / name,
            filename=f"notification-{item['lead_id'][:8]}-v{item['revision']}.{format}",
        )

    @app.post("/api/reports/{report_id}/delivery")
    def delivery(report_id: str, body: Delivery):
        item = store.one("SELECT * FROM reports WHERE id=?", (report_id,))
        if not item:
            raise HTTPException(404, "Report not found")
        lead = get_lead(item["entity_id"], item["case_id"])
        timestamp = datetime.fromisoformat(body.sent_at.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        cases.attempt(
            item["case_id"],
            dict(
                expected_version=lead["case"]["version"],
                report_id=report_id,
                occurred_at=timestamp.astimezone(timezone.utc).isoformat(),
                channel="other",
                outcome="delivered",
                recipient=body.recipient.strip()
                or lead["case"]["contact_name"]
                or lead.get("entity_profile", {}).get("contact_name", ""),
                destination=lead["case"]["contact_email"]
                or lead.get("entity_profile", {}).get("contact_email", ""),
                notes=body.note,
                recorded_by=store.settings()["analyst_name"] or lead["draft"]["sender_name"],
                information_source="administrative",
            ),
        )
        return {"ok": True}
