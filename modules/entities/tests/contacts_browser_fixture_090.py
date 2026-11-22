"""Explicit local-only contact browser fixture; no company-site network requests.

Run directly with --workspace pointing to a new scratch directory. The emitted
launcher URL is a one-use local test credential. Never use a working database.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT)]

from tests.fixture_paths import configure_fixture_imports

configure_fixture_imports(ROOT)

from tests.browser_fixture_support import configure_browser_fixture, prepare_browser_fixture

configure_browser_fixture()

import uvicorn
from modules.workspace.components.api import create_app
from modules.investigations.components.cases import Cases
from modules.entities.components.contact_discovery import ContactDiscovery
from modules.entities.tests.support.contacts import attributed_entity


from modules.entities.tests.support.contact_discovery import SyntheticWebsite


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
    prepare_browser_fixture(app, args.workspace, base)
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
