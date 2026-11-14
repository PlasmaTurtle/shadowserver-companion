"""Isolated synthetic workstation fixture for 0.9.5 workflow browser acceptance."""

import argparse
import json
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "components" / "attribution" / "src")]

import uvicorn
from workbench.api import create_app
from workbench.cases import Cases
from workbench.primitives import uid
from test_contacts_invariants_090 import attributed_entity


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
    with store.transaction() as db:
        original = dict(db.execute("SELECT * FROM entries LIMIT 1").fetchone())
        for index, (day, version) in enumerate(
            (("2026-11-04", "7.3.25"), ("2026-11-05", "7.3.25"), ("2026-11-06", "7.4.0"))
        ):
            values = dict(original)
            values["observed_at"] = day + "T01:00:00Z"
            values["version"] = version
            payload = json.loads(values["payload"])
            payload["version"] = version
            payload["source"]["fields"].update(
                timestamp=values["observed_at"], version=version, severity="critical"
            )
            values["payload"] = json.dumps(payload)
            if index == 0:
                db.execute(
                    "UPDATE entries SET observed_at=?,version=?,payload=? WHERE id=?",
                    (values["observed_at"], version, values["payload"], values["id"]),
                )
            else:
                values["id"] = uid()
                db.execute(
                    "INSERT INTO entries("
                    + ",".join(values)
                    + ") VALUES("
                    + ",".join("?" for _ in values)
                    + ")",
                    tuple(values.values()),
                )
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
    (args.workspace / "browser.json").write_text(
        json.dumps(
            {
                "base": base,
                "launch_url": base + "/#launch=" + app.state.sessions.issue_launch(),
                "entity_id": entity["id"],
                "case_id": case["case_id"],
            }
        )
    )
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
