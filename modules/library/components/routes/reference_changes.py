"""Read-only HTTP adapter for reference changes affecting retained case sources."""

from fastapi import Query

from ..reference_changes import ReferenceChanges


def register(app, *, store, catalog):
    changes = ReferenceChanges(store, catalog)

    @app.get("/api/library/changes/{cve_id}/impact")
    def impact(
        cve_id: str,
        limit: int = Query(25, ge=1, le=100),
        offset: int = Query(0, ge=0, le=500000),
        include_completed: bool = False,
    ):
        return changes.impact(
            cve_id, limit=limit, offset=offset, include_completed=include_completed
        )
