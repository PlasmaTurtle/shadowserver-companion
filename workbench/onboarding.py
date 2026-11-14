"""Versioned first-run configuration. Secrets remain in credential services."""

from __future__ import annotations

from copy import deepcopy
import json

from .api_models import SettingsUpdate
from .primitives import dump, now

KEY = "workspace_setup"
SCHEMA_VERSION = 1
STEPS = ("connections", "profile", "automation")
# Identity presets only: selecting an agency never grants geography or API access.
AGENCIES = (
    {
        "id": "usss",
        "name": "United States Secret Service",
        "department": "U.S. Department of Homeland Security",
        "short_name": "USSS",
    },
    {
        "id": "fbi",
        "name": "Federal Bureau of Investigation",
        "department": "U.S. Department of Justice",
        "short_name": "FBI",
    },
    {
        "id": "hsi",
        "name": "Homeland Security Investigations",
        "department": "U.S. Department of Homeland Security",
        "short_name": "HSI",
    },
    {
        "id": "atf",
        "name": "Bureau of Alcohol, Tobacco, Firearms and Explosives",
        "department": "U.S. Department of Justice",
        "short_name": "ATF",
    },
    {
        "id": "dea",
        "name": "Drug Enforcement Administration",
        "department": "U.S. Department of Justice",
        "short_name": "DEA",
    },
    {
        "id": "usms",
        "name": "United States Marshals Service",
        "department": "U.S. Department of Justice",
        "short_name": "USMS",
    },
    {
        "id": "uspis",
        "name": "United States Postal Inspection Service",
        "department": "United States Postal Service",
        "short_name": "USPIS",
    },
    {
        "id": "irs-ci",
        "name": "Internal Revenue Service - Criminal Investigation",
        "department": "U.S. Department of the Treasury",
        "short_name": "IRS-CI",
    },
    {
        "id": "dss",
        "name": "Diplomatic Security Service",
        "department": "U.S. Department of State",
        "short_name": "DSS",
    },
    {
        "id": "custom",
        "name": "Other agency or organization",
        "department": "",
        "short_name": "Custom",
    },
)
REGIONS = tuple(
    "Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|District of Columbia|Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|New Mexico|New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|West Virginia|Wisconsin|Wyoming|American Samoa|Guam|Northern Mariana Islands|Puerto Rico|U.S. Virgin Islands".split(
        "|"
    )
)
PROFILE_FIELDS = {
    "analyst_name",
    "analyst_title",
    "agency",
    "department",
    "office",
    "email",
    "regions",
    "display_timezone",
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
            return {"version": SCHEMA_VERSION, "completed": False, "steps": {}, **value}
        except ValueError, TypeError:
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
            "profile": {key: deepcopy(profile.get(key)) for key in PROFILE_FIELDS},
            "agencies": deepcopy(AGENCIES),
            "regions": list(REGIONS),
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
        previous = self.store.settings()
        merged = {**previous, **values}
        checked = SettingsUpdate.model_validate(merged).model_dump()
        if profile_missing(checked):
            raise ValueError(
                "Enter your name, agency, office or location, and at least one jurisdiction"
            )
        # Validation normalizes profile values while preserving unrelated current preferences.
        merged = {**previous, **{key: checked[key] for key in PROFILE_FIELDS}}
        if "agency" in values and previous.get("agency") != merged["agency"]:
            merged["brand_profile"] = (
                "usss" if merged["agency"] == AGENCIES[0]["name"] else "companion"
            )
        with self.store.transaction() as db:
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
