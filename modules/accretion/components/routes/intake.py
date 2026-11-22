"""Intake HTTP adapters."""

from __future__ import annotations

import json
import hashlib
import os
import tempfile
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from urllib.parse import quote
from fastapi import UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from starlette.background import BackgroundTask
from modules.attribution.components.attribution_bridge import checked_result
from ..intake_service import MAX_UPLOAD
from ..intake_progress import retry_label, stage_totals
from attribution import EvidenceRenderer, EvidenceStore
from modules.ui.components.presentation import mark_attribution_bundle
from modules.attribution.components.api_models import (
    AttributionReviewValues,
)
from modules.accretion.components.api_models import (
    DeconflictionValues,
    GroupRetryValues,
)
from modules.workspace.components.primitives import now, uid
from ..deconfliction import identifier_for


def register(app, *, store, intake):
    @app.get("/api/intake/deconfliction")
    def deconfliction_entries():
        return store.all("SELECT * FROM intake_deconfliction ORDER BY identifier,scope")

    def save_entry(values, existing=None):
        try:
            identifier = identifier_for(values.scope, values.identifier)
            with store.transaction() as db:
                params = (values.scope, identifier, values.external_reference, values.reason, now())
                identity = existing or uid()
                if existing is None:
                    db.execute(
                        "INSERT INTO intake_deconfliction VALUES(?,?,?,?,?,?)", (identity, *params)
                    )
                elif not db.execute(
                    "UPDATE intake_deconfliction SET scope=?,identifier=?,external_reference=?,reason=?,updated_at=? WHERE id=?",
                    (*params, identity),
                ).rowcount:
                    raise HTTPException(404, "Deconfliction entry not found")
                store.log(
                    db, "deconfliction_saved", "Saved " + values.scope + " entry for " + identifier
                )
                return dict(
                    db.execute(
                        "SELECT * FROM intake_deconfliction WHERE id=?", (identity,)
                    ).fetchone()
                )
        except sqlite3.IntegrityError:
            raise HTTPException(
                409, "An entry already exists for this identifier and scope"
            ) from None
        except ValueError as error:
            raise HTTPException(400, str(error)) from None

    @app.post("/api/intake/deconfliction")
    def add_deconfliction_entry(values: DeconflictionValues):
        return save_entry(values)

    @app.put("/api/intake/deconfliction/{entry_id}")
    def edit_deconfliction_entry(entry_id: str, values: DeconflictionValues):
        return save_entry(values, entry_id)

    @app.delete("/api/intake/deconfliction/{entry_id}")
    def remove_deconfliction_entry(entry_id: str):
        with store.transaction() as db:
            if not db.execute("DELETE FROM intake_deconfliction WHERE id=?", (entry_id,)).rowcount:
                raise HTTPException(404, "Deconfliction entry not found")
            store.log(db, "deconfliction_removed", "Removed external entry " + entry_id)
        return {"removed": True}

    @app.get("/api/intake/progress")
    def intake_progress():
        from ..intake_progress import overview

        return overview(store)

    @app.get("/api/intake/capabilities")
    def intake_capabilities():
        from ..api_import import MAX_API_DOWNLOAD
        from ..intake.files import MAX_CSV_EXPANDED
        from modules.accretion.components.report_profiles import supported_profiles

        return {
            "manual_formats": [".xlsx", ".xlsm", ".csv", ".csv.gz"],
            "manual_max_bytes": MAX_UPLOAD,
            "receipt_import_max_bytes": MAX_API_DOWNLOAD,
            "csv_expanded_max_bytes": MAX_CSV_EXPANDED,
            "api_live_selection": True,
            "api_status": "Live report selection and offline receipt import are available; configure API credentials in Data → API.",
            "notification_profiles": supported_profiles(),
            "other_profiles": "Retained for research",
        }

    @app.post("/api/imports/api-receipt")
    def upload_api_receipt(
        report: UploadFile = File(...),
        receipt: str = Form(...),
    ):
        from ..api_import import MAX_API_DOWNLOAD, MAX_RECEIPT_JSON, receipt_acquisition

        try:
            if len(receipt.encode("utf-8")) > MAX_RECEIPT_JSON:
                raise ValueError("API receipt exceeds the 64 KiB limit")
            acquisition = receipt_acquisition(json.loads(receipt))
            return intake.enqueue_stream(
                report.filename or "report.csv",
                report.file,
                max_bytes=MAX_API_DOWNLOAD,
                acquisition=acquisition,
            )
        except ValueError as error:
            raise HTTPException(400, str(error)) from None
        finally:
            report.file.close()

    @app.post("/api/imports")
    async def upload_report(files: list[UploadFile] = File(...)):
        if len(files) > 20:
            raise HTTPException(400, "Upload at most 20 workbooks at a time")
        results = []
        for upload in files:
            content = await upload.read(MAX_UPLOAD + 1)
            try:
                results.append(
                    {
                        "name": upload.filename,
                        **intake.enqueue(upload.filename or "report.xlsx", content),
                    }
                )
            except ValueError as error:
                results.append({"name": upload.filename, "error": str(error)})
            finally:
                await upload.close()
        return results

    @app.get("/api/imports")
    def imports():
        rows = store.all("SELECT * FROM imports ORDER BY created_at DESC")
        for row in rows:
            config = json.loads(row["config"])
            row["ignored_empty_rows"] = config.get("intake_stats", {}).get("ignored_empty_rows", 0)
            row["acquisition"] = config.get("acquisition", {})
            row["imported"] = row["status"] == "done"
        return rows

    @app.get("/api/imports/{import_id}")
    def import_detail(import_id: str):
        item = store.one("SELECT * FROM imports WHERE id=?", (import_id,))
        if not item:
            raise HTTPException(404, "Import not found")
        config = json.loads(item["config"])
        item["ignored_empty_rows"] = config.get("intake_stats", {}).get("ignored_empty_rows", 0)
        item["acquisition"] = config.get("acquisition", {})
        item["imported"] = item["status"] == "done"
        item["groups"] = store.all(
            "SELECT id,domain,status,attempts,error,attribution_result_id FROM jobs WHERE import_id=? ORDER BY rowid",
            (import_id,),
        )
        retry_counts = Counter()
        for group in item["groups"]:
            if group["status"] == "deferred":
                attempts = (
                    json.loads(group["attempts"])
                    if group["error"] == "website_capture_error"
                    else None
                )
                label = retry_label(group["error"], attempts=attempts)
                group["retry_label"] = label
                retry_counts[label] += 1
        item["retry_reasons"] = retry_counts
        item["stage_totals"] = stage_totals(
            sum(group["status"] == "qualified" for group in item["groups"]),
            sum(
                group["status"] == "dismissed" and group["error"] == "association_deconflicted"
                for group in item["groups"]
            ),
            sum(
                group["status"] == "deferred" and group["error"] == "association_evidence_changed"
                for group in item["groups"]
            ),
        )
        return item

    @app.get("/api/groups/{job_id}")
    def group_detail(job_id: str):
        job = store.one("SELECT * FROM jobs WHERE id=?", (job_id,))
        if not job:
            raise HTTPException(404, "Hostname group not found")
        job["entries"] = json.loads(job.pop("payload"))
        job["attempts"] = json.loads(job["attempts"])
        result_id = job["attribution_result_id"]
        if result_id:
            with closing(EvidenceStore(store.root / "attribution.sqlite3")) as evidence_store:
                job["attribution_result"] = checked_result(evidence_store, result_id, job["domain"])
                job["partial_records"] = {
                    e["snapshot_id"]: evidence_store.snapshot(e["snapshot_id"]).record()
                    for e in job["attribution_result"].get("partial_evidence", [])
                }
        job["reviews"] = store.all(
            "SELECT * FROM attribution_reviews WHERE job_id=? ORDER BY reviewed_at", (job_id,)
        )
        job["can_retry"] = job["status"] in (
            "review",
            "no_match",
            "deferred",
            "no_public_ip",
            "dismissed",
        )
        return job

    @app.get("/api/reviews")
    def attribution_reviews():
        rows = store.all(
            "SELECT j.*,i.name import_name FROM jobs j JOIN imports i ON i.id=j.import_id WHERE j.status='review' ORDER BY j.rowid"
        )
        with closing(EvidenceStore(store.root / "attribution.sqlite3")) as evidence_store:
            for row in rows:
                entries = json.loads(row.pop("payload"))
                attempts = json.loads(row.pop("attempts"))
                result_id = row["attribution_result_id"]
                result = (
                    checked_result(evidence_store, result_id, row["domain"]) if result_id else {}
                )
                partials = result.get("partial_evidence", [])
                row.update(
                    observations=len(entries),
                    assets=len({e["ip"] for e in entries}),
                    matches=partials,
                    lookup_incomplete=any(
                        a["status"] in ("incomplete", "deferred") for a in attempts
                    ),
                )
                row["rank"] = max(
                    (
                        sum(len(w) for w in set(e["details"]["matched_words"]))
                        / max(1, len(e["details"]["domain_label"]))
                        for e in partials
                    ),
                    default=0,
                )
        return sorted(rows, key=lambda row: row["rank"], reverse=True)

    @app.post("/api/groups/{job_id}/review")
    def review_attribution(job_id: str, values: AttributionReviewValues):
        return intake.review_group(
            job_id, values.result_id, values.evidence_index, values.decision, values.note
        )

    @app.post("/api/groups/{job_id}/retry")
    def retry_attribution(job_id: str, values: GroupRetryValues):
        intake.retry_group(job_id, values.result_id)
        return {"ok": True}

    @app.get("/api/groups/{job_id}/attribution.zip")
    def group_attribution(job_id: str):
        job = group_detail(job_id)
        result = job.get("attribution_result")
        if not result:
            raise HTTPException(409, "This older group does not have a raw attribution bundle")
        handle, path = tempfile.mkstemp(suffix=".zip")
        os.close(handle)
        try:
            with (
                tempfile.TemporaryDirectory() as temp,
                closing(EvidenceStore(store.root / "attribution.sqlite3")) as evidence_store,
            ):
                folder = Path(temp) / "attribution"
                EvidenceRenderer(evidence_store).export(
                    result["result_id"],
                    folder,
                    review_decisions=store.all(
                        "SELECT * FROM attribution_reviews WHERE result_id=? ORDER BY reviewed_at",
                        (result["result_id"],),
                    ),
                )
                mark_attribution_bundle(folder)
                inherited = {
                    attempt["source_result_id"]
                    for attempt in job["attempts"]
                    if attempt.get("source_result_id")
                    and attempt.get("result_id") == result["result_id"]
                    and attempt.get("source_result_id") != result["result_id"]
                }
                for source_id in sorted(inherited):
                    checked_result(evidence_store, source_id, job["domain"])
                    reviews = store.all(
                        "SELECT * FROM attribution_reviews WHERE result_id=? AND decision='accept' ORDER BY reviewed_at",
                        (source_id,),
                    )
                    if not reviews:
                        raise ValueError("Inherited attribution has no recorded source approval")
                    source_folder = folder / "prior-approval" / source_id
                    EvidenceRenderer(evidence_store).export(
                        source_id, source_folder, review_decisions=reviews
                    )
                    mark_attribution_bundle(source_folder)
                if inherited:
                    (folder / "approval-reuse.json").write_text(
                        json.dumps(
                            {
                                "result_id": result["result_id"],
                                "source_result_ids": sorted(inherited),
                                "basis": "Prior analyst approval reused; each result retains its own evidence and dates.",
                            },
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                with ZipFile(path, "w", ZIP_DEFLATED) as archive:
                    for file in folder.rglob("*"):
                        if file.is_file():
                            archive.write(file, file.relative_to(folder))
        except Exception:
            Path(path).unlink(missing_ok=True)
            raise
        return FileResponse(
            path,
            filename=f"attribution-{job['domain']}.zip",
            background=BackgroundTask(Path(path).unlink, missing_ok=True),
        )

    @app.post("/api/inbox/scan")
    def scan():
        return {"added": intake.scan_inbox()}

    @app.post("/api/imports/{import_id}/retry")
    def retry(import_id: str):
        intake.retry(import_id)
        return {"ok": True}

    @app.post("/api/imports/{import_id}/reevaluate")
    def reevaluate(import_id: str):
        return intake.reevaluate(import_id)

    @app.post("/api/imports/{import_id}/pause")
    def pause(import_id: str):
        with store.transaction() as db:
            db.execute(
                "UPDATE imports SET status='paused',stage='Paused' WHERE id=? AND status IN ('queued','running')",
                (import_id,),
            )
        return {"ok": True}

    @app.get("/api/imports/{import_id}/original")
    def original(import_id: str):
        item = store.one("SELECT * FROM imports WHERE id=?", (import_id,))
        if not item:
            raise HTTPException(404, "Import not found")
        from ..api_import import MAX_API_DOWNLOAD

        # Copy and hash once on demand. Streaming that verified copy prevents a
        # later change to the original pathname from changing this response.
        verified = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
        digest, size = hashlib.sha256(), 0
        try:
            with store.path(item["path"]).open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_API_DOWNLOAD:
                        raise HTTPException(
                            409, "Original report exceeds the recorded import limits"
                        )
                    digest.update(chunk)
                    verified.write(chunk)
            if digest.hexdigest() != item["sha256"]:
                raise HTTPException(
                    409, "Original report no longer matches its recorded fingerprint"
                )
            verified.seek(0)
        except HTTPException:
            verified.close()
            raise
        except (OSError, ValueError):
            verified.close()
            raise HTTPException(404, "Original report is unavailable") from None

        def chunks():
            try:
                while chunk := verified.read(1024 * 1024):
                    yield chunk
            finally:
                verified.close()

        filename = quote(item["name"])
        disposition = f"attachment; filename*=utf-8''{filename}"
        return StreamingResponse(
            chunks(),
            media_type="application/octet-stream",
            headers={"Content-Disposition": disposition, "Content-Length": str(size)},
            background=BackgroundTask(verified.close),
        )
