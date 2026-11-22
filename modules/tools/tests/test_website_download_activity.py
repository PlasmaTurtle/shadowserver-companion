"""Bounded download evidence projection, independent of the browser transport."""

import json

from modules.tools.components.website_capture import download_activity
from modules.tools.components.website_capture.downloads import DownloadObservations, MAX_ATTEMPTS


def test_bounded_output_distinguishes_unconfirmed_and_completed_and_ignores_duplicate_events():
    seen = DownloadObservations()
    for index in range(MAX_ATTEMPTS + 3):
        params = {"guid": str(index), "frameId": "popup"}
        seen.observe("Browser.downloadWillBegin", params)
        seen.observe("Browser.downloadWillBegin", params)
    seen.observe("Browser.downloadProgress", {"guid": "0", "state": "completed"})
    seen.observe("Browser.downloadProgress", {"guid": "0", "state": "inProgress"})
    seen.observe("Browser.downloadProgress", {"guid": "missing", "state": "canceled"})
    activity = seen.snapshot()["download_activity"]
    assert activity["truncated"] and len(activity["attempts"]) == MAX_ATTEMPTS
    assert [row["outcome"] for row in activity["attempts"]] == ["completed"] + ["unconfirmed"] * (
        MAX_ATTEMPTS - 1
    )


def test_storage_projection_discards_unrecognized_content():
    good = {"observed_at": "2026-11-21T23:00:00Z", "outcome": "canceled"}
    assert download_activity(None) == {}
    assert download_activity(
        {
            "download_activity": {
                "attempts": [
                    {"observed_at": "2026-02-31T00:00:00Z", "outcome": "completed"},
                    {"observed_at": "private URL", "outcome": "canceled"},
                    {**good, "outcome": "arbitrary site text"},
                    {**good, "url": "private"},
                ],
                "filePath": "private",
            }
        }
    ) == {"download_activity": {"attempts": [good], "truncated": False}}
