"""Owned synthetic Task Scheduler state; never reads or changes real user tasks."""

import base64
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
from types import SimpleNamespace

import pytest

from modules.accretion.components import windows_schedule as schedule


SID = "S-1-5-21-1-2-3-1001"


def set_xml(text, path, value):
    tree = schedule._xml(text)
    parent_path, name = path.rsplit("/", 1)
    parent = schedule._one(tree, parent_path)
    node = parent.find("{" + schedule._NS + "}" + name)
    if node is None:
        node = schedule.ET.SubElement(parent, "{" + schedule._NS + "}" + name)
    node.text = value
    return schedule.ET.tostring(tree, encoding="unicode")


class Tasks:
    def __init__(self, xml=None):
        self.xml = xml
        self.state = 3 if xml and self.enabled else 1
        self.instances = 0
        self.calls = []
        self.race_instances = 0
        self.fail_after_register = False

    @property
    def enabled(self):
        if self.xml is None:
            return False
        node = schedule._xml(self.xml).find(
            "{" + schedule._NS + "}Settings/{" + schedule._NS + "}Enabled"
        )
        return node is None or node.text == "true"

    def snapshot(self):
        return {
            "exists": self.xml is not None,
            "sid": SID,
            "xml": self.xml,
            "enabled": self.enabled,
            "state": self.state,
            "instances": self.instances,
        }

    def __call__(self, workspace, operation="query", *, expected_xml=None, xml=None, runner=None):
        self.calls.append(operation)
        if operation != "query":
            assert self.xml == expected_xml, "Task changed before mutation"
        if operation == "disable":
            self.xml = set_xml(self.xml, "Settings/Enabled", "false")
            self.state = 1
            self.instances = self.race_instances
        elif operation == "register":
            self.xml = xml
            self.state = 3 if self.enabled else 1
            if self.fail_after_register:
                self.fail_after_register = False
                raise ValueError("Synthetic interrupted registration acknowledgement")
        elif operation == "delete":
            assert not self.enabled and self.instances == 0
            self.xml = None
        return self.snapshot()


@pytest.fixture
def installation(tmp_path):
    root = tmp_path / "Program & Zoë"
    (root / "bootstrap").mkdir(parents=True)
    workspace = tmp_path / "Synthetic records & Zoë"
    workspace.mkdir()
    launcher = add_launcher(root, b"Synthetic immutable bootstrap; never executed")
    (root / "installation-ready.ini").write_text(
        "[installation]\napp_id=OutreachWorkbench\nprotocol=1\n", encoding="utf-8"
    )
    sentinel = root / "retained-program.bin"
    sentinel.write_bytes(b"program files must not change during task preflight")
    return root, workspace, launcher, root / "installation-task.json"


def add_launcher(root, data):
    digest = hashlib.sha256(data).hexdigest()
    name = f"bootstrap/launch-{digest}.exe"
    path = root / name
    path.write_bytes(data)
    ledger_path = root / "bootstrap-ledger.json"
    ledger = (
        json.loads(ledger_path.read_text(encoding="utf-8"))
        if ledger_path.exists()
        else {"schema": 1, "app_id": "OutreachWorkbench", "active": name, "files": {}}
    )
    ledger["files"][name] = digest
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    return path


def legacy(root, workspace, *, modular=False, windowless=True, enabled=True):
    script = root / (
        "app/modules/accretion/tools/run_scheduled.py" if modular else "app/tools/run_scheduled.py"
    )
    xml = schedule.task_xml(
        workspace,
        root / "runtime" / ("pythonw.exe" if windowless else "python.exe"),
        script,
        SID,
        current=datetime(2026, 11, 21),
    ).decode("utf-16")
    xml = set_xml(xml, "Triggers/CalendarTrigger/Repetition/Interval", "PT2H")
    return set_xml(xml, "Settings/Enabled", "true" if enabled else "false")


@pytest.mark.parametrize("modular", [False, True])
@pytest.mark.parametrize("windowless", [False, True])
@pytest.mark.parametrize("enabled", [False, True])
def test_upgrade_moves_only_action_preserving_schedule_and_enabled_intent(
    installation, monkeypatch, modular, windowless, enabled
):
    root, workspace, launcher, journal = installation
    original = legacy(root, workspace, modular=modular, windowless=windowless, enabled=enabled)
    tasks = Tasks(original)
    monkeypatch.setattr(schedule, "_task_operation", tasks)
    result = schedule.prepare_upgrade(root, workspace, launcher, journal_path=journal)
    assert result == {"installed": True, "enabled": enabled}
    saved = json.loads(journal.read_text(encoding="utf-8"))
    assert saved["original_xml"] == original and saved["enabled"] is enabled
    assert not tasks.enabled and tasks.instances == 0
    assert schedule.commit_upgrade(root, workspace, launcher, journal_path=journal) == result
    assert not journal.exists() and tasks.enabled is enabled
    tree = schedule._xml(tasks.xml)
    assert schedule._one(tree, "Actions/Exec/Command").text == str(launcher)
    assert schedule._one(tree, "Actions/Exec/Arguments").text == subprocess.list2cmdline(
        ["--scheduled", "--data-dir", str(workspace.resolve())]
    )
    assert schedule._one(tree, "Actions/Exec/WorkingDirectory").text == str(root)
    assert schedule._shape(original, ignore_action=True) == schedule._shape(
        tasks.xml, ignore_action=True
    )
    assert (
        root / "retained-program.bin"
    ).read_bytes() == b"program files must not change during task preflight"


def test_missing_task_does_not_create_a_schedule(installation, monkeypatch):
    root, workspace, launcher, journal = installation
    tasks = Tasks()
    monkeypatch.setattr(schedule, "_task_operation", tasks)
    assert schedule.prepare_upgrade(root, workspace, launcher, journal_path=journal) == {
        "installed": False
    }
    assert schedule.commit_upgrade(root, workspace, launcher, journal_path=journal) == {
        "installed": False
    }
    assert not journal.exists() and tasks.calls == ["query", "query"]


@pytest.mark.parametrize(
    "state,instances,enabled",
    [(4, 0, True), (2, 0, True), (1, 1, False), (3, 1, True), (0, 0, False)],
)
def test_busy_or_unverifiable_task_stops_before_journal_or_task_changes(
    installation, monkeypatch, state, instances, enabled
):
    root, workspace, launcher, journal = installation
    tasks = Tasks(legacy(root, workspace, enabled=enabled))
    tasks.state, tasks.instances = state, instances
    original = tasks.xml
    monkeypatch.setattr(schedule, "_task_operation", tasks)
    with pytest.raises(ValueError, match="queued or running"):
        schedule.prepare_upgrade(root, workspace, launcher, journal_path=journal)
    assert not journal.exists() and tasks.xml == original and tasks.calls == ["query"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("Actions/Exec/Command", "C:\\unowned\\python.exe"),
        ("Actions/Exec/Arguments", "--data-dir unrelated"),
        ("Actions/Exec/WorkingDirectory", "C:\\unowned"),
        ("Principals/Principal/UserId", "S-1-5-21-999"),
        ("Principals/Principal/LogonType", "Password"),
        ("Principals/Principal/RunLevel", "HighestAvailable"),
    ],
)
def test_unknown_actions_or_identity_are_never_disabled_or_overwritten(
    installation, monkeypatch, field, value
):
    root, workspace, launcher, journal = installation
    tasks = Tasks(set_xml(legacy(root, workspace), field, value))
    original = tasks.xml
    monkeypatch.setattr(schedule, "_task_operation", tasks)
    with pytest.raises(ValueError):
        schedule.prepare_upgrade(root, workspace, launcher, journal_path=journal)
    assert tasks.xml == original and tasks.calls == ["query"] and not journal.exists()


def test_instance_started_during_disable_keeps_journal_for_safe_retry(installation, monkeypatch):
    root, workspace, launcher, journal = installation
    tasks = Tasks(legacy(root, workspace))
    tasks.race_instances = 1
    monkeypatch.setattr(schedule, "_task_operation", tasks)
    with pytest.raises(ValueError, match="queued or running"):
        schedule.prepare_upgrade(root, workspace, launcher, journal_path=journal)
    assert journal.exists() and not tasks.enabled
    tasks.race_instances = tasks.instances = 0
    schedule.prepare_upgrade(root, workspace, launcher, journal_path=journal)
    schedule.commit_upgrade(root, workspace, launcher, journal_path=journal)
    assert tasks.enabled and not journal.exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("Actions/Exec/Arguments", "unexpected action"),
        ("Triggers/CalendarTrigger/Repetition/Interval", "PT1M"),
    ],
)
def test_commit_rejects_external_task_drift(installation, monkeypatch, field, value):
    root, workspace, launcher, journal = installation
    tasks = Tasks(legacy(root, workspace))
    monkeypatch.setattr(schedule, "_task_operation", tasks)
    schedule.prepare_upgrade(root, workspace, launcher, journal_path=journal)
    tasks.xml = set_xml(tasks.xml, field, value)
    original = tasks.xml
    with pytest.raises(ValueError, match="changed"):
        schedule.commit_upgrade(root, workspace, launcher, journal_path=journal)
    assert tasks.xml == original and journal.exists() and "register" not in tasks.calls


def test_interrupted_commit_can_be_acknowledged_without_second_registration(
    installation, monkeypatch
):
    root, workspace, launcher, journal = installation
    tasks = Tasks(legacy(root, workspace))
    monkeypatch.setattr(schedule, "_task_operation", tasks)
    schedule.prepare_upgrade(root, workspace, launcher, journal_path=journal)
    tasks.fail_after_register = True
    with pytest.raises(ValueError, match="interrupted"):
        schedule.commit_upgrade(root, workspace, launcher, journal_path=journal)
    assert tasks.enabled and journal.exists()
    # A newly migrated bootstrap may now be waiting at the installer's start gate.
    tasks.state, tasks.instances = 4, 1
    schedule.commit_upgrade(root, workspace, launcher, journal_path=journal)
    assert tasks.calls.count("register") == 1 and not journal.exists()


def test_repair_to_newer_launcher_preserves_first_enabled_state_and_original_xml(
    installation, monkeypatch
):
    root, workspace, first, journal = installation
    original = legacy(root, workspace)
    tasks = Tasks(original)
    monkeypatch.setattr(schedule, "_task_operation", tasks)
    schedule.prepare_upgrade(root, workspace, first, journal_path=journal)
    tasks.fail_after_register = True
    with pytest.raises(ValueError):
        schedule.commit_upgrade(root, workspace, first, journal_path=journal)
    second = add_launcher(root, b"Synthetic second immutable bootstrap")
    schedule.prepare_upgrade(root, workspace, second, journal_path=journal)
    saved = json.loads(journal.read_text(encoding="utf-8"))
    assert saved["original_xml"] == original and saved["enabled"] is True
    schedule.commit_upgrade(root, workspace, second, journal_path=journal)
    assert schedule._one(schedule._xml(tasks.xml), "Actions/Exec/Command").text == str(second)


def test_deleted_task_is_not_resurrected_from_upgrade_journal(installation, monkeypatch):
    root, workspace, launcher, journal = installation
    tasks = Tasks(legacy(root, workspace))
    monkeypatch.setattr(schedule, "_task_operation", tasks)
    schedule.prepare_upgrade(root, workspace, launcher, journal_path=journal)
    tasks.xml = None
    assert schedule.commit_upgrade(root, workspace, launcher, journal_path=journal) == {
        "installed": False
    }
    assert not journal.exists() and "register" not in tasks.calls


def test_unicode_task_journal_stays_readable_within_declared_limits(installation, monkeypatch):
    root, workspace, launcher, journal = installation
    original = set_xml(legacy(root, workspace), "RegistrationInfo/Description", "é" * 60000)
    tasks = Tasks(original)
    monkeypatch.setattr(schedule, "_task_operation", tasks)
    schedule.prepare_upgrade(root, workspace, launcher, journal_path=journal)
    assert journal.stat().st_size <= schedule._MAX_JOURNAL
    assert schedule._journal(root, workspace, journal)[1]["original_xml"] == original
    schedule.commit_upgrade(root, workspace, launcher, journal_path=journal)
    assert tasks.enabled and not journal.exists()


def test_uninstall_uses_embedded_owned_bootstrap_when_local_metadata_and_file_are_missing(
    installation, monkeypatch
):
    root, workspace, launcher, journal = installation
    xml = schedule._migrated_xml(legacy(root, workspace), workspace, launcher, True)
    tasks = Tasks(xml)
    monkeypatch.setattr(schedule, "_task_operation", tasks)
    name = launcher.relative_to(root).as_posix()
    owned = {name: hashlib.sha256(launcher.read_bytes()).hexdigest()}
    launcher.unlink()
    (root / "bootstrap-ledger.json").unlink()
    assert schedule.remove_installation_task(
        root, workspace, journal_path=journal, owned_bootstraps=owned
    ) == {"installed": False}
    assert tasks.calls == ["query", "disable", "delete"]


def test_prepare_repairs_missing_ledger_using_verified_manifest_ownership(
    installation, monkeypatch
):
    root, workspace, launcher, journal = installation
    tasks = Tasks(schedule._migrated_xml(legacy(root, workspace), workspace, launcher, True))
    monkeypatch.setattr(schedule, "_task_operation", tasks)
    name = launcher.relative_to(root).as_posix()
    owned = {name: hashlib.sha256(launcher.read_bytes()).hexdigest()}
    (root / "bootstrap-ledger.json").unlink()
    with pytest.raises(ValueError, match="unknown"):
        schedule.prepare_upgrade(root, workspace, launcher, journal_path=journal)
    assert tasks.enabled and not journal.exists()
    schedule.prepare_upgrade(
        root, workspace, launcher, journal_path=journal, owned_bootstraps=owned
    )
    assert not tasks.enabled and journal.exists()


def test_uninstall_rejects_unrecorded_or_changed_bootstrap_without_touching_task(
    installation, monkeypatch
):
    root, workspace, launcher, journal = installation
    tasks = Tasks(schedule._migrated_xml(legacy(root, workspace), workspace, launcher, True))
    monkeypatch.setattr(schedule, "_task_operation", tasks)
    launcher.write_bytes(b"changed existing bytes")
    with pytest.raises(ValueError, match="bytes"):
        schedule.remove_installation_task(root, workspace, journal_path=journal)
    assert not tasks.calls and tasks.enabled


def test_uninstall_cleans_owned_pending_journal_only_after_task_removal(installation, monkeypatch):
    root, workspace, launcher, journal = installation
    tasks = Tasks(legacy(root, workspace))
    monkeypatch.setattr(schedule, "_task_operation", tasks)
    schedule.prepare_upgrade(root, workspace, launcher, journal_path=journal)
    schedule.remove_installation_task(root, workspace, journal_path=journal)
    assert not journal.exists() and tasks.xml is None


@pytest.mark.parametrize("damage", ["ready", "ledger", "launcher", "journal"])
def test_installed_configuration_requires_complete_verified_launcher(
    installation, monkeypatch, damage
):
    root, workspace, launcher, journal = installation
    tasks = Tasks()
    monkeypatch.setattr(schedule, "_installation_root", lambda: root)
    monkeypatch.setattr(schedule, "_task_operation", tasks)
    if damage == "ready":
        (root / "installation-ready.ini").unlink()
    elif damage == "ledger":
        (root / "bootstrap-ledger.json").unlink()
    elif damage == "launcher":
        launcher.write_bytes(b"tampered")
    else:
        journal.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        schedule.configure(workspace, True)
    assert not tasks.calls


def test_installed_configure_registers_bootstrap_mode_first(installation, monkeypatch):
    root, workspace, launcher, journal = installation
    tasks = Tasks()
    monkeypatch.setattr(schedule, "_installation_root", lambda: root)
    monkeypatch.setattr(schedule, "_task_operation", tasks)
    assert schedule.configure(workspace, True)["installed"]
    assert schedule._one(schedule._xml(tasks.xml), "Actions/Exec/Command").text == str(launcher)
    assert schedule._one(schedule._xml(tasks.xml), "Actions/Exec/Arguments").text.startswith(
        "--scheduled --data-dir "
    )
    assert schedule.configure(workspace, False) == {"installed": False}


def test_source_configuration_keeps_existing_contract(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(schedule, "_installation_root", lambda: None)
    monkeypatch.setattr(
        schedule,
        "_configure_source",
        lambda *args, **kwargs: calls.append((args, kwargs)) or {"source": True},
    )
    assert schedule.configure(tmp_path, True, runner="synthetic") == {"source": True}
    assert calls == [((tmp_path, True), {"runner": "synthetic"})]


def native_export(root, workspace):
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/windows_schedule_normalization.json").read_text(
            encoding="utf-8"
        )
    )
    values = {}
    for name in ("requested_xml", "exported_xml"):
        text = fixture[name]
        text = set_xml(text, "Actions/Exec/Command", str(root / "runtime/pythonw.exe"))
        text = set_xml(
            text,
            "Actions/Exec/Arguments",
            subprocess.list2cmdline(
                [str(root / "app/tools/run_scheduled.py"), "--data-dir", str(workspace.resolve())]
            ),
        )
        values[name] = set_xml(text, "Actions/Exec/WorkingDirectory", str(root / "app"))
    return values


def test_actual_native_export_preserves_semantics_and_can_complete_upgrade(
    installation, monkeypatch
):
    root, workspace, launcher, journal = installation
    fixture = native_export(root, workspace)
    assert schedule._shape(fixture["requested_xml"]) == schedule._shape(fixture["exported_xml"])
    tasks = Tasks(fixture["exported_xml"])
    monkeypatch.setattr(schedule, "_task_operation", tasks)
    schedule.prepare_upgrade(root, workspace, launcher, journal_path=journal)
    schedule.commit_upgrade(root, workspace, launcher, journal_path=journal)
    assert tasks.enabled and not journal.exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("Settings/AllowStartOnDemand", "false"),
        ("Settings/Hidden", "true"),
        ("Triggers/CalendarTrigger/Enabled", "false"),
        ("Triggers/CalendarTrigger/Repetition/StopAtDurationEnd", "true"),
        ("Settings/IdleSettings/StopOnIdleEnd", "false"),
        ("Settings/IdleSettings/RestartOnIdle", "true"),
        ("Settings/ExecutionTimeLimit", "PT1H"),
    ],
)
def test_native_normalization_does_not_erase_nondefault_changes(installation, field, value):
    root, workspace, _, _ = installation
    fixture = native_export(root, workspace)["exported_xml"]
    assert schedule._shape(fixture) != schedule._shape(set_xml(fixture, field, value))


@pytest.mark.parametrize(
    "values", [("HighestAvailable",), ("unknown",), ("",), ("LeastPrivilege", "LeastPrivilege")]
)
def test_omitted_runlevel_default_does_not_allow_elevated_unknown_or_duplicate_principal(
    installation, monkeypatch, values
):
    root, workspace, launcher, journal = installation
    tree = schedule._xml(native_export(root, workspace)["exported_xml"])
    principal = schedule._one(tree, "Principals/Principal")
    for value in values:
        schedule.ET.SubElement(principal, "{" + schedule._NS + "}RunLevel").text = value
    tasks = Tasks(schedule.ET.tostring(tree, encoding="unicode"))
    monkeypatch.setattr(schedule, "_task_operation", tasks)
    with pytest.raises(ValueError):
        schedule.prepare_upgrade(root, workspace, launcher, journal_path=journal)
    assert tasks.calls == ["query"] and not journal.exists()


def test_com_transport_keeps_xml_out_of_command_line_and_queries_instances(tmp_path):
    if schedule.os.name != "nt":
        pytest.skip("Windows subprocess flags; all lifecycle tests use synthetic COM snapshots")
    paths = []

    def runner(command, **options):
        script = base64.b64decode(command[-1]).decode("utf-16-le")
        encoded_path = re.search(r"FromBase64String\('([^']+)'\)", script)[1]
        path = Path(base64.b64decode(encoded_path).decode("utf-8"))
        paths.append(path)
        assert json.loads(path.read_text(encoding="utf-8"))["name"] == schedule.task_name(tmp_path)
        assert "GetInstances(0).Count" in script and "StringComparison]::Ordinal" in script
        assert options["timeout"] == 20 and options["creationflags"] == subprocess.CREATE_NO_WINDOW
        return SimpleNamespace(returncode=0, stdout=json.dumps({"exists": False, "sid": SID}))

    assert schedule._task_operation(tmp_path, runner=runner) == {"exists": False, "sid": SID}
    assert all(not path.exists() for path in paths)


@pytest.mark.parametrize(
    "payload",
    [
        {"exists": "false", "sid": SID},
        {"exists": False, "sid": "not-a-sid"},
        {"exists": True, "sid": SID, "xml": "invalid"},
    ],
)
def test_unverifiable_native_results_fail_closed_without_request_details(tmp_path, payload):
    if schedule.os.name != "nt":
        pytest.skip("Windows transport flags")

    def runner(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload))

    with pytest.raises(ValueError) as caught:
        schedule._task_operation(tmp_path, runner=runner)
    assert str(tmp_path) not in str(caught.value)
