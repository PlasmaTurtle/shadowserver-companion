"""Chaos uses independent install/data identities without migrating private folders."""

from contextlib import nullcontext, closing
import json
from pathlib import Path
import re
import sqlite3
import sys
from types import SimpleNamespace

import pytest

from modules.workspace.components import startup as workspace_startup
from modules.workspace.components.release import (
    check_output_name,
    installation_identity,
    load_release,
)
from tests.support.installation import installation, upgrade

from tests.support.installation import (
    ROOT,
    helper,
    tree_bytes,
)


@pytest.fixture(autouse=True)
def legacy_chaos_runtime_metadata(monkeypatch):
    """These historical identity contracts remain Chaos even in a newer variant tree."""
    release = {
        "schema": 1,
        "version": "0.9.81",
        "channel": "unstable",
        "edition": "chaos",
        "variant": "",
        "home_confirmation": None,
        "app_name": "Shadowserver Companion Chaos",
        "display_version": "0.9.81 (Chaos, unstable)",
    }
    monkeypatch.setattr(
        "modules.workspace.components.release.load_release",
        lambda root=None: dict(release) if root is None else load_release(root),
    )


def release_metadata(root, *, edition=None, channel="unstable", confirmed=False):
    root.mkdir(parents=True, exist_ok=True)
    (root / "VERSION").write_text("0.9.81")
    data = {"schema": 1, "version": "0.9.81", "channel": channel, "home_confirmation": None}
    if edition is not None:
        data["edition"] = edition
    if confirmed:
        data["home_confirmation"] = {
            "version": "0.9.81",
            "confirmed_by": "Synthetic test",
            "confirmed_at": "2026-11-11T00:00:00Z",
            "notes": "Synthetic release gate test only",
        }
    (root / "RELEASE.json").write_text(json.dumps(data))
    return root


def mark_manifest(path, edition):
    data = json.loads(path.read_text(encoding="utf-8"))
    data["release"] = {"edition": edition}
    path.write_text(json.dumps(data))


def test_release_edition_keeps_legacy_identity_and_home_gate(tmp_path):
    standard = load_release(release_metadata(tmp_path / "standard"))
    chaos = load_release(release_metadata(tmp_path / "chaos", edition="chaos"))
    assert standard["edition"] == "standard"
    assert standard["app_name"] == "Shadowserver Companion"
    assert chaos["app_name"] == "Shadowserver Companion Chaos"
    assert chaos["display_version"] == "0.9.81 (Chaos, unstable)"
    assert chaos["validation_status"] == "awaiting_home_validation"
    for edition in ("standard", "chaos"):
        with pytest.raises(ValueError, match="explicit home confirmation"):
            load_release(release_metadata(tmp_path / edition, edition=edition, channel="stable"))
    with pytest.raises(ValueError, match="Chaos edition must remain unstable"):
        load_release(
            release_metadata(tmp_path / "chaos", edition="chaos", channel="stable", confirmed=True)
        )
    with pytest.raises(ValueError, match="Unknown application edition"):
        load_release(release_metadata(tmp_path / "bad", edition="../OutreachWorkbench"))
    check_output_name(Path("Companion-0.9.81-chaos-unstable.exe"), chaos)
    with pytest.raises(ValueError, match="Chaos release filenames"):
        check_output_name(Path("Companion-0.9.81-unstable.exe"), chaos)
    with pytest.raises(ValueError, match="Unstable release filenames"):
        check_output_name(Path("Companion-0.9.81-chaos.exe"), chaos)


def test_identities_do_not_share_ports_mutex_registry_or_shortcuts(tmp_path):
    standard, chaos = (installation_identity(e) for e in ("standard", "chaos"))
    assert standard["app_id"] == "OutreachWorkbench"
    assert chaos["app_id"] == "ShadowserverCompanionChaos"
    assert (standard["port"], standard["demo_port"]) == (8877, 8878)
    assert (chaos["port"], chaos["demo_port"]) == (8879, 8880)
    assert not set(standard.values()) & set(chaos.values())
    builder = helper("build")
    config = builder.installer_definitions(
        load_release(release_metadata(tmp_path, edition="chaos"))
    )
    script = (ROOT / "tools/windows_installer/installer.nsi").read_text(encoding="utf-8")
    # The standard rename cleanup is compiled out of Chaos entirely.
    legacy = re.search(r'!if "\$\{APP_EDITION\}" == "standard"\n(.*?)!endif', script, re.S)
    assert legacy and 'Delete "$DESKTOP\\Outreach Workbench.lnk"' in legacy[1]
    script = script.replace(legacy[0], "")
    for key, value in config.items():
        script = script.replace("${" + key + "}", value)
    assert "OutreachWorkbench" not in script and "Outreach Workbench" not in script
    assert 'InstallDir "$LOCALAPPDATA\\Programs\\ShadowserverCompanionChaos"' in script
    assert '!define KEY "Software\\ShadowserverCompanionChaos"' in script
    assert "Uninstall\\ShadowserverCompanionChaos" in script
    assert "Local\\ShadowserverCompanionChaos.Installed.Running" in script
    assert "$DESKTOP\\Shadowserver Companion Chaos.lnk" in script
    assert "Companion Chaos Demo.lnk" in script
    assert "--confirmation DELETE --edition chaos" in script
    assert 'GetFullPathName $1 "$LOCALAPPDATA\\Programs\\ShadowserverCompanionChaos"' in script
    assert "Chaos must use its separate installation folder" in script
    uninstall_init = script.split("Function un.onInit", 1)[1].split("FunctionEnd", 1)[0]
    assert "!insertmacro CheckInstallLocation" in uninstall_init
    assert "RMDir /r" not in script


@pytest.mark.parametrize("demo,expected_port", [(False, 8879), (True, 8880)])
def test_source_and_installed_launch_defaults_are_isolated(
    tmp_path, monkeypatch, demo, expected_port
):
    desktop = helper("desktop")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    expected = tmp_path / "ShadowserverCompanionChaos" / ("data-demo" if demo else "data")
    assert desktop.default_workspace(demo) == expected
    assert desktop.RUNNING_MUTEX == installation_identity("chaos")["running_mutex"]
    observed = []
    monkeypatch.setattr(desktop, "configure_logging", lambda path: observed.append(path))
    monkeypatch.setattr(desktop, "hold_installation_mutex", lambda: None)
    monkeypatch.setattr(
        desktop,
        "existing_instance",
        lambda port, path, is_demo: observed.append((port, path, is_demo)) or "http://local",
    )
    desktop.main(["--no-browser", *(["--demo"] if demo else [])])
    assert observed == [expected, (expected_port, expected, demo)]
    observed.clear()
    monkeypatch.setattr(sys, "argv", ["run.py", "--no-browser", *(["--demo"] if demo else [])])
    monkeypatch.setattr(workspace_startup, "workspace_session", lambda path: nullcontext())
    monkeypatch.setattr(
        workspace_startup, "serve", lambda args, data, preview: observed.append((args.port, data))
    )
    workspace_startup.main()
    assert observed == [(expected_port, ROOT / ("data-demo" if demo else "data"))]
    assert not list(tmp_path.iterdir())


def test_installed_launcher_refuses_standard_data_before_creating_logs(tmp_path, monkeypatch):
    desktop = helper("desktop")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    baseline = tmp_path / "OutreachWorkbench/data"
    baseline.mkdir(parents=True)
    (baseline / "record").write_bytes(b"original records")
    before = tree_bytes(tmp_path)
    with pytest.raises(ValueError, match="Export a backup"):
        desktop.main(["--data-dir", str(baseline), "--no-browser"])
    monkeypatch.setattr(sys, "argv", ["run.py", "--data-dir", str(baseline), "--no-browser"])
    with pytest.raises(SystemExit) as stopped:
        workspace_startup.main()
    assert stopped.value.code == 2
    assert tree_bytes(tmp_path) == before
    assert not (tmp_path / "OutreachWorkbench/data-logs").exists()


def test_logs_restore_points_transfers_and_credentials_are_separate(tmp_path, monkeypatch):
    from modules.accretion.components.api_acquisition import APIAcquisition
    from modules.workspace.components.workspace_data import restore_dir, transfer_dir

    desktop = helper("desktop")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    standard = tmp_path / "OutreachWorkbench/data"
    chaos = desktop.default_workspace()
    assert restore_dir(chaos) == tmp_path / "ShadowserverCompanionChaos/data-restore-points"
    assert transfer_dir(chaos) == tmp_path / "ShadowserverCompanionChaos/.data-companion-transfer"
    captured = []
    monkeypatch.setattr(
        desktop.logging, "basicConfig", lambda **kw: captured.extend(kw["handlers"])
    )
    monkeypatch.setattr(desktop.tempfile, "gettempdir", lambda: str(tmp_path / "temporary"))
    try:
        assert desktop.configure_logging(chaos) == tmp_path / "ShadowserverCompanionChaos/data-logs"
        assert (
            desktop.configure_logging() == tmp_path / "temporary/ShadowserverCompanionChaos-startup"
        )
    finally:
        for handler in captured:
            handler.close()
    services = [APIAcquisition(SimpleNamespace(root=p), None) for p in (standard, chaos)]
    try:
        assert services[0].windows.profile != services[1].windows.profile
    finally:
        for service in services:
            service.close()
    assert not standard.parent.exists()


def test_chaos_fresh_start_preserves_every_standard_file(tmp_path):
    for edition in ("OutreachWorkbench", "ShadowserverCompanionChaos"):
        for folder in (
            "data",
            "data-demo",
            "data-logs",
            ".data-companion-transfer",
            "data-restore-points",
        ):
            path = tmp_path / edition / folder
            path.mkdir(parents=True)
            (path / "sentinel").write_bytes((edition + "/" + folder).encode())
    baseline = tree_bytes(tmp_path / "OutreachWorkbench")
    fresh = helper("workspace_data")
    fresh.start_fresh(tmp_path, edition="chaos")
    assert tree_bytes(tmp_path / "OutreachWorkbench") == baseline
    chaos = tmp_path / "ShadowserverCompanionChaos"
    assert not list((chaos / "data").iterdir())
    assert not (chaos / ".data-companion-transfer").exists()
    assert not (chaos / "data-restore-points").exists()
    assert (chaos / "data-demo/sentinel").exists()
    assert (chaos / "data-logs/sentinel").exists()
    with pytest.raises(ValueError, match="Unknown application edition"):
        fresh.start_fresh(tmp_path, edition="../OutreachWorkbench")
    assert tree_bytes(tmp_path / "OutreachWorkbench") == baseline


def test_explicit_backup_import_makes_independent_comparison_workspace(tmp_path):
    from modules.workspace.components.store import Store
    from modules.workspace.components.workspace_data import (
        apply_pending_workspace,
        export_workspace,
        restore_dir,
    )
    from modules.workspace.tests.support.workspace_data import label, manager

    original = Store(tmp_path / "OutreachWorkbench/data")
    label(original, "Original comparison records")
    (original.root / "inbox/scan.csv").write_bytes(b"domain,ip\nexample.com,192.0.2.1\n")
    archive = export_workspace(original)
    try:
        baseline = tree_bytes(original.root.parent)
        chaos = Store(tmp_path / "ShadowserverCompanionChaos/data")
        label(chaos, "Empty comparison workspace")
        manager(chaos).stage("import", archive)
        assert chaos.settings()["office"] == "Empty comparison workspace"
        apply_pending_workspace(chaos.root)
        imported = Store(chaos.root)
        assert imported.settings()["office"] == "Original comparison records"
        assert (imported.root / "inbox/scan.csv").read_bytes() == (
            original.root / "inbox/scan.csv"
        ).read_bytes()
        label(imported, "Chaos-only change")
        assert tree_bytes(original.root.parent) == baseline
        assert list(restore_dir(imported.root).glob("*.zip"))
    finally:
        archive.unlink()


@pytest.mark.parametrize("old,new", [("standard", "chaos"), ("chaos", "standard")])
@pytest.mark.parametrize("reset", [False, True])
def test_cross_edition_install_overlay_rejected_before_cleanup(tmp_path, old, new, reset):
    root, staged = installation(tmp_path)
    mark_manifest(root / "payload-manifest.json", old)
    mark_manifest(staged, new)
    before = tree_bytes(root)
    with pytest.raises(upgrade.UpgradeError, match="Different application edition"):
        upgrade.cleanup(root, staged, reset_data=reset)
    assert tree_bytes(root) == before


def test_chaos_schema_guard_checks_only_chaos_workspace(tmp_path, monkeypatch):
    root, staged = installation(tmp_path)
    mark_manifest(root / "payload-manifest.json", "chaos")
    mark_manifest(staged, "chaos")
    data = json.loads(staged.read_text(encoding="utf-8"))
    data["database_schema_max"] = 10
    staged.write_text(json.dumps(data))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    baseline = tmp_path / "local/OutreachWorkbench/data/workbench.sqlite3"
    baseline.parent.mkdir(parents=True)
    baseline.write_bytes(b"Not a database: Chaos must not attempt to read this")
    before = baseline.read_bytes()
    upgrade.check_workspace_compatibility(data)
    chaos = tmp_path / "local/ShadowserverCompanionChaos/data/workbench.sqlite3"
    chaos.parent.mkdir(parents=True)
    with closing(sqlite3.connect(chaos)) as db, db:
        db.execute("PRAGMA user_version=999")
    with pytest.raises(upgrade.UpgradeError, match="schema 999"):
        upgrade.cleanup(root, staged)
    assert (root / "app/workbench/old.py").exists()
    assert baseline.read_bytes() == before


def test_generated_uninstall_inventory_is_confined_to_chaos_program_files(tmp_path):
    payload = tmp_path / "payload"
    program = tmp_path / "local/Programs/ShadowserverCompanionChaos"
    preserved = tmp_path / "local/Programs/OutreachWorkbench/app/run.py"
    preserved.parent.mkdir(parents=True)
    preserved.write_bytes(b"normal application")
    for root in (payload, program):
        (root / "app").mkdir(parents=True)
        (root / "app/run.py").write_bytes(b"Chaos program")
    for namespace in ("OutreachWorkbench", "ShadowserverCompanionChaos"):
        data = tmp_path / "local" / namespace / "data"
        data.mkdir(parents=True)
        (data / "records").write_bytes(namespace.encode())
    before = tree_bytes(tmp_path / "local")
    inventory = helper("build").uninstall_inventory(payload)
    lines = inventory.splitlines()
    assert lines[0] == "ClearErrors"
    guard = [
        "${If} ${Errors}",
        '  MessageBox MB_OK|MB_ICONSTOP "Some application files are still in use or could not be removed. Close the application and retry uninstall. Working records are retained." /SD IDOK',
        "  SetErrorLevel 5",
        "  Abort",
        "${EndIf}",
    ]
    guard_start = lines.index(guard[0])
    assert lines[guard_start : guard_start + len(guard)] == guard
    deletes = lines[1:guard_start]
    directories = lines[guard_start + len(guard) :]
    assert all(line.startswith('Delete "') for line in deletes)
    assert all(line.startswith('RMDir "') for line in directories)
    for line in deletes + directories:
        match = re.fullmatch(r'(Delete|RMDir) "\$INSTDIR\\(.+)"', line)
        assert match, line
        target = program.joinpath(*match[2].split("\\"))
        assert target.is_relative_to(program)
        target.unlink() if match[1] == "Delete" else target.rmdir()
    after = tree_bytes(tmp_path / "local")
    assert after == {
        k: v for k, v in before.items() if not k.startswith("Programs/ShadowserverCompanionChaos/")
    }
