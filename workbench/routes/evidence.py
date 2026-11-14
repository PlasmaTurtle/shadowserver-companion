"""Evidence HTTP adapters."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool
from ..primitives import now, uid
from ..image_evidence import decode_screenshot, metadata_path
from ..reviews.queries import SectionReviewQueries
from ..api_models import EvidenceUpdate, WebsiteCaptureRequest


def register(app, *, store, cases, get_lead):
    @app.get("/api/cases/{case_id}/website-capture")
    def capture_scope(case_id: str):
        _, hosts = app.state.website_jobs.scope(case_id)
        return {"hostnames": hosts}

    @app.post("/api/cases/{case_id}/website-capture")
    def capture_start(case_id: str, body: WebsiteCaptureRequest):
        return app.state.website_jobs.start(case_id, body.hostname)

    @app.get("/api/website-captures/{job_id}")
    def capture_status(job_id: str):
        return app.state.website_jobs.get(job_id)

    @app.post("/api/website-captures/{job_id}/cancel")
    def capture_cancel(job_id: str):
        return app.state.website_jobs.cancel(job_id)

    @app.post("/api/leads/{lead_id}/evidence")
    async def evidence_upload(
        lead_id: str,
        file: UploadFile = File(...),
        kind: str = Form("website"),
        caption: str = Form(""),
        source_url: str = Form(""),
        captured_at: str = Form(""),
        case_id: str | None = None,
    ):
        lead = get_lead(lead_id, case_id)
        if lead["status"] == "completed":
            raise HTTPException(409, "Reopen this notification to attach evidence")
        if kind not in ("website", "sos", "cve", "other"):
            raise HTTPException(400, "Unknown evidence category")
        if source_url and urlsplit(source_url).scheme not in ("http", "https"):
            raise HTTPException(400, "Source URL must use HTTP or HTTPS")
        content = await file.read(20 * 1024 * 1024 + 1)
        await file.close()
        if len(content) > 20 * 1024 * 1024:
            raise HTTPException(413, "Screenshot exceeds 20 MB")
        name = Path((file.filename or "screenshot").replace("\\", "/")).name
        try:
            image, metadata = await run_in_threadpool(decode_screenshot, name, content)
            preview = io.BytesIO()
            await run_in_threadpool(image.save, preview, "PNG")
            preview_bytes = preview.getvalue()
            metadata["preview_sha256"] = hashlib.sha256(preview_bytes).hexdigest()
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        evidence_id = uid()
        relative = f"evidence/{evidence_id}.original.bin"
        preview_path = f"evidence/{evidence_id}-preview.png"
        written = [
            store.path(relative),
            store.path(preview_path),
            store.path(metadata_path(evidence_id)),
        ]
        try:
            await run_in_threadpool(written[0].write_bytes, content)
            await run_in_threadpool(written[1].write_bytes, preview_bytes)
            await run_in_threadpool(written[2].write_text, json.dumps(metadata), encoding="utf-8")
            with store.transaction() as db:
                cases.require(db, lead["case_id"], editable=True)
                SectionReviewQueries(store).assert_editable(db, lead["case_id"], ("attribution",))
                db.execute(
                    "INSERT INTO evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        evidence_id,
                        lead_id,
                        kind,
                        name,
                        relative,
                        preview_path,
                        caption[:1000],
                        source_url[:2000],
                        captured_at or now(),
                        hashlib.sha256(content).hexdigest(),
                        1,
                        lead["case_id"],
                    ),
                )
                db.execute(
                    "UPDATE cases SET draft=json_set(draft,'$.reviewed',json('false')),draft_revision=draft_revision+1,version=version+1,updated_at=? WHERE id=?",
                    (now(), lead["case_id"]),
                )
                store.log(db, "evidence_added", caption or name, lead_id, lead["case_id"])
        except BaseException:
            for path in written:
                path.unlink(missing_ok=True)
            raise
        return get_lead(lead_id, lead["case_id"])

    @app.put("/api/evidence/{evidence_id}")
    def evidence_update(evidence_id: str, body: EvidenceUpdate):
        item = store.one("SELECT * FROM evidence WHERE id=?", (evidence_id,))
        if not item:
            raise HTTPException(404, "Evidence not found")
        if get_lead(item["lead_id"], item["case_id"])["status"] == "completed":
            raise HTTPException(409, "Reopen this notification to change evidence")
        if body.source_url and urlsplit(body.source_url).scheme not in ("http", "https"):
            raise HTTPException(400, "Source URL must use HTTP or HTTPS")
        source_metadata = store.path(metadata_path(evidence_id))
        if source_metadata.is_file():
            provenance = json.loads(source_metadata.read_text(encoding="utf-8")).get(
                "website_capture"
            )
            if provenance and (
                body.source_url != item["source_url"] or body.captured_at != item["captured_at"]
            ):
                raise HTTPException(
                    409, "Captured URL and time are retained as original provenance"
                )
        with store.transaction() as db:
            cases.require(db, item["case_id"], editable=True)
            SectionReviewQueries(store).assert_editable(db, item["case_id"], ("attribution",))
            db.execute(
                "UPDATE evidence SET included=?,caption=?,source_url=?,captured_at=? WHERE id=?",
                (int(body.included), body.caption, body.source_url, body.captured_at, evidence_id),
            )
            db.execute(
                "UPDATE cases SET draft=json_set(draft,'$.reviewed',json('false')),draft_revision=draft_revision+1,version=version+1,updated_at=? WHERE id=?",
                (now(), item["case_id"]),
            )
            store.log(
                db,
                "evidence_updated",
                "Updated screenshot details or inclusion",
                item["lead_id"],
                item["case_id"],
            )
        return {"ok": True}

    @app.get("/api/evidence/{evidence_id}/image")
    def evidence_image(evidence_id: str):
        item = store.one("SELECT * FROM evidence WHERE id=?", (evidence_id,))
        if not item:
            raise HTTPException(404, "Evidence not found")
        metadata_file = store.path(metadata_path(item["id"]))
        if metadata_file.is_file():
            metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
            if (
                metadata.get("preview_sha256")
                and hashlib.sha256(store.path(item["preview_path"]).read_bytes()).hexdigest()
                != metadata["preview_sha256"]
            ):
                raise HTTPException(409, "Screenshot preview failed its recorded SHA-256 check")
        return FileResponse(store.path(item["preview_path"]), media_type="image/png")
