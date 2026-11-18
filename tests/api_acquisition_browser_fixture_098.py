"""Local-only synthetic API browser fixture; never uses a real account."""

import argparse
import json
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "components" / "attribution" / "src")]

import uvicorn
from workbench.api import create_app
from workbench.shadowserver_reports import ReportDownloader, SignedTransport
from workbench.shadowserver_reports.demo import _Opener, _SyntheticService


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    if args.workspace.exists():
        raise SystemExit("Use a new synthetic workspace directory")
    args.workspace.mkdir(parents=True)
    control = args.workspace / "control.json"
    control.write_text('{"mode":"normal"}')
    remote = _SyntheticService()

    class ControlledDownloader:
        def __init__(self, root):
            self.real = ReportDownloader(root, opener=_Opener(remote.download_open))

        def download_report(self, report, *, operation):
            if json.loads(control.read_text())["mode"] == "slow":
                operation.wait(8)
            return self.real.download_report(report, operation=operation)

    app = create_app(
        args.workspace / "data",
        worker=False,
        api_transport_factory=lambda provider: SignedTransport(
            provider, backend=_Opener(remote.api_open)
        ),
        api_downloader_factory=ControlledDownloader,
    )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        base = "http://127.0.0.1:" + str(sock.getsockname()[1])
        metadata = {
            "base": base,
            "launch_url": base + "/#launch=" + app.state.sessions.issue_launch(),
            "control_path": str(control),
            "api_key": remote.credentials.api_key,
            "secret": remote.credentials.secret,
        }
        (args.workspace / "browser.json").write_text(json.dumps(metadata))
        uvicorn.Server(uvicorn.Config(app, log_level="warning")).run(sockets=[sock])


if __name__ == "__main__":
    main()
