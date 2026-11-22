"""Settings profile update adapter and its acquisition-scope notification."""

from __future__ import annotations

from modules.workspace.components.primitives import dump
from ..api_models import SettingsUpdate


def register(app, *, store):
    @app.put("/api/settings")
    def settings(body: SettingsUpdate):
        with store.transaction() as db:
            previous = store.settings(db)
            changes = body.model_dump(exclude_unset=True)
            values = {**previous, **changes}
            if "outreach_mode" not in changes and "critical_only" in changes:
                values["outreach_mode"] = "critical" if changes["critical_only"] else "targeted"
            values["critical_only"] = values["outreach_mode"] == "critical"
            if not values["critical_only"] and not values["targeted_reason"].strip():
                raise ValueError("Targeted outreach requires a recorded reason.")
            db.execute("UPDATE settings SET value=? WHERE key=?", (dump(values), "profile"))
        if previous.get("regions") != values.get("regions"):
            acquisition = getattr(app.state, "api_acquisition", None)
            if acquisition is not None:
                acquisition.scope_changed()
        return values
