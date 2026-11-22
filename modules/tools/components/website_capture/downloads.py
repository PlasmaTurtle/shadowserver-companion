"""Project browser download notifications into bounded, content-free evidence."""

from datetime import datetime
import re

from modules.workspace.components.primitives import now

MAX_ATTEMPTS = 16
_OUTCOMES = ("unconfirmed", "canceled", "completed")
_UTC_STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)", re.ASCII)


def download_activity(metadata):
    """Select only local observation times and browser outcomes at storage boundaries."""
    activity = metadata.get("download_activity") if isinstance(metadata, dict) else None
    if not isinstance(activity, dict) or not isinstance(activity.get("attempts"), list):
        return {}
    items = activity["attempts"]
    attempts = []
    for item in items[:MAX_ATTEMPTS]:
        if not isinstance(item, dict) or item.get("outcome") not in _OUTCOMES:
            continue
        stamp = item.get("observed_at")
        if not isinstance(stamp, str) or not _UTC_STAMP.fullmatch(stamp):
            continue
        try:
            datetime.fromisoformat(stamp)
        except ValueError:
            continue
        attempts.append({"observed_at": stamp, "outcome": item["outcome"]})
    if not attempts:
        return {}
    truncated = len(items) > MAX_ATTEMPTS or activity.get("truncated") is True
    return {"download_activity": {"attempts": attempts, "truncated": truncated}}


class DownloadObservations:
    """One capture context, across targets. Browser IDs are used only in memory."""

    def __init__(self):
        self.attempts = []
        self.truncated = False

    async def attach(self, browser):
        """Use Playwright's public CDP API for terminal download observations.

        A denied Playwright Download exposes an inaccessible-artifact error,
        not the browser's terminal state. This dedicated browser has exactly
        one isolated context; enable its events on our observation session.
        """
        events = await browser.new_browser_cdp_session()
        for method in ("Browser.downloadWillBegin", "Browser.downloadProgress"):
            events.on(method, lambda data, name=method: self.observe(name, data))
        contexts = (await events.send("Target.getBrowserContexts"))["browserContextIds"]
        if len(contexts) != 1:
            raise ValueError("Capture browser could not configure download observations")
        await events.send(
            "Browser.setDownloadBehavior",
            {"behavior": "deny", "eventsEnabled": True, "browserContextId": contexts[0]},
        )

    def _start(self, guid):
        if len(self.attempts) == MAX_ATTEMPTS:
            self.truncated = True
            return
        self.attempts.append({"guid": guid, "observed_at": now(), "outcome": "unconfirmed"})

    def observe(self, method, params):
        guid = params.get("guid")
        if not isinstance(guid, str) or not 0 < len(guid) <= 128:
            return
        item = next((item for item in self.attempts if item["guid"] == guid), None)
        if method == "Browser.downloadWillBegin" and item is None:
            self._start(guid)
        elif method == "Browser.downloadProgress" and item and item["outcome"] == "unconfirmed":
            if params.get("state") in ("canceled", "completed"):
                item["outcome"] = params["state"]

    def snapshot(self):
        return download_activity(
            {"download_activity": {"attempts": self.attempts, "truncated": self.truncated}}
        )
