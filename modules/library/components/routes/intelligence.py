"""Intelligence HTTP adapters."""

from __future__ import annotations

from modules.workspace.components.primitives import dump, now
from ..cve_sources import identifiers
from modules.library.components.api_models import (
    SourceJobRequest,
)
from ..intelligence.selection_identity import selection_key


def register(app, *, store, source_jobs, fetch):
    def retain_selections(records):
        with store.transaction() as db:
            for record in records:
                db.execute(
                    "INSERT OR IGNORE INTO cache VALUES(?,?,?)",
                    (selection_key(record), dump(record), now()),
                )

    def retained_job(result):
        # A local retrieval may finish before its POST response is returned, or
        # while cancellation is requested. Every emitted record must be an
        # adoptable immutable selection even if the browser never polls GET.
        retain_selections(result["results"])
        return result

    @app.post("/api/cves/{cve_id}/retrieve")
    def cve(cve_id: str, refresh: bool = False):
        result = fetch(store, cve_id, refresh=refresh)
        retain_selections([result])
        return result

    @app.post("/api/source-jobs")
    def start_source_job(body: SourceJobRequest):
        values = identifiers(body.cve_ids)
        if set(values) != set(body.cve_ids):
            raise ValueError("Each source request must be an exact uppercase CVE identifier")
        return retained_job(
            source_jobs.start(
                values, body.refresh, **({"local_only": True} if body.local_only else {})
            )
        )

    @app.get("/api/source-jobs/{job_id}")
    def source_job(job_id: str):
        return retained_job(source_jobs.get(job_id))

    @app.post("/api/source-jobs/{job_id}/cancel")
    def cancel_source_job(job_id: str):
        return retained_job(source_jobs.cancel(job_id))
