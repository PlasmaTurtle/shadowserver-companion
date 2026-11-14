"""Process-level workspace exclusion shared by launchers and scheduled handoff."""

import os


def acquire_lock(folder, filename="workspace.lock"):
    folder.mkdir(parents=True, exist_ok=True)
    handle = (folder / filename).open("a+b")
    handle.seek(0, 2)
    if handle.tell() == 0:
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise SystemExit(
            "This workspace is already open. Use the existing window, or close its console first."
        )
    return handle
