"""Research discovery and saved-view HTTP adapters."""

from fastapi import HTTPException, Query
from ..reviewed_guides import GuideResults, ReviewedGuide, guides

from ..research import Research, SavedViewInput, SavedViewUpdate, SavedViewImport, SavedViewConflict


def register(app, *, store, catalog):
    research = Research(store, catalog)

    @app.get("/api/library/guides")
    def reviewed_guides(q: str = Query(default="", max_length=200)) -> GuideResults:
        return {"items": guides(q)}

    @app.get("/api/library/guides/{guide_id}")
    def reviewed_guide(guide_id: str) -> ReviewedGuide:
        for guide in guides(guide_id):
            if guide["id"] == guide_id:
                return guide
        raise HTTPException(404, "Guide not found")

    def command(operation):
        try:
            return operation()
        except SavedViewConflict as error:
            raise HTTPException(409, str(error)) from error
        except KeyError as error:
            raise HTTPException(404, str(error.args[0])) from error

    @app.get("/api/library/views")
    def views():
        return research.views()

    @app.post("/api/library/views")
    def create_view(body: SavedViewInput):
        return research.create_view(body)

    @app.post("/api/library/views/import")
    def import_views(body: SavedViewImport):
        return research.import_views(body)

    @app.put("/api/library/views/{identity}")
    def update_view(identity: str, body: SavedViewUpdate):
        return command(lambda: research.update_view(identity, body))

    @app.delete("/api/library/views/{identity}")
    def delete_view(identity: str, expected_revision: int = Query(ge=1)):
        return command(lambda: research.delete_view(identity, expected_revision))

    @app.get("/api/library/search")
    def search(
        q: str = Query(default="", max_length=200), limit: int = Query(default=10, ge=1, le=25)
    ):
        return research.search(q, limit)
