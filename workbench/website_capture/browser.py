"""Capture one public root domain using an isolated installed Edge/Chrome session."""

import base64
from concurrent.futures import ThreadPoolExecutor, CancelledError, TimeoutError as FutureTimeout
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from urllib.parse import urljoin, urlsplit

from .cdp import CDP
from .diagnostics import network_error, navigation_error
from .deny_proxy import DenyProxy
from .process_guard import BrowserProcessGuard
from .transport import web_url, fetch, MAX_RESOURCE
from ..contact_discovery.policy import hostname
from ..contact_discovery.transport import _CombinedCancel
from ..primitives import now
from .. import aegis

VIEWPORT = {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False}
MAX_SECONDS = 35
MAX_REQUESTS = 160
MAX_IN_FLIGHT = 48
MAX_BYTES = 24 * 1024 * 1024

# Common multi-part public suffixes so e.g. support.company.co.uk -> company.co.uk
_MULTI_LABEL_TLDS = {
    "co.uk", "org.uk", "ac.uk", "gov.uk", "com.au", "net.au", "org.au",
    "co.jp", "ne.jp", "or.jp", "com.br", "com.mx", "co.nz", "co.za",
    "com.sg", "com.hk", "com.tw", "co.in", "co.kr", "com.tr", "com.ar",
}


def extract_root_domain(url_or_host: str) -> str:
    """Reduce any URL or subdomain (e.g. support.ninevirtualtech.com) to its root domain."""
    raw = str(url_or_host).strip()
    if "://" in raw:
        host = hostname(urlsplit(raw).hostname or "")
    else:
        host = hostname(raw.split("/", 1)[0])
    labels = host.split(".")
    if len(labels) <= 2:
        return host
    if ".".join(labels[-2:]) in _MULTI_LABEL_TLDS and len(labels) >= 3:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def _same_or_subdomain(found_host: str, root_domain: str) -> bool:
    found = found_host.strip(".").lower()
    target = root_domain.strip(".").lower()
    return found == target or found.endswith("." + target)


def find_browser():
    if os.name == "nt":
        for variable, suffix in [
            ("PROGRAMFILES(X86)", "Microsoft/Edge/Application/msedge.exe"),
            ("PROGRAMFILES", "Microsoft/Edge/Application/msedge.exe"),
            ("LOCALAPPDATA", "Microsoft/Edge/Application/msedge.exe"),
            ("PROGRAMFILES", "Google/Chrome/Application/chrome.exe"),
            ("PROGRAMFILES(X86)", "Google/Chrome/Application/chrome.exe"),
            ("LOCALAPPDATA", "Google/Chrome/Application/chrome.exe"),
        ]:
            folder = os.environ.get(variable)
            if folder and (Path(folder) / suffix).is_file():
                return str(Path(folder) / suffix)
    else:
        for name in ("microsoft-edge", "google-chrome", "chromium", "chromium-browser"):
            if found := shutil.which(name):
                return found
    raise ValueError(
        "Website capture needs Microsoft Edge or Google Chrome installed. Manual attachment is still available."
    )


def browser_arguments(executable, profile, proxy_port=9):
    return [
        executable,
        "--headless=new",
        "--remote-debugging-port=0",
        "--remote-debugging-address=127.0.0.1",
        "--user-data-dir=" + str(profile),
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-extensions",
        "--disable-sync",
        "--disable-component-update",
        "--disable-quic",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
        "--host-resolver-rules=MAP * ~NOTFOUND",
        f"--proxy-server=http://127.0.0.1:{proxy_port}",
        "--proxy-bypass-list=<-loopback>",
        "--window-size=1440,900",
        "about:blank",
    ]


def classify_page(info, http_status, loaded, document_failed):
    text = (info.get("title", "") + " " + info.get("text", "")).casefold()
    if (
        http_status in (401, 407)
        or info.get("password")
        or re.search(r"/(?:login|signin|sign-in)(?:/|\?|$)", info.get("url", ""), re.I)
    ):
        return "login_required"
    if http_status in (403, 429) or any(
        s in text
        for s in (
            "verify you are human",
            "checking your browser",
            "just a moment...",
            "enable javascript and cookies to continue",
            "access denied",
            "attention required! | cloudflare",
            "captcha",
        )
    ):
        return "challenge"
    if (
        document_failed
        or not http_status
        or http_status >= 400
        or not info.get("url", "").startswith(("https://", "http://"))
    ):
        return "load_failed"
    if not loaded or not (info.get("text", "").strip() or info.get("title", "").strip()):
        return "partial"
    return "captured"


def _fetch_scanned(url, *, document=False, root_domain=None, **kwargs):
    """Follow HTTP redirects and scan the final payload before it reaches the browser."""
    current = web_url(url)
    hops = []
    for _ in range(6):
        response = fetch(current, **kwargs)
        if response.status_code in (301, 302, 303, 307, 308) and "location" in response.headers:
            next_url = web_url(urljoin(current, response.headers["location"]))
            if document and root_domain:
                next_host = urlsplit(next_url).hostname or ""
                if not _same_or_subdomain(next_host, root_domain):
                    raise ValueError("Website address is not public; request blocked")
            hops.append(next_url[:4096])
            current = next_url
            continue
        receipt = aegis.scan_buffer(
            response.body,
            context="website-resource",
            timeout=min(3.0, kwargs.get("timeout", 3.0)),
            cancel_event=kwargs.get("cancel_event"),
        )
        return response, receipt, current, hops
    raise ValueError("Website exceeded its redirect limit")


def resolve_root_website(url_or_host, *, timeout=10.0, cancel_event=None):
    """Verify the root domain loads (trying https://<root>, https://www.<root>, http://<root>).

    Returns (root_domain, final_url, response, scan_receipt, redirects).
    Raises ValueError if the root domain does not load or redirects off-domain.
    """
    root = extract_root_domain(url_or_host)
    candidates = [
        f"https://{root}/",
        f"https://www.{root}/",
        f"http://{root}/",
    ]
    last_error = None
    for candidate in candidates:
        try:
            response, receipt, final_url, hops = _fetch_scanned(
                candidate,
                document=True,
                root_domain=root,
                timeout=min(8.0, timeout),
                cancel_event=cancel_event,
                max_bytes=MAX_RESOURCE,
            )
            if response.status_code >= 400 and candidate != candidates[-1]:
                last_error = ValueError(f"HTTP {response.status_code}")
                continue
            return root, final_url, response, receipt, [candidate, *hops]
        except aegis.ContentScanError:
            raise
        except Exception as error:
            last_error = error
    detail = network_error(last_error) if last_error else "Network connection failed"
    raise ValueError(f"Website navigation failed: {detail}")


def _finish_resources(futures, cancel_event, client):
    """Join cancellation before PNG capture; unresolved scans never look successful."""
    cancel_event.local.set()
    for future, (rid, _) in futures.items():
        future.cancel()
        try:
            client.send("Fetch.failRequest", {"requestId": rid, "errorReason": "Aborted"})
        except (OSError, ValueError):
            pass
        try:
            future.result(timeout=0.25)
        except CancelledError:
            continue
        except aegis.ContentScanError:
            raise
        except FutureTimeout:
            if not future.done():
                raise aegis.scan_unavailable(representation="bytes") from None
        except Exception:
            continue


def capture_website(url, *, cancel_event=None, executable=None):
    root_domain = extract_root_domain(url)
    requested_url = web_url(f"https://{root_domain}/")
    cancel_event = cancel_event or threading.Event()
    network_cancel = _CombinedCancel(cancel_event)
    start = time.monotonic()
    deadline = start + MAX_SECONDS
    profile = Path(tempfile.mkdtemp(prefix="companion-website-"))
    process = client = guard = deny_proxy = None
    pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="website-resources")
    futures = {}
    metadata = {
        "requested_url": requested_url,
        "root_domain": root_domain,
        "final_url": "",
        "title": "",
        "captured_at": now(),
        "viewport": dict(VIEWPORT),
        "capture_status": "load_failed",
        "http_status": None,
        "redirects": [],
        "blocked_requests": 0,
        "resource_bytes": 0,
        "policy": "public-web-viewport-v1",
        "browser": "",
        "resource_failures": [],
        "content_scans": {},
    }
    png = None
    try:
        # Step 1: Probe root domain (https://root -> https://www.root -> http://root)
        # before spawning Chrome/Edge. Fails fast if the root domain does not load.
        _, entry_url, preloaded_doc, preloaded_scan, initial_redirects = resolve_root_website(
            root_domain,
            timeout=min(12.0, max(1.0, deadline - time.monotonic() - 10)),
            cancel_event=network_cancel,
        )
        metadata["redirects"] = initial_redirects
        metadata["final_url"] = entry_url[:4096]
        metadata["http_status"] = preloaded_doc.status_code
        scan_status = preloaded_scan["status"]
        metadata["content_scans"][scan_status] = 1
        metadata["resource_bytes"] = len(preloaded_doc.body)
        preloaded_consumed = False

        # Step 2: Launch isolated headless browser to render the verified root page
        deny_proxy = DenyProxy()
        process = subprocess.Popen(
            browser_arguments(executable or find_browser(), profile, deny_proxy.port),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        guard = BrowserProcessGuard(process)
        port_file = profile / "DevToolsActivePort"
        while not port_file.is_file():
            if cancel_event.wait(0.05) or time.monotonic() > min(deadline, start + 12):
                raise ValueError("Capture browser did not become ready in time")
            if process.poll() is not None:
                raise ValueError(
                    "Capture browser could not start; workstation policy may prevent headless capture"
                )
        lines = port_file.read_text().splitlines()
        if (
            len(lines) < 2
            or not lines[0].isdigit()
            or not lines[1].startswith("/devtools/browser/")
        ):
            raise ValueError("Invalid capture browser endpoint")
        client = CDP("ws://127.0.0.1:" + lines[0] + lines[1], deadline)
        client.cancel_event = cancel_event
        metadata["browser"] = client.call("Browser.getVersion", browser=True).get("product", "")[
            :160
        ]
        client.call("Browser.setDownloadBehavior", {"behavior": "deny"}, browser=True)
        target = client.call("Target.createTarget", {"url": "about:blank"}, browser=True)[
            "targetId"
        ]
        client.session = client.call(
            "Target.attachToTarget", {"targetId": target, "flatten": True}, browser=True
        )["sessionId"]
        client.call("Page.enable")
        client.call("Page.setLifecycleEventsEnabled", {"enabled": True})
        client.call("Emulation.setDeviceMetricsOverride", VIEWPORT)
        client.call("Network.enable", {"maxTotalBufferSize": 1024 * 1024})
        client.call("Network.setBypassServiceWorker", {"bypass": True})
        client.call("Network.setCacheDisabled", {"cacheDisabled": True})
        client.call(
            "Fetch.enable",
            {
                "patterns": [
                    {"urlPattern": "http://*", "requestStage": "Request"},
                    {"urlPattern": "https://*", "requestStage": "Request"},
                ],
                "handleAuthRequests": True,
            },
        )
        navigation = client.send("Page.navigate", {"url": entry_url})
        requests = 1
        loaded_at = None
        main_frame = None
        latest_document = None
        top_status = preloaded_doc.status_code
        settled_at = None
        document_error = ""
        loading_deadline = deadline - 5

        def failure(error, document):
            nonlocal document_error
            detail = network_error(error)
            stage = "document" if document else "resource"
            if document:
                document_error = detail
            if len(metadata["resource_failures"]) < 8:
                metadata["resource_failures"].append({"stage": stage, "reason": detail})

        while time.monotonic() < loading_deadline:
            if cancel_event.is_set():
                raise ValueError("Website capture cancelled")
            if navigation in client.results:
                response = client.results.pop(navigation)
                if "error" in response or response.get("result", {}).get("errorText"):
                    raise ValueError(navigation_error(response, document_error))
                main_frame = response.get("result", {}).get("frameId", main_frame)
                navigation = -1
            events, client.events = client.events, []
            for event in events:
                if event.get("sessionId") != client.session:
                    continue
                method, p = event["method"], event.get("params", {})
                if method == "Page.frameNavigated" and not p.get("frame", {}).get("parentId"):
                    main_frame = p["frame"]["id"]
                    metadata["final_url"] = p["frame"].get("url", "")[:4096]
                elif (
                    method == "Page.lifecycleEvent"
                    and p.get("name") in ("DOMContentLoaded", "load")
                    and p.get("frameId") == main_frame
                    and latest_document
                ):
                    loaded_at = loaded_at or time.monotonic()
                elif method == "Fetch.authRequired":
                    client.send(
                        "Fetch.continueWithAuth",
                        {
                            "requestId": p["requestId"],
                            "authChallengeResponse": {"response": "CancelAuth"},
                        },
                    )
                elif method == "Fetch.requestPaused":
                    request = p["request"]
                    rid = p["requestId"]
                    resource_type = p.get("resourceType", "")
                    document = resource_type == "Document" and (
                        main_frame is None or p.get("frameId") == main_frame
                    )
                    if request["method"] != "GET" or resource_type in (
                        "Media",
                        "WebSocket",
                        "EventSource",
                        "Ping",
                        "CSPViolationReport",
                    ):
                        client.send(
                            "Fetch.failRequest",
                            {"requestId": rid, "errorReason": "Aborted"},
                        )
                        continue
                    if document and not preloaded_consumed:
                        preloaded_consumed = True
                        main_frame = p.get("frameId")
                        latest_document = rid
                        headers = [
                            {"name": k, "value": v}
                            for k, v in preloaded_doc.headers.items()
                            if k.lower() != "location"
                        ]
                        client.send(
                            "Fetch.fulfillRequest",
                            {
                                "requestId": rid,
                                "responseCode": preloaded_doc.status_code,
                                "responseHeaders": headers,
                                "body": base64.b64encode(preloaded_doc.body).decode(),
                            },
                        )
                        continue
                    requests += 1
                    if document:
                        main_frame = p.get("frameId")
                        latest_document = rid
                        loaded_at = None
                        if len(metadata["redirects"]) >= 10:
                            raise ValueError("Website exceeded its redirect limit")
                        metadata["redirects"].append(request["url"][:4096])
                    try:
                        requested = web_url(request["url"])
                        if document and not _same_or_subdomain(
                            urlsplit(requested).hostname or "", root_domain
                        ):
                            raise ValueError("Website address is not public; request blocked")
                        if (
                            requests > MAX_REQUESTS
                            or len(futures) >= MAX_IN_FLIGHT
                            or metadata["resource_bytes"] >= MAX_BYTES
                        ):
                            raise ValueError("Request blocked by capture limits")
                        future = pool.submit(
                            _fetch_scanned,
                            requested,
                            document=document,
                            root_domain=root_domain,
                            timeout=min(
                                10 if document else 5,
                                max(0.01, loading_deadline - time.monotonic()),
                            ),
                            cancel_event=network_cancel,
                            max_bytes=min(MAX_RESOURCE, MAX_BYTES - metadata["resource_bytes"]),
                        )
                        futures[future] = (rid, document)
                    except ValueError as error:
                        failure(error, document)
                        metadata["blocked_requests"] += 1
                        client.send(
                            "Fetch.failRequest",
                            {"requestId": rid, "errorReason": "BlockedByClient"},
                        )
            for future in list(futures):
                if not future.done():
                    continue
                rid, document = futures.pop(future)
                try:
                    response, scan_receipt, final_target_url, hops = future.result()
                    scan_status = scan_receipt["status"]
                    metadata["content_scans"][scan_status] = (
                        metadata["content_scans"].get(scan_status, 0) + 1
                    )
                    metadata["resource_bytes"] += len(response.body)
                    if metadata["resource_bytes"] > MAX_BYTES:
                        raise ValueError("Capture byte budget exceeded")
                    if document and rid == latest_document:
                        top_status = response.status_code
                        metadata["redirects"].extend(hops)
                        metadata["final_url"] = final_target_url[:4096]
                    headers = [
                        {"name": k, "value": v}
                        for k, v in response.headers.items()
                        if k.lower() != "location"
                    ]
                    client.send(
                        "Fetch.fulfillRequest",
                        {
                            "requestId": rid,
                            "responseCode": response.status_code,
                            "responseHeaders": headers,
                            "body": base64.b64encode(response.body).decode(),
                        },
                    )
                except Exception as error:
                    failure(error, document)
                    metadata["blocked_requests"] += 1
                    client.send(
                        "Fetch.failRequest", {"requestId": rid, "errorReason": "BlockedByClient"}
                    )
                    if isinstance(error, aegis.ContentScanError):
                        raise error
            if loaded_at and not futures:
                settled_at = settled_at or time.monotonic()
                if time.monotonic() - settled_at >= 1.2:
                    break
            else:
                settled_at = None
            if loaded_at and time.monotonic() - loaded_at >= 7:
                break
            try:
                client.receive()
            except socket.timeout:
                pass
            for identity in list(client.results):
                if identity != navigation:
                    result = client.results.pop(identity, None)
                    if result and result.get("error"):
                        metadata["blocked_requests"] += 1
        metadata["blocked_requests"] += len(futures)
        _finish_resources(futures, network_cancel, client)
        client.call("Page.stopLoading")
        info = client.call(
            "Runtime.evaluate",
            {
                "expression": "JSON.stringify({url:location.href,title:document.title,text:(document.body?.innerText||'').slice(0,12000),password:!!document.querySelector('input[type=password]')})",
                "returnByValue": True,
                "timeout": 1500,
            },
        )
        page = json.loads(info.get("result", {}).get("value", "{}"))
        if not metadata["final_url"]:
            metadata["final_url"] = page.get("url", "")[:4096]
        metadata["title"] = page.get("title", "")[:500]
        metadata["http_status"] = top_status
        metadata["capture_status"] = classify_page(
            page, top_status, loaded_at is not None, bool(document_error)
        )
        screenshot = client.call(
            "Page.captureScreenshot",
            {
                "format": "png",
                "fromSurface": True,
                "captureBeyondViewport": False,
                "clip": {"x": 0, "y": 0, "width": 1440, "height": 900, "scale": 1},
            },
        )
        png = base64.b64decode(screenshot["data"], validate=True)
        if len(png) > 10 * 1024 * 1024:
            raise ValueError("Viewport image exceeded its size limit")
        metadata["captured_at"] = now()
    finally:
        network_cancel.local.set()
        pool.shutdown(wait=False, cancel_futures=True)
        if client:
            try:
                client.send("Browser.close", browser=True)
            except (OSError, ValueError):
                pass
            client.close()
        if guard:
            guard.close()
        if process:
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
        if deny_proxy:
            deny_proxy.close()
        shutil.rmtree(profile, ignore_errors=True)
    metadata["elapsed_seconds"] = round(time.monotonic() - start, 2)
    return png, metadata