"""DarkMatter is a third isolated identity; prior Chaos and standard homes stay intact."""

from contextlib import nullcontext
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

import run
from test_chaos_isolation_0981 import helper, tree_bytes
from test_upgrade_cleanup_072 import installation, upgrade
from workbench.release import check_output_name, installation_identity, load_release

ROOT = Path(__file__).resolve().parents[1]
NAMESPACES = ("OutreachWorkbench", "ShadowserverCompanionChaos", "ShadowserverCompanionDarkMatter")


def mark(path, edition, variant=""):
    data = json.loads(path.read_text())
    data["release"] = {"edition": edition, "variant": variant}
    path.write_text(json.dumps(data))


def test_dark_matter_metadata_and_all_three_identities_are_distinct(tmp_path):
    release = load_release()
    assert release["edition"] == "chaos" and release["variant"] == "dark_matter"
    assert release["channel"] == "candidate" and release["home_confirmation"] is None
    assert release["app_name"] == "Shadowserver Eclipse"
    assert release["display_version"] == f"{release['version']} (Release candidate)"
    identities = [
        installation_identity(),
        installation_identity("chaos"),
        installation_identity("chaos", "dark_matter"),
    ]
    assert [identity["app_id"] for identity in identities] == list(NAMESPACES)
    assert [(identity["port"], identity["demo_port"]) for identity in identities] == [
        (8877, 8878),
        (8879, 8880),
        (8881, 8882),
    ]
    for index, identity in enumerate(identities):
        for other in identities[index + 1 :]:
            assert not set(identity.values()) & set(other.values())
    for name in (
        "Companion-professional-review-rc-darkmatter.exe",
        "Companion-dark-matter-rc.zip",
    ):
        check_output_name(Path(name), release)
    with pytest.raises(ValueError, match="DarkMatter release filenames"):
        check_output_name(Path("Companion-rc.exe"), release)
    with pytest.raises(ValueError, match="Release candidate filenames"):
        check_output_name(Path("Companion-darkmatter.exe"), release)
    for variant in (None, [], "../ShadowserverCompanionChaos", "unknown"):
        with pytest.raises(ValueError, match="variant"):
            installation_identity("chaos", variant)
    with pytest.raises(ValueError, match="requires"):
        installation_identity("standard", "dark_matter")
    (tmp_path / "VERSION").write_text("0.9.82")
    data = {
        "schema": 1,
        "version": "0.9.82",
        "channel": "stable",
        "edition": "chaos",
        "variant": "dark_matter",
        "home_confirmation": {
            "version": "0.9.82",
            "confirmed_by": "Synthetic",
            "confirmed_at": "2026-11-11T00:00:00Z",
            "notes": "Synthetic gate test",
        },
    }
    (tmp_path / "RELEASE.json").write_text(json.dumps(data))
    assert load_release(tmp_path)["channel"] == "stable"


@pytest.mark.parametrize("demo,expected_port", [(False, 8881), (True, 8882)])
def test_dark_matter_source_and_installed_launch_defaults(
    tmp_path, monkeypatch, demo, expected_port
):
    desktop = helper("desktop")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    expected = tmp_path / NAMESPACES[2] / ("data-demo" if demo else "data")
    assert desktop.default_workspace(demo) == expected
    assert desktop.RUNNING_MUTEX == "Local\\ShadowserverCompanionDarkMatter.Installed.Running"
    recorded = []
    monkeypatch.setattr(desktop, "configure_logging", lambda path: recorded.append(path))
    monkeypatch.setattr(desktop, "hold_installation_mutex", lambda: None)
    monkeypatch.setattr(
        desktop,
        "existing_instance",
        lambda port, path, is_demo: recorded.append((port, path, is_demo)) or "http://local",
    )
    desktop.main(["--no-browser", *(["--demo"] if demo else [])])
    assert recorded == [expected, (expected_port, expected, demo)]
    recorded.clear()
    monkeypatch.setattr(sys, "argv", ["run.py", "--no-browser", *(["--demo"] if demo else [])])
    monkeypatch.setattr(run, "workspace_session", lambda path: nullcontext())
    monkeypatch.setattr(
        run, "serve", lambda args, data, preview: recorded.append((args.port, data))
    )
    run.main()
    assert recorded == [(expected_port, ROOT / ("data-demo" if demo else "data"))]
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("namespace", NAMESPACES[:2])
def test_foreign_installed_workspaces_rejected_before_any_log_or_data_write(
    tmp_path, monkeypatch, namespace
):
    desktop = helper("desktop")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    foreign = tmp_path / namespace / "data"
    foreign.mkdir(parents=True)
    (foreign / "sentinel").write_bytes(b"Protected previous-edition records")
    before = tree_bytes(tmp_path)
    with pytest.raises(ValueError, match="Export a backup"):
        desktop.main(["--data-dir", str(foreign), "--no-browser"])
    monkeypatch.setattr(sys, "argv", ["run.py", "--data-dir", str(foreign), "--no-browser"])
    with pytest.raises(SystemExit) as stopped:
        run.main()
    assert stopped.value.code == 2
    assert tree_bytes(tmp_path) == before
    assert not (tmp_path / NAMESPACES[2]).exists()
    assert not (foreign.parent / "data-logs").exists()


def test_credentials_logs_restore_points_and_transfers_stay_in_dark_matter(tmp_path, monkeypatch):
    from workbench.api_acquisition import APIAcquisition
    from workbench.local_session import LocalSessions, read_instance, write_instance
    from workbench.workspace_data import restore_dir, transfer_dir

    desktop = helper("desktop")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    workspaces = [tmp_path / name / "data" for name in NAMESPACES]
    dark = desktop.default_workspace()
    assert dark == workspaces[2]
    assert restore_dir(dark) == tmp_path / NAMESPACES[2] / "data-restore-points"
    assert transfer_dir(dark) == tmp_path / NAMESPACES[2] / ".data-companion-transfer"
    captured = []
    monkeypatch.setattr(
        desktop.logging, "basicConfig", lambda **kwargs: captured.extend(kwargs["handlers"])
    )
    monkeypatch.setattr(desktop.tempfile, "gettempdir", lambda: str(tmp_path / "temporary"))
    try:
        assert desktop.configure_logging(dark) == tmp_path / NAMESPACES[2] / "data-logs"
        assert desktop.configure_logging() == tmp_path / "temporary" / (NAMESPACES[2] + "-startup")
    finally:
        for handler in captured:
            handler.close()
    services = [APIAcquisition(SimpleNamespace(root=workspace), None) for workspace in workspaces]
    try:
        assert len({service.windows.profile for service in services}) == 3
    finally:
        for service in services:
            service.close()
    keys = []
    for index, workspace in enumerate(workspaces):
        workspace.mkdir(parents=True, exist_ok=True)
        sessions = LocalSessions()
        write_instance(workspace, 8877 + index * 2, False, sessions)
        keys.append(read_instance(workspace, 8877 + index * 2, False))
        with pytest.raises(ValueError, match="different workspace"):
            read_instance(workspace, 8888, False)
    assert len(set(keys)) == 3


def test_standalone_dark_matter_fresh_start_preserves_both_previous_installs(tmp_path):
    for namespace in NAMESPACES:
        for folder in (
            "data",
            "data-demo",
            "data-logs",
            ".data-companion-transfer",
            "data-restore-points",
        ):
            path = tmp_path / namespace / folder
            path.mkdir(parents=True)
            (path / "sentinel").write_bytes((namespace + "/" + folder).encode())
    before = {namespace: tree_bytes(tmp_path / namespace) for namespace in NAMESPACES[:2]}
    import os

    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            str(ROOT / "tools/windows_installer/workspace_data.py"),
            "--confirmation",
            "DELETE",
            "--edition",
            "chaos",
            "--variant",
            "dark_matter",
        ],
        env={**os.environ, "LOCALAPPDATA": str(tmp_path)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    for namespace in NAMESPACES[:2]:
        assert tree_bytes(tmp_path / namespace) == before[namespace]
    dark = tmp_path / NAMESPACES[2]
    assert not list((dark / "data").iterdir())
    assert not (dark / ".data-companion-transfer").exists()
    assert not (dark / "data-restore-points").exists()
    assert (dark / "data-demo/sentinel").exists() and (dark / "data-logs/sentinel").exists()
    retained = tree_bytes(tmp_path)
    with pytest.raises(ValueError, match="variant"):
        helper("workspace_data").start_fresh(
            tmp_path, edition="chaos", variant="../OutreachWorkbench"
        )
    assert tree_bytes(tmp_path) == retained


@pytest.mark.parametrize(
    "old,new",
    [
        (("standard", ""), ("chaos", "dark_matter")),
        (("chaos", ""), ("chaos", "dark_matter")),
        (("chaos", "dark_matter"), ("standard", "")),
        (("chaos", "dark_matter"), ("chaos", "")),
    ],
)
@pytest.mark.parametrize("reset", [False, True])
def test_cross_variant_overlay_rejected_before_program_cleanup(tmp_path, old, new, reset):
    root, staged = installation(tmp_path)
    mark(root / "payload-manifest.json", *old)
    mark(staged, *new)
    before = tree_bytes(root)
    with pytest.raises(upgrade.UpgradeError, match="Different application edition or variant"):
        upgrade.cleanup(root, staged, reset_data=reset)
    assert tree_bytes(root) == before


def test_schema_guard_checks_only_dark_matter_database(tmp_path, monkeypatch):
    root, staged = installation(tmp_path)
    mark(root / "payload-manifest.json", "chaos", "dark_matter")
    mark(staged, "chaos", "dark_matter")
    data = json.loads(staged.read_text())
    data["database_schema_max"] = 10
    staged.write_text(json.dumps(data))
    local = tmp_path / "local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    for namespace in NAMESPACES[:2]:
        database = local / namespace / "data/workbench.sqlite3"
        database.parent.mkdir(parents=True)
        database.write_bytes(b"Foreign database must not be read")
    before = tree_bytes(local)
    upgrade.check_workspace_compatibility(data)
    assert tree_bytes(local) == before
    database = local / NAMESPACES[2] / "data/workbench.sqlite3"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as db:
        db.execute("PRAGMA user_version=999")
    before = tree_bytes(local)
    with pytest.raises(upgrade.UpgradeError, match="schema 999"):
        upgrade.cleanup(root, staged)
    assert tree_bytes(local) == before
    assert (root / "app/workbench/old.py").exists()


def test_dark_matter_installer_definitions_namespace_every_managed_surface():
    config = helper("build").installer_definitions(load_release())
    assert config["APP_ID"] == NAMESPACES[2]
    assert config["APP_EDITION"] == "chaos" and config["APP_VARIANT"] == "dark_matter"
    assert config["DEMO_NAME"] == "Shadowserver Eclipse Demo"
    script = (ROOT / "tools/windows_installer/installer.nsi").read_text()
    script = re.sub(r'!if "\$\{APP_EDITION\}" == "standard"\n.*?!endif', "", script, flags=re.S)
    for key, value in config.items():
        script = script.replace("${" + key + "}", value)
    assert "OutreachWorkbench" not in script and "ShadowserverCompanionChaos" not in script
    for value in (
        'InstallDir "$LOCALAPPDATA\\Programs\\ShadowserverCompanionDarkMatter"',
        '!define KEY "Software\\ShadowserverCompanionDarkMatter"',
        "Uninstall\\ShadowserverCompanionDarkMatter",
        "Local\\ShadowserverCompanionDarkMatter.Installed.Running",
        "$DESKTOP\\Shadowserver Eclipse.lnk",
        "Shadowserver Eclipse Demo.lnk",
        '--edition chaos --variant "dark_matter"',
        "data-restore-points",
        "data-logs",
    ):
        assert value in script
    assert 'GetFullPathName $1 "$LOCALAPPDATA\\Programs\\ShadowserverCompanionDarkMatter"' in script
    assert "RMDir /r" not in script


@pytest.mark.parametrize(
    "edition,variant,prefix",
    [
        ("standard", "", "shadowserver-companion"),
        ("chaos", "", "shadowserver-companion-chaos"),
        ("chaos", "dark_matter", "shadowserver-eclipse"),
    ],
)
def test_source_zip_extracts_into_distinct_program_directory(
    tmp_path, monkeypatch, edition, variant, prefix
):
    import importlib.util
    import zipfile

    spec = importlib.util.spec_from_file_location(
        "isolated_source_builder", ROOT / "tools/build_release.py"
    )
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    source = tmp_path / "synthetic-source"
    source.mkdir()
    (source / "VERSION").write_text("0.9.82")
    (source / "run.py").write_text("# synthetic release source\n")
    release = {"version": "0.9.82", "channel": "unstable", "edition": edition, "variant": variant}
    output = tmp_path / "Companion-chaos-unstable-darkmatter.zip"
    monkeypatch.setattr(builder, "ROOT", source)
    monkeypatch.setattr(builder, "verify_release", lambda root: release)
    monkeypatch.setattr(builder, "verify_dependencies", lambda root: None)
    monkeypatch.setattr(builder, "verify_architecture", lambda root: None)
    monkeypatch.setattr(sys, "argv", ["build_release.py", str(output)])
    builder.main()
    with zipfile.ZipFile(output) as archive:
        assert {name.split("/")[0] for name in archive.namelist()} == {prefix}
        assert archive.read(prefix + "/run.py") == b"# synthetic release source\n"
        manifest = json.loads(archive.read(prefix + "/release-manifest.json"))
        assert manifest["release"]["variant"] == variant


@pytest.mark.parametrize("edition", ["standard", "chaos"])
def test_legacy_fresh_start_never_touches_dark_matter(tmp_path, edition):
    dark = tmp_path / NAMESPACES[2] / "data"
    dark.mkdir(parents=True)
    (dark / "sentinel").write_bytes(b"DarkMatter records")
    before = tree_bytes(dark.parent)
    helper("workspace_data").start_fresh(tmp_path, edition=edition)
    assert tree_bytes(dark.parent) == before
