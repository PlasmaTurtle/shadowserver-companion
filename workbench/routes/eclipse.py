"""Local read-only Observatory snapshots and bounded relationship projections."""

from typing import Literal
from fastapi import HTTPException, Query


def register(app, *, eclipse):
    @app.get("/api/dark-matter")
    def dark_matter(
        q: str = Query("", max_length=200),
        limit: int = Query(25, ge=1, le=100),
        offset: int = Query(0, ge=0, le=10000000),
    ):
        from ..dark_matter import browse

        return browse(eclipse.store, q=q, limit=limit, offset=offset)

    @app.get("/api/eclipse")
    def eclipse_snapshot(product_id: str = Query("", max_length=100)):
        if product_id:
            from ..observatory_intelligence import validate_query

            validate_query(product_id=product_id)
        return eclipse.snapshot(product_id=product_id)

    @app.get("/api/eclipse/intelligence")
    def eclipse_intelligence(
        lens: Literal[
            "organization", "ip", "service", "vulnerability", "version"
        ] = "vulnerability",
        q: str = Query(default="", max_length=300),
        entity_id: str = Query(default="", max_length=100),
        ip: str = Query(default="", max_length=45),
        cve: str = Query(default="", max_length=100),
        condition: str = Query(default="", max_length=300),
        service: str = Query(default="", max_length=300),
        date_from: str = Query(default="", max_length=10),
        date_to: str = Query(default="", max_length=10),
        status: str = Query(default="", max_length=40),
        intake: Literal["", "lead", "dark_matter", "unclassified"] = "",
        unplaced: bool = False,
        include_undated: bool = False,
        network: str = Query(default="", max_length=20),
        intelligence: Literal["all", "critical", "critical_kev", "kev", "ransomware"] = "all",
        product_id: str = Query(default="", max_length=100),
        focus: str = Query(default="", max_length=100),
        max_nodes: int = Query(default=180, ge=2, le=300),
        max_edges: int = Query(default=300, ge=1, le=600),
    ):
        return eclipse.intelligence(
            lens=lens,
            q=q,
            entity_id=entity_id,
            ip=ip,
            cve=cve,
            condition=condition,
            service=service,
            date_from=date_from,
            date_to=date_to,
            status=status,
            intake=intake,
            unplaced=unplaced,
            include_undated=include_undated,
            network=network,
            intelligence=intelligence,
            product_id=product_id,
            focus=focus,
            max_nodes=max_nodes,
            max_edges=max_edges,
        )

    @app.get("/api/eclipse/view")
    def eclipse_view(
        lens: Literal["organization", "ip", "service", "vulnerability", "version"] = "organization",
        q: str = Query("", max_length=300),
        entity_id: str = Query("", max_length=100),
        asset_id: str = Query("", max_length=100),
        city: str = Query("", max_length=300),
        region: str = Query("", max_length=300),
        country: str = Query("", max_length=300),
        location_key: str = Query("", max_length=100),
        product_name: str = Query("", max_length=300),
        version: str = Query("", max_length=300),
        ip: str = Query("", max_length=45),
        cve: str = Query("", max_length=100),
        condition: str = Query("", max_length=300),
        service: str = Query("", max_length=300),
        date_from: str = Query("", max_length=10),
        date_to: str = Query("", max_length=10),
        status: str = Query("", max_length=40),
        intake: Literal["", "lead", "dark_matter", "unclassified"] = "",
        unplaced: bool = False,
        include_undated: bool = False,
        network: str = Query("", max_length=20),
        intelligence: Literal["all", "critical", "critical_kev", "kev", "ransomware"] = "all",
        product_id: str = Query("", max_length=100),
        focus: str = Query("", max_length=100),
        max_nodes: int = Query(180, ge=2, le=300),
        max_edges: int = Query(300, ge=1, le=600),
        records_only: bool = False,
        field_only: bool = False,
        field_limit: int = Query(24, ge=1, le=60),
        field_offset: int = Query(0, ge=0, le=10000000),
        field_revision: str = Query("", max_length=24, pattern="^[a-f0-9]{0,24}$"),
        field_asset_limit: int = Query(120, ge=1, le=240),
        field_asset_offset: int = Query(0, ge=0, le=10000000),
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0, le=10000000),
    ):
        values = {key: value for key, value in locals().items() if key != "eclipse"}
        from ..observatory_field import FieldRevisionChanged

        try:
            return eclipse.view(**values)
        except FieldRevisionChanged as error:
            raise HTTPException(
                409, {"code": "field_revision_changed", "message": str(error)}
            ) from error

    @app.get("/api/eclipse/observations/{observation_id}")
    def eclipse_observation(
        observation_id: str,
        finding_id: str = Query("", max_length=100),
        intake: Literal["", "dark_matter"] = "",
    ):
        value = eclipse.observation(observation_id, finding_id=finding_id, intake=intake)
        if value is None:
            raise HTTPException(404, "Observation not found")
        return value
