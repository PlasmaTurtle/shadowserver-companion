"""Independent daily risk feed scheduling while the application is open."""

from copy import deepcopy
from datetime import timedelta
import logging
import sqlite3
import threading

from .catalog import sync_lock
from .storage import date, stamp
from .transport import CatalogCancelled, CatalogDeferred


class RiskManager:
    def __init__(self, store, *, enabled=None, maintenance=None):
        self.store = store
        self.enabled = enabled or (lambda: False)
        self.maintenance = maintenance if maintenance is not None else threading.Event()
        self.lock = threading.RLock()
        self.stopped = threading.Event()
        self.cancellation = threading.Event()
        self.scheduler = None
        self.worker = None
        self.job = {"status": "idle", "phase": None, "message": "", "records": 0, "error": None}

    def busy(self):
        with self.lock:
            return bool(self.worker and self.worker.is_alive())

    def status(self):
        with self.lock:
            job = deepcopy(self.job)
            running = bool(self.worker and self.worker.is_alive())
        try:
            value = self.store.status()
            value["enabled"] = bool(value.get("enabled") or self.enabled())
        except ValueError, OSError, sqlite3.Error:
            value = {
                "epss": {"count": 0, "stale": True, "last_error": "Local EPSS data is unavailable"},
                "kev": {"count": 0, "stale": True, "last_error": "Local KEV data is unavailable"},
                "enabled": False,
            }
        return {
            **value,
            "running": running,
            "job": job,
            "schedule": "Daily while the application runs; overdue updates resume when it reopens.",
        }

    def start(self):
        with self.lock:
            if self.scheduler is not None or self.stopped.is_set():
                return
            self.scheduler = threading.Thread(
                target=self._schedule, name="risk-feed-schedule", daemon=True
            )
            self.scheduler.start()

    def _schedule(self):
        while not self.stopped.is_set():
            try:
                if self.store.metadata("enabled", False) or self.enabled():
                    providers = [name for name in ("epss", "kev") if self._due(name)]
                    if providers:
                        self._start_job(providers)
            except ValueError, OSError, sqlite3.Error:
                logging.getLogger(__name__).warning(
                    "Risk feed schedule is unavailable; existing work remains available"
                )
            if self.stopped.wait(60):
                return

    def _due(self, provider):
        state = self.store.metadata(provider, {})
        after = state.get("next_check_at") or state.get("retry_at")
        return not after or date(after) <= self.store.clock()

    def sync(self):
        if self.stopped.is_set():
            raise ValueError("Risk updater is closed")
        with self.lock:
            if self.maintenance.is_set():
                raise ValueError("A workspace data operation or update is in progress")
            self.store.put_metadata("enabled", True)
            self._start_job(["epss", "kev"])
        return self.status()

    def _start_job(self, providers):
        with self.lock:
            if (
                self.stopped.is_set()
                or self.maintenance.is_set()
                or self.worker
                and self.worker.is_alive()
            ):
                return
            self.cancellation = threading.Event()
            self.job = {
                "status": "running",
                "phase": "starting",
                "message": "Updating EPSS and KEV",
                "records": 0,
                "error": None,
                "started_at": stamp(self.store.clock()),
                "completed_at": None,
            }
            self.worker = threading.Thread(
                target=self._run, args=(providers,), name="risk-feed-sync", daemon=True
            )
            self.worker.start()

    def _progress(self, value):
        with self.lock:
            self.job.update(value)

    def _failure(self, provider, error, delay):
        try:
            state = self.store.metadata(provider, {})
            next_check = stamp(self.store.clock() + timedelta(seconds=delay))
            state.update(
                last_error=str(error),
                last_attempt_at=stamp(self.store.clock()),
                next_check_at=next_check,
            )
            if isinstance(error, CatalogDeferred) and error.server_requested:
                state["retry_at"] = next_check
            self.store.put_metadata(provider, state)
        except ValueError, OSError, sqlite3.Error, OverflowError:
            pass

    def _run(self, providers):
        errors = []
        try:
            folder = self.store.folder / "risk-lock"
            folder.mkdir(parents=True, exist_ok=True)
            with sync_lock(folder):
                for provider in providers:
                    if self.cancellation.is_set():
                        raise CatalogCancelled("Risk update cancelled")
                    try:
                        self.store.sync(
                            provider, cancel_event=self.cancellation, progress=self._progress
                        )
                    except CatalogCancelled:
                        raise
                    except Exception as error:
                        message = (
                            str(error)
                            if isinstance(error, (ValueError, CatalogDeferred))
                            else "Risk feed update failed; saved data remains available."
                        )
                        errors.append(provider.upper() + ": " + message)
                        self._failure(
                            provider,
                            error
                            if isinstance(error, (ValueError, CatalogDeferred))
                            else ValueError(message),
                            error.retry_after if isinstance(error, CatalogDeferred) else 3600,
                        )
            self._progress(
                {
                    "status": "error" if errors else "complete",
                    "message": "; ".join(errors) if errors else "EPSS and KEV are up to date",
                    "error": "; ".join(errors) or None,
                }
            )
        except CatalogCancelled:
            self._progress(
                {
                    "status": "cancelled",
                    "message": "Risk update paused; saved data remains available",
                }
            )
            for provider in providers:
                self._failure(provider, ValueError("Update paused"), 86400)
        except Exception as error:
            self._progress(
                {
                    "status": "error",
                    "message": "Risk update is unavailable",
                    "error": type(error).__name__,
                }
            )
            for provider in providers:
                self._failure(provider, ValueError("Risk update is unavailable"), 3600)
        finally:
            self._progress({"completed_at": stamp(self.store.clock())})

    def cancel(self):
        self.cancellation.set()
        return self.status()

    def close(self):
        self.stopped.set()
        self.cancellation.set()
        for thread in (self.scheduler, self.worker):
            if thread:
                thread.join(timeout=1)
