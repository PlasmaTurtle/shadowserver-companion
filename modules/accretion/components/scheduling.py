"""Durable workspace schedules; completion includes Accretion, not just download."""

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import json
import logging
import threading

from modules.workspace.components.primitives import dump, uid
from .api_jurisdiction import require_subscription
from .shadowserver_reports.errors import ShadowserverError

KEY = "scheduled_acquisition"
DEFAULTS = {
    "enabled": False,
    "hour": 6,
    "minute": 0,
    "interval_hours": 4,
    "lookback_days": 7,
    "shadowserver": True,
    "reference": True,
    "subscription": "",
    "report_types": [],
}


def stamp(value):
    return value.astimezone(timezone.utc).isoformat()


def checked(config):
    if not isinstance(config, dict) or set(config) - set(DEFAULTS):
        raise ValueError("Invalid schedule settings")
    result = {**DEFAULTS, **config}
    for name in ("enabled", "shadowserver", "reference"):
        if type(result[name]) is not bool:
            raise ValueError("Schedule switches must be enabled or disabled")
    for name, low, high in (
        ("hour", 0, 23),
        ("minute", 0, 59),
        ("interval_hours", 1, 24),
        ("lookback_days", 1, 30),
    ):
        if type(result[name]) is not int or not low <= result[name] <= high:
            raise ValueError("Schedule time or lookback is outside its supported range")
    if (
        not isinstance(result["subscription"], str)
        or len(result["subscription"]) > 1024
        or any(ord(c) < 32 for c in result["subscription"])
    ):
        raise ValueError("Invalid schedule subscription")
    types = result["report_types"]
    if (
        not isinstance(types, list)
        or len(types) > 64
        or any(
            not isinstance(t, str) or not t.strip() or len(t) > 256 or any(ord(c) < 32 for c in t)
            for t in types
        )
    ):
        raise ValueError("Select up to 64 report types")
    result["report_types"] = list(dict.fromkeys(types))
    if result["enabled"]:
        if not result["shadowserver"] and not result["reference"]:
            raise ValueError("Select reports or reference data for the schedule")
        if result["shadowserver"] and (not result["subscription"] or not result["report_types"]):
            raise ValueError("Select a subscription and report types for scheduled imports")
    return result


def next_due(config, current):
    """Wall-clock anchor; a missed run is coalesced, never replayed in a burst."""
    anchor = current.replace(hour=config["hour"], minute=config["minute"], second=0, microsecond=0)
    step = timedelta(hours=config["interval_hours"])
    if anchor > current:
        return anchor
    return anchor + step * (int((current - anchor) / step) + 1)


def window(config, state, today):
    lookback = today - timedelta(days=config["lookback_days"] - 1)
    cursor = date.fromisoformat(state["cursor"]) if state.get("cursor") else None
    start = min(lookback, cursor + timedelta(days=1)) if cursor else lookback
    return start, min(today, start + timedelta(days=30))


class AcquisitionSchedule:
    def __init__(self, store, acquisition, catalog, *, clock=None):
        self.store, self.acquisition, self.catalog = store, acquisition, catalog
        self.clock = clock or (lambda: datetime.now().astimezone())
        self.stop_event = threading.Event()
        self.lock = threading.RLock()
        self.thread = None
        self.active = False
        # A process killed during download has no live request to resume. Already
        # enqueued imports remain recorded and are checked before any new run.
        state = self._read()
        run = state.get("run") or {}
        if run.get("status") == "retrieving":
            run.update(
                status="importing",
                interrupted=True,
                message="Resuming interrupted scheduled intake",
            )
            self._write(state)

    def _read(self):
        row = self.store.one("SELECT value FROM settings WHERE key=?", (KEY,))
        if not row:
            return {"config": dict(DEFAULTS), "history": []}
        try:
            state = json.loads(row["value"])
            if not isinstance(state, dict):
                raise ValueError
            state["config"] = checked(state.get("config", {}))
            for key in (
                "next_run_at",
                "last_success_at",
                "reference_success_at",
                "reports_success_at",
            ):
                if state.get(key) and datetime.fromisoformat(state[key]).tzinfo is None:
                    raise ValueError
            if state.get("cursor"):
                date.fromisoformat(state["cursor"])
            history = state.get("history", [])
            if not isinstance(history, list) or len(history) > 20:
                raise ValueError
            for run in history + ([state["run"]] if state.get("run") else []):
                if not isinstance(run, dict) or run.get("status") not in {
                    "retrieving",
                    "importing",
                    "complete",
                    "partial",
                    "failed",
                }:
                    raise ValueError
                imports = run.get("imports", [])
                if (
                    not isinstance(imports, list)
                    or len(imports) > 1000
                    or any(not isinstance(i, str) or len(i) > 128 for i in imports)
                ):
                    raise ValueError
                if run["status"] in {"retrieving", "importing"}:
                    date.fromisoformat(run["start"])
                    date.fromisoformat(run["end"])
            return state
        except (ValueError, TypeError, KeyError):
            # An optional restored/corrupt schedule must not prevent agents from
            # opening existing records. Do not overwrite the original until saved.
            return {
                "config": dict(DEFAULTS),
                "history": [],
                "configuration_error": "Schedule settings need to be saved again",
            }

    def _write(self, state):
        with self.store.transaction() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (KEY, dump(state)))

    def _validate_scope(self, config):
        if config.get("shadowserver") and config.get("subscription"):
            require_subscription(config["subscription"], self.store.settings()["regions"])
            validate = getattr(self.acquisition, "validate_schedule", None)
            if validate:
                validate(config)

    def _scope_error(self, config):
        try:
            self._validate_scope(config)
        except (ValueError, ShadowserverError) as error:
            return str(error)
        return None

    def status(self):
        state = self._read()
        return {
            **deepcopy(state),
            "scope_error": self._scope_error(state.get("config", DEFAULTS)),
            "running": self.active,
            "timezone": str(self.clock().tzinfo),
            "background": state.get("background", {"installed": False}),
        }

    def configure(self, config):
        values = checked(config)
        if values["enabled"]:
            self._validate_scope(values)
        with self.lock:
            if self.active or (self._read().get("run") or {}).get("status") in {
                "retrieving",
                "importing",
            }:
                raise ValueError("Wait for scheduled intake to finish before changing its scope")
            state = self._read()
            old = state.get("config", DEFAULTS)
            if (old.get("subscription"), old.get("report_types")) != (
                values["subscription"],
                values["report_types"],
            ):
                state.pop("cursor", None)
            state["config"] = values
            current = self.clock()
            first = current.replace(
                hour=values["hour"], minute=values["minute"], second=0, microsecond=0
            )
            state["next_run_at"] = stamp(first if first > current else current)
            self._write(state)
        return self.status()

    def start(self):
        if self.thread is not None:
            return
        self.thread = threading.Thread(target=self._loop, name="scheduled-acquisition", daemon=True)
        self.thread.start()

    def busy(self):
        return self.active or (self._read().get("run") or {}).get("status") in {
            "retrieving",
            "importing",
        }

    def _loop(self):
        while not self.stop_event.is_set():
            try:
                self.tick()
            except Exception:
                logging.getLogger(__name__).warning("Scheduled acquisition could not advance")
            self.stop_event.wait(15)

    def request_run(self):
        with self.lock:
            if self.busy():
                raise ValueError("Scheduled intake is already running")
            state = self._read()
            if not state.get("config", DEFAULTS)["enabled"]:
                raise ValueError("Enable and save a schedule first")
            self._validate_scope(state["config"])
            state["next_run_at"] = stamp(self.clock())
            self._write(state)
        return self.status()

    def tick(self):
        if (
            self.stop_event.is_set()
            or getattr(self.store, "maintenance", threading.Event()).is_set()
        ):
            return
        with self.lock:
            if self.active:
                return
            state = self._read()
            if (state.get("run") or {}).get("status") == "importing":
                self._finish_intake(state)
                return
            config = state.get("config", DEFAULTS)
            if not config["enabled"] or self.acquisition.busy() or self._scope_error(config):
                return
            due = state.get("next_run_at")
            if due and datetime.fromisoformat(due) > self.clock():
                return
            self.active = True
        try:
            self._run(state, config)
        finally:
            self.active = False

    def _references(self, run):
        status = self.catalog.status()
        if not status.get("running"):
            self.catalog.sync()
        while self.catalog.status().get("running"):
            if self.stop_event.wait(0.25):
                raise ValueError("Scheduled acquisition was interrupted")
        status = self.catalog.status()
        run["reference"] = {
            "status": status.get("job", {}).get("status"),
            "records": status.get("total", 0),
        }
        if status.get("job", {}).get("status") != "complete":
            raise ValueError("Reference update failed; check the CVE catalog status")
        risk = getattr(self.catalog, "risk", None)
        freshness = [status.get("last_success_at") or stamp(self.clock())]
        if risk:

            def current(value):
                for provider in ("epss", "kev"):
                    item = value.get(provider, {})
                    when = item.get("last_success_at")
                    if not isinstance(when, str):
                        return False
                    try:
                        age = self.clock() - datetime.fromisoformat(when.replace("Z", "+00:00"))
                    except (KeyError, ValueError, TypeError):
                        return False
                    if (
                        not timedelta(0) <= age < timedelta(hours=20)
                        or item.get("stale")
                        or item.get("last_error")
                    ):
                        return False
                return True

            risk_state = risk.status()
            if not risk_state.get("running") and not current(risk_state):
                risk.sync()
            while risk.status().get("running"):
                if self.stop_event.wait(0.25):
                    raise ValueError("Scheduled acquisition was interrupted")
            risk_state = risk.status()
            run["reference"]["risk"] = "complete" if current(risk_state) else "error"
            if run["reference"]["risk"] != "complete":
                raise ValueError("EPSS or KEV update failed; check the Library status")
            freshness.extend(
                risk_state[provider]["last_success_at"] for provider in ("epss", "kev")
            )
        run["reference"]["checked_at"] = min(
            freshness, key=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00"))
        )

    def _run(self, state, config):
        current = self.clock()
        start, end = window(config, state, current.date())
        run = {
            "id": uid(),
            "status": "retrieving",
            "started_at": stamp(current),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "imports": [],
            "message": "Updating scheduled data",
        }
        state["run"] = run
        self._write(state)
        try:
            if config["reference"]:
                last = state.get("reference_success_at")
                if not last or self.clock() - datetime.fromisoformat(last) >= timedelta(hours=20):
                    try:
                        self._references(run)
                        state["reference_success_at"] = run["reference"]["checked_at"]
                    except Exception:
                        if self.stop_event.is_set():
                            raise ValueError("Scheduled acquisition was interrupted") from None
                        run["reference_error"] = "Reference update failed; check Library status"
                    self._write(state)
            if config["shadowserver"]:

                def queued(result):
                    if result["import_id"] not in run["imports"]:
                        run["imports"].append(result["import_id"])
                    self._write(state)

                self.acquisition.scheduled(
                    config, start, end, cancel_event=self.stop_event, queued=queued
                )
            run.update(status="importing", message="Waiting for Accretion to complete")
            self._write(state)
            self._finish_intake(state)
        except Exception as error:
            # Only our bounded local messages are surfaced. Upstream exceptions
            # never expose response bodies, credentials, or download capabilities.
            run.update(
                status="importing",
                interrupted=True,
                message=str(error)[:300]
                if type(error) is ValueError or isinstance(error, ShadowserverError)
                else "Scheduled retrieval failed; completed imports are retained",
                error_code=error.code if isinstance(error, ShadowserverError) else "schedule_error",
            )
            self._write(state)
            self._finish_intake(state)

    def _finish_intake(self, state):
        run = state["run"]
        identities = run.get("imports", [])
        observed = {}
        with self.store.read_snapshot() as db:
            for start in range(0, len(identities), 200):
                chunk = identities[start : start + 200]
                marks = ",".join("?" for _ in chunk)
                observed.update(
                    (row["id"], row["status"])
                    for row in db.execute(
                        f"SELECT id,status FROM imports WHERE id IN ({marks})", chunk
                    )
                )
        statuses = [observed.get(identity, "missing") for identity in identities]
        if any(status in {"queued", "running"} for status in statuses):
            return
        intake_success = not run.get("interrupted") and all(status == "done" for status in statuses)
        success = intake_success and not run.get("reference_error")
        current = self.clock()
        run.update(
            status="complete" if success else "partial" if statuses else "failed",
            completed_at=stamp(current),
            intake_completed=sum(s == "done" for s in statuses),
            intake_failed=sum(s != "done" for s in statuses),
        )
        if intake_success and state["config"].get("shadowserver"):
            state["cursor"] = run["end"]
            state["reports_success_at"] = stamp(current)
        if success:
            state["last_success_at"] = stamp(current)
            run["message"] = (
                "Scheduled intake completed"
                if statuses
                else "Scheduled check completed; no new reports"
            )
        elif run.get("reference_error") and intake_success:
            run["message"] = (
                "Report intake completed; reference update needs attention"
                if state["config"].get("shadowserver")
                else run["reference_error"]
            )
        elif not run.get("interrupted"):
            run["message"] = "Some imports need attention in Accretion"
        state["next_run_at"] = stamp(
            next_due(state["config"], current) if success else current + timedelta(hours=1)
        )
        state["history"] = ([deepcopy(run)] + state.get("history", []))[:20]
        self._write(state)

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)
