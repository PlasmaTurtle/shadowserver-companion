"""Isolated Field browser universe: 96 entities, history, dark rows and dense assets.

All data and registration responses are synthetic. No external lookup is made.
Run with a fresh --workspace; browser.json contains its one-use local launch URL.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "components" / "attribution" / "src")]

import uvicorn
from excel_intake import WhoisRecord
from workbench.api import create_app
from workbench.cases import Cases
from workbench.eclipse import Eclipse
from workbench.primitives import now
from test_workbench import csv_bytes, record_synthetic_evaluations

DOMAINS = [f"lab-{index:03d}-eclipse-qa.org" for index in range(96)]
PLACES = [
    ("Charlotte", 35.227, -80.843),
    ("Raleigh", 35.779, -78.638),
    ("Asheville", 35.595, -82.551),
    ("Wilmington", 34.226, -77.945),
]


class SyntheticRegistry:
    def lookup(self, address):
        index = int(address.split(".")[2]) - 1
        return WhoisRecord(
            address,
            "TEST REGISTRY",
            "https://example.test/synthetic-registration",
            now(),
            {
                "contact": "security@" + DOMAINS[index],
                "startAddress": address,
                "endAddress": address,
                "notice": "Synthetic local Field fixture; no external request.",
            },
        )

    def close(self):
        pass


def rows(anchor):
    result = []
    for index, domain in enumerate(DOMAINS):
        city, lat, lon = PLACES[index % len(PLACES)]
        count = {0: 270, 1: 1001, 2: 201, 3: 51}.get(index, 2)
        observed = anchor - timedelta(days=index if index != 1 else 60)
        for sample in range(count):
            host = sample if index == 0 else sample % 2
            result.append(
                {
                    "report_type": "scan_http_vulnerable",
                    "severity": "critical",
                    "http_code": "200",
                    "hostname": f"asset-{host:03d}.{domain}",
                    "ip": f"8.8.{index + 1}.{host % 240 + 1}",
                    "tag": "eol-php" if index % 3 else "eol-openssl",
                    "version": "7.3.25" if index % 3 else "1.0.2",
                    "product": "PHP" if index % 3 else "OpenSSL",
                    "region": "North Carolina",
                    "city": city if index != 4 else "",
                    "geo": "US",
                    "timestamp": (observed + timedelta(minutes=sample)).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "protocol": "tcp",
                    "port": "443",
                    "asn": str(64512 + index),
                    "latitude": lat if index != 4 else "",
                    "longitude": lon if index != 4 else "",
                    "source_note": "Synthetic local Field browser verification",
                }
            )
        # Keep unadmitted evidence attached to a known organization without
        # claiming that a rejected source row became a validated finding.
        if index % 8 == 0:
            result.append(
                {
                    **result[-1],
                    "hostname": "unqualified." + domain,
                    "version": "",
                    "timestamp": observed.strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
    return result


def serve(app, args, summary):
    base = f"http://127.0.0.1:{args.port}"
    (args.workspace / "browser.json").write_text(
        json.dumps(
            {
                "base": base,
                "launch_url": base + "/#launch=" + app.state.sessions.issue_launch(),
                **summary,
            }
        )
    )
    print(
        json.dumps(
            {
                "workspace": str(args.workspace),
                "entities": summary["entities"],
                "source_rows": summary["source_rows"],
            }
        ),
        flush=True,
    )
    if not args.prepare_only:
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8981)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--serve-existing", action="store_true")
    args = parser.parse_args()
    if args.serve_existing:
        if not (args.workspace / "fixture-summary.json").is_file():
            raise SystemExit("Only a previously generated synthetic Field fixture can be served")
        app = create_app(args.workspace / "data", worker=False, report_processes=False)
        if app.state.store.one("SELECT count(*) n FROM leads WHERE demo<>1")["n"]:
            raise SystemExit("Refusing a workspace containing non-demonstration entities")
        summary = json.loads((args.workspace / "fixture-summary.json").read_text())
        field = Eclipse(app.state.store).view(field_only=True, lens="organization", field_limit=24)
        summary.update(
            counts=field["snapshot"]["counts"],
            field=field["intelligence"]["field"],
            limits=field["intelligence"]["graph"]["limits"],
        )
        (args.workspace / "fixture-summary.json").write_text(json.dumps(summary, indent=2))
        serve(app, args, summary)
        return
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
    anchor = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    with app.state.store.transaction() as db:
        settings = app.state.store.settings()
        settings.update(
            analyst_name="Field Browser QA", watch_inbox=False, regions=["North Carolina"]
        )
        db.execute("UPDATE settings SET value=? WHERE key='profile'", (json.dumps(settings),))
    report = rows(anchor)
    imported = app.state.intake.enqueue_stream("synthetic-field.csv", BytesIO(csv_bytes(report)))
    app.state.intake.process(imported["id"])
    state = app.state.store.one("SELECT status,error FROM imports WHERE id=?", (imported["id"],))
    if state["status"] != "done":
        raise RuntimeError(state["error"] or state["status"])
    with app.state.store.transaction() as db:
        for entity in db.execute("SELECT id,domain FROM leads").fetchall():
            index = DOMAINS.index(entity["domain"])
            label = ["Aster Health", "Northline Logistics", "Cedar Research", "Harbor Energy"][
                index % 4
            ]
            db.execute(
                "UPDATE leads SET company=?,demo=1 WHERE id=?",
                (f"{label} {index + 1:02d}", entity["id"]),
            )
            # Seed simulated prior processing dates after the actual intake.
            # Otherwise every intentionally rejected row looks newly discovered
            # at fixture startup, hiding the old/new contrast this QA needs.
            stamp = (anchor - timedelta(days=index if index != 1 else 60)).isoformat()
            db.execute(
                "UPDATE awareness_findings SET changed_at=?,created_at=? WHERE asset_id IN "
                "(SELECT id FROM awareness_assets WHERE entity_id=?)",
                (stamp, stamp, entity["id"]),
            )
    entities = app.state.store.all("SELECT id FROM leads ORDER BY domain")
    if len(entities) != 96:
        raise RuntimeError(f"Expected 96 fixture entities, found {len(entities)}")
    Cases(app.state.store).create(entities[0]["id"], "Field QA active investigation")
    field = Eclipse(app.state.store).view(field_only=True, lens="organization", field_limit=24)
    summary = {
        "entities": len(entities),
        "source_rows": len(report),
        "counts": field["snapshot"]["counts"],
        "field": field["intelligence"]["field"],
        "limits": field["intelligence"]["graph"]["limits"],
    }
    if summary["field"]["total_objects"] != 96:
        raise RuntimeError("Field fixture must expose 96 organization objects")
    (args.workspace / "fixture-summary.json").write_text(json.dumps(summary, indent=2))
    serve(app, args, summary)


if __name__ == "__main__":
    main()
