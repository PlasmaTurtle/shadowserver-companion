"""Durable, single-flight report operations with explicit publication boundaries.

Rendering runs in a killable child process in the installed application. Case
mutation stays in the parent and is never automatically retried. Cancellation
is accepted only before the atomic publication boundary.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import shutil
import threading
from time import monotonic
from uuid import uuid4

from fastapi import HTTPException

_deadline = ContextVar("report_deadline", default=None)
_current = ContextVar("report_operation", default=None)
log = logging.getLogger(__name__)
ACTIVE = {"running", "cancelling", "committing"}
TERMINAL = {"completed", "failed", "cancelled", "timed_out", "interrupted"}
MAX_HISTORY = 200


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class ReportCancelled(ValueError):
    pass


class ReportTimedOut(ValueError):
    pass


def current_operation():
    return _current.get()


def check_deadline():
    current = _current.get()
    if current is not None:
        manager, identifier = current
        with manager._lock:
            record = manager._records[identifier]
            # Once publication begins we finish the existing transaction rather
            # than claiming cancellation after it has already committed.
            if record["state"] == "committing":
                return
            cancelled = identifier in manager._cancelled
        if cancelled:
            raise ReportCancelled(
                "Report preparation was cancelled before publication. Existing saved case data remains available."
            )
    deadline = _deadline.get()
    if deadline is not None and monotonic() >= deadline:
        raise ReportTimedOut(
            "Report preparation exceeded its time limit and stopped before publication. "
            "Review the case and retry when ready."
        )


def phase(value):
    check_deadline()
    current = _current.get()
    if current is not None:
        current[0].set_phase(current[1], value)


@contextmanager
def publication():
    """Refuse new cancellation only after the final pre-commit checkpoint."""
    check_deadline()
    current = _current.get()
    if current is not None:
        manager, identifier = current
        with manager._lock:
            # Serialize cancellation admission and the irreversible boundary.
            check_deadline()
            if identifier in manager._cancelled:
                raise ReportCancelled("Report preparation was cancelled before publication.")
            manager._records[identifier].update(
                state="committing", phase="Saving the reviewed revision", cancellable=False
            )
            manager._save()
    yield


class ReportOperations:
    def __init__(self, root=None, *, process_rendering=True):
        self._lock = threading.RLock()
        self._active = {}
        self._records = {}
        self._cancelled = set()
        self._processes = {}
        self._closed = False
        self.process_rendering = process_rendering
        self.folder = Path(root) / "operations" if root is not None else None
        self.history_warning = ""
        if self.folder is not None:
            if self.folder.is_symlink() or self.folder.is_junction():
                raise ValueError("Report operation folder cannot be a link")
            self.folder.mkdir(parents=True, exist_ok=True)
            self.path = self.folder / "reports.json"
            if self.path.is_symlink() or self.path.is_junction():
                raise ValueError("Report operation history cannot be a link")
            self._load()
            # The application holds the existing workspace process lock. These
            # are pure-render staging directories, never certified packages.
            for child in self.folder.glob(".render-*"):
                if child.is_dir() and not child.is_symlink() and not child.is_junction():
                    shutil.rmtree(child, ignore_errors=True)

    def _load(self):
        if not self.path.exists():
            return
        try:
            if self.path.stat().st_size > 2 * 1024 * 1024:
                raise ValueError("history exceeds its size limit")
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if payload.get("format") != 1 or not isinstance(payload.get("operations"), list):
                raise ValueError("invalid history format")
            records = payload["operations"]
            if len(records) > MAX_HISTORY:
                raise ValueError("too many operation records")
            for item in records:
                if (
                    not isinstance(item, dict)
                    or item.get("state") not in ACTIVE | TERMINAL
                    or not isinstance(item.get("id"), str)
                    or not isinstance(item.get("case_id"), str)
                ):
                    raise ValueError("invalid operation record")
                if not isinstance(item.get("operation"), str) or not isinstance(
                    item.get("started_at"), str
                ):
                    raise ValueError("invalid operation details")
                started = datetime.fromisoformat(item["started_at"])
                if started.tzinfo is None or len(item["id"]) > 128 or len(item["case_id"]) > 256:
                    raise ValueError("invalid operation identity or time")
                item["cancellable"] = False
                if item["state"] in ACTIVE:
                    item.update(
                        state="interrupted",
                        phase="Application stopped",
                        cancellable=False,
                        finished_at=timestamp(),
                        error="The application stopped before this action returned. Review the saved case and report status before retrying; completion is not assumed.",
                    )
                self._records[item["id"]] = item
            self._save()
        except OSError, ValueError, TypeError, AttributeError:
            self._records = {}
            self.history_warning = "Previous report-operation history could not be read. Case records were not changed."
            log.exception("Cannot load report operation history")
            # Keep the unreadable bytes for diagnostics, never silently replace.
            if self.path.exists():
                self.path.replace(
                    self.path.with_name("reports-unreadable-" + uuid4().hex + ".json")
                )

    def _save(self):
        if self.folder is None:
            return
        records = list(self._records.values())[-MAX_HISTORY:]
        keep = {record["id"] for record in records}
        self._records = {key: value for key, value in self._records.items() if key in keep}
        temporary = self.path.with_name("reports-" + uuid4().hex + ".tmp")
        try:
            with temporary.open("x", encoding="utf-8") as stream:
                json.dump({"format": 1, "operations": records}, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def busy(self):
        with self._lock:
            return bool(self._active)

    def list(self, case_id=None, limit=20):
        with self._lock:
            rows = [
                deepcopy(row)
                for row in reversed(list(self._records.values()))
                if case_id is None or row["case_id"] == case_id
            ][: max(1, min(int(limit), MAX_HISTORY))]
        for row in rows:
            if row["state"] in ACTIVE:
                row["elapsed_seconds"] = max(
                    0,
                    round(
                        (
                            datetime.now(timezone.utc) - datetime.fromisoformat(row["started_at"])
                        ).total_seconds(),
                        1,
                    ),
                )
        return rows

    def get(self, identifier):
        with self._lock:
            record = self._records.get(identifier)
            if record is None:
                raise HTTPException(404, "Report operation not found")
            return deepcopy(record)

    def set_phase(self, identifier, value):
        with self._lock:
            self._records[identifier]["phase"] = str(value)[:120]
            self._save()

    def cancel(self, identifier):
        with self._lock:
            record = self._records.get(identifier)
            if record is None:
                raise HTTPException(404, "Report operation not found")
            if record["state"] == "committing":
                raise HTTPException(
                    409,
                    "The reviewed revision is already being saved. Check its final status; it cannot be cancelled now.",
                )
            if record["state"] not in ACTIVE:
                return deepcopy(record)
            self._cancelled.add(identifier)
            record.update(
                state="cancelling", phase="Stopping report preparation", cancellable=False
            )
            self._save()
            return deepcopy(record)

    def close(self):
        with self._lock:
            self._closed = True
            for identifier in self._active.values():
                if self._records[identifier]["state"] != "committing":
                    self._cancelled.add(identifier)
            processes = list(self._processes.values())
        for process in processes:
            if process.poll() is None:
                process.terminate()

    @contextmanager
    def run(self, case_id, operation, *, timeout=110):
        started = monotonic()
        identifier = uuid4().hex
        with self._lock:
            if self._closed:
                raise HTTPException(
                    503, "The application is stopping. Reopen it before preparing a report."
                )
            if self._active:
                raise HTTPException(
                    409,
                    "Report work is already running. Wait for it to finish or stop it before starting another report action.",
                )
            self._records[identifier] = {
                "id": identifier,
                "case_id": str(case_id),
                "operation": str(operation),
                "state": "running",
                "phase": "Checking saved content and evidence",
                "started_at": timestamp(),
                "finished_at": None,
                "elapsed_seconds": 0,
                "cancellable": True,
                "error": "",
            }
            try:
                self._save()  # Do not begin without a durable admission record.
            except OSError:
                self._records.pop(identifier, None)
                raise
            self._active[case_id] = identifier
        token = _deadline.set(started + timeout if timeout is not None else None)
        operation_token = _current.set((self, identifier))
        state, error = "completed", ""
        try:
            yield identifier
            check_deadline()
        except ReportCancelled as problem:
            state, error = "cancelled", str(problem)
            raise
        except ReportTimedOut as problem:
            state, error = "timed_out", str(problem)
            raise
        except BaseException as problem:
            state = (
                "interrupted" if isinstance(problem, (KeyboardInterrupt, SystemExit)) else "failed"
            )
            error = str(getattr(problem, "detail", problem))[:2000]
            raise
        finally:
            _current.reset(operation_token)
            _deadline.reset(token)
            with self._lock:
                self._active.pop(case_id, None)
                self._cancelled.discard(identifier)
                self._processes.pop(identifier, None)
                self._records[identifier].update(
                    state=state,
                    error=error,
                    finished_at=timestamp(),
                    elapsed_seconds=round(monotonic() - started, 3),
                    cancellable=False,
                    phase="Completed" if state == "completed" else "Needs attention",
                )
                try:
                    self._save()
                except OSError:
                    # A completed database publication must not be disguised as
                    # a failed request because the status journal could not flush.
                    self.history_warning = "Report status history could not be saved. Check the case for the authoritative outcome."
                    log.exception("Cannot finish report operation journal")
            log.info("Report %s %s after %.3fs", operation, state, monotonic() - started)


def register_operations(app):
    if not hasattr(app.state, "report_operations"):
        app.state.report_operations = ReportOperations(
            app.state.store.root,
            process_rendering=getattr(app.state, "report_processes", True),
        )
    return app.state.report_operations
