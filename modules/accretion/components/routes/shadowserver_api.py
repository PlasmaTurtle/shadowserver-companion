"""Authenticated local endpoints for Shadowserver API acquisition and schedules."""

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictBool
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse

from ..shadowserver_reports.errors import ShadowserverError


class CredentialsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: SecretStr = Field(min_length=1, max_length=1024)
    secret: SecretStr = Field(min_length=1, max_length=1024)
    remember: bool = False


class CatalogSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: str = Field(max_length=10)
    end: str = Field(max_length=10)
    subscription: str = Field(min_length=1, max_length=1024)
    report_type: str = Field(min_length=1, max_length=256)


class ImportSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_ids: list[str] = Field(min_length=1, max_length=100)
    narrative_date_basis: str | None = None  # Ignored legacy clients; not an admission requirement.


class ScheduleValues(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool = False
    hour: int = Field(default=6, ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)
    interval_hours: int = Field(default=4, ge=1, le=24)
    lookback_days: int = Field(default=7, ge=1, le=30)
    shadowserver: StrictBool = True
    reference: StrictBool = True
    subscription: str = Field(default="", max_length=1024)
    report_types: list[str] = Field(default_factory=list, max_length=64)


class BackgroundValues(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool


def register(app, *, acquisition, schedule=None):
    @app.exception_handler(RequestValidationError)
    async def safe_validation_error(request, error):
        # Pydantic's ordinary JSON error includes the rejected input, even for
        # SecretStr fields whose conversion/length validation did not succeed.
        if request.url.path in {"/api/shadowserver/credentials", "/api/nvd/credentials"}:
            return JSONResponse({"detail": "Enter valid API credentials."}, status_code=422)
        return await request_validation_exception_handler(request, error)

    @app.exception_handler(ShadowserverError)
    async def acquisition_error(request, error):
        return JSONResponse({"detail": str(error)}, status_code=400)

    @app.get("/api/shadowserver/status")
    def status():
        return {**acquisition.status(), "schedule": schedule.status() if schedule else None}

    @app.put("/api/shadowserver/credentials")
    def credentials(body: CredentialsUpdate):
        return acquisition.configure(
            body.api_key.get_secret_value(), body.secret.get_secret_value(), remember=body.remember
        )

    @app.delete("/api/shadowserver/credentials")
    def forget():
        return acquisition.forget()

    @app.post("/api/shadowserver/connection")
    def connection():
        return acquisition.start("connection")

    @app.post("/api/shadowserver/catalog")
    def catalog(body: CatalogSelection):
        return acquisition.start("catalog", selection=body.model_dump())

    @app.post("/api/shadowserver/import")
    def import_reports(body: ImportSelection):
        return acquisition.start("import", report_ids=body.report_ids)

    @app.get("/api/shadowserver/jobs/{identity}")
    def job(identity: str):
        return acquisition.get(identity)

    @app.post("/api/shadowserver/jobs/{identity}/cancel")
    def cancel(identity: str):
        return acquisition.cancel(identity)

    if schedule is not None:

        @app.get("/api/schedule")
        def schedule_status():
            return schedule.status()

        @app.put("/api/schedule")
        def schedule_settings(body: ScheduleValues):
            return schedule.configure(body.model_dump())

        @app.post("/api/schedule/run")
        def schedule_run():
            return schedule.request_run()

        @app.put("/api/schedule/background")
        def schedule_background(body: BackgroundValues):
            from ..windows_schedule import configure

            with schedule.lock:
                if schedule.busy():
                    raise ValueError(
                        "Wait for scheduled intake to finish before changing background operation"
                    )
                state = schedule._read()
                if body.enabled:
                    if not state.get("config", {}).get("enabled"):
                        raise ValueError("Save an enabled schedule first")
                    schedule._validate_scope(state["config"])
                    if (
                        state["config"].get("shadowserver")
                        and acquisition.status().get("storage") != "windows"
                    ):
                        raise ValueError(
                            "Save the Shadowserver key in Windows Credential Manager for closed-app imports"
                        )
                    if state["config"].get("reference"):
                        from modules.library.components.cve_catalog.credentials import NVDKeys

                        if NVDKeys(acquisition.store.root).status().get("source") != "windows":
                            raise ValueError(
                                "Save the NVD key in Windows Credential Manager for closed-app updates"
                            )
                state["background"] = configure(acquisition.store.root, body.enabled)
                schedule._write(state)
            return schedule.status()
