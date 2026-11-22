"""Local synthetic multientity source universe for Observatory browser acceptance."""

from tests.support.qualification import registry_factory, capture_website

import argparse
from io import BytesIO
import json
from pathlib import Path
import socket
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
from modules.observatory.components.eclipse import Eclipse
from tests.support.workbench import csv_bytes


from modules.observatory.tests.support.observations import DOMAINS, SyntheticRegistry


def rows():
    values = []
    places = [
        ("Charlotte", "North Carolina", 35.227, -80.843),
        ("Raleigh", "North Carolina", 35.779, -78.638),
        ("Charleston", "South Carolina", 32.783, -79.932),
        ("Greenville", "South Carolina", 34.852, -82.394),
        ("Asheville", "North Carolina", 35.595, -82.551),
        ("Wilmington", "North Carolina", 34.226, -77.945),
    ]
    for org, domain in enumerate(DOMAINS):
        city, region, lat, lon = places[org]
        for host in range(6):
            for day in range(3 + (host % 3)):
                values.append(
                    {
                        "report_type": "scan_http_vulnerable",
                        "severity": "critical",
                        "http_code": "200",
                        "hostname": f"{['mail', 'gateway', 'app', 'vpn', 'portal', 'edge'][host]}.{domain}",
                        "ip": f"8.8.{org + 1}.{host + 1}",
                        "tag": ["CVE-2021-44228", "CVE-2024-3094", "eol-openssl"][host % 3],
                        "version": ["2.14.1", "5.6.0", "1.0.2"][host % 3],
                        "product": ["Log4j", "xz", "OpenSSL"][host % 3],
                        "region": region,
                        "city": city,
                        "geo": "US",
                        "timestamp": f"2026-11-{2 + day * 2:02d} 01:02:03",
                        "protocol": "tcp",
                        "port": "443" if host % 2 else "8443",
                        "asn": str(15169 + org),
                        "latitude": lat + (host - 2) * 0.06 if host < 4 else "",
                        "longitude": lon + (host - 2) * 0.04 if host < 4 else "",
                        "source_note": "Synthetic Observatory acceptance observation",
                    }
                )
    # A factual shared source identifier across hosts, without inferred ownership.
    values.append(
        {**values[0], "hostname": "shared.harbor-energy.com", "timestamp": "2026-11-10 01:02:03"}
    )
    values.append(
        {
            **values[0],
            "hostname": "unplaced.aster-fabrication.com",
            "ip": "8.8.1.40",
            "city": "",
            "latitude": "",
            "longitude": "",
            "timestamp": "",
        }
    )
    values.append(
        {
            **values[0],
            "hostname": "escaped.aster-fabrication.com",
            "ip": "8.8.1.41",
            "source_note": '<img src=x onerror="window.eclipseInjected=true">',
            "tag": "eol-openssl",
        }
    )
    return values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--empty", action="store_true")
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

    with app.state.store.transaction() as db:
        settings = app.state.store.settings()
        settings.update(
            analyst_name="Synthetic Observatory Reviewer",
            agency="Synthetic acceptance workspace",
            office="Local fixture; no real exposure assessed",
            watch_inbox=False,
            regions=["North Carolina", "South Carolina"],
        )
        db.execute("UPDATE settings SET value=? WHERE key='profile'", (json.dumps(settings),))
    if not args.empty:
        item = app.state.intake.enqueue_stream(
            "synthetic-observatory.csv", BytesIO(csv_bytes(rows()))
        )
        app.state.intake.process(item["id"])
        entities = app.state.store.all("SELECT id,domain FROM leads WHERE merged_into IS NULL")
        if entities:
            Cases(app.state.store).create(entities[0]["id"], "Synthetic Observatory notification")
        with app.state.store.transaction() as db:
            # Saved business locations deliberately differ from some scan
            # coordinates. Two share a city, one uses its latest reported
            # city/state, and one has an unmatched saved city.
            entity_places = {
                DOMAINS[0]: ("Charlotte", "NC"),
                DOMAINS[1]: ("Charlotte", "NC"),
                DOMAINS[2]: ("Charleston", "SC"),
                DOMAINS[3]: ("Greenville", "SC"),
                DOMAINS[5]: ("Unknown City", "GA"),
            }
            for entity in entities:
                city, state = entity_places.get(entity["domain"], ("", ""))
                db.execute(
                    "INSERT OR REPLACE INTO entity_profiles VALUES(?,?)",
                    (entity["id"], json.dumps({"city": city, "state": state})),
                )
            db.execute("UPDATE leads SET demo=1")
    entity_map = Eclipse(app.state.store).view(include_undated=True)["intelligence"]["atlas"]
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", args.port))
        sock.listen()
        base = f"http://127.0.0.1:{sock.getsockname()[1]}"
        prepare_browser_fixture(app, args.workspace, base)
        (args.workspace / "browser.json").write_text(
            json.dumps(
                {
                    "base": base,
                    "launch_url": base + "/#launch=" + app.state.sessions.issue_launch(),
                    "empty": args.empty,
                    "entity_map": {
                        key: entity_map[key]
                        for key in ("total_entities", "mapped_entities", "unplaced_entities")
                    },
                }
            ),
            encoding="utf-8",
        )
        uvicorn.Server(uvicorn.Config(app, log_level="warning")).run(sockets=[sock])


if __name__ == "__main__":
    main()
