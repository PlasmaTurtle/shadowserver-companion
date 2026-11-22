"""Current-user Task Scheduler integration; no credentials in task arguments."""

from datetime import datetime
import csv
import base64
import configparser
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


def task_name(workspace):
    digest = hashlib.sha256(str(Path(workspace).resolve()).encode()).hexdigest()[:20]
    return "ShadowserverCompanion-Schedule-" + digest


def task_xml(workspace, executable, script, user_sid, *, current=None):
    if not re.fullmatch(r"S-1-\d+(?:-\d+)+", user_sid):
        raise ValueError("Windows user identity was unavailable")
    ns = "http://schemas.microsoft.com/windows/2004/02/mit/task"
    ET.register_namespace("", ns)

    def node(parent, name, text=None, **attributes):
        child = ET.SubElement(parent, "{" + ns + "}" + name, attributes)
        if text is not None:
            child.text = str(text)
        return child

    root = ET.Element("{" + ns + "}Task", version="1.2")
    info = node(root, "RegistrationInfo")
    node(
        info,
        "Description",
        "Run saved Companion schedules while this user is signed in. No browser is opened.",
    )
    triggers = node(root, "Triggers")
    daily = node(triggers, "CalendarTrigger")
    repeat = node(daily, "Repetition")
    node(repeat, "Interval", "PT1H")
    node(repeat, "Duration", "P1D")
    node(repeat, "StopAtDurationEnd", "false")
    node(
        daily,
        "StartBoundary",
        (current or datetime.now()).replace(hour=0, minute=0, second=0, microsecond=0).isoformat(),
    )
    node(daily, "Enabled", "true")
    node(node(daily, "ScheduleByDay"), "DaysInterval", 1)
    principals = node(root, "Principals")
    principal = node(principals, "Principal", id="Author")
    node(principal, "UserId", user_sid)
    node(principal, "LogonType", "InteractiveToken")
    node(principal, "RunLevel", "LeastPrivilege")
    settings = node(root, "Settings")
    node(settings, "MultipleInstancesPolicy", "IgnoreNew")
    node(settings, "DisallowStartIfOnBatteries", "false")
    node(settings, "StopIfGoingOnBatteries", "false")
    node(settings, "StartWhenAvailable", "true")
    node(settings, "RunOnlyIfNetworkAvailable", "true")
    node(settings, "AllowStartOnDemand", "true")
    node(settings, "Enabled", "true")
    node(settings, "Hidden", "false")
    node(settings, "ExecutionTimeLimit", "PT6H")
    actions = node(root, "Actions", Context="Author")
    action = node(actions, "Exec")
    node(action, "Command", str(executable))
    node(
        action,
        "Arguments",
        subprocess.list2cmdline([str(script), "--data-dir", str(Path(workspace).resolve())]),
    )
    node(action, "WorkingDirectory", str(Path(script).resolve().parents[1]))
    return ET.tostring(root, encoding="utf-16", xml_declaration=True)


def _task_exists(system, name, runner, options):
    result = runner([str(system / "schtasks.exe"), "/Query", "/TN", name], **options)
    if result.returncode == 0:
        return True
    # schtasks collapses not-found and permission failures to the same exit
    # status. Ask Task Scheduler's COM interface for an exact HRESULT instead
    # of interpreting localized stderr or reporting a false successful removal.
    if not re.fullmatch(r"[A-Za-z0-9-]+", name):
        raise ValueError("Invalid scheduled task identity")
    script = (
        "$ErrorActionPreference='Stop'; try { $s=New-Object -ComObject Schedule.Service; $s.Connect(); $f=$s.GetFolder('\\'); } catch { exit 3 }; "
        "try { $null=$f.GetTask('" + name + "'); exit 0 } catch { "
        "$e=$_.Exception; while ($null -ne $e) { if ($e.HResult -eq -2147024894) { exit 2 }; $e=$e.InnerException }; exit 3 }"
    )
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    result = runner(
        [
            str(system / "WindowsPowerShell" / "v1.0" / "powershell.exe"),
            "-NoProfile",
            "-NonInteractive",
            "-EncodedCommand",
            encoded,
        ],
        **options,
    )
    if result.returncode == 2:
        return False
    if result.returncode == 0:
        return True
    raise ValueError("Windows could not verify the scheduled task; no task was removed")


def _configure_source(workspace, enabled, *, runner=subprocess.run):
    if os.name != "nt":
        raise ValueError("Closed-app scheduling is available in the Windows installation")
    system = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    schtasks = str(system / "schtasks.exe")
    options = dict(
        capture_output=True, text=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW
    )
    name = task_name(workspace)
    try:
        if not enabled:
            if _task_exists(system, name, runner, options):
                result = runner([schtasks, "/Delete", "/TN", name, "/F"], **options)
                if result.returncode:
                    raise ValueError("Windows could not remove this workspace's scheduled task")
            return {"installed": False}
        result = runner([str(system / "whoami.exe"), "/user", "/fo", "csv", "/nh"], **options)
        user_sid = next(csv.reader(io.StringIO(result.stdout)))[1]
        app = Path(__file__).resolve().parents[3]
        script = app / "modules/accretion/tools/run_scheduled.py"
        executable = Path(sys.executable)
        windowless = executable.with_name("pythonw.exe")
        if windowless.is_file():
            executable = windowless
        if not script.is_file():
            raise ValueError("The scheduled runner is missing from this installation")
        with tempfile.TemporaryDirectory(prefix="companion-schedule-") as temporary:
            xml = Path(temporary) / "task.xml"
            xml.write_bytes(task_xml(workspace, executable, script, user_sid))
            result = runner([schtasks, "/Create", "/TN", name, "/XML", str(xml), "/F"], **options)
        if result.returncode:
            raise ValueError(
                "Windows could not register the scheduled task; check workstation policy"
            )
        return {
            "installed": True,
            "task_name": name,
            "scope": "Current user while signed in",
            "checked_at": datetime.now().astimezone().isoformat(),
        }
    except (OSError, subprocess.TimeoutExpired, IndexError, StopIteration, csv.Error):
        raise ValueError("Windows scheduled-task setup could not complete") from None


_NS = "http://schemas.microsoft.com/windows/2004/02/mit/task"
_BOOTSTRAP = re.compile(r"bootstrap/launch-([0-9a-f]{64})\.exe\Z")
_APP_IDS = {"OutreachWorkbench", "ShadowserverCompanionChaos", "ShadowserverCompanionDarkMatter"}
_MAX_XML = 128 * 1024
_MAX_JOURNAL = 4 * _MAX_XML


def _plain_path(path):
    """Inspect before resolving: neither journals nor launcher checks follow links."""
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Scheduled-task installation paths must not be links")
        if part != path and not stat.S_ISDIR(info.st_mode):
            raise ValueError("Scheduled-task installation parent is not a directory")
    return path


def _json_file(path, limit):
    path = _plain_path(path)
    if not path.is_file() or path.stat().st_size > limit:
        raise ValueError("Scheduled-task installation metadata is unavailable or too large")
    try:
        with path.open("rb") as stream:
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise ValueError("Scheduled-task installation metadata is too large")
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, ValueError):
        raise ValueError("Scheduled-task installation metadata is invalid") from None
    if not isinstance(value, dict):
        raise ValueError("Scheduled-task installation metadata is invalid")
    return value


def _launcher(root, launcher, *, required=False):
    path = _plain_path(launcher)
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError:
        raise ValueError("Scheduled launcher is outside this installation") from None
    matched = _BOOTSTRAP.fullmatch(relative)
    if not matched:
        raise ValueError("Scheduled launcher has an unrecognized immutable identity")
    if path.exists():
        if not path.is_file() or path.stat().st_size > 32 * 1024 * 1024:
            raise ValueError("Scheduled launcher is not a bounded regular file")
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != matched[1]:
            raise ValueError("Scheduled launcher bytes do not match its owned identity")
    elif required:
        raise ValueError("Scheduled launcher is missing; repair the installation")
    return relative


def _owned_launchers(root, supplied=None):
    """An absent recorded file is repairable; changed existing bytes are not adopted."""
    ledger_path = _plain_path(root / "bootstrap-ledger.json")
    ledger = None
    owned = {}
    if ledger_path.exists():
        ledger = _json_file(ledger_path, _MAX_JOURNAL)
        if (
            set(ledger) != {"schema", "app_id", "active", "files"}
            or type(ledger["schema"]) is not int
            or ledger["schema"] != 1
            or not isinstance(ledger["app_id"], str)
            or ledger["app_id"] not in _APP_IDS
            or not isinstance(ledger["files"], dict)
            or (ledger["active"] is not None and not isinstance(ledger["active"], str))
            or (ledger["active"] is not None and ledger["active"] not in ledger["files"])
        ):
            raise ValueError("Scheduled launcher ownership metadata is invalid")
        owned.update(ledger["files"])
    if supplied is not None:
        if not isinstance(supplied, dict):
            raise ValueError("Scheduled launcher ownership map is invalid")
        for name, digest in supplied.items():
            if name in owned and owned[name] != digest:
                raise ValueError("Scheduled launcher ownership maps disagree")
            owned[name] = digest
    for name, digest in owned.items():
        matched = _BOOTSTRAP.fullmatch(name) if isinstance(name, str) else None
        if not matched or digest != matched[1]:
            raise ValueError("Scheduled launcher ownership map is invalid")
        _launcher(root, root / name)
    return owned, ledger


def _active_launcher(root):
    if _plain_path(root / "installation-task.json").exists():
        raise ValueError("A scheduled-task upgrade is incomplete; repair the installation")
    owned, ledger = _owned_launchers(root)
    if ledger is None or ledger["active"] not in owned:
        raise ValueError(
            "Installed scheduling needs a complete launcher ledger; repair the installation"
        )
    marker = _plain_path(root / "installation-ready.ini")
    if not marker.is_file() or marker.stat().st_size > 4096:
        raise ValueError("Installation is incomplete; scheduling was not changed")
    try:
        config = configparser.ConfigParser(interpolation=None)
        config.read_string(marker.read_text(encoding="utf-8"))
        valid = (
            config.sections() == ["installation"]
            and config["installation"].get("app_id") == ledger["app_id"]
            and config["installation"].get("protocol") == "1"
        )
    except (OSError, UnicodeError, configparser.Error):
        valid = False
    if not valid:
        raise ValueError("Installation is incomplete; scheduling was not changed")
    path = root / ledger["active"]
    _launcher(root, path, required=True)
    return path


def _task_operation(
    workspace, operation="query", *, expected_xml=None, xml=None, runner=subprocess.run
):
    """One bounded COM transaction; only ASCII JSON crosses the console boundary."""
    if os.name != "nt":
        raise ValueError("Installed scheduling is available only on Windows")
    if operation not in {"query", "disable", "register", "delete"}:
        raise ValueError("Invalid scheduled-task operation")
    name = task_name(workspace)
    request = {"name": name, "operation": operation, "expected": expected_xml, "xml": xml}
    # XML is data in a temporary file, avoiding command-line length and quoting limits.
    with tempfile.TemporaryDirectory(prefix="companion-task-") as directory:
        request_path = Path(directory) / "request.json"
        request_path.write_text(json.dumps(request), encoding="utf-8")
        encoded_path = base64.b64encode(str(request_path).encode("utf-8")).decode("ascii")
        script = r"""
$ErrorActionPreference='Stop'
try {
 $path=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('REQUEST_PATH'))
 $r=Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
 $sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
 $service=New-Object -ComObject Schedule.Service; $service.Connect()
 $folder=$service.GetFolder('\'); $task=$null
 try { $task=$folder.GetTask($r.name) } catch {
  $e=$_.Exception; $missing=$false
  while ($null -ne $e) { if ($e.HResult -eq -2147024894) { $missing=$true }; $e=$e.InnerException }
  if (-not $missing) { throw }
 }
 if ($r.operation -ne 'query') {
  if ($null -eq $r.expected) {
   if ($null -ne $task) { throw 'Task appeared during update' }
  } elseif ($null -eq $task -or -not [String]::Equals($task.Xml,$r.expected,[StringComparison]::Ordinal)) {
   throw 'Task changed during update'
  }
  if ($r.operation -eq 'disable') { $task.Enabled=$false; $task=$folder.GetTask($r.name) }
  elseif ($r.operation -eq 'register') {
   $task=$folder.RegisterTask($r.name,$r.xml,6,$sid,$null,3,$null)
  } elseif ($r.operation -eq 'delete') {
   if ($task.State -eq 0 -or $task.State -eq 2 -or $task.State -eq 4 -or $task.GetInstances(0).Count -ne 0) { throw 'Task is active' }
   $folder.DeleteTask($r.name,0); $task=$null
  }
 }
 if ($null -eq $task) { $result=@{exists=$false;sid=$sid} }
 else {
  $result=@{exists=$true;sid=$sid;path=$task.Path;enabled=[bool]$task.Enabled;state=[int]$task.State;instances=[int]$task.GetInstances(0).Count;xml=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($task.Xml))}
 }
 [Console]::Write(($result | ConvertTo-Json -Compress))
} catch { exit 3 }
""".replace("REQUEST_PATH", encoded_path)
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        system = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
        try:
            result = runner(
                [
                    str(system / "WindowsPowerShell/v1.0/powershell.exe"),
                    "-NoProfile",
                    "-NonInteractive",
                    "-EncodedCommand",
                    encoded,
                ],
                capture_output=True,
                text=True,
                timeout=20,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode or len(result.stdout) > 2 * _MAX_XML:
                raise ValueError("Windows could not verify or update the scheduled task")
            value = json.loads(result.stdout)
            if (
                not isinstance(value, dict)
                or type(value.get("exists")) is not bool
                or not re.fullmatch(r"S-1-\d+(?:-\d+)+", value.get("sid", ""))
            ):
                raise ValueError("Windows returned invalid scheduled-task state")
            if value["exists"]:
                value["xml"] = base64.b64decode(value["xml"], validate=True).decode("utf-8")
                if (
                    type(value.get("enabled")) is not bool
                    or type(value.get("state")) is not int
                    or value["state"] not in range(5)
                    or type(value.get("instances")) is not int
                    or value["instances"] < 0
                    or value.get("path", "").casefold() != ("\\" + name).casefold()
                ):
                    raise ValueError("Windows returned invalid scheduled-task state")
            return value
        except (
            OSError,
            subprocess.TimeoutExpired,
            UnicodeError,
            KeyError,
            TypeError,
            json.JSONDecodeError,
            base64.binascii.Error,
        ):
            raise ValueError("Windows scheduled-task inspection could not complete") from None


def _xml(text):
    if not isinstance(text, str) or len(text.encode("utf-8")) > _MAX_XML or "<!" in text:
        raise ValueError("Scheduled-task XML is unsupported or too large")
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        raise ValueError("Scheduled-task XML is invalid") from None
    if root.tag != "{" + _NS + "}Task":
        raise ValueError("Scheduled-task XML has an unknown schema")
    return root


def _one(root, path):
    nodes = root.findall("/".join("{" + _NS + "}" + part for part in path.split("/")))
    if len(nodes) != 1:
        raise ValueError("Scheduled task has an unrecognized structure")
    return nodes[0]


def _same_path(left, right):
    return (
        Path(left).is_absolute()
        and Path(right).is_absolute()
        and os.path.normcase(os.path.abspath(left)) == os.path.normcase(os.path.abspath(right))
    )


def _optional(root, name):
    nodes = root.findall("{" + _NS + "}" + name)
    if len(nodes) > 1:
        raise ValueError("Scheduled task repeats a singleton setting")
    return nodes[0] if nodes else None


def _defaulted(root, name, default):
    node = _optional(root, name)
    return default if node is None else node.text


def _ensure_default(root, name, default):
    node = _optional(root, name)
    if node is None:
        node = ET.SubElement(root, "{" + _NS + "}" + name)
        node.text = default
    return node


def _task_enabled(tree):
    value = _defaulted(_one(tree, "Settings"), "Enabled", "true")
    if value not in {"true", "false"}:
        raise ValueError("Scheduled task enabled state is invalid")
    return value == "true"


def _validate_task(root, workspace, snapshot, owned):
    tree = _xml(snapshot["xml"])
    principal = _one(tree, "Principals/Principal")
    if (
        len(_one(tree, "Principals")) != 1
        or _one(principal, "UserId").text != snapshot["sid"]
        or _one(principal, "LogonType").text != "InteractiveToken"
        or _defaulted(principal, "RunLevel", "LeastPrivilege") != "LeastPrivilege"
        or _one(tree, "Actions").get("Context") != principal.get("id")
        or len(_one(tree, "Actions")) != 1
    ):
        raise ValueError("Scheduled task is not owned by this signed-in user")
    action = _one(tree, "Actions/Exec")
    if len(action) != 3:
        raise ValueError("Scheduled task has an unrecognized action")
    command = _one(action, "Command").text or ""
    arguments = _one(action, "Arguments").text or ""
    directory = _one(action, "WorkingDirectory").text or ""
    if _task_enabled(tree) != snapshot["enabled"]:
        raise ValueError("Scheduled task enabled state is inconsistent")
    workspace = Path(workspace).resolve()
    legacy_python = any(
        _same_path(command, root / "runtime" / name) for name in ("python.exe", "pythonw.exe")
    )
    if legacy_python:
        for relative in (
            "app/tools/run_scheduled.py",
            "app/modules/accretion/tools/run_scheduled.py",
        ):
            script = root / relative
            if arguments == subprocess.list2cmdline(
                [str(script), "--data-dir", str(workspace)]
            ) and _same_path(directory, script.parents[1]):
                return tree
    for relative in owned:
        if (
            _same_path(command, root / relative)
            and arguments == subprocess.list2cmdline(["--scheduled", "--data-dir", str(workspace)])
            and _same_path(directory, root)
        ):
            return tree
    raise ValueError("Scheduled task action is unknown; no task or program files were changed")


def _idle(snapshot):
    if snapshot["state"] not in {1, 3} or snapshot["instances"]:
        raise ValueError("Scheduled task has a queued or running instance; retry after it finishes")


def _shape(text, *, ignore_action=False):
    tree = _xml(text)
    # Task Scheduler may refresh informational registration metadata on registration.
    info = tree.find("{" + _NS + "}RegistrationInfo")
    if info is not None:
        tree.remove(info)
    if ignore_action:
        tree.remove(_one(tree, "Actions"))
    # Native exports omit defaults, add IdleSettings and reorder xs:all fields.
    # Normalize documented defaults, retaining every nondefault/unknown value.
    # https://learn.microsoft.com/en-us/windows/win32/taskschd/task-scheduler-schema
    _ensure_default(_one(tree, "Principals/Principal"), "RunLevel", "LeastPrivilege")
    settings = _one(tree, "Settings")
    for name, default in (("Enabled", "true"), ("AllowStartOnDemand", "true"), ("Hidden", "false")):
        _ensure_default(settings, name, default)
    _one(settings, "Enabled").text = "<enabled-state>"
    idle = _ensure_default(settings, "IdleSettings", None)
    for name, default in (("StopOnIdleEnd", "true"), ("RestartOnIdle", "false")):
        _ensure_default(idle, name, default)
    triggers = _optional(tree, "Triggers")
    if triggers is not None:
        for trigger in triggers:
            _ensure_default(trigger, "Enabled", "true")
            repetition = _optional(trigger, "Repetition")
            if repetition is not None:
                _ensure_default(repetition, "StopAtDurationEnd", "false")
    unordered = {
        "{" + _NS + "}" + name
        for name in (
            "Task",
            "Principal",
            "Settings",
            "IdleSettings",
            "CalendarTrigger",
            "Repetition",
            "Exec",
        )
    }

    def shape(node):
        children = [shape(child) for child in node]
        if node.tag in unordered:
            children.sort()
        return (
            node.tag,
            tuple(sorted(node.attrib.items())),
            (node.text or "").strip(),
            tuple(children),
        )

    return shape(tree)


def _migrated_xml(text, workspace, launcher, enabled):
    tree = _xml(text)
    action = _one(tree, "Actions/Exec")
    _one(action, "Command").text = str(launcher)
    _one(action, "Arguments").text = subprocess.list2cmdline(
        ["--scheduled", "--data-dir", str(Path(workspace).resolve())]
    )
    _one(action, "WorkingDirectory").text = str(Path(launcher).parent.parent)
    _ensure_default(_one(tree, "Settings"), "Enabled", "true").text = "true" if enabled else "false"
    ET.register_namespace("", _NS)
    result = ET.tostring(tree, encoding="unicode")
    _xml(result)
    return result


def _journal(root, workspace, path):
    path = _plain_path(path)
    if path != root / "installation-task.json":
        raise ValueError("Scheduled-task journal must belong to this installation")
    if not path.exists():
        return path, None
    value = _json_file(path, _MAX_JOURNAL)
    if (
        set(value)
        != {
            "schema",
            "install_dir",
            "workspace",
            "task_name",
            "sid",
            "enabled",
            "original_xml",
            "expected_xml",
            "launcher",
        }
        or type(value["schema"]) is not int
        or value["schema"] != 1
        or value["install_dir"] != str(root)
        or value["workspace"] != str(Path(workspace).resolve())
        or value["task_name"] != task_name(workspace)
        or type(value["enabled"]) is not bool
        or not isinstance(value["sid"], str)
        or not re.fullmatch(r"S-1-\d+(?:-\d+)+", value["sid"])
        or not isinstance(value["launcher"], str)
    ):
        raise ValueError("Scheduled-task upgrade journal does not match this installation")
    _xml(value["original_xml"])
    _xml(value["expected_xml"])
    _launcher(root, root / value["launcher"])
    return path, value


def _save_journal(path, value):
    _plain_path(path)
    serialized = json.dumps(value, ensure_ascii=False)
    if len(serialized.encode("utf-8")) > _MAX_JOURNAL:
        raise ValueError("Scheduled-task upgrade journal is too large")
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=".installation-task-", delete=False
    ) as stream:
        temporary = Path(stream.name)
        stream.write(serialized)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        _plain_path(path)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _validate_journal(root, workspace, record, snapshot, owned):
    if record["sid"] != snapshot["sid"]:
        raise ValueError("Scheduled-task journal belongs to another user")
    for key in ("original_xml", "expected_xml"):
        enabled = _task_enabled(_xml(record[key]))
        _validate_task(
            root, workspace, {"xml": record[key], "sid": record["sid"], "enabled": enabled}, owned
        )
    if _task_enabled(_xml(record["original_xml"])) != record["enabled"] or _shape(
        record["original_xml"], ignore_action=True
    ) != _shape(record["expected_xml"], ignore_action=True):
        raise ValueError("Scheduled-task journal changed the original configuration")
    if snapshot["exists"]:
        expected = _shape(record["expected_xml"])
        migrated = _shape(
            _migrated_xml(
                record["expected_xml"], workspace, root / record["launcher"], record["enabled"]
            )
        )
        if _shape(snapshot["xml"]) not in (expected, migrated):
            raise ValueError(
                "Scheduled task changed after upgrade preparation; it was not overwritten"
            )


def prepare_upgrade(
    install_dir,
    data_dir,
    launcher_path,
    *,
    journal_path,
    owned_bootstraps=None,
    runner=subprocess.run,
):
    """Called under the installer gate, before replaceable program files change."""
    root = _plain_path(install_dir)
    launcher = _launcher(root, launcher_path)
    owned, _ = _owned_launchers(root, owned_bootstraps)
    path, record = _journal(root, data_dir, journal_path)
    snapshot = _task_operation(data_dir, runner=runner)
    if record:
        _validate_journal(root, data_dir, record, snapshot, owned)
    if not snapshot["exists"]:
        return {"installed": False}
    _validate_task(root, data_dir, snapshot, owned)
    _idle(snapshot)
    _migrated_xml(snapshot["xml"], data_dir, root / launcher, snapshot["enabled"])
    if record is None:
        record = {
            "schema": 1,
            "install_dir": str(root),
            "workspace": str(Path(data_dir).resolve()),
            "task_name": task_name(data_dir),
            "sid": snapshot["sid"],
            "enabled": snapshot["enabled"],
            "original_xml": snapshot["xml"],
        }
    record.update(expected_xml=snapshot["xml"], launcher=launcher)
    _save_journal(path, record)
    disabled = _task_operation(data_dir, "disable", expected_xml=snapshot["xml"], runner=runner)
    if not disabled["exists"] or disabled["enabled"]:
        raise ValueError("Windows did not disable the owned scheduled task")
    _validate_task(root, data_dir, disabled, owned)
    _idle(disabled)
    if _shape(disabled["xml"]) != _shape(snapshot["xml"]):
        raise ValueError("Scheduled task changed while being disabled")
    return {"installed": True, "enabled": record["enabled"]}


def commit_upgrade(install_dir, data_dir, launcher_path, *, journal_path, runner=subprocess.run):
    """Migrate while the start gate is still held; preserve the user's saved task."""
    root = _plain_path(install_dir)
    launcher = _launcher(root, launcher_path, required=True)
    owned, _ = _owned_launchers(root)
    owned.setdefault(launcher, _BOOTSTRAP.fullmatch(launcher)[1])
    path, record = _journal(root, data_dir, journal_path)
    snapshot = _task_operation(data_dir, runner=runner)
    if record is None:
        if snapshot["exists"]:
            raise ValueError("Scheduled task appeared without an upgrade journal")
        return {"installed": False}
    _validate_journal(root, data_dir, record, snapshot, owned)
    if record["launcher"] != launcher:
        raise ValueError("Scheduled-task upgrade target changed without preparation")
    if not snapshot["exists"]:
        path.unlink()
        return {"installed": False}
    _validate_task(root, data_dir, snapshot, owned)
    target_xml = _migrated_xml(record["expected_xml"], data_dir, root / launcher, record["enabled"])
    complete = (
        _shape(snapshot["xml"]) == _shape(target_xml) and snapshot["enabled"] == record["enabled"]
    )
    if not complete:
        _idle(snapshot)
        if snapshot["enabled"]:
            raise ValueError("Scheduled task was re-enabled during upgrade")
        snapshot = _task_operation(
            data_dir, "register", expected_xml=snapshot["xml"], xml=target_xml, runner=runner
        )
    if not snapshot["exists"]:
        raise ValueError("Windows did not retain the migrated scheduled task")
    _validate_task(root, data_dir, snapshot, owned)
    if _shape(snapshot["xml"]) != _shape(target_xml) or snapshot["enabled"] != record["enabled"]:
        raise ValueError("Windows did not preserve the scheduled-task configuration")
    path.unlink()
    return {"installed": True, "enabled": record["enabled"]}


def remove_installation_task(
    install_dir, data_dir, *, journal_path, owned_bootstraps=None, runner=subprocess.run
):
    """Remove only verified task/journal ownership before uninstall deletes programs."""
    root = _plain_path(install_dir)
    owned, _ = _owned_launchers(root, owned_bootstraps)
    path, record = _journal(root, data_dir, journal_path)
    snapshot = _task_operation(data_dir, runner=runner)
    if record:
        _validate_journal(root, data_dir, record, snapshot, owned)
    if snapshot["exists"]:
        _validate_task(root, data_dir, snapshot, owned)
        _idle(snapshot)
        if snapshot["enabled"]:
            disabled = _task_operation(
                data_dir, "disable", expected_xml=snapshot["xml"], runner=runner
            )
            if not disabled["exists"] or disabled["enabled"]:
                raise ValueError("Windows did not disable the task before uninstall")
            _validate_task(root, data_dir, disabled, owned)
            _idle(disabled)
            if _shape(disabled["xml"]) != _shape(snapshot["xml"]):
                raise ValueError("Scheduled task changed while being disabled")
            snapshot = disabled
        removed = _task_operation(data_dir, "delete", expected_xml=snapshot["xml"], runner=runner)
        if removed["exists"]:
            raise ValueError("Windows did not remove the owned scheduled task")
    if record:
        path.unlink()
    return {"installed": False}


def _installation_root():
    app = Path(__file__).resolve().parents[3]
    root = app.parent
    if app.name.casefold() == "app" and _same_path(
        Path(sys.executable).resolve().parent, root / "runtime"
    ):
        return _plain_path(root)
    return None


def configure(workspace, enabled, *, runner=subprocess.run):
    root = _installation_root()
    if root is None:
        return _configure_source(workspace, enabled, runner=runner)
    if not enabled:
        return remove_installation_task(
            root, workspace, journal_path=root / "installation-task.json", runner=runner
        )
    launcher = _active_launcher(root)
    owned, _ = _owned_launchers(root)
    snapshot = _task_operation(workspace, runner=runner)
    if snapshot["exists"]:
        _validate_task(root, workspace, snapshot, owned)
        _idle(snapshot)
        original = snapshot["xml"]
    else:
        original = task_xml(
            workspace,
            root / "runtime/pythonw.exe",
            root / "app/modules/accretion/tools/run_scheduled.py",
            snapshot["sid"],
        ).decode("utf-16")
    desired = _migrated_xml(original, workspace, launcher, True)
    registered = _task_operation(
        workspace, "register", expected_xml=snapshot.get("xml"), xml=desired, runner=runner
    )
    if not registered["exists"] or not registered["enabled"]:
        raise ValueError("Windows could not register the installed scheduled task")
    _validate_task(root, workspace, registered, owned)
    if _shape(registered["xml"]) != _shape(desired):
        raise ValueError("Windows did not preserve the scheduled-task configuration")
    return {
        "installed": True,
        "task_name": task_name(workspace),
        "scope": "Current user while signed in",
        "checked_at": datetime.now().astimezone().isoformat(),
    }
