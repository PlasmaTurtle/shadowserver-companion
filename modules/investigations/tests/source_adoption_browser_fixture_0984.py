"""Synthetic full source adoption fixture with a real local NVD catalog."""

from tests.support.qualification import registry_factory, capture_website

import argparse
import gzip
import hashlib
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

from tests.session_helpers import TestClient, authenticate
from modules.library.tests.support.cve_program import kev
from modules.library.tests.support.cve_sources import ID, nvd
from tests.support.workbench import FakeRegistry, import_rows, observations, ready
from modules.workspace.components.api import create_app
from modules.library.components.cve_catalog import Catalog
from modules.library.components.cve_catalog.risk import RiskStore, EPSS_FEED, KEV_FEED


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()
    args.workspace.mkdir(parents=True, exist_ok=False)
    app = create_app(
        args.workspace / "data",
        worker=False,
        report_processes=False,
        attribution_factory=registry_factory(FakeRegistry),
        capture=capture_website,
    )

    catalog = Catalog(app.state.store.root)
    raw = nvd("Exact official local catalog wording with an integral CVSS score.")[
        "vulnerabilities"
    ][0]["cve"]
    raw["metrics"]["cvssMetricV31"][0]["cvssData"]["baseScore"] = 10.0
    source = {
        "url": "https://nvd.nist.gov/feeds/json/cve/2.0/nvdcve-2.0-2025.json.gz",
        "retrieved_at": "2026-11-10T23:00:00Z",
        "feed_sha256": "a" * 64,
    }
    with catalog.connection() as db:
        catalog.upsert(db, raw, source)
        catalog.upsert(db, {**raw, "id": "CVE-2025-98765"}, source)
    risk = RiskStore(app.state.store.root)
    epss = args.workspace / "synthetic-epss.csv.gz"
    epss.write_bytes(
        gzip.compress(
            (
                "#model_version:fixture,score_date:2026-11-10\ncve,epss,percentile\n"
                + ID
                + ",1.0,1.0\n"
            ).encode("utf-8")
        )
    )
    kev_file = args.workspace / "synthetic-kev.json"
    kev_file.write_text(json.dumps(kev()), encoding="utf-8")
    for path, url, importer in (
        (epss, EPSS_FEED, risk.import_epss),
        (kev_file, KEV_FEED, risk.import_kev),
    ):
        importer(
            path,
            {
                "source_url": url,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "last_success_at": "2026-11-10T23:00:00Z",
            },
        )
    client = authenticate(TestClient(app), app)
    import_rows(client, app, [{**observations()[0], "ip": "8.8.8.8", "tag": ID}])
    lead_id = client.get("/api/leads").json()[0]["id"]
    lead = ready(client, lead_id, validate=False)
    client.close()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        base = "http://127.0.0.1:" + str(sock.getsockname()[1])
        prepare_browser_fixture(app, args.workspace, base)
        (args.workspace / "browser.json").write_text(
            json.dumps(
                {
                    "base": base,
                    "launch_url": base + "/#launch=" + app.state.sessions.issue_launch(),
                    "case_id": lead["case_id"],
                }
            ),
            encoding="utf-8",
        )
        uvicorn.Server(uvicorn.Config(app, log_level="warning")).run(sockets=[sock])


if __name__ == "__main__":
    main()
