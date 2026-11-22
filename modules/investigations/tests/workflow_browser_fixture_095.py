"""Isolated synthetic workstation fixture for 0.9.5 workflow browser acceptance."""

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
from modules.workspace.components.api import create_app
from modules.investigations.components.cases import Cases
from modules.entities.tests.support.contacts import attributed_entity
from modules.observatory.tests.support.observations import add, base as observation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    if args.workspace.exists():
        raise SystemExit("Use a new synthetic workspace")
    args.workspace.mkdir(parents=True)
    app = create_app(args.workspace / "data", worker=False)
    store = app.state.store
    entity = attributed_entity(store)
    for day, version in (
        ("2026-11-04", "7.3.25"),
        ("2026-11-05", "7.3.25"),
        ("2026-11-06", "7.3.26"),
    ):
        add(
            store,
            observation(timestamp=day + " 01:00:00", version=version),
            filename="workflow-" + day + ".csv",
        )
    with store.transaction() as db:
        profile = store.settings()
        profile.update(analyst_name="Workflow Reviewer", watch_inbox=False)
        db.execute("UPDATE settings SET value=? WHERE key='profile'", (json.dumps(profile),))
        db.execute(
            "UPDATE leads SET company='Workflow Example (synthetic)',demo=1 WHERE id=?",
            (entity["id"],),
        )
    case = Cases(store).create(entity["id"], "Synthetic workflow verification")
    with store.transaction() as db:
        db.execute("UPDATE cases SET follow_up_date='2000-01-01' WHERE id=?", (case["case_id"],))
    port = args.port
    if not port:
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
                "entity_id": entity["id"],
                "case_id": case["case_id"],
            }
        ),
        encoding="utf-8",
    )
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
