"""Application viewport-readiness policy over Playwright page observations."""

import asyncio
import time

from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeout

from .page_observations import PageObservations
from .diagnostics import navigation_error

SETTLE_SECONDS = 1.0


_PAGE_STATE = r"""(()=>{
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
   site_name:(document.querySelector('meta[property="og:site_name"]')?.content||'').slice(0,300),
   heading:([...document.querySelectorAll('h1')].find(shown)?.innerText||'').slice(0,300),
   ready_state:document.readyState,images_ready:images.every(i=>i.complete&&i.naturalWidth>0),
   images_finished:images.every(i=>i.complete),
   media_ready:videos.every(mediaReady),fonts_ready:!document.fonts||document.fonts.status==='loaded',
   media_finished:videos.every(v=>mediaReady(v)||!!v.error||!!poster(v)?.complete),
   media_states:videos.map(v=>({ready_state:v.readyState,network_state:v.networkState,error:v.error?.code||null,width:v.videoWidth,height:v.videoHeight})),
   image_count:images.length,video_count:videos.length,width:body?.scrollWidth||0,height:body?.scrollHeight||0};
})()"""


async def render_page(page, url, *, deadline, metadata, classify):
    observations = PageObservations(page, url, metadata)
    state = {}
    settled_at = content_ready_at = None
    signature = None
    ready = loaded = False
    try:
        await page.goto(
            url, wait_until="domcontentloaded", timeout=max(1, (deadline - time.monotonic()) * 1000)
        )
    except PlaywrightError as error:
        if page.is_closed() or not page.context.browser.is_connected():
            raise
        if observations.download or "Download is starting" in str(error):
            return {
                "outcome": "load_failed",
                "final_url": "",
                "http_status": None,
                "reason": "Website offered a file download",
            }
        if not observations.status:
            return {
                "outcome": "load_failed",
                "final_url": "",
                "http_status": None,
                "reason": navigation_error({"result": {"errorText": str(error)}}),
            }
    while time.monotonic() < deadline:
        if observations.document_error:
            break
        if (
            observations.status
            and observations.status >= 400
            and observations.status not in {401, 403, 407, 429}
        ):
            observations.document_error = f"Website returned HTTP {observations.status}"
            break
        try:
            state_handle = await page.wait_for_function(
                _PAGE_STATE, timeout=max(1, min(2000, (deadline - time.monotonic()) * 1000))
            )
            latest = await state_handle.json_value()
            await state_handle.dispose()
        except PlaywrightTimeout:
            break
        except PlaywrightError:
            if page.is_closed() or not page.context.browser.is_connected():
                raise
            latest = None  # A navigation can replace the execution context.
        current_time = time.monotonic()
        if latest and latest.get("url", "").startswith(("http://", "https://")):
            state = latest
            observations.redirect(state["url"])
            loaded = state.get("ready_state") in {"interactive", "complete"}
            visible = bool(state.get("visible"))
            assets_ready = all(
                state.get(key, False) for key in ("images_ready", "fonts_ready", "media_ready")
            )
            finished = all(
                state.get(key, False)
                for key in ("images_finished", "fonts_ready", "media_finished")
            )
            if loaded and visible and finished:
                content_ready_at = content_ready_at or current_time
            else:
                content_ready_at = None
            quiet = not observations.active and current_time - observations.last_activity >= 0.5
            settled_network = not observations.render_pending() and (
                quiet or (content_ready_at is not None and current_time - content_ready_at >= 3)
            )
            ready = loaded and visible and assets_ready and settled_network
            can_capture = loaded and visible and finished and settled_network
            current = (
                state["url"],
                state.get("text"),
                state.get("width"),
                state.get("height"),
                state.get("image_count"),
                state.get("video_count"),
            )
            if can_capture and current == signature:
                settled_at = settled_at or current_time
            else:
                settled_at = None
            signature = current
            if settled_at and current_time - settled_at >= SETTLE_SECONDS:
                break
        await asyncio.sleep(0.1)
    reason = observations.document_error
    outcome = classify(state, observations.status, ready, bool(reason))
    if not state.get("visible") or not loaded:
        outcome = "load_failed"
    if outcome == "partial":
        reason = (
            "Some visible images or video could not be displayed"
            if not state.get("images_ready") or not state.get("media_ready")
            else "Website fonts did not finish loading"
            if not state.get("fonts_ready")
            else "Website viewport was still loading at the capture timeout"
        )
    metadata["load_readiness"] = {
        "document_loaded": loaded,
        "document_ready": loaded,
        "images_ready": state.get("images_ready", False),
        "fonts_ready": state.get("fonts_ready", False),
        "media_ready": state.get("media_ready", False),
        "media_states": state.get("media_states", []),
        "pending_requests": len(observations.active),
        "pending_types": observations.pending_types(),
    }
    return {
        "outcome": outcome,
        "final_url": state.get("url", ""),
        "http_status": observations.status,
        "title": state.get("title", "")[:500],
        "site_name": state.get("site_name", ""),
        "heading": state.get("heading", ""),
        "page_text": state.get("text", ""),
        "reason": reason,
    }
