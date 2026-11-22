"""Private pure-render subprocess; never publishes reports or writes case records."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import threading

# Executed by absolute script path, including the embedded Windows interpreter.
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
ATTRIBUTION = ROOT / "modules/attribution/components/engine/src"
if str(ATTRIBUTION) not in sys.path:
    sys.path.insert(0, str(ATTRIBUTION))


def watch_parent(parent_pid):
    """Stop an orphan renderer even when the parent is forcibly terminated."""
    if os.name == "nt":
        import ctypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = (ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_ulong)
        kernel.WaitForSingleObject.restype = ctypes.c_ulong
        kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
        handle = kernel.OpenProcess(0x00100000, False, parent_pid)
        if not handle:
            os._exit(70)
        try:
            # WAIT_OBJECT_0 means the original process handle was signalled;
            # unlike repeated PID checks, handle identity survives PID reuse.
            if kernel.WaitForSingleObject(handle, 0xFFFFFFFF) != 0x00000102:
                os._exit(70)
        finally:
            kernel.CloseHandle(handle)
    else:
        stopper = threading.Event()
        while not stopper.wait(0.25):
            if os.getppid() != parent_pid:
                os._exit(70)


class RenderWorkspace:
    """Only the file access surface required by package assembly; no database."""

    def __init__(self, root):
        self.root = Path(root).resolve()

    def path(self, relative):
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Invalid workspace path")
        return path


def execute(job_path, parent_pid):
    job_path = Path(job_path)
    result_path = job_path.parent / "result.json"
    try:
        threading.Thread(target=watch_parent, args=(parent_pid,), daemon=True).start()
        from modules.workspace.components.compact_json import loads, dump
        from modules.investigations.components.report_execution import MAX_RENDER_MESSAGE

        if job_path.stat().st_size > MAX_RENDER_MESSAGE:
            raise ValueError("Report renderer input exceeds the supported size")
        job = loads(job_path.read_bytes())
        if job["parent_pid"] != parent_pid:
            raise ValueError("Renderer parent identity mismatch")
        kind = job["kind"]
        data = job["data"]
        if kind == "capture":
            from modules.ui.components.exhibit_rendering import capture_exhibit_masters

            capture_exhibit_masters(data, sections=job["sections"])
            result = {"ok": True, "content": data}
        elif kind == "pdf":
            from modules.investigations.components.report_renderers import render_pdf

            render_pdf(
                data, Path(job["destination"]), Path(job["evidence_root"]), draft=job["draft"]
            )
            result = {"ok": True}
        elif kind == "closing":
            from modules.investigations.components.closing import render_closing

            render_closing(data, Path(job["destination"]))
            result = {"ok": True}
        elif kind == "package":
            from modules.investigations.components.report_package import (
                assemble_package,
                PackageRenderers,
            )
            from modules.investigations.components.report_renderers import render_pdf, render_docx

            package = assemble_package(
                RenderWorkspace(job["evidence_root"]),
                data,
                Path(job["destination"]),
                PackageRenderers(pdf=render_pdf, docx=render_docx),
            )
            result = {"ok": True, "files": package.files}
        else:
            raise ValueError("Unknown report rendering task")
        with result_path.open("w", encoding="utf-8") as stream:
            dump(result, stream)
        return 0
    except Exception as error:
        # Initialization and decoding fail through the same bounded result as
        # rendering. No full models, credentials or traceback locals are emitted.
        result_path.write_text(
            json.dumps(
                {
                    "ok": False,
                    "error": str(error)[:2000],
                    "error_type": type(error).__name__,
                }
            ),
            encoding="utf-8",
        )
        return 1


if __name__ == "__main__":
    # Accept the previous private two-argument launcher as well. This protects
    # an already-running parent during developer hot reloads; installed updates
    # still require the application to be stopped before replacing its files.
    parent_pid = int(sys.argv[2]) if len(sys.argv) > 2 else os.getppid()
    raise SystemExit(execute(sys.argv[1], parent_pid))
