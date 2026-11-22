"""Bounded pure-render stages; the parent owns validation and publication."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile

from .report_operations import current_operation, check_deadline, phase, ReportCancelled
from modules.workspace.helpers.installed_process import installed_child_options


MAX_RENDER_MESSAGE = 256 * 1024 * 1024


def _process_enabled():
    current = current_operation()
    return current is not None and current[0].process_rendering


def _run(kind, data, **values):
    from modules.workspace.components.compact_json import dump, loads

    check_deadline()
    manager, identifier = current_operation()
    with tempfile.TemporaryDirectory(prefix=".render-", dir=manager.folder) as directory:
        folder = Path(directory)
        job_path = folder / "job.json"
        with job_path.open("w", encoding="utf-8") as stream:
            dump({"kind": kind, "data": data, "parent_pid": os.getpid(), **values}, stream)
        check_deadline()
        if job_path.stat().st_size > MAX_RENDER_MESSAGE:
            raise ValueError(
                "Report content exceeds the renderer message size limit; no revision was published."
            )
        application_root = Path(__file__).resolve().parents[3]
        with installed_child_options(application_root) as inherited:
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(Path(__file__).with_name("report_worker.py")),
                    str(job_path),
                    str(os.getpid()),
                ],
                cwd=application_root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
                **inherited,
            )
        with manager._lock:
            manager._processes[identifier] = process
        try:
            while True:
                check_deadline()
                try:
                    code = process.wait(timeout=0.1)
                    break
                except subprocess.TimeoutExpired:
                    continue
            check_deadline()
            result_path = folder / "result.json"
            if not result_path.is_file():
                if manager._closed:
                    raise ReportCancelled(
                        "Report preparation stopped because the application is closing."
                    )
                raise ValueError(
                    "The report renderer stopped unexpectedly. Saved case data was not published; review the operation and retry."
                )
            if result_path.stat().st_size > MAX_RENDER_MESSAGE:
                raise ValueError(
                    "Report renderer output exceeds the supported size; no revision was published."
                )
            result = loads(result_path.read_bytes())
            if code or not result.get("ok"):
                category = str(result.get("error_type") or "RenderError")[:80]
                detail = str(result.get("error") or "Report rendering failed")[:2000]
                raise ValueError(f"Report renderer {category} (exit code {code}): {detail}")
            return result
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            with manager._lock:
                manager._processes.pop(identifier, None)


def prepare_pdf(data, destination, evidence_root, *, draft, fallback):
    phase("Rendering notification PDF")
    if _process_enabled():
        _run(
            "pdf", data, destination=str(destination), evidence_root=str(evidence_root), draft=draft
        )
    else:
        fallback(data, destination, evidence_root, draft=draft)
    check_deadline()


def capture_content(content, *, sections, fallback):
    phase("Preparing section artwork")
    if _process_enabled():
        result = _run("capture", content, sections=list(sections) if sections is not None else None)
        content.clear()
        content.update(result["content"])
    else:
        fallback(content, sections=sections)
    check_deadline()


def prepare_package(store, data, destination, renderers, *, fallback):
    phase("Rendering the report and supporting records")
    if _process_enabled():
        from modules.workspace.components.compact_json import loads
        from .report_package import BuiltPackage

        result = _run("package", data, destination=str(destination), evidence_root=str(store.root))
        snapshot_path = destination / "snapshot.json"
        if snapshot_path.stat().st_size > MAX_RENDER_MESSAGE:
            raise ValueError(
                "Report snapshot exceeds the supported size; no revision was published."
            )
        package = BuiltPackage(snapshot=loads(snapshot_path.read_bytes()), files=result["files"])
    else:
        package = fallback(store, data, destination, renderers)
    check_deadline()
    return package


def prepare_closing(data, destination, *, fallback):
    phase("Rendering the closing report")
    if _process_enabled():
        _run("closing", data, destination=str(destination))
    else:
        fallback(data, destination)
    check_deadline()
