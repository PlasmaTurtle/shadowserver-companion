"""Native Chromium navigation, reported-host fallback and viewport readiness."""

from collections import Counter
from ipaddress import ip_address
import json
import re
import socket
import time
from urllib.parse import urlsplit, urlunsplit

from modules.tools.components.network_identity import root_domain
from .diagnostics import navigation_error
from .transport import web_url

NAVIGATION_SECONDS = 30
SETTLE_SECONDS = 1.0
SCREENSHOT_RESERVE = 5


class WebsiteLoadError(ValueError):
    """The browser ran, but no acceptable target page loaded."""

    def __init__(self, message, metadata):
        super().__init__(message)
        self.metadata = metadata
        self.attempted_urls = tuple(metadata.get("attempted_urls", ()))


def extract_root_domain(value):
    host = urlsplit(value if "://" in value else "https://" + value).hostname or ""
    return root_domain(host)


def navigation_candidates(requested_url):
    """Try the reported address before changing scheme or using its main site."""
    requested = web_url(requested_url)
    parsed = urlsplit(requested)
    host = parsed.hostname or ""
    values = [
        (requested, False),
        (
            urlunsplit(parsed._replace(scheme="http" if parsed.scheme == "https" else "https")),
            False,
        ),
    ]
    try:
        ip_address(host)
        local = True
    except ValueError:
        local = "." not in host or host.endswith(".localhost")
    if not local:
        root = extract_root_domain(requested)
        values.extend(
            (f"{scheme}://{prefix}{root}/", True)
            for scheme in ("https", "http")
            for prefix in ("", "www.")
        )
    seen = set()
    for url, fallback in values:
        if url not in seen:
            seen.add(url)
            yield url, fallback


def _check(cancel_event):
    if cancel_event.is_set():
        raise ValueError("Website capture cancelled")


_PAGE_STATE = r"""JSON.stringify((()=>{
 const body=document.body;
 const shown=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);
   return r.width>0&&r.height>0&&r.top<innerHeight&&r.bottom>0&&r.left<innerWidth&&r.right>0&&s.display!=='none'&&s.visibility!=='hidden'};
 const images=[...document.images].filter(shown), videos=[...document.querySelectorAll('video')].filter(shown);
 const posters=globalThis.__companionVideoPosters||(globalThis.__companionVideoPosters=new WeakMap());
 for(const v of videos){if(v.poster&&posters.get(v)?.src!==v.poster){const image=new Image();image.src=v.poster;posters.set(v,{src:v.poster,image})}}
 const poster=v=>posters.get(v)?.image;
 const mediaReady=v=>v.readyState>=2||!!(poster(v)?.complete&&poster(v)?.naturalWidth>0);
 const elements=body?[body,...document.querySelectorAll('body *')].filter(shown):[];
 const text=(body?.innerText||'').slice(0,12000);
 const visible=elements.some(e=>[...e.childNodes].some(n=>n.nodeType===3&&n.textContent.trim())||
   (e.tagName==='IMG'&&e.complete&&e.naturalWidth>0)||(e.tagName==='VIDEO'&&mediaReady(e))||
   e.tagName==='CANVAS'||e.tagName==='IFRAME'||e.tagName.toLowerCase()==='svg'||getComputedStyle(e).backgroundImage!=='none');
 return {url:location.href,title:document.title,text,visible,password:[...document.querySelectorAll('input[type=password]')].some(shown),
   ready_state:document.readyState,images_ready:images.every(i=>i.complete&&i.naturalWidth>0),
   images_finished:images.every(i=>i.complete),
   media_ready:videos.every(mediaReady),fonts_ready:!document.fonts||document.fonts.status==='loaded',
   media_finished:videos.every(v=>mediaReady(v)||!!v.error||!!poster(v)?.complete),
   media_states:videos.map(v=>({ready_state:v.readyState,network_state:v.networkState,error:v.error?.code||null,width:v.videoWidth,height:v.videoHeight})),
   image_count:images.length,video_count:videos.length,width:body?.scrollWidth||0,height:body?.scrollHeight||0};
})())"""


def _page_state(client):
    result = client.call(
        "Runtime.evaluate",
        {
            "expression": _PAGE_STATE,
            "returnByValue": True,
            "timeout": 2000,
        },
    )
    if result.get("exceptionDetails"):
        return None
    value = result.get("result", {}).get("value")
    return json.loads(value) if value else None


def _attempt(client, url, *, deadline, cancel_event, metadata, classify):
    """Let the browser load naturally, then wait for a rendered viewport."""
    client.events.clear()
    client.deadline = min(deadline, time.monotonic() + NAVIGATION_SECONDS)
    answer = client.call("Page.navigate", {"url": url})
    frame = answer.get("frameId")
    if answer.get("errorText") and answer["errorText"] != "net::ERR_ABORTED":
        return {
            "outcome": "load_failed",
            "final_url": "",
            "http_status": None,
            "reason": navigation_error({"result": answer}),
        }
    client.deadline = deadline
    navigation_deadline = min(deadline, time.monotonic() + NAVIGATION_SECONDS)
    active, failures = {}, []
    top_status = None
    document_request = None
    document_error = ""
    page = {}
    last_state = 0
    last_activity = time.monotonic()
    settled_at = None
    content_ready_at = None
    signature = None
    loaded = False
    ready = False
    metadata["redirects"] = [url]
    metadata["resource_failures"] = failures

    def redirect(value):
        if value.startswith(("http://", "https://")) and metadata["redirects"][-1] != value:
            metadata["redirects"].append(value)

    while time.monotonic() < deadline:
        _check(cancel_event)
        events, client.events = client.events, []
        for event in events:
            if event.get("sessionId") != client.session:
                continue
            method, params = event["method"], event.get("params", {})
            if method == "Network.requestWillBeSent":
                kind = params.get("type", "")
                identity = params["requestId"]
                if kind not in {"Media", "WebSocket", "EventSource", "Ping"}:
                    active[identity] = (kind, params.get("frameId"))
                    last_activity = time.monotonic()
                metadata["fetched_requests"] += 1
                if kind == "Document" and params.get("frameId") == frame:
                    document_request = identity
                    document_error = ""
                    top_status = None
                    loaded = False
                    settled_at = None
                    content_ready_at = None
                    redirect(params["request"]["url"])
            elif method == "Network.responseReceived":
                response = params["response"]
                status = int(response["status"])
                if params.get("type") == "Document" and params.get("frameId") == frame:
                    top_status = status
                if status >= 400 and len(failures) < 8:
                    failures.append(
                        {
                            "stage": "resource",
                            "type": params.get("type", ""),
                            "reason": f"Website resource returned HTTP {status}",
                        }
                    )
            elif method in {"Network.loadingFinished", "Network.loadingFailed"}:
                identity = params["requestId"]
                if identity in active:
                    active.pop(identity)
                    last_activity = time.monotonic()
                if method == "Network.loadingFinished":
                    metadata["resource_bytes"] += int(params.get("encodedDataLength", 0))
                else:
                    detail = params.get("errorText", "")
                    detail = (
                        detail
                        if re.fullmatch(r"net::ERR_[A-Z0-9_]+", detail)
                        else "Browser resource request failed"
                    )
                    if identity == document_request and not params.get("canceled"):
                        document_error = detail
                    if not params.get("canceled") and len(failures) < 8:
                        failures.append({"stage": "network", "reason": detail})
            elif method == "Page.frameNavigated":
                value = params.get("frame", {})
                if value.get("id") == frame:
                    redirect(value.get("url", ""))
            elif method == "Page.navigatedWithinDocument" and params.get("frameId") == frame:
                redirect(params.get("url", ""))
            elif method == "Page.lifecycleEvent" and params.get("frameId") == frame:
                if params.get("name") in {"DOMContentLoaded", "load"}:
                    loaded = True

        if document_error:
            break
        if top_status and top_status >= 400 and top_status not in {401, 403, 407, 429}:
            document_error = f"Website returned HTTP {top_status}"
            break
        now = time.monotonic()
        if now >= last_state + 0.25:
            last_state = now
            try:
                state = _page_state(client)
            except ValueError:
                # Redirects can replace an execution context between commands.
                state = None
            if state and state.get("url", "").startswith(("http://", "https://")):
                page = state
                redirect(page["url"])
                document_ready = page.get("ready_state") in {"interactive", "complete"}
                loaded |= document_ready
                visible = bool(page.get("visible"))
                assets_ready = all(
                    page.get(key, False) for key in ("images_ready", "fonts_ready", "media_ready")
                )
                quiet = not active and now - last_activity >= 0.5
                finished = all(
                    page.get(key, False)
                    for key in ("images_finished", "fonts_ready", "media_finished")
                )
                if document_ready and visible and finished:
                    content_ready_at = content_ready_at or now
                else:
                    content_ready_at = None
                render_pending = any(
                    request_frame == frame and kind in {"Document", "Stylesheet", "Image", "Font"}
                    for kind, request_frame in active.values()
                )
                settled_network = not render_pending and (
                    quiet or (content_ready_at is not None and now - content_ready_at >= 3)
                )
                ready = document_ready and visible and assets_ready and settled_network
                can_capture = document_ready and visible and finished and settled_network
                current = (
                    page["url"],
                    page.get("text"),
                    page.get("width"),
                    page.get("height"),
                    page.get("image_count"),
                    page.get("video_count"),
                )
                if can_capture and current == signature:
                    settled_at = settled_at or now
                else:
                    settled_at = None
                signature = current
                if settled_at and now - settled_at >= SETTLE_SECONDS:
                    break
        if now >= navigation_deadline:
            if not loaded:
                document_error = "Website navigation did not finish before its timeout"
            break
        try:
            client.receive()
        except socket.timeout:
            pass

    _check(cancel_event)
    visible = bool(page.get("visible"))
    outcome = classify(page, top_status, ready, bool(document_error))
    if not visible or not loaded:
        outcome = "load_failed"
    reason = document_error
    if outcome == "partial":
        reason = (
            "Some visible images or video could not be displayed"
            if not page.get("images_ready") or not page.get("media_ready")
            else "Website fonts did not finish loading"
            if not page.get("fonts_ready")
            else "Website viewport was still loading at the capture timeout"
        )
    metadata["load_readiness"] = {
        "document_loaded": loaded,
        "document_ready": page.get("ready_state") in {"interactive", "complete"},
        "images_ready": page.get("images_ready", False),
        "fonts_ready": page.get("fonts_ready", False),
        "media_ready": page.get("media_ready", False),
        "media_states": page.get("media_states", []),
        "pending_requests": len(active),
        "pending_types": dict(Counter(kind for kind, _ in active.values())),
    }
    return {
        "outcome": outcome,
        "final_url": page.get("url", ""),
        "http_status": top_status,
        "title": page.get("title", "")[:500],
        "reason": reason,
    }


def load_page(
    requested_url,
    *,
    open_page,
    deadline,
    cancel_event,
    metadata,
    classify,
    skip_urls=(),
    require_usable=False,
):
    skipped = set(skip_urls)
    for url, fallback in navigation_candidates(requested_url):
        if url in skipped:
            continue
        _check(cancel_event)
        if time.monotonic() >= deadline - SCREENSHOT_RESERVE:
            break
        attempt = {"url": url, "outcome": "load_failed", "final_url": "", "http_status": None}
        metadata["attempted_urls"].append(url)
        metadata["attempts"].append(attempt)
        client = open_page()
        try:
            attempt.update(
                _attempt(
                    client,
                    url,
                    deadline=deadline - SCREENSHOT_RESERVE,
                    cancel_event=cancel_event,
                    metadata=metadata,
                    classify=classify,
                )
            )
        except TimeoutError:
            _check(cancel_event)
            attempt["reason"] = "Website navigation timed out"
        if attempt["outcome"] in {"captured", "login_required"} or (
            not require_usable and attempt["outcome"] != "load_failed"
        ):
            metadata.update(
                final_url=attempt["final_url"],
                title=attempt.pop("title", ""),
                http_status=attempt["http_status"],
                capture_status=attempt["outcome"],
                fallback_used=fallback,
            )
            client.deadline = deadline
            client.call(
                "Runtime.evaluate",
                {
                    "expression": "new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve(true))))",
                    "awaitPromise": True,
                },
            )
            return
    detail = (
        metadata["attempts"][-1].get("reason") if metadata["attempts"] else "Navigation timed out"
    )
    raise WebsiteLoadError(
        "Website could not be loaded: " + (detail or "No acceptable rendered page was available"),
        metadata,
    )
