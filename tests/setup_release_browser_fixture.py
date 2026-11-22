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
sys.path[:0] = [str(ROOT)]

from tests.fixture_paths import configure_fixture_imports

configure_fixture_imports(ROOT)

from tests.browser_fixture_support import configure_browser_fixture, prepare_browser_fixture

configure_browser_fixture()

import uvicorn
from modules.workspace.components.api import create_app
from modules.accretion.components.shadowserver_reports import SignedTransport
from modules.accretion.components.shadowserver_reports.demo import _Opener


from modules.settings.tests.support.setup import SetupService


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
        prepare_browser_fixture(app, args.workspace, base, established=False)
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
