"""Synthetic intake fixture with qualified leads and no notification cases."""

from tests.support.qualification import registry_factory, capture_website

import argparse
from io import BytesIO
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
from modules.entities.components.contact_discovery import ContactDiscovery
from tests.support.workbench import FakeRegistry, csv_bytes, observations
from modules.entities.tests.support.contact_discovery import SyntheticWebsite
from modules.entities.tests.support.entity_dns import DNSFixture


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8908)
    args = parser.parse_args()
    if args.workspace.exists():
        raise SystemExit("Use a new synthetic workspace")
    args.workspace.mkdir(parents=True)
    (args.workspace / "control.json").write_text('{"mode":"normal"}', encoding="utf-8")
    website = SyntheticWebsite(args.workspace)
    app = create_app(
        args.workspace / "data",
        worker=False,
        report_processes=False,
        attribution_factory=registry_factory(FakeRegistry),
        capture=capture_website,
        contact_discovery_factory=lambda: ContactDiscovery(fetcher=website),
    )
    app.state.entity_dns.provider_factory = DNSFixture().factory

    with app.state.store.transaction() as db:
        settings = app.state.store.settings()
        settings.update(analyst_name="Synthetic Reviewer", watch_inbox=False)
        db.execute("UPDATE settings SET value=? WHERE key='profile'", (json.dumps(settings),))
    record = app.state.intake.enqueue_stream(
        "navigation-fixture.csv", BytesIO(csv_bytes(observations()))
    )
    app.state.intake.process(record["id"])
    entity = app.state.store.one("SELECT id FROM leads WHERE merged_into IS NULL")
    assert app.state.store.all("SELECT id FROM cases") == []
    base = f"http://127.0.0.1:{args.port}"
    prepare_browser_fixture(app, args.workspace, base)
    (args.workspace / "browser.json").write_text(
        json.dumps(
            {
                "base": base,
                "launch_url": base + "/#launch=" + app.state.sessions.issue_launch(),
                "entity_id": entity["id"],
            }
        ),
        encoding="utf-8",
    )
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
