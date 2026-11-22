"""Download evidence from Chromium events, including failed and interrupted captures."""

from contextlib import closing
import json
import socket
import struct
import time
from unittest.mock import Mock

import pytest

from modules.tools.components.website_capture import WebsiteLoadError, browser, download_activity
from modules.tools.components.website_capture.cdp import CDP
from modules.tools.components.website_capture.downloads import DownloadObservations, MAX_ATTEMPTS


def send_message(peer, message):
    payload = json.dumps(message).encode()
    length = len(payload)
    header = bytes([length]) if length < 126 else b"\x7e" + struct.pack("!H", length)
    peer.sendall(b"\x81" + header + payload)


@pytest.mark.parametrize("begin_first", [False, True])
def test_browser_events_correlate_with_navigation_without_leaking_download_data(begin_first):
    local, peer = socket.socketpair()
    with closing(local), closing(peer):
        # Drive real DevTools frames through the adapter after its loopback handshake.
        client = CDP.__new__(CDP)
        client.socket = local
        client.buffer = bytearray()
        client.cancel_event = client.session = None
        client.sequence, client.results, client.events = 0, {}, []
        client.deadline = time.monotonic() + 3
        client.downloads = DownloadObservations()
        begin = {
            "method": "Browser.downloadWillBegin",
            "params": {
                "guid": "g1",
                "frameId": "f1",
                "url": "data:,private",
                "suggestedFilename": "private.txt",
            },
        }
        reply = {"id": 1, "result": {"frameId": "f1", "isDownload": True}}
        for message in [begin, reply] if begin_first else [reply, begin]:
            send_message(peer, message)
        send_message(peer, {"method": "Page.loadEventFired", "sessionId": "target", "params": {}})
        send_message(
            peer,
            {
                "method": "Browser.downloadProgress",
                "params": {
                    "guid": "g1",
                    "state": "canceled",
                    "filePath": "private",
                    "receivedBytes": 0,
                },
            },
        )
        client.call("Page.navigate", {"url": "https://localhost/"})
        client.finish_downloads()
        assert [e["method"] for e in client.events] == ["Page.loadEventFired"]
        activity = client.downloads.snapshot()["download_activity"]
        assert not activity["truncated"]
        assert [row["outcome"] for row in activity["attempts"]] == ["canceled"]
        assert set(activity["attempts"][0]) == {"outcome", "observed_at"}
        assert "private" not in json.dumps(activity)


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


@pytest.mark.parametrize("result", ["screenshot", "load_failure", "connection_lost"])
def test_capture_returns_observation_with_or_without_a_screenshot(monkeypatch, tmp_path, result):
    profile = tmp_path / "capture"
    profile.mkdir()
    (profile / "DevToolsActivePort").write_text("9876\n/devtools/browser/fixture\n")
    monkeypatch.setattr(browser.tempfile, "mkdtemp", lambda **kwargs: str(profile))
    monkeypatch.setattr(browser.subprocess, "Popen", Mock())
    monkeypatch.setattr(browser, "BrowserProcessGuard", Mock())
    client = Mock()

    def connect(url, deadline, *, downloads):
        client.call.side_effect = lambda method, *a, **k: (
            {"data": "UE5H"} if method == "Page.captureScreenshot" else {}
        )
        client.downloads = downloads
        return client

    def load(url, *, metadata, **kwargs):
        client.downloads.observe("Browser.downloadWillBegin", {"frameId": "sub", "guid": "fixture"})
        if result == "connection_lost":
            raise ConnectionResetError("browser closed")
        client.downloads.observe(
            "Browser.downloadProgress", {"guid": "fixture", "state": "canceled"}
        )
        if result == "load_failure":
            raise WebsiteLoadError("No rendered page", metadata)

    monkeypatch.setattr(browser, "CDP", connect)
    monkeypatch.setattr(browser, "load_page", load)
    if result == "screenshot":
        png, metadata = browser.capture_website("https://localhost/", executable="fixture")
        assert png == b"PNG"
    else:
        expected = WebsiteLoadError if result == "load_failure" else browser.CaptureOperationError
        with pytest.raises(expected) as failure:
            browser.capture_website("https://localhost/", executable="fixture")
        metadata = failure.value.metadata
    outcomes = [row["outcome"] for row in metadata["download_activity"]["attempts"]]
    assert outcomes == ["unconfirmed" if result == "connection_lost" else "canceled"]
    assert not profile.exists()
