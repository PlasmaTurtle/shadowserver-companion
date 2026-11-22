"""Observe Playwright page events for capture provenance, without intercepting traffic."""

from collections import Counter
import re
import time

from playwright.async_api import Error as PlaywrightError


class PageObservations:
    def __init__(self, page, url, metadata):
        self.page, self.metadata = page, metadata
        self.active = {}
        self.status = None
        self.document_error = ""
        self.download = False
        self.last_activity = time.monotonic()
        metadata["redirects"] = [url]
        metadata["resource_failures"] = []
        page.on("request", self.request)
        page.on("response", self.response)
        page.on("requestfinished", self.finished)
        page.on("requestfailed", self.failed)
        page.on("framenavigated", self.navigated)
        page.on("download", self.offered_download)

    def redirect(self, url):
        values = self.metadata["redirects"]
        if url.startswith(("https://", "http://")) and values[-1] != url:
            values.append(url)

    def main_document(self, request):
        return request.is_navigation_request() and self.main_frame(request)

    def main_frame(self, request):
        try:
            return request.frame == self.page.main_frame
        except PlaywrightError:
            # Requests can precede frame creation or belong to a service worker.
            return False

    def request(self, request):
        self.metadata["fetched_requests"] += 1
        if request.resource_type not in {"media", "websocket", "eventsource", "ping"}:
            self.active[request] = request.resource_type
            self.last_activity = time.monotonic()
        if self.main_document(request):
            self.status = None
            self.document_error = ""
            self.redirect(request.url)

    def response(self, response):
        if self.main_document(response.request):
            self.status = response.status
        if response.status >= 400:
            self.failure(
                stage="resource",
                type=response.request.resource_type.title(),
                reason=f"Website resource returned HTTP {response.status}",
            )

    def finished(self, request):
        self.active.pop(request, None)
        self.last_activity = time.monotonic()

    def failed(self, request):
        self.finished(request)
        error = request.failure or ""
        if error == "net::ERR_ABORTED":
            return
        detail = (
            error
            if re.fullmatch(r"net::ERR_[A-Z0-9_]+", error)
            else "Browser resource request failed"
        )
        if self.main_document(request):
            self.document_error = detail
        self.failure(stage="network", reason=detail)

    def failure(self, **detail):
        if len(self.metadata["resource_failures"]) < 8:
            self.metadata["resource_failures"].append(detail)

    def navigated(self, frame):
        if frame == self.page.main_frame:
            self.redirect(frame.url)

    def offered_download(self, download):
        self.download = True

    def render_pending(self):
        return any(
            kind in {"document", "stylesheet", "image", "font"} and self.main_frame(request)
            for request, kind in self.active.items()
        )

    def pending_types(self):
        return dict(Counter(kind.title() for kind in self.active.values()))
