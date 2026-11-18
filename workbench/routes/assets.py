"""Per-asset attribution jobs and immutable saved evidence."""

import os
from pathlib import Path
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile

from attribution import EvidenceRenderer, EvidenceStore
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.background import BackgroundTask

from ..asset_attribution import adopt_attribution, saved_result
from ..presentation import mark_attribution_bundle


class AssetLookupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entry_id: str | None = Field(default=None, min_length=1, max_length=100)


class AssetAdoptionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)


def register(app, *, store, jobs):
    @app.get("/api/cases/{case_id}/assets/attribution")
    def asset_status(case_id: str):
        return jobs.state(case_id)

    @app.post("/api/cases/{case_id}/assets/attribution")
    def start_assets(case_id: str, body: AssetLookupRequest):
        return jobs.start(case_id, body.entry_id)

    @app.get("/api/asset-attribution/jobs/{job_id}")
    def asset_job(job_id: str):
        return jobs.get(job_id)

    @app.post("/api/asset-attribution/jobs/{job_id}/cancel")
    def cancel_assets(job_id: str):
        return jobs.cancel(job_id)

    @app.get("/api/asset-attribution/results/{lookup_id}")
    def asset_result(lookup_id: str):
        return saved_result(store, lookup_id)

    @app.post("/api/asset-attribution/results/{lookup_id}/adopt")
    def adopt_asset(lookup_id: str, body: AssetAdoptionRequest):
        return adopt_attribution(store, lookup_id, body.expected_revision)

    @app.get("/api/asset-attribution/results/{lookup_id}/evidence.zip")
    def asset_evidence(lookup_id: str):
        saved = saved_result(store, lookup_id)
        handle, path = tempfile.mkstemp(suffix=".zip")
        os.close(handle)
        try:
            with (
                tempfile.TemporaryDirectory() as temp,
                EvidenceStore(store.root / "attribution.sqlite3") as evidence_store,
            ):
                folder = Path(temp) / "attribution"
                EvidenceRenderer(evidence_store).export(saved["result_id"], folder)
                mark_attribution_bundle(folder)
                with ZipFile(path, "w", ZIP_DEFLATED) as archive:
                    for file in folder.rglob("*"):
                        if file.is_file():
                            archive.write(file, file.relative_to(folder))
        except Exception:
            Path(path).unlink(missing_ok=True)
            raise
        return FileResponse(
            path,
            filename=f"asset-attribution-{saved['root_domain']}.zip",
            background=BackgroundTask(Path(path).unlink, missing_ok=True),
        )
