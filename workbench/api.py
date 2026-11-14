"""Compose the local application, lifecycle, and existing request boundary."""

from __future__ import annotations

import secrets
import sqlite3
from pathlib import Path
from contextlib import asynccontextmanager, closing, ExitStack
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .store import Store
from .intake_service import IntakeService
from .cve_sources import enrich
from .cases import Cases
from .eclipse import Eclipse
from .crypto_policy import validate_runtime
from .request_limits import RequestBodyLimit
from .source_jobs import SourceJobs
from .website_jobs import WebsiteCaptureJobs
from .asset_attribution import AssetAttributionJobs
from .contact_jobs import ContactDiscoveryJobs
from .api_acquisition import APIAcquisition
from .scheduling import AcquisitionSchedule
from .onboarding import SetupService
from .software_updates import SoftwareUpdates
from .cve_catalog import Catalog, CatalogManager
from .cve_catalog.risk import RiskStore
from .cve_catalog.risk_manager import RiskManager
from .catalog_outreach import CatalogOutreach
from .workspace_data import WorkspaceData, apply_pending_workspace, before_schema_upgrade
from .migrations import SCHEMA_VERSION
from .local_session import LocalSessions, same_origin
from .services.drafts import DraftService
from .services.notification_views import load_notification
from .routes import overview as overview_routes
from .routes import cases as case_routes
from .routes import entities as entity_routes
from .routes import drafts as draft_routes
from .routes import intake as intake_routes
from .routes import evidence as evidence_routes
from .routes import reports as report_routes
from .routes import intelligence as intelligence_routes
from .routes import workspace as workspace_routes
from .routes import assets as asset_routes
from .routes import contacts as contact_routes
from .routes import activity as activity_routes
from .routes import shadowserver_api as shadowserver_api_routes
from .routes import search as search_routes
from .routes import cve_catalog as cve_catalog_routes
from .routes import onboarding as onboarding_routes
from .routes import software_updates as software_update_routes
from .api_models import (
    AttributionReviewValues as AttributionReviewValues,
    GroupRetryValues as GroupRetryValues,
    CVEDisposition as CVEDisposition,
    ReportTemplateValues as ReportTemplateValues,
    NarrativeValues as NarrativeValues,
    EntityProfileValues as EntityProfileValues,
    DraftValues as DraftValues,
    DraftUpdate as DraftUpdate,
    PresentationAdoption as PresentationAdoption,
    SourceJobRequest as SourceJobRequest,
    SettingsUpdate as SettingsUpdate,
    BlockSourceMetadata as BlockSourceMetadata,
    BlockUpdate as BlockUpdate,
    EvidenceUpdate as EvidenceUpdate,
    Delivery as Delivery,
    EntityRename as EntityRename,
    EntityMerge as EntityMerge,
    CaseCreate as CaseCreate,
    CaseVersion as CaseVersion,
    CaseRevision as CaseRevision,
    SectionVersion as SectionVersion,
    SectionReopen as SectionReopen,
    CasePlan as CasePlan,
    ContactAttempt as ContactAttempt,
    ClosingValues as ClosingValues,
)

ROOT = Path(__file__).resolve().parent.parent


def create_app(
    data_root=None,
    *,
    worker=True,
    demo=False,
    preview=False,
    lookup_factory=None,
    contact_discovery_factory=None,
    api_transport_factory=None,
    api_downloader_factory=None,
    report_processes=True,
    website_capture=None,
):
    validate_runtime()
    root = Path(data_root or ROOT / "data").resolve()
    apply_pending_workspace(root)
    if (root / "workbench.sqlite3").is_file():
        with closing(sqlite3.connect(root / "workbench.sqlite3")) as existing:
            prior_schema = existing.execute("PRAGMA user_version").fetchone()[0]
        before_schema_upgrade(root, prior_schema, SCHEMA_VERSION)
    store = Store(root)
    intake = IntakeService(store, lookup_factory)
    cases = Cases(store)
    eclipse = Eclipse(store)
    source_jobs = SourceJobs(store, enrich)
    website_jobs = WebsiteCaptureJobs(store, website_capture)
    catalog_manager = cve_catalog_routes.CatalogAccess(
        lambda: CatalogManager(
            Catalog(root),
            risk=RiskManager(
                RiskStore(root), enabled=lambda: Catalog(root).metadata("enabled", False)
            ),
        )
    )
    asset_attribution_jobs = AssetAttributionJobs(store)
    contact_discovery_jobs = ContactDiscoveryJobs(
        store, discovery_factory=contact_discovery_factory
    )
    api_acquisition = APIAcquisition(
        store,
        intake,
        transport_factory=api_transport_factory,
        downloader_factory=api_downloader_factory,
    )
    acquisition_schedule = AcquisitionSchedule(store, api_acquisition, catalog_manager)
    setup = SetupService(store, api_acquisition, acquisition_schedule)
    software_updates = SoftwareUpdates(root, root=ROOT)
    token = secrets.token_urlsafe(32)
    sessions = LocalSessions()

    @asynccontextmanager
    async def lifespan(app):
        # Every service closes on startup failure, shutdown error or cancellation.
        # ExitStack still runs remaining closers if one of them raises.
        with ExitStack() as cleanup:
            # Callbacks run in reverse: stop scheduling, drain the API producer,
            # then stop its intake consumer. Keep reference data available until
            # the other services have finished closing.
            for service in (
                catalog_manager,
                intake,
                api_acquisition,
                source_jobs,
                website_jobs,
                asset_attribution_jobs,
                contact_discovery_jobs,
                acquisition_schedule,
                software_updates,
            ):
                cleanup.callback(service.close)
            for name in ("entity_dns", "report_operations"):
                cleanup.callback(
                    lambda name=name: (
                        getattr(app.state, name).close() if hasattr(app.state, name) else None
                    )
                )
            cleanup.callback(
                lambda: (
                    app.state.workspace_health_jobs.shutdown()
                    if hasattr(app.state, "workspace_health_jobs")
                    else None
                )
            )
            if demo:
                from .demo import seed_demo

                seed_demo(store, intake)
            if worker:
                intake.start()
                if not demo and not preview:
                    catalog_manager.start()
                    contact_discovery_jobs.start_automatic()
                    acquisition_schedule.start()
            yield

    app = FastAPI(
        title="Shadowserver Companion",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(RequestBodyLimit)
    app.state.store, app.state.intake, app.state.token = store, intake, token
    app.state.sessions = sessions
    app.state.source_jobs = source_jobs
    app.state.website_jobs = website_jobs
    app.state.cve_catalog = catalog_manager
    app.state.asset_attribution_jobs = asset_attribution_jobs
    app.state.contact_discovery_jobs = contact_discovery_jobs
    app.state.api_acquisition = api_acquisition
    app.state.acquisition_schedule = acquisition_schedule
    app.state.setup = setup
    app.state.software_updates = software_updates
    app.state.report_processes = report_processes
    app.state.workspace_data = WorkspaceData(app, store)
    software_updates.install_guard = app.state.workspace_data.begin_update
    software_updates.install_cancel = app.state.workspace_data.cancel_update

    def protected_response(request, response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; frame-src 'self' blob:; object-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        is_api = request.url.path.startswith("/api/")
        public = request.url.path in ("/api/health", "/api/session/exchange", "/api/session/launch")
        if is_api and not public and not sessions.authorized(request):
            response = JSONResponse(
                {
                    "detail": "Open Shadowserver Companion from its desktop launcher to start a session."
                },
                status_code=401,
            )
        elif is_api and not same_origin(request):
            response = JSONResponse({"detail": "Request origin is not allowed."}, status_code=403)
        elif (
            request.method not in ("GET", "HEAD", "OPTIONS")
            and not public
            and not secrets.compare_digest(request.headers.get("X-Workbench-Token", ""), token)
        ):
            response = JSONResponse(
                {"detail": "Reload the app to refresh its session."}, status_code=403
            )
        else:
            admitted = is_api and not public
            problem = (
                app.state.workspace_data.enter_request(request.url.path, request.method)
                if admitted
                else None
            )
            if problem:
                response = JSONResponse({"detail": problem}, status_code=409)
            else:
                try:
                    response = await call_next(request)
                finally:
                    if admitted:
                        app.state.workspace_data.exit_request(request.url.path)
        return protected_response(request, response)

    @app.exception_handler(ValueError)
    async def invalid(request, error):
        return JSONResponse({"detail": str(error)}, status_code=422)

    @app.post("/api/session/exchange")
    async def session_exchange(request: Request):
        # Fixed-size credential in a header avoids arbitrary request-body parsing.
        session = sessions.exchange(request.headers.get("X-Workbench-Launch", ""))
        if session is None:
            return JSONResponse(
                {"detail": "Launch link is expired or already used. Reopen the desktop launcher."},
                status_code=401,
            )
        response = JSONResponse({"ok": True})
        response.set_cookie(
            sessions.cookie_name,
            session,
            httponly=True,
            samesite="strict",
            secure=request.url.scheme == "https",
            path="/api",
        )
        return response

    @app.post("/api/session/launch")
    def session_launch(request: Request):
        if not sessions.launcher_authorized(request.headers.get("X-Workbench-Launcher", "")):
            return JSONResponse({"detail": "Launcher authentication required."}, status_code=401)
        return {"launch": sessions.issue_launch()}

    def get_lead(lead_id, case_id=None):
        return load_notification(store, cases, lead_id, case_id)

    drafts = DraftService(store, cases)
    overview_routes.register(app, store=store, eclipse=eclipse, token=token, demo=demo)
    case_routes.register(app, store=store, cases=cases, get_lead=get_lead)
    entity_routes.register(app, store=store, cases=cases, get_lead=get_lead)
    draft_routes.register(app, store=store, get_lead=get_lead, drafts=drafts)
    intake_routes.register(app, store=store, intake=intake)
    evidence_routes.register(app, store=store, cases=cases, get_lead=get_lead)
    report_routes.register(app, store=store, cases=cases, get_lead=get_lead)
    intelligence_routes.register(
        app,
        store=store,
        source_jobs=source_jobs,
        fetch=lambda *args, **kwargs: enrich(*args, **kwargs),
    )
    workspace_routes.register(app, store=store)
    onboarding_routes.register(app, setup=setup)
    software_update_routes.register(app, updates=software_updates)
    asset_routes.register(app, store=store, jobs=asset_attribution_jobs)
    contact_routes.register(app, store=store, jobs=contact_discovery_jobs, cases=cases)
    activity_routes.register(app, store=store)
    shadowserver_api_routes.register(
        app, acquisition=api_acquisition, schedule=acquisition_schedule
    )
    search_routes.register(app, store=store)
    cve_catalog_routes.register(
        app,
        manager=catalog_manager,
        outreach=CatalogOutreach(eclipse, catalog_manager),
        workspace_root=root,
    )

    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return FileResponse(ROOT / "static/favicon.ico", media_type="image/vnd.microsoft.icon")

    @app.get("/")
    def index():
        return FileResponse(ROOT / "static/index.html", headers={"Cache-Control": "no-store"})

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["*"] if preview else ["localhost", "127.0.0.1", "[::1]"],
    )
    return app
