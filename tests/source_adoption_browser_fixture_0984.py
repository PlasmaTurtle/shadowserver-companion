"""Synthetic full source adoption fixture with a real local NVD catalog."""

import argparse
import json
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "components" / "attribution" / "src")]

import uvicorn

from session_helpers import TestClient, authenticate
from test_070_intelligence import kev, program
from test_cve_sources_040 import ID, nvd, response
from test_workbench import (
    FakeRegistry,
    import_rows,
    observations,
    ready,
    record_synthetic_evaluations,
)
from workbench.api import create_app
from workbench.cve_catalog import Catalog
from workbench.intelligence import acquisition


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()
    args.workspace.mkdir(parents=True, exist_ok=False)
    calls = []

    def fixture_provider(url, **kwargs):
        calls.append(url)
        (args.workspace / "provider-calls.json").write_text(json.dumps(calls))
        if "mitre.org" in url:
            return response(program())
        if "first.org" in url:
            return response(
                {
                    "status": "OK",
                    "data": [{"cve": ID, "epss": "1.0", "percentile": "1.0", "date": "2026-11-10"}],
                }
            )
        if url == acquisition.KEV_URL:
            return response(kev())
        raise AssertionError("Unexpected external provider destination: " + url)

    acquisition._response_get = fixture_provider
    app = create_app(
        args.workspace / "data",
        worker=False,
        report_processes=False,
        lookup_factory=FakeRegistry,
    )
    record_synthetic_evaluations(app)
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
    client = authenticate(TestClient(app), app)
    import_rows(client, app, [{**observations()[0], "ip": "8.8.8.8", "tag": ID}])
    lead_id = client.get("/api/leads").json()[0]["id"]
    lead = ready(client, lead_id, validate=False)
    client.close()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        base = "http://127.0.0.1:" + str(sock.getsockname()[1])
        (args.workspace / "browser.json").write_text(
            json.dumps(
                {
                    "base": base,
                    "launch_url": base + "/#launch=" + app.state.sessions.issue_launch(),
                    "case_id": lead["case_id"],
                }
            )
        )
        uvicorn.Server(uvicorn.Config(app, log_level="warning")).run(sockets=[sock])


if __name__ == "__main__":
    main()
