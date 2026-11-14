"""Exercise real capture coordination with a synthetic CDP peer and transport."""

import base64
import json
from pathlib import Path
import socket
import threading
import time

import pytest
from test_website_capture_0985 import captured
from workbench.website_capture import browser
from workbench.website_capture.cdp import CDP, MAX_MESSAGE
from workbench.contact_discovery.transport import FetchResponse


@pytest.mark.parametrize("scan_status", ["allowed", "blocked", "unavailable"])
def test_capture_driver_fulfills_public_page_and_cleans_process(monkeypatch, tmp_path, scan_status):
    commands = []
    objects = []

    class Proxy:
        port = 9911

        def close(self):
            objects.append("proxy closed")

    class Guard:
        def __init__(self, process):
            pass

        def close(self):
            objects.append("guard closed")

    class Process:
        def __init__(self, args, **kwargs):
            assert "--proxy-server=http://127.0.0.1:9911" in args
            profile = Path(
                next(a.split("=", 1)[1] for a in args if a.startswith("--user-data-dir="))
            )
            (profile / "DevToolsActivePort").write_text("12345\n/devtools/browser/synthetic\n")
            self.profile = profile
            objects.append(self)

        def poll(self):
            return None

        def wait(self, timeout):
            objects.append("waited")

    class Peer:
        def __init__(self, url, deadline):
            self.results = {}
            self.events = []
            self.session = None
            self.sequence = 0

        def call(self, method, params=None, **kwargs):
            commands.append((method, params))
            if method == "Browser.getVersion":
                return {"product": "Synthetic Edge"}
            if method == "Target.createTarget":
                return {"targetId": "target"}
            if method == "Target.attachToTarget":
                return {"sessionId": "session"}
            if method == "Runtime.evaluate":
                return {
                    "result": {
                        "value": json.dumps(
                            {
                                "url": "https://example.com/",
                                "title": "Example business",
                                "text": "Our business",
                                "password": False,
                            }
                        )
                    }
                }
            if method == "Page.captureScreenshot":
                assert params["captureBeyondViewport"] is False
                assert params["clip"]["height"] == 900
                return {"data": base64.b64encode(captured()[0]).decode()}
            return {}

        def send(self, method, params=None, **kwargs):
            self.sequence += 1
            commands.append((method, params))
            self.results[self.sequence] = {"result": {}}
            if method == "Page.navigate":
                self.results[self.sequence] = {"result": {"frameId": "main"}}
                self.events.append(
                    {
                        "method": "Fetch.requestPaused",
                        "sessionId": "session",
                        "params": {
                            "requestId": "doc",
                            "frameId": "main",
                            "resourceType": "Document",
                            "request": {"url": params["url"], "method": "GET"},
                        },
                    }
                )
            if method == "Fetch.fulfillRequest":
                self.events.extend(
                    [
                        {
                            "method": "Page.frameNavigated",
                            "sessionId": "session",
                            "params": {"frame": {"id": "main", "url": "https://example.com/"}},
                        },
                        {
                            "method": "Page.lifecycleEvent",
                            "sessionId": "session",
                            "params": {"frameId": "main", "name": "DOMContentLoaded"},
                        },
                    ]
                )
            return self.sequence

        def receive(self):
            time.sleep(0.005)
            raise socket.timeout()

        def close(self):
            objects.append("peer closed")

    monkeypatch.setattr(browser, "DenyProxy", Proxy)
    monkeypatch.setattr(browser, "BrowserProcessGuard", Guard)
    monkeypatch.setattr(browser.subprocess, "Popen", Process)
    monkeypatch.setattr(browser, "CDP", Peer)
    fetched = []

    def response(url, **kwargs):
        fetched.append(url)
        return FetchResponse(200, {"content-type": "text/html"}, b"<html>Our business</html>")

    monkeypatch.setattr(browser, "fetch", response)
    cancel = threading.Event()
    scans = []

    def scan_buffer(body, **kwargs):
        scans.append(body)
        receipt = {
            "status": scan_status,
            "provider": "windows_amsi",
            "representation": "bytes",
            "verdict": "synthetic",
        }
        if scan_status != "allowed":
            raise browser.aegis.ContentScanError(
                "content_scan_" + scan_status, "Synthetic content scan stopped capture", receipt
            )
        return receipt

    monkeypatch.setattr(browser.aegis, "scan_buffer", scan_buffer)
    if scan_status != "allowed":
        with pytest.raises(browser.aegis.ContentScanError):
            browser.capture_website(
                "https://example.com/", cancel_event=cancel, executable="synthetic-browser"
            )
        assert scans == [b"<html>Our business</html>"]
        assert not any(
            name in {"Fetch.fulfillRequest", "Page.captureScreenshot"} for name, _ in commands
        )
        assert any(name == "Fetch.failRequest" for name, _ in commands)
        assert not objects[0].profile.exists()
        assert {"proxy closed", "guard closed", "peer closed", "waited"} <= {
            x for x in objects if isinstance(x, str)
        }
        return
    png, metadata = browser.capture_website(
        "https://example.com/", cancel_event=cancel, executable="synthetic-browser"
    )
    assert png == captured()[0]
    assert metadata["capture_status"] == "captured"
    assert metadata["content_scans"] == {"allowed": 1}
    assert scans == [b"<html>Our business</html>"]
    assert metadata["browser"] == "Synthetic Edge"
    assert fetched == ["https://example.com/"]
    assert not cancel.is_set(), "Internal network shutdown must not mark user cancellation"
    assert ("Browser.setDownloadBehavior", {"behavior": "deny"}) in commands
    assert not any(name == "Fetch.continueRequest" for name, _ in commands)
    assert not objects[0].profile.exists()
    assert {"proxy closed", "guard closed", "peer closed", "waited"} <= set(
        x for x in objects if isinstance(x, str)
    )


def peer_for(data):
    peer = object.__new__(CDP)
    peer.buffer = bytearray(data)
    peer.deadline = time.monotonic() + 1
    peer.cancel_event = None
    peer.events = []
    peer.results = {}

    class FakeSocket:
        def settimeout(self, t):
            pass

        def recv(self, n):
            raise AssertionError("Unexpected read beyond synthetic frame")

    peer.socket = FakeSocket()
    return peer


def test_cdp_fragmentation_and_payload_limit():
    message = b'{"id":1,"result":{"ok":true}}'
    peer = peer_for(bytes([1, 12]) + message[:12] + bytes([128, len(message) - 12]) + message[12:])
    peer.receive()
    assert peer.results[1]["result"]["ok"]
    import struct

    oversized = peer_for(bytes([129, 127]) + struct.pack("!Q", MAX_MESSAGE + 1))
    with pytest.raises(ValueError, match="exceeds limit"):
        oversized.receive()


def test_cdp_cancellation_interrupts_an_incomplete_message():
    peer = peer_for(b"")
    peer.cancel_event = threading.Event()
    peer.cancel_event.set()
    with pytest.raises(ValueError, match="cancelled"):
        peer._read(1)


def test_pending_native_scan_cannot_be_treated_as_partial_capture():
    from concurrent.futures import Future
    from workbench.contact_discovery.transport import _CombinedCancel

    future = Future()
    assert future.set_running_or_notify_cancel()
    cancelled = _CombinedCancel()
    commands = []

    class Peer:
        def send(self, method, params):
            commands.append((method, params))

    with pytest.raises(browser.aegis.ContentScanError) as error:
        browser._finish_resources({future: ("script", False)}, cancelled, Peer())
    assert error.value.code == "content_scan_unavailable"
    assert cancelled.is_set()
    assert commands == [("Fetch.failRequest", {"requestId": "script", "errorReason": "Aborted"})]
    future.set_result(None)
