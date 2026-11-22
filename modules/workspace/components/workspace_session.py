"""Exclusive workspace lifetime and pending replacement for application callers."""

from contextlib import contextmanager

from .workspace_lock import acquire_lock


@contextmanager
def workspace_session(data):
    """Keep a stable process lock while replacing a closed workspace on startup."""
    guard = acquire_lock(data.parent, "." + data.name + "-companion.lock")
    legacy = None
    try:
        # Refuse to replace data used by an older release. Close the probe before
        # renaming: Windows cannot move folders containing these open handles.
        if (data / "workspace.lock").exists():
            probe = acquire_lock(data)
            probe.close()
        from .workspace_data import apply_pending_workspace
        from .workspace_recovery import guard_interrupted_recovery

        guard_interrupted_recovery(data)
        apply_pending_workspace(data)
        # Older releases still see the legacy lock throughout normal operation.
        legacy = acquire_lock(data)
        yield
    finally:
        if legacy is not None:
            legacy.close()
        guard.close()
