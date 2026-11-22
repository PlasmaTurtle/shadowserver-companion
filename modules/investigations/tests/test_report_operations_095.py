"""Durable status, renderer termination, cancellation and atomic publication."""

from tests.filesystem_helpers import create_test_symlink

from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
from threading import Event, Thread
from zipfile import ZipFile

import pytest
from fastapi import HTTPException

from tests.support.workbench import app, client, import_rows, ready
from modules.investigations.components.report_operations import (
    ReportOperations,
    ReportCancelled,
    ReportTimedOut,
    check_deadline,
    publication,
)
from modules.investigations.components.report_execution import prepare_pdf


def test_durable_history_and_global_report_admission(tmp_path):
    operations = ReportOperations(tmp_path)
    with operations.run("one", "preview") as identifier:
        assert operations.get(identifier)["cancellable"]
        with pytest.raises(HTTPException, match="already running"):
            with operations.run("different-case", "certification"):
                pytest.fail("A second heavy render was admitted")
    assert not operations.busy()
    reopened = ReportOperations(tmp_path)
    assert reopened.get(identifier)["state"] == "completed"
    assert reopened.get(identifier)["finished_at"]
    assert not reopened.get(identifier)["cancellable"]


def test_restart_marks_unfinished_work_without_assuming_no_commit(tmp_path):
    folder = tmp_path / "operations"
    folder.mkdir()
    (folder / "reports.json").write_text(
        json.dumps(
            {
                "format": 1,
                "operations": [
                    {
                        "id": "crashed",
                        "case_id": "case",
                        "operation": "certification",
                        "state": "committing",
                        "started_at": "2026-11-08T12:00:00+00:00",
                    }
                ],
            }
        )
    )
    operations = ReportOperations(tmp_path)
    record = operations.get("crashed")
    assert record["state"] == "interrupted"
    assert "completion is not assumed" in record["error"]
    assert not operations.busy()


def test_cancellation_stops_before_publication(tmp_path):
    operations = ReportOperations(tmp_path)
    published = []
    with pytest.raises(ReportCancelled):
        with operations.run("case", "certification") as identifier:
            operations.cancel(identifier)
            with publication():
                published.append(True)
    assert not published
    assert operations.get(identifier)["state"] == "cancelled"
    with operations.run("case", "retry after explicit review"):
        pass


def test_publication_refuses_late_cancellation(tmp_path):
    operations = ReportOperations(tmp_path)
    with operations.run("case", "certification") as identifier:
        with publication():
            assert operations.get(identifier)["state"] == "committing"
            with pytest.raises(HTTPException, match="already being saved"):
                operations.cancel(identifier)
            check_deadline()
    assert operations.get(identifier)["state"] == "completed"


def _shared_render(kind):
    from modules.ui.components.exhibit_rendering import png, svg
    from modules.ui.components.vector_layout import ExhibitPage, _wrap

    if kind == "layout":
        return _wrap("retained text", 100)
    page = ExhibitPage("example", 1, 80, 80, [], "Synthetic empty page")
    return {"svg": svg, "png": png}[kind](page)


@pytest.mark.parametrize("kind", ["layout", "svg", "png"])
@pytest.mark.parametrize("stop", ["cancelled", "timed_out"])
def test_shared_rendering_obeys_operation_control_and_releases_it(tmp_path, kind, stop):
    operations = ReportOperations(tmp_path, process_rendering=False)
    error = ReportCancelled if stop == "cancelled" else ReportTimedOut
    with pytest.raises(error):
        with operations.run(
            "case", "preview", timeout=-1 if stop == "timed_out" else None
        ) as identifier:
            if stop == "cancelled":
                operations.cancel(identifier)
            _shared_render(kind)
            pytest.fail("Shared rendering ignored the operation's stop condition")
    assert operations.get(identifier)["state"] == stop
    assert not operations.busy()
    assert _shared_render(kind), "A completed operation leaked its rendering checkpoint"


@pytest.mark.parametrize("kind", ["layout", "svg", "png"])
def test_shared_rendering_preserves_publication_boundary(monkeypatch, tmp_path, kind):
    from modules.investigations.components import report_operations

    clock = [100.0]
    monkeypatch.setattr(report_operations, "monotonic", lambda: clock[0])
    operations = ReportOperations(tmp_path, process_rendering=False)
    with operations.run("case", "certification", timeout=10) as identifier:
        with publication():
            clock[0] += 20
            with pytest.raises(HTTPException, match="already being saved"):
                operations.cancel(identifier)
            assert _shared_render(kind)
    assert operations.get(identifier)["state"] == "completed"
    assert not operations.busy()


def sleeping_renderer(monkeypatch):
    from modules.investigations.components import report_execution

    real_popen = subprocess.Popen
    children = []
    launched = Event()

    def launch(_args, **kwargs):
        child = real_popen([sys.executable, "-c", "import time; time.sleep(60)"], **kwargs)
        children.append(child)
        launched.set()
        return child

    monkeypatch.setattr(report_execution.subprocess, "Popen", launch)
    return children, launched


def test_deadline_kills_noncooperative_renderer(monkeypatch, tmp_path):
    children, launched = sleeping_renderer(monkeypatch)
    operations = ReportOperations(tmp_path)
    with pytest.raises(ReportTimedOut, match="time limit"):
        with operations.run("case", "preview", timeout=0.35) as identifier:
            prepare_pdf({}, tmp_path / "preview.pdf", tmp_path, draft=True, fallback=None)
    assert launched.is_set()
    assert all(child.poll() is not None for child in children)
    assert operations.get(identifier)["state"] == "timed_out"
    assert not list((tmp_path / "operations").glob(".render-*"))


def test_cancellation_kills_noncooperative_renderer(monkeypatch, tmp_path):
    children, launched = sleeping_renderer(monkeypatch)
    operations = ReportOperations(tmp_path)
    failures = []

    def render():
        try:
            with operations.run("case", "preview"):
                prepare_pdf({}, tmp_path / "preview.pdf", tmp_path, draft=True, fallback=None)
        except ReportCancelled as error:
            failures.append(error)

    thread = Thread(target=render)
    thread.start()
    assert launched.wait(5)
    identifier = operations.list()[0]["id"]
    operations.cancel(identifier)
    thread.join(5)
    assert not thread.is_alive()
    assert failures and all(child.poll() is not None for child in children)
    assert operations.get(identifier)["state"] == "cancelled"


def test_operation_status_and_cancel_api(client, app):
    operations = app.state.report_operations
    with pytest.raises(ReportCancelled), operations.run("case", "preview") as identifier:
        result = client.get("/api/report-operations?case_id=case").json()
        assert result["operations"][0]["id"] == identifier
        assert (
            client.post(f"/api/report-operations/{identifier}/cancel", json={}).status_code == 200
        )
        assert client.get(f"/api/report-operations/{identifier}").json()["state"] == "cancelling"
    assert client.get("/api/report-operations?case_id=other").json()["operations"] == []
    assert client.get("/api/report-operations/absent").status_code == 404


def test_real_child_preview_capture_and_package_publication(client, app):
    import_rows(client, app)
    lead = client.get("/api/leads").json()[0]
    lead = ready(client, lead["id"], validate=False)
    operations = app.state.report_operations
    operations.process_rendering = True
    # Actual child imports and rendering, using the same executable and absolute
    # script bootstrap used by the installed Windows edition.
    preview = client.get(f"/api/leads/{lead['id']}/preview.pdf?case_id={lead['case_id']}")
    assert preview.status_code == 200, preview.text
    assert preview.content.startswith(b"%PDF")
    captured = client.post(
        f"/api/cases/{lead['case_id']}/sections/closing/validate",
        json={"expected_revision": lead["draft_revision"]},
    )
    assert captured.status_code == 200, captured.text
    assert (
        next(row for row in captured.json()["section_reviews"] if row["key"] == "closing")["status"]
        == "validated"
    )
    # Finish all remaining reviewed sections, then package through the child;
    # publication and database state transitions still occur in the parent.
    from tests.support.workbench import validate_sections

    lead = validate_sections(client, captured.json())
    response = client.post(f"/api/leads/{lead['id']}/finalize?case_id={lead['case_id']}")
    assert response.status_code == 200, response.text
    report = response.json()
    saved = client.get(f"/api/cases/{lead['case_id']}").json()
    assert saved["case"]["certified_report_id"] == report["id"]
    exported = client.get(f"/api/reports/{report['id']}/recipient-zip")
    assert exported.status_code == 200, exported.text
    with ZipFile(BytesIO(exported.content)) as archive:
        assert set(archive.namelist()) == {"notification.pdf", "recipient-manifest.json"}
    rows = client.get(f"/api/report-operations?case_id={lead['case_id']}").json()["operations"]
    assert rows[0]["operation"] == "certification" and rows[0]["state"] == "completed"
    assert all(row["state"] == "completed" for row in rows)


def test_render_message_limit_rejects_before_launch(monkeypatch, tmp_path):
    from modules.investigations.components import report_execution

    monkeypatch.setattr(report_execution, "MAX_RENDER_MESSAGE", 32)
    monkeypatch.setattr(
        report_execution.subprocess,
        "Popen",
        lambda *a, **kw: pytest.fail("Oversized render input launched a child"),
    )
    operations = ReportOperations(tmp_path)
    with pytest.raises(ValueError, match="message size limit"):
        with operations.run("case", "preview") as identifier:
            prepare_pdf(
                {"content": "x" * 100},
                tmp_path / "preview.pdf",
                tmp_path,
                draft=True,
                fallback=None,
            )
    assert operations.get(identifier)["state"] == "failed"
    assert not list((tmp_path / "operations").glob(".render-*"))


def test_corrupt_journal_is_preserved_and_does_not_claim_success(tmp_path):
    folder = tmp_path / "operations"
    folder.mkdir()
    original = b"{unfinished"
    (folder / "reports.json").write_bytes(original)
    operations = ReportOperations(tmp_path)
    assert operations.history_warning
    assert not operations.list()
    preserved = list(folder.glob("reports-unreadable-*.json"))
    assert len(preserved) == 1 and preserved[0].read_bytes() == original


def test_operation_journal_rejects_redirected_folder(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "workspace"
    root.mkdir()
    create_test_symlink(root / "operations", outside, target_is_directory=True)
    with pytest.raises(ValueError, match="cannot be a link"):
        ReportOperations(root)
    assert not list(outside.iterdir())


def test_failed_admission_does_not_leave_running_state(monkeypatch, tmp_path):
    operations = ReportOperations(tmp_path)

    def fail_save():
        raise OSError("simulated full disk")

    monkeypatch.setattr(operations, "_save", fail_save)
    with pytest.raises(OSError, match="full disk"):
        with operations.run("case", "preview"):
            pytest.fail("Unrecorded work was admitted")
    assert not operations.busy() and not operations.list()


@pytest.mark.skipif(
    sys.platform == "win32", reason="Native Windows process-handle acceptance is separate"
)
def test_posix_orphan_watchdog_exits_when_original_parent_dies():
    import os
    import signal

    # The child inherits the driver's stdout pipe. communicate cannot observe
    # EOF until the orphan watchdog exits, even after the driver has returned.
    child_code = (
        "import sys,threading,time; "
        "from modules.investigations.components.report_worker import watch_parent; "
        "threading.Thread(target=watch_parent,args=(int(sys.argv[1]),),daemon=True).start(); "
        "time.sleep(60)"
    )
    driver_code = (
        "import os,subprocess,sys; "
        f"p=subprocess.Popen([sys.executable,'-c',{child_code!r},str(os.getpid())]); "
        "print(p.pid,flush=True)"
    )
    driver = subprocess.Popen(
        [sys.executable, "-c", driver_code], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    child_pid = int(driver.stdout.readline())
    completed = False
    try:
        _, errors = driver.communicate(timeout=5)
        completed = True
        assert driver.returncode == 0, errors.decode()
    finally:
        if driver.poll() is None:
            driver.kill()
            driver.wait(timeout=2)
        if not completed:
            try:
                os.kill(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


@pytest.mark.parametrize("explicit_parent", [False, True])
def test_worker_initialization_failure_is_structured_and_cli_compatible(tmp_path, explicit_parent):
    import os
    from modules.investigations.components import report_worker

    job = tmp_path / "job.json"
    job.write_text("{unfinished")
    command = [sys.executable, str(Path(report_worker.__file__)), str(job)]
    if explicit_parent:
        command.append(str(os.getpid()))
    completed = subprocess.run(command, capture_output=True, timeout=10)
    assert completed.returncode == 1
    result = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert result["ok"] is False and result["error_type"] == "JSONDecodeError"
    assert len(result["error"]) <= 2000


def test_real_child_closing_preview_and_atomic_closure(client, app):
    from modules.investigations.tests.support.cases import opened, closing_values

    lead = opened(client, app)
    app.state.report_operations.process_rendering = True
    values = closing_values(lead, "unable_to_contact")
    preview = client.post(f"/api/cases/{lead['case_id']}/closing-preview", json=values)
    assert preview.status_code == 200 and preview.content.startswith(b"%PDF"), preview.text
    closed = client.post(f"/api/cases/{lead['case_id']}/close", json=values)
    assert closed.status_code == 200, closed.text
    current = client.get(f"/api/cases/{lead['case_id']}").json()["case"]
    assert current["stage"] == "closed" and not current["delivered_at"]
    history = app.state.report_operations.list(lead["case_id"])
    assert [row["operation"] for row in history] == ["closing publication", "closing preview"]
    assert all(row["state"] == "completed" for row in history)


def test_preview_omits_validation_archive_but_keeps_current_reviews(client, app, monkeypatch):
    from modules.investigations.components.routes import reports

    import_rows(client, app)
    lead = client.get("/api/leads/" + client.get("/api/leads").json()[0]["id"]).json()
    frozen = client.post(
        f"/api/cases/{lead['case_id']}/sections/closing/validate",
        json={"expected_revision": lead["draft_revision"]},
    )
    assert frozen.status_code == 200, frozen.text
    original = reports.snapshot
    captured = []

    def preview_snapshot(*args, **kwargs):
        assert kwargs["include_validation_history"] is False
        data = original(*args, **kwargs)
        assert data["section_validations"] == []
        assert (
            next(row for row in data["section_reviews"] if row["key"] == "closing")["status"]
            == "validated"
        )
        captured.append(True)
        return data

    monkeypatch.setattr(reports, "snapshot", preview_snapshot)
    preview = client.get(f"/api/leads/{lead['id']}/preview.pdf?case_id={lead['case_id']}")
    assert preview.status_code == 200, preview.text
    assert captured == [True] and preview.content.startswith(b"%PDF")
    archive = original(app.state.store, lead["id"], lead["case_id"], capture_sections=())
    assert len(archive["section_validations"]) == 1, (
        "Certification retains the full validation archive by default"
    )
