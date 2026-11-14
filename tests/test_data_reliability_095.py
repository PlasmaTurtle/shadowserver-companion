"""0.9.5 backup contracts, recovery copies and diagnostics protect real workflows."""

from contextlib import closing

import importlib.util
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from workbench import workspace_data as data
from workbench.api import create_app
from workbench.store import Store
from test_workspace_data_080 import label, login, manager
from test_upgrade_cleanup_072 import installation, upgrade


@pytest.mark.parametrize("limit", ["MAX_ARCHIVE", "MAX_EXPANDED", "MAX_MEMBERS", "MAX_MANIFEST"])
def test_export_cannot_offer_backup_that_exceeds_restore_contract(tmp_path, monkeypatch, limit):
    store = Store(tmp_path / "data")
    good = data.export_workspace(store)
    good.unlink()
    prior = data.backup_status(store.root)["last_export"]
    monkeypatch.setattr(data, limit, 1)
    with pytest.raises(ValueError, match="limit"):
        data.export_workspace(store)
    assert data.backup_status(store.root)["last_export"] == prior


def test_disk_preflight_and_restore_validation_leave_last_good_export(tmp_path, monkeypatch):
    store = Store(tmp_path / "data")
    archive = data.export_workspace(store)
    archive.unlink()
    prior = data.backup_status(store.root)["last_export"]
    original_usage = data.shutil.disk_usage
    monkeypatch.setattr(data.shutil, "disk_usage", lambda _: SimpleNamespace(free=0))
    with pytest.raises(ValueError, match="disk space"):
        data.export_workspace(store)
    monkeypatch.setattr(data.shutil, "disk_usage", original_usage)
    monkeypatch.setattr(
        data,
        "validate_workspace",
        lambda _: (_ for _ in ()).throw(ValueError("Synthetic missing evidence")),
    )
    with pytest.raises(ValueError, match="missing evidence"):
        data.export_workspace(store)
    assert data.backup_status(store.root)["last_export"] == prior


def test_restorable_pre_import_points_rotate_and_permanent_delete_removes_them(tmp_path):
    source, target = Store(tmp_path / "source"), Store(tmp_path / "target")
    label(source, "replacement")
    label(target, "original")
    (target.root / "operations").mkdir()
    (target.root / "operations" / "finished.json").write_text('{"state":"succeeded"}')
    archive = data.export_workspace(source)
    control = manager(target)
    try:
        for _ in range(4):
            control.stage("import", archive)
            control.cancel()
        status = control.status()["backup"]
        assert len(status["restore_points"]) == 3
        assert len(list(data.restore_dir(target.root).glob("*.zip"))) == 3
        point = status["restore_points"][0]
        restored = tmp_path / "verified-point"
        data.unpack_workspace(data.restore_point_path(target.root, point["id"]), restored)
        assert Store(restored).settings()["office"] == "original"
        assert (restored / "operations" / "finished.json").read_text() == '{"state":"succeeded"}'
        control.stage("delete")
        assert data.restore_dir(target.root).exists()
        data.apply_pending_workspace(target.root)
        assert not data.restore_dir(target.root).exists()
    finally:
        archive.unlink()


def test_pre_schema_snapshot_includes_files_and_skips_isolated_recursion(tmp_path):
    store = Store(tmp_path / "data")
    (store.root / "inbox" / "retained.csv").write_text("original")
    point = data.before_schema_upgrade(store.root, 7, 8)
    assert point["reason"] == "before_schema_7_to_8"
    restored = tmp_path / "restore"
    data.unpack_workspace(data.restore_point_path(store.root, point["id"]), restored)
    assert (restored / "inbox" / "retained.csv").read_text() == "original"
    token = data.ISOLATED_VALIDATION.set(True)
    try:
        assert data.before_schema_upgrade(store.root, 7, 8) is None
    finally:
        data.ISOLATED_VALIDATION.reset(token)


def test_application_startup_saves_pre_upgrade_schema_and_complete_files(tmp_path):
    from workbench.migrations import MIGRATIONS, SCHEMA_VERSION
    from zipfile import ZipFile

    root = tmp_path / "legacy"
    (root / "inbox").mkdir(parents=True)
    (root / "inbox" / "retained.csv").write_text("retained original bytes")
    with closing(sqlite3.connect(root / "workbench.sqlite3")) as db, db:
        db.row_factory = sqlite3.Row
        for version in range(1, 8):
            MIGRATIONS[version](db)
            db.execute(f"PRAGMA user_version={version}")
    app = create_app(root, worker=False, report_processes=False)
    with closing(app.state.store.connect()) as db, db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    point = data.backup_status(root)["restore_points"][0]
    path = data.restore_point_path(root, point["id"])
    with ZipFile(path) as archive:
        assert archive.read("data/inbox/retained.csv") == b"retained original bytes"
        old_db = tmp_path / "before.sqlite3"
        old_db.write_bytes(archive.read("data/workbench.sqlite3"))
    with closing(sqlite3.connect(old_db)) as db, db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 7


def test_failed_pre_upgrade_backup_does_not_migrate_or_replace_existing_records(
    tmp_path, monkeypatch
):
    from workbench.migrations import MIGRATIONS

    root = tmp_path / "legacy"
    (root / "inbox").mkdir(parents=True)
    marker = root / "inbox/retained.csv"
    marker.write_bytes(b"exact original")
    with closing(sqlite3.connect(root / "workbench.sqlite3")) as db, db:
        db.row_factory = sqlite3.Row
        for version in range(1, 8):
            MIGRATIONS[version](db)
            db.execute(f"PRAGMA user_version={version}")
    monkeypatch.setattr(
        data,
        "_require_space",
        lambda *args: (_ for _ in ()).throw(ValueError("Synthetic full disk")),
    )
    with pytest.raises(ValueError, match="full disk"):
        create_app(root, worker=False, report_processes=False)
    with closing(sqlite3.connect(root / "workbench.sqlite3")) as db, db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 7
    assert marker.read_bytes() == b"exact original"


def test_failed_restore_point_publication_preserves_previous_point(tmp_path, monkeypatch):
    store = Store(tmp_path / "data")
    prior = data.create_restore_point(store)
    replace = Path.replace

    def fail_publication(path, destination):
        if path.suffix == ".partial":
            raise OSError("Synthetic rename failure")
        return replace(path, destination)

    monkeypatch.setattr(Path, "replace", fail_publication)
    with pytest.raises(OSError, match="rename failure"):
        data.create_restore_point(store)
    assert data.backup_status(store.root)["restore_points"] == [prior]
    assert data.restore_point_path(store.root, prior["id"]).exists()
    assert not list(data.restore_dir(store.root).glob("*.partial"))
    assert len(list(data.restore_dir(store.root).glob("*.zip"))) == 1


def test_changed_restore_point_is_never_downloaded_as_valid(tmp_path):
    store = Store(tmp_path / "data")
    point = data.create_restore_point(store)
    path = data.restore_point_path(store.root, point["id"])
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="missing or changed"):
        data.restore_point_path(store.root, point["id"])
    with pytest.raises(ValueError, match="Unknown"):
        data.restore_point_path(store.root, "../outside")


def test_active_report_operation_blocks_backup_and_transient_render_files_are_omitted(tmp_path):
    from workbench.report_operations import ReportOperations
    from zipfile import ZipFile

    store = Store(tmp_path / "data")
    jobs = ReportOperations(store.root, process_rendering=False)
    control = manager(store)
    control.app.state.report_operations = jobs
    with jobs.run("synthetic-case", "preview"):
        with pytest.raises(ValueError, match="active reports"):
            with control.operation():
                data.export_workspace(store)
    scratch = store.root / "operations/.render-abandoned"
    scratch.mkdir()
    (scratch / "input.json").write_text("transient")
    (store.root / "operations/reports.tmp").write_text("unfinished")
    with control.operation():
        archive = data.export_workspace(store)
    try:
        with ZipFile(archive) as backup:
            assert "data/operations/reports.json" in backup.namelist()
            assert not any(
                ".render-" in name or name.endswith("reports.tmp") for name in backup.namelist()
            )
    finally:
        archive.unlink()


def test_repair_import_requires_explicit_skip_when_current_backup_cannot_be_verified(
    tmp_path, monkeypatch
):
    source, target = Store(tmp_path / "source"), Store(tmp_path / "target")
    label(source, "repaired")
    label(target, "damaged current")
    archive = data.export_workspace(source)
    control = manager(target)
    monkeypatch.setattr(
        data,
        "create_restore_point",
        lambda *args: (_ for _ in ()).throw(ValueError("Current evidence missing")),
    )
    try:
        with pytest.raises(ValueError, match="Current evidence missing"):
            control.stage("import", archive)
        assert control.pending is None
        assert target.settings()["office"] == "damaged current"
        assert (
            control.stage("import", archive, retain_current=False)["restore_point_skipped"] is True
        )
        data.apply_pending_workspace(target.root)
        assert Store(target.root).settings()["office"] == "repaired"
    finally:
        archive.unlink()


def test_linked_restore_point_directory_prevents_deletion_without_touching_target(tmp_path):
    store = Store(tmp_path / "data")
    label(store, "retained")
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "keep.txt"
    marker.write_text("retained")
    data.restore_dir(store.root).symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="links"):
        manager(store).stage("delete")
    assert store.settings()["office"] == "retained"
    assert marker.read_text() == "retained"


def test_diagnostics_exclude_operational_values_and_paths(tmp_path):
    app = create_app(tmp_path / "sensitive-path", worker=False)
    label(app.state.store, "SENSITIVE OFFICE VALUE")
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get("/api/data/diagnostics").status_code == 401
        login(client, app)
        response = client.get("/api/data/diagnostics")
        assert response.status_code == 200
        assert "SENSITIVE OFFICE VALUE" not in response.text
        assert str(tmp_path) not in response.text
        assert response.json()["record_counts"]["reports"] == 0
        assert client.post("/api/data/check").json()["ok"] is True


def test_installer_stops_downgrade_before_removing_program_files(tmp_path):
    root, staged = installation(tmp_path)
    manifest = json.loads((root / "payload-manifest.json").read_text())
    manifest["application_version"] = "0.9.5"
    (root / "payload-manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(upgrade.UpgradeError, match="downgrade"):
        upgrade.cleanup(root, staged)
    assert (root / "app/workbench/old.py").exists()


def test_installer_stops_incompatible_existing_schema_before_cleanup(tmp_path, monkeypatch):
    root, staged = installation(tmp_path)
    local = tmp_path / "local"
    database = local / "OutreachWorkbench" / "data" / "workbench.sqlite3"
    database.parent.mkdir(parents=True)
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("PRAGMA user_version=999")
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    manifest = json.loads(staged.read_text())
    manifest["database_schema_max"] = 9
    staged.write_text(json.dumps(manifest))
    with pytest.raises(upgrade.UpgradeError, match="schema 999"):
        upgrade.cleanup(root, staged)
    assert (root / "app/workbench/old.py").exists()


def test_installer_fresh_start_removes_managed_restore_points(tmp_path):
    path = Path(__file__).resolve().parents[1] / "tools/windows_installer/workspace_data.py"
    spec = importlib.util.spec_from_file_location("fresh_095", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    retained = tmp_path / "OutreachWorkbench/data-restore-points"
    retained.mkdir(parents=True)
    (retained / "backup.zip").write_bytes(b"retained")
    module.start_fresh(tmp_path)
    assert not retained.exists()
    assert (tmp_path / "OutreachWorkbench/data").is_dir()


def test_launcher_initializes_logs_before_session_or_port_errors(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / "tools/windows_installer/desktop.py"
    spec = importlib.util.spec_from_file_location("desktop_095", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []
    monkeypatch.setattr(module, "configure_logging", lambda workspace: calls.append("logging"))
    monkeypatch.setattr(module, "hold_installation_mutex", lambda: calls.append("mutex"))

    def session(*args):
        calls.append("session")
        raise RuntimeError("Synthetic early failure")

    monkeypatch.setattr(module, "existing_instance", session)
    with pytest.raises(RuntimeError, match="early failure"):
        module.main(["--data-dir", str(tmp_path), "--no-browser"])
    assert calls == ["logging", "mutex", "session"]
