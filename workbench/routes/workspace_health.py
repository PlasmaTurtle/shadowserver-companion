"""Health jobs and explicitly reviewed, evidence-preserving maintenance."""

from pydantic import BaseModel, Field

from ..workspace_health_jobs import WorkspaceHealthJobs
from ..workspace_maintenance import plan, cleanup


class CleanupData(BaseModel):
    confirmation: str
    cutoff: float = Field(gt=0, allow_inf_nan=False)
    token: str = Field(pattern=r"^[0-9a-f]{64}$")


class RebuildData(BaseModel):
    confirmation: str


def register(app, *, store):
    jobs = WorkspaceHealthJobs(store.root)
    app.state.workspace_health_jobs = jobs

    @app.get("/api/data/health")
    def health_status():
        return jobs.get()

    @app.post("/api/data/health")
    def health_start():
        gate = app.state.workspace_data
        with gate.lock:
            if gate.preparing or gate.pending:
                raise ValueError(
                    "Finish or cancel the pending workspace operation before checking health"
                )
            return jobs.start()

    @app.delete("/api/data/health")
    def health_cancel():
        return jobs.cancel()

    @app.get("/api/data/maintenance")
    def maintenance_plan():
        return plan(store.root)

    @app.post("/api/data/maintenance")
    def maintenance_apply(body: CleanupData):
        if body.confirmation != "CLEAN":
            raise ValueError("Type CLEAN after reviewing the cleanup estimate")
        with app.state.workspace_data.operation():
            return cleanup(store.root, cutoff=body.cutoff, token=body.token)

    @app.post("/api/data/analytical-index/rebuild")
    def rebuild_index(body: RebuildData):
        if body.confirmation != "REBUILD":
            raise ValueError("Type REBUILD to recreate disposable analytical counters")
        from ..analytical_index import available, reconcile, rebuild

        with app.state.workspace_data.operation(), store.transaction() as db:
            if not available(db):
                raise ValueError(
                    "This workspace must be upgraded before rebuilding its analytical index"
                )
            rebuild(db)
            result = reconcile(db)
            if not result["healthy"]:
                raise ValueError("Analytical index verification failed; changes were rolled back")
        return result
