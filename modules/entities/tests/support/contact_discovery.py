"""Reusable synthetic contact discovery fixtures and builders."""

import json
import threading
import time

from modules.entities.components.contact_discovery import FetchResponse

ROOT = "https://example.org/"


SECURITY = ROOT + ".well-known/security.txt"


def html(body):
    return FetchResponse(200, {"content-type": "text/html; charset=utf-8"}, body.encode())


class FixtureFetcher:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def fetch(self, url, *, timeout, max_bytes, cancel_event=None):
        self.calls.append(url)
        return self.pages.get(url, FetchResponse(404, {}, b""))


class SyntheticWebsite:
    def __init__(self, folder):
        self.folder = folder
        self.lock = threading.Lock()

    def fetch(self, url, *, timeout, max_bytes, cancel_event=None):
        with self.lock:
            with (self.folder / "requests.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"url": url}) + "\n")
        mode = json.loads((self.folder / "control.json").read_text(encoding="utf-8"))["mode"]
        if mode == "slow" and cancel_event is not None:
            deadline = time.monotonic() + min(4, timeout)
            while time.monotonic() < deadline and not cancel_event.is_set():
                time.sleep(0.02)
        pages = {
            "https://example.com/": (
                "text/html",
                "<html><title>Synthetic Example Company</title><body><h1>Example Company</h1>"
                "<p>This is a browser verification fixture, never a real business.</p>"
                '<nav><a href="/contact">Contact us</a><a href="/team">Leadership team</a></nav>'
                "<script>window.sourceExecuted=true</script></body></html>",
            ),
            "https://example.com/.well-known/security.txt": (
                "text/plain",
                "Contact: mailto:security@example.com\nExpires: 2099-01-01T00:00:00Z\n"
                "Canonical: https://example.com/.well-known/security.txt\n",
            ),
            "https://example.com/contact": (
                "text/html",
                "<html><title>Contact Example Company</title><body>"
                '<p>Customer support: <a href="mailto:support@example.com">support@example.com</a></p>'
                '<p>IT Department: <a href="mailto:it@example.com">it@example.com</a></p>'
                '<p>Business phone: <a href="tel:+17045550100">+1 704 555 0100</a></p>'
                '<p>Contact form: <form action="/send" method="post"><input name="message"></form></p>'
                "</body></html>",
            ),
            "https://example.com/team": (
                "text/html",
                "<html><title>Leadership</title><body><section><h2>Alex Example</h2>"
                "<p>Information Technology Director</p></section></body></html>",
            ),
        }
        content_type, body = pages.get(url, ("text/plain", "Synthetic page not found"))
        return {
            "status_code": 200 if url in pages else 404,
            "headers": {"content-type": content_type},
            "body": body.encode(),
        }
