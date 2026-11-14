"""Explicit local-only contact browser fixture; no company-site network requests.

Run directly with --workspace pointing to a new scratch directory. The emitted
launcher URL is a one-use local test credential. Never use a working database.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "components" / "attribution" / "src")]

import uvicorn
from workbench.api import create_app
from workbench.cases import Cases
from workbench.contact_discovery import ContactDiscovery
from test_contacts_invariants_090 import attributed_entity


class SyntheticWebsite:
    def __init__(self, folder):
        self.folder = folder
        self.lock = threading.Lock()

    def fetch(self, url, *, timeout, max_bytes, cancel_event=None):
        with self.lock:
            with (self.folder / "requests.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"url": url}) + "\n")
        mode = json.loads((self.folder / "control.json").read_text())["mode"]
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--port", default=8899, type=int)
    args = parser.parse_args()
    if args.workspace.exists():
        raise SystemExit("Use a new, empty synthetic workspace directory")
    args.workspace.mkdir(parents=True)
    (args.workspace / "control.json").write_text('{"mode":"normal"}', encoding="utf-8")
    website = SyntheticWebsite(args.workspace)
    app = create_app(
        args.workspace / "data",
        worker=False,
        contact_discovery_factory=lambda: ContactDiscovery(fetcher=website),
    )
    entity = attributed_entity(app.state.store)
    case = Cases(app.state.store).create(entity["id"], "Synthetic contact discovery verification")
    with app.state.store.transaction() as db:
        profile = app.state.store.settings()
        profile.update(analyst_name="Synthetic Reviewer", watch_inbox=False)
        db.execute("UPDATE settings SET value=? WHERE key='profile'", (json.dumps(profile),))
        db.execute(
            "UPDATE leads SET company='Example Company (synthetic)', demo=1 WHERE id=?",
            (entity["id"],),
        )
    base = f"http://127.0.0.1:{args.port}"
    metadata = {
        "base": base,
        "launch_url": base + "/#launch=" + app.state.sessions.issue_launch(),
        "entity_id": entity["id"],
        "case_id": case["case_id"],
        "control_path": str(args.workspace / "control.json"),
        "requests_path": str(args.workspace / "requests.jsonl"),
    }
    (args.workspace / "browser.json").write_text(json.dumps(metadata), encoding="utf-8")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
