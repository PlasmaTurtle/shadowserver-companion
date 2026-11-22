"""HTTP adapters for Library's revision-checked explainer lifecycle."""

from fastapi import HTTPException, Query

from ..api_models import BlockArchive, BlockCreate, BlockRevisionRequest, BlockUpdate
from ..services.content import ContentService, ExplainerConflict


def _result(operation, *args, **kwargs):
    try:
        return operation(*args, **kwargs)
    except ExplainerConflict as error:
        raise HTTPException(
            409,
            {
                "message": str(error),
                "current_revision": error.current["revision"],
                "current": error.current,
            },
        ) from error
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


def register(app, *, store):
    service = ContentService(store)

    @app.get("/api/explainers")
    def explainers(include_archived: bool = False):
        return service.list(include_archived=include_archived)

    @app.get("/api/explainers/{block_id}")
    def get_block(block_id: str):
        return _result(service.get, block_id)

    @app.get("/api/explainers/{block_id}/history")
    def history(
        block_id: str,
        before: int | None = Query(default=None, ge=1),
        limit: int = Query(default=30, ge=1, le=100),
    ):
        return _result(service.history, block_id, before=before, limit=limit)

    @app.get("/api/explainers/{block_id}/revisions/{revision}")
    def revision(block_id: str, revision: int):
        return _result(service.revision, block_id, revision)

    @app.get("/api/explainers/{block_id}/usage")
    def usage(
        block_id: str,
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ):
        return _result(service.usage, block_id, limit=limit, offset=offset)

    @app.put("/api/explainers/{block_id}")
    def save_block(block_id: str, body: BlockUpdate):
        return _result(
            service.update,
            block_id,
            body.content_values(preserve_omitted=True),
            body.expected_revision,
        )

    @app.post("/api/explainers")
    def add_block(body: BlockCreate):
        return _result(service.create, body.content_values())

    @app.post("/api/explainers/{block_id}/archive")
    def archive(block_id: str, body: BlockArchive):
        return _result(service.archive, block_id, body.expected_revision, body.archived)

    @app.post("/api/explainers/{block_id}/restore/{revision}")
    def restore(block_id: str, revision: int, body: BlockRevisionRequest):
        return _result(service.restore, block_id, revision, body.expected_revision)
