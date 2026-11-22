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
from modules.accretion.components.intake_service import IntakeService
from modules.library.components.cve_sources import enrich
from modules.investigations.components.cases import Cases
from modules.observatory.components.eclipse import Eclipse
from modules.observatory.components.routes import eclipse as eclipse_routes
from .crypto_policy import validate_runtime
from .request_limits import RequestBodyLimit
from modules.library.components.source_jobs import SourceJobs
from modules.investigations.components.website_jobs import WebsiteCaptureJobs
from modules.attribution.components.asset_attribution import AssetAttributionJobs
from modules.entities.components.contact_jobs import ContactDiscoveryJobs
from modules.accretion.components.api_acquisition import APIAcquisition
from modules.accretion.components.scheduling import AcquisitionSchedule
from modules.settings.components.onboarding import SetupService
from modules.settings.components.software_updates import SoftwareUpdates
from modules.library.components.cve_catalog import Catalog, CatalogManager
from modules.library.components.cve_catalog.risk import RiskStore
from modules.library.components.cve_catalog.risk_manager import RiskManager
from modules.library.components.catalog_outreach import CatalogOutreach
from .workspace_data import WorkspaceData, apply_pending_workspace, before_schema_upgrade
from ..databases.migrations import SCHEMA_VERSION
from .local_session import LocalSessions, same_origin
from modules.investigations.components.services.drafts import DraftService
from modules.investigations.components.services.notification_views import load_notification
from .routes import overview as overview_routes
from modules.investigations.components.routes import cases as case_routes
from modules.entities.components.routes import entities as entity_routes
from modules.leads.components.lead_queue import LeadQueue
from modules.leads.components.routes import queue as lead_routes
from modules.investigations.components.routes import drafts as draft_routes
from modules.accretion.components.routes import intake as intake_routes
from modules.investigations.components.routes import evidence as evidence_routes
from modules.investigations.components.routes import reports as report_routes
from modules.library.components.routes import intelligence as intelligence_routes
from modules.library.components.routes import content as content_routes
from modules.library.components.routes import research as research_routes
from modules.library.components.routes import reference_changes as reference_change_routes
from modules.library.components.routes import vendor_statements as vendor_statement_routes
from .routes import workspace as workspace_routes
from modules.attribution.components.routes import assets as asset_routes
from modules.entities.components.routes import contacts as contact_routes
from modules.activity.components.routes import activity as activity_routes
from modules.accretion.components.routes import shadowserver_api as shadowserver_api_routes
from modules.library.components.routes import cve_catalog as cve_catalog_routes
from modules.settings.components.routes import onboarding as onboarding_routes
from modules.settings.components.routes import software_updates as software_update_routes
from modules.settings.components.routes import settings as settings_routes

ROOT = Path(__file__).resolve().parents[3]


def create_app(
    data_root=None,
    *,
    worker=True,
    demo=False,
    preview=False,
    attribution_factory=None,
    capture=None,
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
    intake = IntakeService(store, attribution_factory=attribution_factory, capture=capture)
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
                    lambda name=name: getattr(app.state, name).close()
                    if hasattr(app.state, name)
                    else None
                )
            cleanup.callback(
                lambda: app.state.workspace_health_jobs.shutdown()
                if hasattr(app.state, "workspace_health_jobs")
                else None
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
    overview_routes.register(app, store=store, token=token, demo=demo)
    eclipse_routes.register(app, eclipse=eclipse)
    case_routes.register(app, store=store, cases=cases, get_lead=get_lead)
    lead_queue = LeadQueue(store)
    lead_routes.register(app, queue=lead_queue)
    entity_routes.register(app, store=store, cases=cases, get_lead=get_lead, queue=lead_queue)
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
    content_routes.register(app, store=store)
    research_routes.register(app, store=store, catalog=catalog_manager)
    reference_change_routes.register(app, store=store, catalog=catalog_manager)
    vendor_statement_routes.register(app, store=store)
    settings_routes.register(app, store=store)
    onboarding_routes.register(app, setup=setup)
    software_update_routes.register(app, updates=software_updates)
    asset_routes.register(app, store=store, jobs=asset_attribution_jobs)
    contact_routes.register(app, store=store, jobs=contact_discovery_jobs, cases=cases)
    activity_routes.register(app, store=store)
    shadowserver_api_routes.register(
        app, acquisition=api_acquisition, schedule=acquisition_schedule
    )
    cve_catalog_routes.register(
        app,
        manager=catalog_manager,
        outreach=CatalogOutreach(eclipse, catalog_manager),
        workspace_root=root,
    )

    # Expose each module's browser assets without serving its Python source or tests.
    for module in (
        "workspace",
        "investigations",
        "observatory",
        "entities",
        "leads",
        "attribution",
        "accretion",
        "library",
        "settings",
        "activity",
        "ui",
    ):
        app.mount(
            f"/modules/{module}/static",
            StaticFiles(directory=ROOT / "modules" / module / "static"),
            name=f"static-{module}",
        )

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return FileResponse(
            ROOT / "modules/ui/static/favicon.ico", media_type="image/vnd.microsoft.icon"
        )

    @app.get("/")
    def index():
        return FileResponse(
            ROOT / "modules/ui/static/index.html", headers={"Cache-Control": "no-store"}
        )

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["*"] if preview else ["localhost", "127.0.0.1", "[::1]"],
    )
    return app
