"""Fresh local setup fixture with synthetic credentials and jurisdiction choices.

Never contacts an account or installs software. Metadata is written only inside
an explicitly new synthetic workspace and contains deliberately nonfunctional
credentials for browser acceptance.
"""

import argparse
import json
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "components" / "attribution" / "src")]

import uvicorn
from workbench.api import create_app
from workbench.shadowserver_reports import SignedTransport
from workbench.shadowserver_reports.demo import _Opener, _Response, _SyntheticService


class SetupService(_SyntheticService):
    """The real signer/client sees state, national and unclassified selections."""

    def api_open(self, request, timeout):
        response = super().api_open(request, timeout)
        endpoint = request.full_url.removeprefix("https://transform.shadowserver.org/api2/")
        if endpoint == "reports/subscribed":
            return _Response(
                json.dumps(["US-NC", "US-SC", "united-states", "agency-custom"]).encode(),
                "application/json",
            )
        if endpoint == "reports/list":
            rows = json.loads(response.read())
            for row in rows:
                row["report"] = "US-NC"
                row["file"] = "2026-11-06-US-NC-scan_http_vulnerable.csv"
            return _Response(json.dumps(rows).encode(), "application/json")
        return response


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    if args.workspace.exists():
        raise SystemExit("Use a new synthetic workspace directory")
    args.workspace.mkdir(parents=True)
    service = SetupService()
    app = create_app(
        args.workspace / "data",
        worker=False,
        report_processes=False,
        api_transport_factory=lambda provider: SignedTransport(
            provider, backend=_Opener(service.api_open)
        ),
    )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        base = "http://127.0.0.1:" + str(sock.getsockname()[1])
        metadata = {
            "base": base,
            "launch_url": base + "/#launch=" + app.state.sessions.issue_launch(),
            "api_key": service.credentials.api_key,
            "secret": service.credentials.secret,
            "mode": "synthetic-setup-acceptance",
        }
        (args.workspace / "browser.json").write_text(json.dumps(metadata), encoding="utf-8")
        uvicorn.Server(uvicorn.Config(app, log_level="warning")).run(sockets=[sock])


if __name__ == "__main__":
    main()
