"""Versioned first-run configuration. Secrets remain in credential services."""

from __future__ import annotations

from copy import deepcopy
import json

from modules.settings.components.api_models import ProfileValues, merge_settings
from modules.settings.components.profile_catalog import (
    AGENCIES,
    REGIONS,
    TIMEZONES,
    agency_for_name,
)
from modules.workspace.components.primitives import dump, now

KEY = "workspace_setup"
SCHEMA_VERSION = 1
STEPS = ("connections", "profile", "automation")
PROFILE_FIELDS = {
    "analyst_name",
    "analyst_title",
    "agency",
    "department",
    "office",
    "email",
    "regions",
    "display_timezone",
    "targeted_reason",
}


def profile_missing(values):
    missing = [
        key
        for key in ("analyst_name", "agency", "office")
        if not str(values.get(key) or "").strip()
    ]
    if not values.get("regions"):
        missing.append("regions")
    return missing


class SetupService:
    def __init__(self, store, acquisition=None, schedule=None):
        self.store, self.acquisition, self.schedule = store, acquisition, schedule

    def _read(self, db=None):
        row = (
            db.execute("SELECT value FROM settings WHERE key=?", (KEY,)).fetchone()
            if db is not None
            else self.store.one("SELECT value FROM settings WHERE key=?", (KEY,))
        )
        if not row:
            return {"version": SCHEMA_VERSION, "completed": False, "steps": {}}
        try:
            value = json.loads(row["value"])
            if not isinstance(value, dict) or not isinstance(value.get("steps", {}), dict):
                raise ValueError
            if any(
                not isinstance(value.get(flag, False), bool)
                for flag in ("completed", "needs_review")
            ):
                raise ValueError
            steps = value.get("steps", {})
            for name, step in steps.items():
                modes = ("configured",) if name == "profile" else ("configured", "manual")
                if name not in STEPS or not isinstance(step, dict) or step.get("mode") not in modes:
                    raise ValueError
            if value.get("completed") and not all(name in steps for name in STEPS):
                raise ValueError
            return {"version": SCHEMA_VERSION, "completed": False, "steps": {}, **value}
        except (ValueError, TypeError):
            return {
                "version": SCHEMA_VERSION,
                "completed": False,
                "steps": {},
                "needs_review": True,
            }

    def _write(self, db, value):
        db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (KEY, dump(value)))

    def status(self):
        record, profile = self._read(), self.store.settings()
        missing = profile_missing(profile)
        established = (
            not missing and not record.get("started_at") and not record.get("needs_review")
        )
        required = bool(
            missing
            or record.get("needs_review")
            or (record.get("started_at") and not record.get("completed"))
        )
        steps = record.get("steps", {})
        step = next((name for name in STEPS if name not in steps), "automation")
        if missing and "connections" in steps:
            step = "profile"
        shadow = self.acquisition.status() if self.acquisition else {}
        return {
            "version": SCHEMA_VERSION,
            "required": required,
            "completed": bool(record.get("completed")),
            "established_profile": established,
            "step": step,
            "steps": deepcopy(steps),
            "profile_missing": missing,
            "profile": {
                key: deepcopy(profile.get(key))
                for key in PROFILE_FIELDS | {"outreach_mode", "targeted_authority"}
            },
            "agencies": deepcopy(AGENCIES),
            "regions": list(REGIONS),
            "timezones": list(TIMEZONES),
            "connections": {
                key: shadow.get(key)
                for key in ("configured", "connected", "storage", "can_remember")
            },
            "schedule": self.schedule.status() if self.schedule else None,
        }

    def progress(self, step, mode):
        if step not in {"connections", "automation"} or mode not in {"configured", "manual"}:
            raise ValueError("Choose a valid setup step and mode")
        if step == "automation" and mode == "configured":
            status = self.schedule.status() if self.schedule else {}
            if status.get("scope_error"):
                raise ValueError(status["scope_error"])
            if not status.get("config", {}).get("enabled"):
                raise ValueError("Save an enabled schedule before completing automatic setup")
        if (
            step == "automation"
            and mode == "manual"
            and self.schedule
            and self.schedule.status().get("config", {}).get("enabled")
        ):
            raise ValueError("Turn off automatic checks before completing manual setup")
        with self.store.transaction() as db:
            value = self._read(db)
            value.setdefault("started_at", now())
            value["steps"][step] = {"mode": mode, "reviewed_at": now()}
            self._write(db, value)
        return self.status()

    def save_profile(self, values):
        if set(values) - PROFILE_FIELDS:
            raise ValueError("Unknown setup profile field")
        with self.store.transaction() as db:
            previous = self.store.settings(db)
            submitted = ProfileValues.model_validate(values).model_dump(exclude_unset=True)
            # Setup explicitly reviews the entire identity, not unrelated legacy
            # preferences. The optional reason remains an explicit review signal.
            profile = {key: previous.get(key) for key in PROFILE_FIELDS - {"targeted_reason"}}
            profile.update(submitted)
            if "department" not in submitted:
                profile["department"] = agency_for_name(profile["agency"])["department"]
            changes = ProfileValues.model_validate(profile).model_dump(exclude_unset=True)
            merged = merge_settings(previous, changes)
            if profile_missing(merged):
                raise ValueError(
                    "Enter your name, agency, office or location, and at least one jurisdiction"
                )
            if "agency" in values and previous.get("agency") != merged["agency"]:
                merged["brand_profile"] = (
                    "usss" if agency_for_name(merged["agency"])["id"] == "usss" else "companion"
                )
            db.execute("UPDATE settings SET value=? WHERE key='profile'", (dump(merged),))
            record = self._read(db)
            record.setdefault("started_at", now())
            record["steps"]["profile"] = {"mode": "configured", "reviewed_at": now()}
            self._write(db, record)
        if previous.get("regions") != merged["regions"] and self.acquisition:
            changed = getattr(self.acquisition, "scope_changed", None)
            if changed:
                changed()
        return {"settings": merged, "setup": self.status()}

    def complete(self):
        profile = self.store.settings()
        if profile_missing(profile):
            raise ValueError("Complete your identity and jurisdiction before finishing setup")
        schedule = self.schedule.status() if self.schedule else {}
        if schedule.get("config", {}).get("enabled") and schedule.get("scope_error"):
            raise ValueError(schedule["scope_error"])
        with self.store.transaction() as db:
            value = self._read(db)
            if not all(name in value.get("steps", {}) for name in STEPS):
                raise ValueError("Review all three setup steps before finishing")
            value.update(completed=True, completed_at=now(), needs_review=False)
            self._write(db, value)
        return self.status()
