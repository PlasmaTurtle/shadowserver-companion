"""Shared offline boundary and explicit startup state for synthetic browser fixtures."""

import json
from pathlib import Path
from urllib.parse import urlsplit

import requests


def configure_browser_fixture():
    """Use controlled providers; missing fixtures must not contact public services."""
    from tests.content_scan_helpers import NativeProvider
    from modules.library.components.cve_catalog import feed_http
    from modules.library.components.intelligence import acquisition
    from modules.workspace.components.aegis import antimalware

    def blocked(*args, **kwargs):
        raise requests.RequestException("External networking disabled in browser fixtures")

    requests.get = blocked
    acquisition._response_get = blocked
    feed_http._stream_response = blocked
    if antimalware._is_windows():
        antimalware._dll = NativeProvider()


def prepare_browser_fixture(app, workspace: Path, base: str, *, established=True):
    """Publish a protected test launcher; feature checks start after release review.

    First-run setup acceptance passes established=False and exercises its real
    setup and release dialogs. No production startup or UI action is replaced.
    """
    from modules.workspace.components.local_session import write_instance

    address = urlsplit(base)
    if address.scheme != "http" or address.hostname != "127.0.0.1" or not address.port:
        raise ValueError("Browser fixtures must use an explicit loopback HTTP port")
    if established:
        if app.state.setup.status()["required"]:
            raise ValueError("Feature browser fixture needs a complete synthetic analyst profile")
        store = app.state.store
        profile = store.settings()
        if not profile.get("appearance"):
            profile["appearance"] = "dark"
            with store.transaction() as db:
                db.execute(
                    "UPDATE settings SET value=? WHERE key='profile'", (json.dumps(profile),)
                )
        updates = app.state.software_updates
        updates.mark_seen(updates.whats_new()["version"])
    write_instance(workspace, address.port, False, app.state.sessions)
