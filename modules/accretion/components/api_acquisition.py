"""API acquisition using the independently tested Reports module.

Credentials and download capabilities never enter the workspace database or
browser responses. Completed reports enter the same bounded intake as files.
"""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date
import hashlib
import os
from pathlib import Path
import tempfile
import threading

from .api_import import enqueue_download
from .api_jurisdiction import available_subscriptions, require_subscription
from modules.workspace.components.primitives import now, uid
from .shadowserver_reports import (
    Credentials,
    Operation,
    ReportDownloader,
    ReportsClient,
    ReportSelection,
    SignedTransport,
)
from .shadowserver_reports.credentials import WindowsCredentialProvider
from .shadowserver_reports.errors import Cancelled, ConfigurationError, ShadowserverError


class APIAcquisition:
    def __init__(self, store, intake, *, transport_factory=None, downloader_factory=None):
        self.store, self.intake = store, intake
        self.lock = threading.RLock()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="companion-api")
        self.transport_factory = transport_factory or SignedTransport
        self.downloader_factory = downloader_factory or ReportDownloader
        profile = "companion-" + hashlib.sha256(str(store.root.resolve()).encode()).hexdigest()[:24]
        self.windows = WindowsCredentialProvider(profile)
        self.session_credentials = None
        self.jobs = {}
        self.catalog = {}
        self.catalog_completeness = None
        self.catalog_reasons = []
        self.subscriptions = []
        self.types = []
        self.connected = False
        self.closed = False
        self.scheduled_active = False

    def _credentials(self):
        if self.session_credentials is not None:
            return self.session_credentials
        if os.name == "nt":
            return self.windows()
        raise ConfigurationError("Configure an API key and secret first.")

    def configure(self, api_key, secret, *, remember=False):
        if (
            not isinstance(api_key, str)
            or not isinstance(secret, str)
            or any(
                not value.strip() or len(value) > 1024 or "\x00" in value
                for value in (api_key, secret)
            )
        ):
            raise ValueError("Enter a valid API key and secret.")
        credentials = Credentials(api_key, secret)
        with self.lock:
            self._idle()
            if remember:
                if os.name != "nt":
                    raise ConfigurationError("Saved credentials are available only on Windows.")
                self.windows.store(credentials)
                self.session_credentials = None
            else:
                # An explicit session-only replacement must not restore an old
                # saved account the next time the application opens.
                if os.name == "nt":
                    self.windows.delete()
                self.session_credentials = credentials
            self._clear_catalog()
        return self.status()

    def forget(self):
        with self.lock:
            self._idle()
            if os.name == "nt":
                self.windows.delete()
            self.session_credentials = None
            self._clear_catalog()
        return self.status()

    def _clear_catalog(self):
        self.catalog = {}
        self.catalog_completeness = None
        self.catalog_reasons = []
        self.connected = False
        self.subscriptions = []
        self.types = []

    def _idle(self):
        if self.closed:
            raise ValueError("API retrieval is closing.")
        if self.busy():
            raise ValueError("Wait for the current API operation or cancel it.")
        if getattr(self.store, "maintenance", threading.Event()).is_set():
            raise ValueError("A workspace data operation is in progress.")

    def _regions(self):
        return self.store.settings()["regions"]

    def scope_changed(self):
        """Invalidate old listed selections without losing the account catalog."""
        with self.lock:
            self.catalog = {}
            self.catalog_completeness = None
            self.catalog_reasons = []
        return self.status()

    def validate_schedule(self, config):
        """Reject stale scope before save/run; account data is memory-only."""
        if not config.get("shadowserver") or not config.get("subscription"):
            return
        require_subscription(config["subscription"], self._regions())
        with self.lock:
            if self.connected and (
                config["subscription"] not in self.subscriptions
                or not set(config.get("report_types", ())) <= {t["type"] for t in self.types}
            ):
                raise ConfigurationError(
                    "The saved API selection is no longer available. Connect and select "
                    "an available subscription and report types."
                )

    def status(self):
        with self.lock:
            try:
                self._credentials()
                configured = True
            except ConfigurationError:
                configured = False
            subscriptions, scope = available_subscriptions(self.subscriptions, self._regions())
            reports = [
                dict(report.public_dict(), id=key)
                for key, report in self.catalog.items()
                if report.subscription in subscriptions
            ]
            preferred = [
                name
                for name in ("scan_http_vulnerable", "scan6_http_vulnerable")
                if name in {item["type"] for item in self.types}
            ]
            return {
                "configured": configured,
                "connected": self.connected,
                "can_remember": os.name == "nt",
                "storage": "session"
                if self.session_credentials
                else "windows"
                if configured
                else None,
                "subscriptions": subscriptions,
                "jurisdiction": scope,
                "selection_defaults": {
                    "subscription": scope["matched_subscriptions"][0]
                    if len(scope["matched_subscriptions"]) == 1
                    else "",
                    "report_types": preferred,
                },
                "types": deepcopy(self.types),
                "reports": reports,
                "completeness": self.catalog_completeness,
                "reasons": list(self.catalog_reasons),
                "job": self.get(next(reversed(self.jobs))) if self.jobs else None,
            }

    def start(self, kind, *, selection=None, report_ids=None, narrative_date_basis=None):
        if kind not in {"connection", "catalog", "import"}:
            raise ValueError("Unknown API operation.")
        with self.lock:
            self._idle()
            credentials = self._credentials()
            reports = []
            if kind == "catalog":
                if not isinstance(selection, dict):
                    raise ValueError("Select a subscription, report type, and date range.")
                require_subscription(selection["subscription"], self._regions())
                selection = ReportSelection(
                    date.fromisoformat(selection["start"]),
                    date.fromisoformat(selection["end"]),
                    (selection["subscription"],),
                    (selection["report_type"],),
                    limit=100,
                )
                if (
                    not self.connected
                    or selection.subscriptions[0] not in self.subscriptions
                    or selection.types[0] not in {t["type"] for t in self.types}
                ):
                    raise ValueError(
                        "Connect and select an available subscription and report type."
                    )
                if (selection.end - selection.start).days > 30:
                    raise ValueError("Select no more than 31 days per retrieval.")
                # An unsuccessful refresh must not show the previous selection
                # as though it were the result of these dates and filters.
                self.catalog = {}
                self.catalog_completeness = None
                self.catalog_reasons = []
            elif kind == "import":
                if not isinstance(report_ids, list) or not 1 <= len(report_ids) <= 100:
                    raise ValueError("Select between 1 and 100 listed reports.")
                if any(not isinstance(key, str) or key not in self.catalog for key in report_ids):
                    raise ValueError("The report selection expired. List reports again.")
                reports = [self.catalog[key] for key in dict.fromkeys(report_ids)]
                for report in reports:
                    require_subscription(report.subscription, self._regions())
            identity = uid()
            for key in list(self.jobs)[:-19]:
                del self.jobs[key]
            self.jobs[identity] = {
                "id": identity,
                "kind": kind,
                "status": "queued",
                "created_at": now(),
                "completed": 0,
                "total": len(reports),
                "results": [],
                "message": "",
                "cancel": threading.Event(),
            }
            self.pool.submit(self._run, identity, credentials, selection, reports)
        return self.get(identity)

    def _run(self, identity, credentials, selection, reports):
        job = self.jobs[identity]
        operation = Operation(
            timeout=300 if job["kind"] == "import" else 120,
            max_requests=100,
            max_bytes=512 * 1024**2,
            cancel_event=job["cancel"],
        )
        with self.lock:
            job.update(status="running", started_at=now())
        try:
            operation.check()
            if job["kind"] == "import":
                with tempfile.TemporaryDirectory(prefix="companion-api-") as temporary:
                    downloader = self.downloader_factory(Path(temporary))
                    for report in reports:
                        operation.check()
                        require_subscription(report.subscription, self._regions())
                        receipt = downloader.download_report(report, operation=operation)
                        operation.check()
                        require_subscription(report.subscription, self._regions())
                        result = enqueue_download(self.intake, receipt.path, receipt)
                        with self.lock:
                            job["results"].append(
                                {
                                    "filename": report.filename,
                                    "import_id": result["id"],
                                    "duplicate": bool(result.get("duplicate")),
                                    "sha256": receipt.sha256,
                                }
                            )
                            job["completed"] += 1
            else:
                with self.transport_factory(lambda: credentials) as transport:
                    client = ReportsClient(transport)
                    if job["kind"] == "connection":
                        result = client.check_connection(operation=operation)
                        if not result["reports_access"]:
                            raise ConfigurationError(
                                "This key does not advertise Reports API access."
                            )
                        subscriptions = client.list_subscriptions(operation=operation)
                        types = client.list_report_types(operation=operation)
                        with self.lock:
                            operation.check()
                            self.connected = True
                            self.subscriptions = subscriptions
                            self.types = [
                                {
                                    "type": item if isinstance(item, str) else item["type"],
                                    "description": ""
                                    if isinstance(item, str)
                                    else str(item.get("description", ""))[:500],
                                }
                                for item in types
                            ]
                            job["completed"] = 1
                            job["total"] = 1
                    else:
                        require_subscription(selection.subscriptions[0], self._regions())
                        catalog = client.list_reports(selection, operation=operation)
                        with self.lock:
                            operation.check()
                            require_subscription(selection.subscriptions[0], self._regions())
                            self.catalog = {uid(): report for report in catalog.reports}
                            self.catalog_completeness = catalog.completeness
                            self.catalog_reasons = list(catalog.reasons)
                            job["completed"] = len(catalog.reports)
                            job["total"] = len(catalog.reports)
                            if catalog.completeness != "complete":
                                job["message"] = (
                                    "The report listing is incomplete. Narrow the date range or report selection."
                                )
            with self.lock:
                job["status"] = "completed"
        except Cancelled:
            with self.lock:
                job.update(
                    status="cancelled", message="Cancelled. Completed imports were retained."
                )
        except ShadowserverError as error:
            with self.lock:
                job.update(
                    status="partial" if job["completed"] else "failed",
                    message=str(error),
                    error_code=error.code,
                )
                if job["kind"] == "connection":
                    self.connected = False
        except (ValueError, OSError):
            with self.lock:
                job.update(
                    status="partial" if job["completed"] else "failed",
                    message="The downloaded report could not be imported. Completed imports were retained.",
                    error_code="import_error",
                )
        except Exception:
            # No upstream objects, tokens, request URLs, or credential text in
            # progress, logs, or exception responses.
            with self.lock:
                job.update(
                    status="partial" if job["completed"] else "failed",
                    message="API retrieval failed. Completed imports were retained.",
                    error_code="retrieval_error",
                )
        finally:
            with self.lock:
                job.update(
                    finished_at=now(),
                    requests=operation.requests,
                    bytes_received=operation.bytes_received,
                )

    def scheduled(self, config, start, end, *, cancel_event, queued):
        """Read current catalog and enqueue full intake; no browser catalog state."""
        with self.lock:
            self._idle()
            self.validate_schedule(config)
            credentials = self._credentials()
            self.scheduled_active = True
        operation = Operation(
            timeout=1800, max_requests=1000, max_bytes=2 * 1024**3, cancel_event=cancel_event
        )
        try:
            selection = ReportSelection(
                start, end, (config["subscription"],), tuple(config["report_types"]), limit=1000
            )
            with self.transport_factory(lambda: credentials) as transport:
                catalog = ReportsClient(transport).list_reports(selection, operation=operation)
            require_subscription(config["subscription"], self._regions())
            if catalog.completeness != "complete":
                raise ValueError(
                    "Scheduled report listing was incomplete; narrow its report selection"
                )
            with tempfile.TemporaryDirectory(prefix="companion-scheduled-") as temporary:
                downloader = self.downloader_factory(Path(temporary))
                for report in catalog.reports:
                    operation.check()
                    require_subscription(report.subscription, self._regions())
                    receipt = downloader.download_report(report, operation=operation)
                    operation.check()
                    require_subscription(report.subscription, self._regions())
                    result = enqueue_download(self.intake, receipt.path, receipt)
                    existing = self.store.one(
                        "SELECT status FROM imports WHERE id=?", (result["id"],)
                    )
                    if existing and existing["status"] == "needs_retry":
                        self.intake.retry(result["id"])
                    queued({"import_id": result["id"], "duplicate": bool(result.get("duplicate"))})
        finally:
            with self.lock:
                self.scheduled_active = False

    def get(self, identity):
        with self.lock:
            if identity not in self.jobs:
                raise ValueError(
                    "API operation is unavailable. Imported reports remain in Shadowserver Data."
                )
            return deepcopy(
                {key: value for key, value in self.jobs[identity].items() if key != "cancel"}
            )

    def cancel(self, identity):
        with self.lock:
            if identity not in self.jobs:
                raise ValueError("API operation not found.")
            self.jobs[identity]["cancel"].set()
        return self.get(identity)

    def busy(self):
        with self.lock:
            return self.scheduled_active or any(
                job["status"] in {"queued", "running"} for job in self.jobs.values()
            )

    def close(self):
        with self.lock:
            self.closed = True
            for job in self.jobs.values():
                job["cancel"].set()
        # Drain the producer before the application's intake consumer closes.
        # Queued work runs its cancellation check and reaches a terminal state.
        self.pool.shutdown(wait=True, cancel_futures=False)
        with self.lock:
            self.session_credentials = None
            self._clear_catalog()
