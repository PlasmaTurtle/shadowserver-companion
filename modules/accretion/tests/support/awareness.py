"""Reusable synthetic awareness fixtures and builders."""

from modules.leads.tests.support.lead_queue import queue_import
from tests.support.workbench import observations


def ingest(client, app, **changes):
    row = {**observations()[2], **changes}
    result, _ = queue_import(client, app, [row], "scan_http_vulnerable.csv")
    assert (
        app.state.store.one("SELECT status FROM imports WHERE id=?", (result["id"],))["status"]
        == "done"
    )
    return result
