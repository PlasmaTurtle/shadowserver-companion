"""Local product/KEV catalog and imported reports for cross-surface acceptance."""

import argparse
from io import BytesIO
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "components" / "attribution" / "src")]

import uvicorn
from workbench.api import create_app
from workbench.eclipse import Eclipse
from eclipse_browser_fixture_0981 import SyntheticRegistry
from test_catalog_outreach_0984 import PRODUCT, CRITICAL_KEV, reported_rows, seed_catalog
from test_workbench import csv_bytes, observations, record_synthetic_evaluations
from test_entity_dns_0984 import DNSFixture


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
        lookup_factory=SyntheticRegistry,
    )
    record_synthetic_evaluations(app)
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
        )
    )
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
