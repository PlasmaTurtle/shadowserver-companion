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

    def _start(self, frame, guid):
        if len(self.attempts) == MAX_ATTEMPTS:
            self.truncated = True
            return
        self.attempts.append(
            {"frame": frame, "guid": guid, "observed_at": now(), "outcome": "unconfirmed"}
        )

    def navigation_download(self, frame):
        # Page.navigate can report isDownload before or after downloadWillBegin.
        # Each navigation candidate gets a fresh target and main frame.
        if frame and not any(item["frame"] == frame for item in self.attempts):
            self._start(frame, None)

    def observe(self, method, params):
        guid = params.get("guid")
        if not isinstance(guid, str) or not 0 < len(guid) <= 128:
            return
        item = next((item for item in self.attempts if item["guid"] == guid), None)
        if method == "Browser.downloadWillBegin" and item is None:
            frame = params.get("frameId")
            pending = next(
                (item for item in self.attempts if item["frame"] == frame and item["guid"] is None),
                None,
            )
            if pending is None:
                self._start(frame, guid)
            else:
                pending["guid"] = guid
        elif method == "Browser.downloadProgress" and item and item["outcome"] == "unconfirmed":
            if params.get("state") in ("canceled", "completed"):
                item["outcome"] = params["state"]

    def pending(self):
        return any(item["outcome"] == "unconfirmed" for item in self.attempts)

    def snapshot(self):
        return download_activity(
            {"download_activity": {"attempts": self.attempts, "truncated": self.truncated}}
        )
