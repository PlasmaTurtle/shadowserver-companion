"""Authenticated local cross-record search."""

from fastapi import Query
from datetime import date

from ..search import search_records
from ..workspace_brief import workspace_brief


def register(app, *, store):
    @app.get("/api/search")
    def search(
        q: str = Query(default="", max_length=120), limit: int = Query(default=6, ge=1, le=10)
    ):
        return search_records(store, q, limit)

    @app.get("/api/workspace/brief")
    def brief(as_of: date | None = None):
        return workspace_brief(store, as_of)
