"""Run due workspace schedules without opening a browser or exposing a server."""

import argparse
import logging
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from modules.workspace.components.runtime_logging import (
    configure_runtime_logging,
    log_failure,
    safe_write,
    windowless_streams,
)

LOG = logging.getLogger("workbench.scheduled_runner")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--remove-task", action="store_true")
    args = parser.parse_args(argv)
    # Configure before release validation, imports, locking, or opening a Store:
    # these failures happen before a schedule job can record an error itself.
    configure_runtime_logging(args.data_dir, name="scheduled", console=False)
    LOG.info("Preparing saved workspace schedules")
    if args.remove_task:
        from modules.accretion.components.windows_schedule import configure

        configure(args.data_dir, False)
        LOG.info("Saved workspace scheduled task removed")
        return 0
    from modules.workspace.components.workspace_session import workspace_session
    from modules.workspace.components.release import load_release, validate_workspace_identity
    import os

    release = load_release()
    validate_workspace_identity(
        args.data_dir.resolve(),
        os.environ.get("LOCALAPPDATA"),
        edition=release["edition"],
        variant=release.get("variant", ""),
    )
    # Keep the install guard alive while this process uses installed code.
    if os.name == "nt":
        sys.path.insert(0, str(ROOT / "tools" / "windows_installer"))
        from desktop import hold_installation_mutex

        hold_installation_mutex()
    try:
        with workspace_session(args.data_dir.resolve()):
            LOG.info("Workspace ownership acquired; checking due work")
            return run(args.data_dir.resolve())
    except SystemExit as error:
        if "already open" in str(error):
            # The interactive backend's own scheduler handles this workspace.
            LOG.info("Workspace already owned; scheduled runner yielded without opening it")
            return 0
        raise


def run(root):
    from modules.accretion.components.api_acquisition import APIAcquisition
    from modules.library.components.cve_catalog import Catalog, CatalogManager
    from modules.library.components.cve_catalog.risk import RiskStore
    from modules.library.components.cve_catalog.risk_manager import RiskManager
    from modules.accretion.components.intake_service import IntakeService
    from modules.accretion.components.scheduling import AcquisitionSchedule
    from modules.workspace.components.store import Store
    from contextlib import ExitStack
    from modules.workspace.components.workspace_data import before_schema_upgrade
    from modules.workspace.databases.migrations import SCHEMA_VERSION
    import sqlite3
    from contextlib import closing

    if (root / "workbench.sqlite3").is_file():
        with closing(sqlite3.connect(root / "workbench.sqlite3")) as db:
            prior = db.execute("PRAGMA user_version").fetchone()[0]
        before_schema_upgrade(root, prior, SCHEMA_VERSION)
    store = Store(root)
    intake = IntakeService(store)
    catalog = CatalogManager(Catalog(root), risk=RiskManager(RiskStore(root)))
    acquisition = APIAcquisition(store, intake)
    schedule = AcquisitionSchedule(store, acquisition, catalog)
    from modules.accretion.components.schedule_handoff import scheduled_ownership

    with scheduled_ownership(root, schedule.stop_event):
        try:
            with ExitStack() as cleanup:
                for service in (catalog, intake, acquisition, schedule):
                    cleanup.callback(service.close)
                intake.start()
                schedule.tick()
                deadline = time.monotonic() + 5 * 3600
                while (
                    schedule.busy()
                    and not schedule.stop_event.is_set()
                    and time.monotonic() < deadline
                ):
                    time.sleep(1)
                    schedule.tick()
                return 0 if not schedule.busy() else 2
        finally:
            # Desktop close is intentionally bounded, but this headless owner
            # MUST retain the workspace lock until every writer has stopped.
            # Their transport deadlines bound cancellation; foreground handoff
            # may time out rather than opening a concurrently written workspace.
            for service in (schedule, intake, catalog, catalog.risk):
                for name in ("thread", "worker", "index_worker", "scheduler"):
                    worker = getattr(service, name, None)
                    if worker is not None:
                        worker.join()


def entrypoint(argv=None):
    """Headless launch boundary: persistent errors, safe streams and exit codes."""
    try:
        # Argument parsing can fail before the workspace is known. Keep those
        # diagnostics in a per-user bootstrap log rather than pythonw's absent
        # stderr. Incidental stdout is discarded, never redirected into a file.
        configure_runtime_logging(name="scheduled", console=False)
        LOG.info("Scheduled runner starting")
        with windowless_streams():
            result = main(argv)
        result = 0 if result is None else result
        if result:
            LOG.warning("Scheduled runner did not finish all work (exit status %s)", result)
        else:
            LOG.info("Scheduled runner finished")
        return result
    except KeyboardInterrupt:
        LOG.warning("Scheduled runner interrupted")
        return 130
    except SystemExit as error:
        code = error.code if isinstance(error.code, int) else 0 if error.code is None else 1
        if code:
            log_failure(
                LOG, f"Scheduled runner stopped before completion (exit status {code})", error
            )
        return code
    except Exception as error:
        log_failure(LOG, "Scheduled runner failed before completion", error)
        safe_write(
            sys.stderr, "Scheduled work could not complete. See scheduled.log for details.\n"
        )
        return 1
    finally:
        for handler in logging.getLogger().handlers:
            try:
                handler.flush()
            except (OSError, ValueError):
                pass


if __name__ == "__main__":
    raise SystemExit(entrypoint())
