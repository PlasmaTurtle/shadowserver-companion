"""Read-only HTTP adapter for reference changes affecting retained case sources."""

from typing import TypedDict

from fastapi import Query

from ..reference_changes import ReferenceChanges


class OpenKevChange(TypedDict):
    case_id: str
    case_title: str
    cve_id: str
    previous: bool
    listed: bool
    pinned_at: str | None
    url: str


class OpenKevChanges(TypedDict):
    items: list[OpenKevChange]
    total: int
    offset: int
    limit: int
    comparable: int
    unknown: int
    unreadable_cases: int
    source: dict | None
    notice: str | None


def register(app, *, store, catalog):
    changes = ReferenceChanges(store, catalog)

    @app.get("/api/library/changes/open-kev")
    def open_kev_changes(
        limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0, le=500000)
    ) -> OpenKevChanges:
        return changes.open_kev_changes(limit=limit, offset=offset)

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
