"""Settings profile update adapter and its acquisition-scope notification."""

from __future__ import annotations

from modules.workspace.components.primitives import dump
from modules.accretion.components.report_profiles import supported_profiles
from ..api_models import SettingsUpdate, merge_settings


def register(app, *, store):
    @app.put("/api/settings")
    def settings(body: SettingsUpdate):
        with store.transaction() as db:
            previous = store.settings(db)
            changes = body.model_dump(exclude_unset=True)
            if "report_type" in changes and changes["report_type"] not in {
                "auto",
                *supported_profiles(),
            }:
                raise ValueError("Select a supported report profile or automatic detection")
            values = merge_settings(previous, changes)
            db.execute("UPDATE settings SET value=? WHERE key=?", (dump(values), "profile"))
        if previous.get("regions") != values.get("regions"):
            acquisition = getattr(app.state, "api_acquisition", None)
            if acquisition is not None:
                acquisition.scope_changed()
        return values
