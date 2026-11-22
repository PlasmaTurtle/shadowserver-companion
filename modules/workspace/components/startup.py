"""Single-workstation launcher. No Node, Word, or cloud account required."""

import argparse
import logging
import os
import threading
import webbrowser
from pathlib import Path

from .workspace_session import workspace_session


def main():
    from modules.workspace.components.release import (
        installation_identity,
        load_release,
        validate_workspace_identity,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--demo", action="store_true", help="Use a separate workspace with synthetic sample records"
    )
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--port", type=int)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--host", default="127.0.0.1", help=argparse.SUPPRESS)
    parser.add_argument("--strictPort", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    release = load_release()
    identity = installation_identity(release["edition"], release.get("variant", ""))
    if args.port is None:
        args.port = identity["demo_port" if args.demo else "port"]
    preview = os.environ.get("WORKBENCH_PREVIEW") == "1"
    if not preview and args.host != "127.0.0.1":
        parser.error("This local edition binds to 127.0.0.1 only.")
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535.")
    root = Path(__file__).resolve().parents[3]
    data = (args.data_dir or root / ("data-demo" if args.demo else "data")).resolve()
    try:
        validate_workspace_identity(
            data,
            os.environ.get("LOCALAPPDATA"),
            edition=release["edition"],
            variant=release.get("variant", ""),
        )
    except ValueError as error:
        parser.error(str(error))
    from modules.accretion.components.schedule_handoff import request_handoff

    request_handoff(data, timeout=30)
    with workspace_session(data):
        serve(args, data, preview)


def serve(args, data, preview):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from modules.workspace.components.api import create_app
    from modules.workspace.components.local_session import write_instance
    from modules.workspace.components.release import load_release
    import uvicorn

    url = f"http://127.0.0.1:{args.port}"
    application = create_app(data, demo=args.demo, preview=preview)
    launch_url = url + "/#launch=" + application.state.sessions.issue_launch()
    instance = write_instance(data, args.port, args.demo, application.state.sessions)
    release = load_release()
    if os.name == "nt":
        import ctypes

        ctypes.windll.kernel32.SetConsoleTitleW(
            f"{release['app_name']} {release['display_version']} - {'Demo' if args.demo else 'Workspace'}"
        )
    print(
        f"\n{release['app_name']} {release['display_version']}\nWorkspace: {data}\nOpen: {launch_url}\nKeep this window open. Press Ctrl+C to stop.\n",
        flush=True,
    )
    server = uvicorn.Server(
        uvicorn.Config(application, host=args.host, port=args.port, workers=1, log_config=None)
    )
    application.state.software_updates.shutdown = lambda: setattr(server, "should_exit", True)
    stopped = threading.Event()
    browser_thread = None
    if not args.no_browser:

        def open_when_ready():
            # This server owns the port only after its bind succeeds. A TCP
            # connection could instead reach an unrelated application.
            while not stopped.wait(0.1):
                if server.started and not stopped.is_set():
                    webbrowser.open(launch_url)
                    return

        browser_thread = threading.Thread(
            target=open_when_ready, name="workbench-browser", daemon=True
        )
        browser_thread.start()
    try:
        server.run()
    except SystemExit as error:
        if not server.started and error.code not in (None, 0):
            raise RuntimeError(
                f"Could not start the local server at {url}. See application.log for details."
            ) from error
        raise
    finally:
        stopped.set()
        if browser_thread is not None:
            browser_thread.join(timeout=1)
        instance.unlink(missing_ok=True)
