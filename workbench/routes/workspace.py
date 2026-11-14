"""Workspace HTTP adapters."""

from __future__ import annotations

import os
import tempfile
import platform
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from ..workspace_data import MAX_ARCHIVE, export_workspace, restore_point_path
from .. import __version__
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from ..primitives import dump, now, uid
from ..content_bank import snapshot_blocks, save_source_metadata
from ..api_models import SettingsUpdate, BlockUpdate


class DeleteData(BaseModel):
    confirmation: str


def register(app, *, store):
    @app.get("/api/explainers")
    def explainers():
        with closing(store.connect()) as db:
            return snapshot_blocks(db)

    @app.put("/api/explainers/{block_id}")
    def save_block(block_id: str, body: BlockUpdate):
        metadata = body.checked_metadata()
        for line in body.sources.splitlines():
            if line.strip() and urlsplit(line.strip()).scheme not in ("http", "https"):
                raise HTTPException(400, "Sources must be HTTP or HTTPS URLs")
        with store.transaction() as db:
            if not db.execute("SELECT id FROM explainers WHERE id=?", (block_id,)).fetchone():
                raise HTTPException(404, "Explainer not found")
            if "source_metadata" not in body.model_fields_set:
                prior_block = next(
                    block for block in snapshot_blocks(db) if block["id"] == block_id
                )
                urls = {line.strip() for line in body.sources.splitlines() if line.strip()}
                metadata = [
                    item for item in prior_block.get("source_metadata", []) if item["url"] in urls
                ]
            db.execute(
                "UPDATE explainers SET title=?,body=?,sources=?,revision=revision+1,updated_at=? WHERE id=?",
                (body.title, body.body, body.sources, now(), block_id),
            )
            revision = db.execute(
                "SELECT revision FROM explainers WHERE id=?", (block_id,)
            ).fetchone()["revision"]
            save_source_metadata(db, block_id, revision, metadata)
        return {"ok": True}

    @app.post("/api/explainers")
    def add_block(body: BlockUpdate):
        metadata = body.checked_metadata()
        for line in body.sources.splitlines():
            if line.strip() and urlsplit(line.strip()).scheme not in ("http", "https"):
                raise HTTPException(400, "Sources must be HTTP or HTTPS URLs")
        with store.transaction() as db:
            block_id = uid()
            db.execute(
                "INSERT INTO explainers VALUES(?,?,?,?,?,?)",
                (block_id, body.title, body.body, body.sources, 1, now()),
            )
            save_source_metadata(db, block_id, 1, metadata)
        return {"id": block_id}

    @app.put("/api/settings")
    def settings(body: SettingsUpdate):
        previous = store.settings()
        values = {**previous, **body.model_dump(exclude_unset=True)}
        if (values["outreach_mode"] == "targeted" or not values["critical_only"]) and not values[
            "targeted_reason"
        ].strip():
            raise ValueError("Targeted outreach requires a recorded reason.")
        values["critical_only"] = values["outreach_mode"] == "critical"
        with store.transaction() as db:
            db.execute("UPDATE settings SET value=? WHERE key=?", (dump(values), "profile"))
        if previous.get("regions") != values.get("regions"):
            acquisition = getattr(app.state, "api_acquisition", None)
            if acquisition is not None:
                acquisition.scope_changed()
        return values

    @app.get("/api/data/status")
    def data_status():
        return app.state.workspace_data.status()

    @app.post("/api/backup")
    @app.post("/api/data/export")
    def backup():
        with app.state.workspace_data.operation():
            path = export_workspace(store)
        return FileResponse(
            path,
            filename="shadowserver-companion-backup.zip",
            background=BackgroundTask(path.unlink, missing_ok=True),
        )

    @app.get("/api/data/restore-points/{identifier}")
    def download_restore_point(identifier: str):
        path = restore_point_path(store.root, identifier)
        return FileResponse(path, filename="companion-restore-point-" + identifier[:8] + ".zip")

    @app.get("/api/data/diagnostics")
    def diagnostics():
        # Deliberately avoid raw logs, file paths, settings, hostnames, contacts,
        # source contents and tokens. The summary is safe to inspect/share.
        with closing(store.connect()) as db:
            counts = {
                table: db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                for table in ("imports", "leads", "entries", "reports")
            }
            schema = db.execute("PRAGMA user_version").fetchone()[0]
        status = app.state.workspace_data.status()
        return {
            "format": "companion-diagnostics",
            "version": 1,
            "generated_at": now(),
            "application_version": __version__,
            "python": platform.python_version(),
            "system": platform.system(),
            "sqlite": sqlite3.sqlite_version,
            "database_schema": schema,
            "record_counts": counts,
            "free_disk_bytes": shutil.disk_usage(store.root).free,
            "pending_data_change": status["pending"],
            "last_export_verified_at": (status["backup"].get("last_export") or {}).get(
                "verified_at"
            ),
            "restore_point_count": len(status["backup"].get("restore_points", [])),
            "excludes": [
                "credentials",
                "tokens",
                "file paths",
                "raw logs",
                "reports",
                "contact values",
            ],
        }

    @app.post("/api/data/check")
    def check_workspace():
        with app.state.workspace_data.operation(), closing(store.connect()) as db:
            ok = db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            references_ok = db.execute("PRAGMA foreign_key_check").fetchone() is None
            if not ok or not references_ok:
                raise ValueError(
                    "Workspace database check failed; preserve existing data and restore a verified backup"
                )
        return {
            "ok": True,
            "message": "Database integrity and record references passed. Export data to verify the complete evidence and report backup.",
        }

    @app.post("/api/data/import")
    def import_data(
        file: UploadFile = File(...),
        confirmation: str = Form(...),
        skip_restore_point: bool = Form(False),
    ):
        if confirmation != "IMPORT":
            raise ValueError("Type IMPORT to confirm replacing all current workspace data")
        handle, filename = tempfile.mkstemp(suffix=".zip")
        path = Path(filename)
        try:
            with os.fdopen(handle, "wb") as output:
                total = 0
                while chunk := file.file.read(1024**2):
                    total += len(chunk)
                    if total > MAX_ARCHIVE:
                        raise ValueError("Backup must be no larger than 2 GB")
                    output.write(chunk)
            return app.state.workspace_data.stage(
                "import", path, retain_current=not skip_restore_point
            )
        finally:
            path.unlink(missing_ok=True)
            file.file.close()

    @app.post("/api/data/delete")
    def delete_data(body: DeleteData):
        if body.confirmation != "DELETE":
            raise ValueError("Type DELETE to confirm deleting all workspace data")
        return app.state.workspace_data.stage("delete")

    @app.post("/api/data/cancel")
    def cancel_data_change():
        return app.state.workspace_data.cancel()

    from . import workspace_health

    workspace_health.register(app, store=store)
