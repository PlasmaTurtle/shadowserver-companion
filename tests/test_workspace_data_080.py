"""Workspace replacement is validated, cancellable, and deferred to startup."""

import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from zipfile import ZipFile, ZipInfo

from fastapi.testclient import TestClient
import pytest

from workbench.api import create_app
from workbench.primitives import dump
from workbench.store import Store
from workbench.workspace_data import (
    WorkspaceData,
    apply_pending_workspace,
    export_workspace,
    transfer_dir,
    unpack_workspace,
)


def label(store, name):
    settings = {**store.settings(), "office": name}
    with store.transaction() as db:
        db.execute("UPDATE settings SET value=? WHERE key='profile'", (dump(settings),))


def manager(store):
    return WorkspaceData(SimpleNamespace(state=SimpleNamespace()), store)


def test_export_sqlite_snapshot_manifest_import_restart_and_cancel(tmp_path):
    source = Store(tmp_path / "source")
    label(source, "Imported office")
    (source.root / "inbox" / "pending.csv").write_text("example")
    archive = export_workspace(source)
    try:
        with ZipFile(archive) as package:
            manifest = json.loads(package.read("manifest.json"))
            assert set(manifest["files"]) == set(package.namelist()) - {"manifest.json"}
            for name, expected in manifest["files"].items():
                assert hashlib.sha256(package.read(name)).hexdigest() == expected
            assert not any(n.endswith(("-wal", "-shm")) for n in package.namelist())
        target = Store(tmp_path / "target")
        label(target, "Current office")
        data = manager(target)
        assert data.stage("import", archive)["pending"] == "import"
        assert target.settings()["office"] == "Current office"
        assert target.maintenance.is_set()
        data.cancel()
        assert not target.maintenance.is_set()
        assert not transfer_dir(target.root).exists()
        data.stage("import", archive)
        apply_pending_workspace(target.root)
        reopened = Store(target.root)
        assert reopened.settings()["office"] == "Imported office"
        assert (reopened.root / "inbox" / "pending.csv").read_text() == "example"
        assert not transfer_dir(target.root).exists()
    finally:
        archive.unlink()


def test_delete_is_staged_and_removes_entire_workspace_only_on_restart(tmp_path):
    target = Store(tmp_path / "target")
    label(target, "Current office")
    (target.root / "backups" / "old.sqlite3").write_bytes(b"old")
    neighbor = tmp_path / "unrelated.txt"
    neighbor.write_text("keep")
    data = manager(target)
    data.stage("delete")
    assert target.settings()["office"] == "Current office"
    apply_pending_workspace(target.root)
    assert Store(target.root).settings()["office"] != "Current office"
    assert not (target.root / "backups" / "old.sqlite3").exists()
    assert neighbor.read_text() == "keep"


@pytest.mark.parametrize(
    "name",
    [
        "data/../outside",
        "/data/file",
        "data\\originals\\x",
        "data/originals/x.",
        "data/CON:stream",
        "unexpected.txt",
        "data/originals/CON",
        "data/originals/nul.txt",
        "data/originals/COM1.bin",
        "data/originals/LPT¹.txt",
    ],
)
def test_import_rejects_unsafe_paths_without_touching_existing_data(tmp_path, name):
    target = Store(tmp_path / "target")
    label(target, "Keep")
    path = tmp_path / "bad.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr(name, b"bad")
    with pytest.raises(ValueError):
        manager(target).stage("import", path)
    assert target.settings()["office"] == "Keep"
    assert not transfer_dir(target.root).exists()


def test_rejects_zip_symlink_and_duplicate_case_paths(tmp_path):
    for mode in ("symlink", "duplicate"):
        path = tmp_path / (mode + ".zip")
        with ZipFile(path, "w") as archive:
            info = ZipInfo("data/originals/file")
            info.external_attr = (0o120777 if mode == "symlink" else 0o100644) << 16
            archive.writestr(info, b"outside")
            if mode == "duplicate":
                archive.writestr("data/Originals/File", b"duplicate")
        with pytest.raises(ValueError):
            unpack_workspace(path, tmp_path / mode)


def test_tampered_archive_and_staged_data_preserve_current_workspace(tmp_path):
    source = Store(tmp_path / "source")
    archive = export_workspace(source)
    tampered = tmp_path / "bad.zip"
    with ZipFile(archive) as source_zip, ZipFile(tampered, "w") as output:
        for item in source_zip.infolist():
            content = source_zip.read(item)
            if item.filename == "manifest.json":
                manifest = json.loads(content)
                manifest["files"]["data/workbench.sqlite3"] = "0" * 64
                content = json.dumps(manifest).encode()
            output.writestr(item, content)
    target = Store(tmp_path / "target")
    label(target, "Keep")
    data = manager(target)
    with pytest.raises(ValueError, match="SHA-256"):
        data.stage("import", tampered)
    data.stage("import", archive)
    (transfer_dir(target.root) / "replacement" / "inbox" / "extra").write_text("modified")
    with pytest.raises(ValueError, match="Staged workspace has changed"):
        apply_pending_workspace(target.root)
    assert target.settings()["office"] == "Keep"
    archive.unlink()


def test_legacy_backup_and_future_schema_validation(tmp_path):
    source = Store(tmp_path / "source")
    archive = export_workspace(source)
    legacy = tmp_path / "legacy.zip"
    with ZipFile(archive) as current, ZipFile(legacy, "w") as old:
        for item in current.infolist():
            if item.filename != "manifest.json":
                old.writestr(item, current.read(item))
    unpack_workspace(legacy, tmp_path / "restored")
    with sqlite3.connect(tmp_path / "restored" / "workbench.sqlite3") as db:
        db.execute("PRAGMA user_version=999")
    from workbench.workspace_data import validate_workspace

    with pytest.raises(ValueError, match="version"):
        validate_workspace(tmp_path / "restored")
    archive.unlink()


@pytest.mark.parametrize("phase", ["ready", "old_moved", "installed"])
def test_startup_recovers_interrupted_switch(tmp_path, phase):
    target = Store(tmp_path / "target")
    data = manager(target)
    data.stage("delete")
    folder = transfer_dir(target.root)
    target.root.rename(folder / "previous")
    if phase != "ready":
        (folder / "replacement").rename(target.root)
    record = json.loads((folder / "pending.json").read_text())
    record["phase"] = phase
    (folder / "pending.json").write_text(json.dumps(record))
    apply_pending_workspace(target.root)
    assert target.db.exists()
    assert not folder.exists()


def test_failed_install_rename_rolls_back(tmp_path, monkeypatch):
    target = Store(tmp_path / "target")
    label(target, "Keep")
    data = manager(target)
    data.stage("delete")
    rename = Path.rename

    def fail_replacement(path, destination):
        if path.name == "replacement":
            raise OSError("Synthetic rename failure")
        return rename(path, destination)

    monkeypatch.setattr(Path, "rename", fail_replacement)
    with pytest.raises(OSError, match="Synthetic"):
        apply_pending_workspace(target.root)
    assert target.settings()["office"] == "Keep"


@pytest.mark.parametrize("damage", ["missing", "changed"])
def test_installed_recovery_preserves_previous_if_replacement_damaged(tmp_path, damage):
    target = Store(tmp_path / "target")
    label(target, "Keep")
    data = manager(target)
    data.stage("delete")
    folder = transfer_dir(target.root)
    target.root.rename(folder / "previous")
    (folder / "replacement").rename(target.root)
    record = json.loads((folder / "pending.json").read_text())
    record["phase"] = "installed"
    (folder / "pending.json").write_text(json.dumps(record))
    if damage == "missing":
        target.db.unlink()
    else:
        target.db.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="Staged workspace has changed"):
        apply_pending_workspace(target.root)
    assert Store(folder / "previous").settings()["office"] == "Keep"


def test_operation_gate_rejects_requests_workers_and_symlinked_workspace(tmp_path):
    store = Store(tmp_path / "target")
    data = manager(store)
    assert data.enter_request("/api/settings", "PUT") is None
    with pytest.raises(ValueError, match="Finish current"):
        data.stage("delete")
    data.exit_request("/api/settings")
    data.app.state.report_operations = SimpleNamespace(busy=lambda: True)
    with pytest.raises(ValueError, match="active reports"):
        data.stage("delete")
    data.app.state.report_operations = SimpleNamespace(busy=lambda: False)
    outside = tmp_path / "outside"
    outside.write_text("keep")
    (store.root / "evidence" / "link").symlink_to(outside)
    with pytest.raises(ValueError, match="links"):
        with data.operation():
            export_workspace(store)
    assert outside.read_text() == "keep"


def login(client, app):
    launch = app.state.sessions.issue_launch()
    assert (
        client.post("/api/session/exchange", headers={"X-Workbench-Launch": launch}).status_code
        == 200
    )
    client.headers["X-Workbench-Token"] = client.get("/api/bootstrap").json()["token"]


def test_api_confirmation_authentication_pending_gate_and_restart_session(tmp_path):
    app = create_app(tmp_path / "data", worker=False)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get("/api/data/status").status_code == 401

        login(client, app)
        assert client.post("/api/data/delete", json={"confirmation": "wrong"}).status_code == 422
        assert (
            client.post("/api/data/delete", json={"confirmation": "DELETE"}).json()["pending"]
            == "delete"
        )
        assert client.put("/api/settings", json={"office": "Blocked"}).status_code == 409
        assert (
            client.get("/api/data/status").json()["message"] == "Close and reopen the app to apply."
        )
        assert client.get("/api/bootstrap").status_code == 200
        assert client.post("/api/data/cancel").json()["pending"] is None
        assert client.post("/api/backup").status_code == 200
        assert client.post("/api/data/export").status_code == 200
        assert client.post("/api/data/delete", json={"confirmation": "DELETE"}).status_code == 200
        old_cookies = dict(client.cookies)
    restarted = create_app(tmp_path / "data", worker=False)
    with TestClient(restarted, base_url="http://127.0.0.1") as client:
        client.cookies.update(old_cookies)
        assert client.get("/api/data/status").status_code == 401


def test_api_import_verifies_upload_and_replaces_only_after_restart(tmp_path):
    source = Store(tmp_path / "source")
    label(source, "Imported")
    archive = export_workspace(source)
    app = create_app(tmp_path / "data", worker=False)
    label(app.state.store, "Current")
    try:
        with TestClient(app, base_url="http://127.0.0.1") as client:
            login(client, app)
            files = {"file": ("backup.zip", archive.read_bytes(), "application/zip")}
            assert (
                client.post(
                    "/api/data/import", data={"confirmation": "wrong"}, files=files
                ).status_code
                == 422
            )
            response = client.post("/api/data/import", data={"confirmation": "IMPORT"}, files=files)
            assert response.status_code == 200, response.text
            assert response.json()["pending"] == "import"
            assert app.state.store.settings()["office"] == "Current"
        restarted = create_app(tmp_path / "data", worker=False)
        assert restarted.state.store.settings()["office"] == "Imported"
    finally:
        archive.unlink()


@pytest.mark.parametrize("job_name", ["report_operations", "source_jobs", "asset_attribution_jobs"])
def test_no_transfer_while_background_job_is_active(tmp_path, job_name):
    store = Store(tmp_path / "data")
    data = manager(store)
    setattr(data.app.state, job_name, SimpleNamespace(busy=lambda: True))
    with pytest.raises(ValueError, match="active reports"):
        data.stage("delete")
    assert not store.maintenance.is_set()
    assert not transfer_dir(store.root).exists()


def test_inbox_and_queued_intake_cannot_race_staged_change(tmp_path):
    from workbench.intake_service import IntakeService

    store = Store(tmp_path / "data")
    data = manager(store)
    intake = IntakeService(store)
    data.stage("delete")
    with pytest.raises(ValueError, match="paused"):
        intake.enqueue("source.csv", b"domain,ip\nexample.com,192.0.2.1")
    data.cancel()
    intake.enqueue("source.csv", b"domain,ip\nexample.com,192.0.2.1")
    with pytest.raises(ValueError, match="intake"):
        data.stage("delete")


def installer_helper():
    source = Path(__file__).parents[1] / "tools/windows_installer/workspace_data.py"
    spec = importlib.util.spec_from_file_location("installer_workspace_data", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_installer_fresh_start_is_exact_and_clears_pending_import(tmp_path):
    base = tmp_path / "OutreachWorkbench"
    for name in ("data", ".data-companion-transfer", "demo", "logs"):
        (base / name).mkdir(parents=True)
        (base / name / "record").write_text(name)
    installer_helper().start_fresh(tmp_path)
    assert list((base / "data").iterdir()) == []
    assert not (base / ".data-companion-transfer").exists()
    assert (base / "demo" / "record").read_text() == "demo"
    assert (base / "logs" / "record").read_text() == "logs"


def test_installer_rejects_links_before_any_deletion(tmp_path):
    base = tmp_path / "OutreachWorkbench"
    (base / "data").mkdir(parents=True)
    (base / "data" / "keep").write_text("keep")
    outside = tmp_path / "outside"
    outside.mkdir()
    (base / ".data-companion-transfer").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="link"):
        installer_helper().start_fresh(tmp_path)
    assert (base / "data" / "keep").read_text() == "keep"


def test_launcher_probes_legacy_lock_then_switches_before_opening_live_lock(tmp_path, monkeypatch):
    import run
    import workbench.workspace_data as transfers

    data = tmp_path / "data"
    data.mkdir()
    (data / "workspace.lock").write_bytes(b"0")
    events = []

    def acquire(folder, filename="workspace.lock"):
        name = "guard" if folder == data.parent else "legacy"
        events.append("open-" + name)
        return SimpleNamespace(close=lambda: events.append("close-" + name))

    monkeypatch.setattr(run, "acquire_lock", acquire)
    monkeypatch.setattr(transfers, "apply_pending_workspace", lambda path: events.append("apply"))
    with run.workspace_session(data):
        events.append("serve")
    assert events == [
        "open-guard",
        "open-legacy",
        "close-legacy",
        "apply",
        "open-legacy",
        "serve",
        "close-legacy",
        "close-guard",
    ]


def test_launcher_rejects_open_old_workspace_before_apply(tmp_path, monkeypatch):
    import run
    import workbench.workspace_data as transfers

    data = tmp_path / "data"
    data.mkdir()
    (data / "workspace.lock").write_bytes(b"0")
    closed = []

    def acquire(folder, filename="workspace.lock"):
        if folder == data:
            raise SystemExit("already open")
        return SimpleNamespace(close=lambda: closed.append(True))

    monkeypatch.setattr(run, "acquire_lock", acquire)
    monkeypatch.setattr(
        transfers, "apply_pending_workspace", lambda path: pytest.fail("Must not apply")
    )
    with pytest.raises(SystemExit, match="already open"), run.workspace_session(data):
        pytest.fail("Must not start")
    assert closed == [True]


def test_launcher_stable_guard_survives_actual_pending_replacement(tmp_path):
    import run

    store = Store(tmp_path / "data")
    label(store, "Old")
    manager(store).stage("delete")
    with run.workspace_session(store.root):
        assert Store(store.root).settings()["office"] != "Old"
        assert (store.root / "workspace.lock").is_file()
        assert (store.root.parent / ".data-companion.lock").is_file()
        with pytest.raises(SystemExit, match="already open"), run.workspace_session(store.root):
            pytest.fail("Second current process must not enter")
