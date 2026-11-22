"""Installed readiness follows complete bytes; immutable launchers retain ownership."""

import hashlib
import json
from pathlib import Path

import pytest

from tests.support.installation import tree_bytes, upgrade


def staged(tmp_path, tag="first", version="0.12.0"):
    source = tmp_path / f"{tag}.exe"
    source.write_bytes(b"synthetic bootstrap " + tag.encode())
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    files = {"app/desktop.py": f"application {tag}".encode(), "runtime/python.exe": b"runtime"}
    metadata = {
        "distribution_policy": upgrade.POLICY,
        "application_version": version,
        "release": {"edition": "standard"},
        "files": {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()},
        "bootstrap": {"protocol": 1, "path": f"bootstrap/launch-{digest}.exe", "sha256": digest},
    }
    manifest = tmp_path / f"{tag}.json"
    manifest.write_text(json.dumps(metadata), encoding="utf-8")
    return source, manifest, metadata, files


def copy_payload(root, manifest, files):
    for name, raw in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    (root / "payload-manifest.json").write_bytes(manifest.read_bytes())


@pytest.fixture
def phase_calls(monkeypatch):
    calls = []

    def transition(action, root, metadata, launcher, **options):
        calls.append((action, (root / upgrade.READY_MARKER).exists()))

    monkeypatch.setattr(upgrade, "_schedule_transition", transition)
    return calls


def install(root, payload):
    source, manifest, _metadata, files = payload
    upgrade.prepare_installation(root, manifest, source)
    copy_payload(root, manifest, files)
    upgrade.commit_installation(root, manifest)


def test_readiness_requires_complete_verified_payload_and_task_commit(tmp_path, phase_calls):
    root = tmp_path / "program"
    source, manifest, metadata, files = staged(tmp_path)
    upgrade.prepare_installation(root, manifest, source)
    assert not (root / upgrade.READY_MARKER).exists()
    with pytest.raises((OSError, upgrade.UpgradeError)):
        upgrade.commit_installation(root, manifest)
    assert not (root / upgrade.READY_MARKER).exists()
    copy_payload(root, manifest, files)
    (root / "runtime/python.exe").write_bytes(b"partial runtime")
    with pytest.raises(upgrade.UpgradeError, match="incomplete"):
        upgrade.commit_installation(root, manifest)
    assert not (root / upgrade.READY_MARKER).exists()
    copy_payload(root, manifest, files)
    upgrade.commit_installation(root, manifest)
    assert "app_id=OutreachWorkbench" in (root / upgrade.READY_MARKER).read_text(encoding="ascii")
    ledger = upgrade.bootstrap_ledger(root, metadata)
    assert ledger["active"] == metadata["bootstrap"]["path"]
    assert phase_calls == [("prepare_upgrade", False), ("commit_upgrade", False)]


def test_upgrade_keeps_loaded_old_launcher_bytes_and_commits_new_owner(tmp_path, phase_calls):
    root = tmp_path / "program"
    first = staged(tmp_path)
    install(root, first)
    old_launcher = root / first[2]["bootstrap"]["path"]
    before = old_launcher.read_bytes(), old_launcher.stat().st_mtime_ns
    sentinel = root / "notes.txt"
    sentinel.write_text("unrelated file", encoding="utf-8")
    second = staged(tmp_path, "second", "0.12.1")
    upgrade.prepare_installation(root, second[1], second[0])
    assert not (root / upgrade.READY_MARKER).exists()
    assert (old_launcher.read_bytes(), old_launcher.stat().st_mtime_ns) == before
    copy_payload(root, second[1], second[3])
    upgrade.commit_installation(root, second[1])
    ledger = upgrade.bootstrap_ledger(root, second[2])
    assert len(ledger["files"]) == 2
    assert ledger["active"] == second[2]["bootstrap"]["path"]
    assert sentinel.read_text(encoding="utf-8") == "unrelated file"


def test_full_ledger_rejects_new_launcher_before_mutation_but_allows_repair(tmp_path, phase_calls):
    root = tmp_path / "program"
    first = staged(tmp_path)
    install(root, first)
    ledger = upgrade.bootstrap_ledger(root, first[2])
    for number in range(127):
        digest = hashlib.sha256(f"Historical bootstrap {number}".encode()).hexdigest()
        ledger["files"][f"bootstrap/launch-{digest}.exe"] = digest
    (root / upgrade.BOOTSTRAP_LEDGER).write_text(json.dumps(ledger), encoding="utf-8")
    before = tree_bytes(root)
    phase_calls.clear()
    second = staged(tmp_path, "second", "0.12.1")

    with pytest.raises(upgrade.UpgradeError, match="ledger is full"):
        upgrade.prepare_installation(root, second[1], second[0])

    assert tree_bytes(root) == before
    assert phase_calls == []
    assert len(upgrade.bootstrap_ledger(root, first[2])["files"]) == 128
    # Reusing an already owned executable needs no new ledger capacity.
    launcher = root / first[2]["bootstrap"]["path"]
    modified = launcher.stat().st_mtime_ns
    install(root, first)
    assert launcher.stat().st_mtime_ns == modified
    assert (root / upgrade.READY_MARKER).is_file()
    assert len(upgrade.bootstrap_ledger(root, first[2])["files"]) == 128


@pytest.mark.parametrize("enabled", [False, True])
def test_missing_ledger_recovers_owned_task_and_preserves_schedule(tmp_path, monkeypatch, enabled):
    from modules.accretion.components import windows_schedule as schedule

    root = tmp_path / "program"
    first = staged(tmp_path)
    with monkeypatch.context() as seed:
        seed.setattr(upgrade, "_schedule_transition", lambda *args, **kwargs: None)
        install(root, first)
    local = tmp_path / "LocalAppData"
    workspace = local / "OutreachWorkbench/data"
    workspace.mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    sid = "S-1-5-21-1-2-3-1001"
    xml = schedule.task_xml(
        workspace,
        root / "runtime/pythonw.exe",
        root / "app/modules/accretion/tools/run_scheduled.py",
        sid,
    ).decode("utf-16")
    original = schedule._migrated_xml(xml, workspace, root / first[2]["bootstrap"]["path"], enabled)
    task = {"xml": original}
    operations = []

    def operation(data_dir, action="query", *, expected_xml=None, xml=None, runner=None):
        assert Path(data_dir) == workspace
        operations.append(action)
        if action != "query":
            assert task["xml"] == expected_xml
        if action == "disable":
            tree = schedule._xml(task["xml"])
            schedule._one(tree, "Settings/Enabled").text = "false"
            task["xml"] = schedule.ET.tostring(tree, encoding="unicode")
        elif action == "register":
            task["xml"] = xml
        else:
            assert action == "query"
        active = schedule._one(schedule._xml(task["xml"]), "Settings/Enabled").text == "true"
        return {
            "exists": True,
            "xml": task["xml"],
            "sid": sid,
            "enabled": active,
            "state": 3 if active else 1,
            "instances": 0,
        }

    monkeypatch.setattr(schedule, "_task_operation", operation)
    # The installer stages this standard-library adapter beside the helper.
    # Keep its real ownership/migration logic and replace only module loading/COM.
    monkeypatch.setattr(
        upgrade.runpy,
        "run_path",
        lambda path: {
            "prepare_upgrade": schedule.prepare_upgrade,
            "commit_upgrade": schedule.commit_upgrade,
        },
    )
    (root / upgrade.BOOTSTRAP_LEDGER).unlink()
    second = staged(tmp_path, "second", "0.12.1")
    upgrade.prepare_installation(root, second[1], second[0])
    assert not (root / upgrade.READY_MARKER).exists()
    assert schedule._one(schedule._xml(task["xml"]), "Settings/Enabled").text == "false"
    assert (root / upgrade.TASK_JOURNAL).exists()
    recovered = upgrade.bootstrap_ledger(root, second[2])
    assert recovered["files"][first[2]["bootstrap"]["path"]] == first[2]["bootstrap"]["sha256"]

    copy_payload(root, second[1], second[3])
    upgrade.commit_installation(root, second[1])

    complete = schedule._xml(task["xml"])
    assert schedule._one(complete, "Actions/Exec/Command").text == str(
        root / second[2]["bootstrap"]["path"]
    )
    assert (schedule._one(complete, "Settings/Enabled").text == "true") is enabled
    assert schedule._shape(original, ignore_action=True) == schedule._shape(
        task["xml"], ignore_action=True
    )
    assert operations == ["query", "disable", "query", "register"]
    assert upgrade.bootstrap_ledger(root, second[2])["active"] == second[2]["bootstrap"]["path"]
    assert (root / upgrade.READY_MARKER).is_file()
    assert not (root / upgrade.TASK_JOURNAL).exists()


def test_interrupted_copy_can_be_repaired_without_replacing_bootstrap(tmp_path, phase_calls):
    root = tmp_path / "program"
    payload = staged(tmp_path)
    source, manifest, metadata, files = payload
    upgrade.prepare_installation(root, manifest, source)
    launcher = root / metadata["bootstrap"]["path"]
    before = launcher.stat().st_mtime_ns
    (root / "runtime").mkdir()
    (root / "runtime/python.exe").write_bytes(b"interrupted copy")
    upgrade.prepare_installation(root, manifest, source, known_installation=True)
    assert launcher.stat().st_mtime_ns == before
    copy_payload(root, manifest, files)
    upgrade.commit_installation(root, manifest)
    assert (root / upgrade.READY_MARKER).is_file()


def test_changed_owned_bootstrap_stops_before_any_payload_or_ready_changes(tmp_path, phase_calls):
    root = tmp_path / "program"
    first = staged(tmp_path)
    install(root, first)
    (root / first[2]["bootstrap"]["path"]).write_bytes(b"changed executable")
    before = (root / "app/desktop.py").read_bytes(), (root / upgrade.READY_MARKER).read_bytes()
    second = staged(tmp_path, "second", "0.12.1")
    with pytest.raises(upgrade.UpgradeError, match="modified"):
        upgrade.prepare_installation(root, second[1], second[0])
    assert (
        (root / "app/desktop.py").read_bytes(),
        (root / upgrade.READY_MARKER).read_bytes(),
    ) == before


def test_unknown_task_cannot_trigger_program_replacement(tmp_path, phase_calls, monkeypatch):
    root = tmp_path / "program"
    first = staged(tmp_path)
    install(root, first)
    before = (root / "app/desktop.py").read_bytes(), (root / upgrade.READY_MARKER).read_bytes()

    def reject(*args, **kwargs):
        raise ValueError("unrecognized task action")

    monkeypatch.setattr(upgrade, "_schedule_transition", reject)
    second = staged(tmp_path, "second", "0.12.1")
    with pytest.raises(ValueError, match="unrecognized"):
        upgrade.prepare_installation(root, second[1], second[0])
    assert (
        (root / "app/desktop.py").read_bytes(),
        (root / upgrade.READY_MARKER).read_bytes(),
    ) == before


def test_task_commit_failure_leaves_complete_program_inert_for_repair(
    tmp_path, phase_calls, monkeypatch
):
    root = tmp_path / "program"
    source, manifest, metadata, files = staged(tmp_path)
    upgrade.prepare_installation(root, manifest, source)
    copy_payload(root, manifest, files)

    def reject(*args, **kwargs):
        raise ValueError("task action changed")

    monkeypatch.setattr(upgrade, "_schedule_transition", reject)
    with pytest.raises(ValueError, match="changed"):
        upgrade.commit_installation(root, manifest)
    assert not (root / upgrade.READY_MARKER).exists()
    assert (root / metadata["bootstrap"]["path"]).is_file()


def test_uninstall_withdraws_readiness_and_removes_only_owned_launchers(
    tmp_path, phase_calls, monkeypatch
):
    root = tmp_path / "program"
    payload = staged(tmp_path)
    install(root, payload)
    unrelated = root / "bootstrap/unrelated.exe"
    unrelated.write_bytes(b"unowned bytes")
    monkeypatch.setattr(upgrade, "remove_scheduled_task", lambda *args, **kwargs: None)
    upgrade.uninstall(root, payload[1])
    assert not (root / upgrade.READY_MARKER).exists()
    upgrade.remove_bootstraps(root, payload[1])
    assert not (root / payload[2]["bootstrap"]["path"]).exists()
    assert not (root / upgrade.BOOTSTRAP_LEDGER).exists()
    assert unrelated.read_bytes() == b"unowned bytes"


def test_uninstall_retains_ownership_when_a_waiting_launcher_stays_locked(
    tmp_path, phase_calls, monkeypatch
):
    root = tmp_path / "program"
    payload = staged(tmp_path)
    install(root, payload)
    (root / upgrade.READY_MARKER).unlink()
    launcher = root / payload[2]["bootstrap"]["path"]
    unlink = Path.unlink

    def locked(path, *args, **kwargs):
        if path == launcher:
            raise PermissionError("synthetic loaded image")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", locked)
    with pytest.raises(upgrade.UpgradeError, match="retry uninstall"):
        upgrade.remove_bootstraps(root, payload[1], wait_seconds=0)
    assert launcher.is_file()
    assert (root / upgrade.BOOTSTRAP_LEDGER).is_file()


def test_embedded_inventory_removes_current_launcher_after_local_metadata_loss(
    tmp_path, phase_calls
):
    root = tmp_path / "program"
    payload = staged(tmp_path)
    install(root, payload)
    (root / upgrade.READY_MARKER).unlink()
    (root / upgrade.BOOTSTRAP_LEDGER).unlink()
    (root / "payload-manifest.json").unlink()
    upgrade.remove_bootstraps(root, payload[1])
    assert not (root / payload[2]["bootstrap"]["path"]).exists()


@pytest.mark.parametrize("active", [[], {}, 1, "../outside.exe"])
def test_invalid_ownership_state_is_rejected_as_validation_error(tmp_path, active):
    root = tmp_path / "program"
    root.mkdir()
    payload = staged(tmp_path)
    (root / upgrade.BOOTSTRAP_LEDGER).write_text(
        json.dumps({"schema": 1, "app_id": "OutreachWorkbench", "active": active, "files": {}}),
        encoding="utf-8",
    )
    with pytest.raises(upgrade.UpgradeError, match="ledger"):
        upgrade.bootstrap_ledger(root, payload[2])
