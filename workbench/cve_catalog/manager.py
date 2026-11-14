"""Opt-in daily catalog work while the local application is running."""

from copy import deepcopy
from datetime import timedelta
import logging
import sqlite3
import threading
import time

from .storage import date, stamp
from .transport import CatalogCancelled, CatalogDeferred


class CatalogManager:
    def __init__(self, catalog, *, risk=None, maintenance=None):
        self.catalog = catalog
        self.risk = risk
        self.maintenance = maintenance if maintenance is not None else threading.Event()
        if self.risk is not None and maintenance is not None:
            self.risk.maintenance = maintenance
        self.lock = threading.RLock()
        self.stopped = threading.Event()
        self.cancellation = threading.Event()
        self.scheduler = None
        self.worker = None
        self.index_worker = None
        self.index_cancellation = threading.Event()
        self.index_job = {"status": "idle", "message": "", "records": 0}
        self.retry_not_before = 0.0
        self.job = {"status": "idle", "phase": None, "message": "", "records": 0, "error": None}

    def busy(self):
        with self.lock:
            running = any(
                thread is not None and thread.is_alive()
                for thread in (self.worker, self.index_worker)
            )
        return running or bool(self.risk and self.risk.busy())

    def status(self):
        with self.lock:
            job = deepcopy(self.job)
            running = self.worker is not None and self.worker.is_alive()
        try:
            status = self.catalog.status()
            index_status = (
                self.catalog.index_status() if hasattr(self.catalog, "index_status") else None
            )
        except (ValueError, OSError, sqlite3.Error):
            index_status = {"ready": False, "error": "Product index is unavailable"}
            status = {
                "source": "NVD",
                "total": 0,
                "enabled": False,
                "bootstrap_complete": False,
                "stale": True,
                "last_error": "The local CVE catalog is unavailable. Existing case records are unaffected.",
                "years_complete": [],
                "required_years": [],
                "last_success_at": None,
                "next_check_at": None,
                "db_bytes": 0,
            }
        return {
            **status,
            "job": job,
            "running": running,
            "schedule": "Every 24 hours while this application runs; overdue updates resume on next launch.",
            "risk": self.risk.status() if self.risk else None,
            "index_job": deepcopy(self.index_job),
            "index_running": bool(self.index_worker and self.index_worker.is_alive()),
            "index_status": index_status,
        }

    def start(self):
        with self.lock:
            if self.scheduler is not None or self.stopped.is_set():
                return
            self.scheduler = threading.Thread(
                target=self._schedule, name="cve-catalog-schedule", daemon=True
            )
            self.scheduler.start()
            if self.risk:
                self.risk.start()
            if self.catalog.db.is_file() and not self.maintenance.is_set():
                self.index()

    def index(self):
        with self.lock:
            if (
                self.maintenance.is_set()
                or not hasattr(self.catalog, "build_index")
                or self.stopped.is_set()
                or self.index_worker
                and self.index_worker.is_alive()
            ):
                return self.status()
            self.index_cancellation = threading.Event()
            self.index_job = {
                "status": "running",
                "message": "Preparing product index",
                "records": 0,
            }
            self.index_worker = threading.Thread(
                target=self._index, name="catalog-product-index", daemon=True
            )
            self.index_worker.start()
        return self.status()

    def _index(self):
        try:
            self.catalog.build_index(
                cancel_event=self.index_cancellation, progress=self._index_progress
            )
            self._index_progress({"status": "complete", "message": "Product index is ready"})
        except CatalogCancelled:
            self._index_progress({"status": "cancelled", "message": "Indexing paused"})
        except Exception:
            self._index_progress(
                {
                    "status": "error",
                    "message": "Product indexing could not finish; existing records remain available",
                }
            )

    def _index_progress(self, value):
        with self.lock:
            self.index_job.update(value)

    def sync_risk(self):
        if self.risk is None:
            raise ValueError("Risk feed updater is unavailable")
        return self.risk.sync()

    def cancel_risk(self):
        return self.risk.cancel() if self.risk else None

    def _schedule(self):
        while not self.stopped.is_set():
            try:
                enabled = self.catalog.metadata("enabled", False)
                next_check = self.catalog.metadata("next_check_at")
                due = not next_check or date(next_check) <= self.catalog.clock()
                if enabled and due and time.monotonic() >= self.retry_not_before:
                    self._start_job()
            except (OSError, ValueError, sqlite3.Error):
                logging.getLogger(__name__).warning(
                    "CVE catalog schedule unavailable; core workspace remains available"
                )
            if self.stopped.wait(60):
                return

    def sync(self):
        if self.stopped.is_set():
            raise ValueError("The catalog worker is closed")
        with self.lock:
            if self.maintenance.is_set():
                raise ValueError("A workspace data operation or update is in progress")
            if self.worker is not None and self.worker.is_alive():
                raise ValueError("A catalog update is already running")
            self.catalog.check_retry()
            self.catalog.set_enabled(True)
            if self.risk:
                try:
                    self.risk.sync()
                except (OSError, ValueError, sqlite3.Error):
                    logging.getLogger(__name__).warning(
                        "Risk updater is unavailable; continuing the CVE catalog update"
                    )
            self._start_job()
        return self.status()

    def _start_job(self):
        with self.lock:
            if (
                self.stopped.is_set()
                or self.maintenance.is_set()
                or self.worker is not None
                and self.worker.is_alive()
            ):
                return
            self.cancellation = threading.Event()
            self.job = {
                "status": "running",
                "phase": "starting",
                "message": "Starting catalog update",
                "records": 0,
                "error": None,
                "started_at": stamp(self.catalog.clock()),
                "completed_at": None,
            }
            self.worker = threading.Thread(target=self._run, name="cve-catalog-sync", daemon=True)
            self.worker.start()

    def _progress(self, values):
        with self.lock:
            self.job.update(values)

    def _run(self):
        try:
            self.catalog.sync(cancel_event=self.cancellation, progress=self._progress)
            self.index()
            self._progress({"status": "complete", "message": "Catalog is up to date"})
        except CatalogCancelled:
            self._progress(
                {"status": "cancelled", "message": "Update paused; completed records are retained"}
            )
            self._failure(None, 86400)
        except Exception as error:
            message = (
                str(error)
                if isinstance(error, (ValueError, CatalogDeferred))
                else "Catalog update failed; existing records remain available."
            )
            self._progress({"status": "error", "message": message, "error": message})
            if isinstance(error, CatalogDeferred):
                self.catalog._defer(error)
            self._failure(
                message, error.retry_after if isinstance(error, CatalogDeferred) else 3600
            )
            logging.getLogger(__name__).warning(
                "CVE catalog update failed: %s", type(error).__name__
            )
        finally:
            self._progress({"completed_at": stamp(self.catalog.clock())})

    def _failure(self, message, delay):
        # Retain backoff even if disk failure prevents persisting its timestamp.
        self.retry_not_before = time.monotonic() + delay
        try:
            self.catalog.put_metadata("last_error", message)
            self.catalog.put_metadata(
                "next_check_at", stamp(self.catalog.clock() + timedelta(seconds=delay))
            )
        except (ValueError, OSError, sqlite3.Error, OverflowError):
            pass

    def cancel(self):
        self.cancellation.set()
        self.index_cancellation.set()
        if self.risk:
            self.risk.cancel()
        return self.status()

    def close(self):
        self.stopped.set()
        self.cancellation.set()
        self.index_cancellation.set()
        if self.risk:
            self.risk.close()
        # Requests have a finite transport timeout. Daemon workers never hold
        # application shutdown hostage; SQLite rolls an interrupted txn back.
        if self.scheduler is not None:
            self.scheduler.join(timeout=1)
        if self.worker is not None:
            self.worker.join(timeout=1)
        if self.index_worker is not None:
            self.index_worker.join(timeout=1)
