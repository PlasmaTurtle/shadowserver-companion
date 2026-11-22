"""Local product/KEV catalog and imported reports for cross-surface acceptance."""

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
from modules.observatory.components.eclipse import Eclipse
from modules.observatory.tests.support.observations import SyntheticRegistry
from modules.library.tests.support.catalog_outreach import (
    PRODUCT,
    CRITICAL_KEV,
    reported_rows,
    seed_catalog,
)
from tests.support.workbench import csv_bytes, observations
from modules.entities.tests.support.entity_dns import DNSFixture


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8966)
    args = parser.parse_args()
    if args.workspace.exists():
        raise SystemExit("Use a fresh synthetic workspace")
    args.workspace.mkdir(parents=True)
    app = create_app(
        args.workspace / "data",
        worker=False,
        report_processes=False,
        attribution_factory=registry_factory(SyntheticRegistry),
        capture=capture_website,
    )

    app.state.entity_dns.provider_factory = DNSFixture().factory
    with app.state.store.transaction() as db:
        profile = app.state.store.settings()
        profile.update(analyst_name="Synthetic catalog reviewer", watch_inbox=False)
        db.execute("UPDATE settings SET value=? WHERE key='profile'", (json.dumps(profile),))
    seed_catalog(app.state.store.root, args.workspace)
    rows = []
    for index, row in enumerate(reported_rows()):
        other_entity = row["entity_id"] == "entity-beta"
        domain = "meridian-care.com" if other_entity else "aster-fabrication.com"
        host = "mail" if index < 3 else row["id"]
        rows.append(
            {
                **observations()[0],
                "hostname": host + "." + domain,
                "ip": "8.8.2.1" if other_entity else "8.8.1.1",
                "tag": row["tag"],
                "product": row["product"],
                "version": row["version"],
                "timestamp": row["observed_day"] + " 12:00:00",
                "latitude": 35.227,
                "longitude": -80.843,
                "source_note": "Synthetic local catalog integration acceptance",
            }
        )
    item = app.state.intake.enqueue_stream("catalog-observations.csv", BytesIO(csv_bytes(rows)))
    app.state.intake.process(item["id"])
    snapshot = Eclipse(app.state.store).snapshot(product_id=PRODUCT)
    base = f"http://127.0.0.1:{args.port}"
    prepare_browser_fixture(app, args.workspace, base)
    (args.workspace / "browser.json").write_text(
        json.dumps(
            {
                "base": base,
                "launch_url": base + "/#launch=" + app.state.sessions.issue_launch(),
                "product_id": PRODUCT,
                "cve_id": CRITICAL_KEV,
                "rows": len(rows),
                "snapshot": snapshot,
            }
        ),
        encoding="utf-8",
    )
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
