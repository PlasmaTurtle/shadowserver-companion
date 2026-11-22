"""Explicit synthetic ready-to-freeze document workbench; no external acquisition."""

import argparse
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
from modules.investigations.tests.support.section_reviews import prepared
from tests.support.workbench import app as application_fixture
from tests.support.workbench import resolve_observation_scope


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
        lead = resolve_observation_scope(client, lead)
        assert all(section["can_validate"] for section in lead["section_reviews"])
    finally:
        client.close()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    prepare_browser_fixture(app, args.workspace, base)
    (args.workspace / "browser.json").write_text(
        json.dumps(
            {
                "base": base,
                "launch_url": base + "/#launch=" + app.state.sessions.issue_launch(),
                "entity_id": lead["id"],
                "case_id": lead["case_id"],
            }
        ),
        encoding="utf-8",
    )
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
