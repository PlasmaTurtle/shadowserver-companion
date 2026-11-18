"""Synthetic intake fixture with qualified leads and no notification cases."""

import argparse
from io import BytesIO
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "components" / "attribution" / "src")]

import uvicorn
from workbench.api import create_app
from workbench.contact_discovery import ContactDiscovery
from test_workbench import FakeRegistry, csv_bytes, observations, record_synthetic_evaluations
from contacts_browser_fixture_090 import SyntheticWebsite
from test_entity_dns_0984 import DNSFixture


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8908)
    args = parser.parse_args()
    if args.workspace.exists():
        raise SystemExit("Use a new synthetic workspace")
    args.workspace.mkdir(parents=True)
    (args.workspace / "control.json").write_text('{"mode":"normal"}')
    website = SyntheticWebsite(args.workspace)
    app = create_app(
        args.workspace / "data",
        worker=False,
        report_processes=False,
        lookup_factory=FakeRegistry,
        contact_discovery_factory=lambda: ContactDiscovery(fetcher=website),
    )
    app.state.entity_dns.provider_factory = DNSFixture().factory
    record_synthetic_evaluations(app)
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
    (args.workspace / "browser.json").write_text(
        json.dumps(
            {
                "base": base,
                "launch_url": base + "/#launch=" + app.state.sessions.issue_launch(),
                "entity_id": entity["id"],
            }
        )
    )
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
