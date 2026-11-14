"""Explicit synthetic ready-to-freeze document workbench; no external acquisition."""

import argparse
import json
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "components" / "attribution" / "src")]

import uvicorn
from session_helpers import TestClient, authenticate
from test_section_validation_050 import prepared
from test_workbench import app as application_fixture


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()
    if args.workspace.exists():
        raise SystemExit("Use a new synthetic workspace")
    args.workspace.mkdir(parents=True)
    app = application_fixture.__wrapped__(args.workspace)
    client = authenticate(TestClient(app), app)
    try:
        lead = prepared(client, app, validate=False)
    finally:
        client.close()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    (args.workspace / "browser.json").write_text(
        json.dumps(
            {
                "base": base,
                "launch_url": base + "/#launch=" + app.state.sessions.issue_launch(),
                "entity_id": lead["id"],
                "case_id": lead["case_id"],
            }
        )
    )
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
