"""Keep installed runtime ownership across Python child creation and parent death."""

from contextlib import contextmanager
import ctypes
import os
from pathlib import Path
import subprocess
import sys


@contextmanager
def installed_child_options(application_root):
    """Inherit only the running guard; source-checkout children need no guard.

    The installed parent is already registered before it starts workers. Open a
    temporary duplicate for CreateProcess, and let the child retain its own copy
    from process creation through interpreter teardown. This also protects the
    worker's imports if the parent dies before its Python watcher starts.
    """
    root = Path(application_root).resolve()
    if os.name != "nt" or Path(sys.executable).resolve().parent != root.parent / "runtime":
        yield {}
        return

    from modules.workspace.components.release import installation_identity, load_release

    release = load_release(root)
    identity = installation_identity(release["edition"], release.get("variant", ""))
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenMutexW.argtypes = (ctypes.c_ulong, ctypes.c_int, ctypes.c_wchar_p)
    kernel.OpenMutexW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
    kernel.CloseHandle.restype = ctypes.c_int
    handle = kernel.OpenMutexW(0x00100000, True, identity["running_mutex"])
    if not handle:
        raise RuntimeError("Installed worker could not inherit the running installation guard")
    try:
        startup = subprocess.STARTUPINFO()
        startup.lpAttributeList = {"handle_list": [handle]}
        yield {"startupinfo": startup, "close_fds": True}
    finally:
        kernel.CloseHandle(handle)
