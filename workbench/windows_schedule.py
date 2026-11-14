"""Current-user Task Scheduler integration; no credentials in task arguments."""

from datetime import datetime
import csv
import base64
import hashlib
import io
import os
from pathlib import Path
import re
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


def configure(workspace, enabled, *, runner=subprocess.run):
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
        app = Path(__file__).resolve().parents[1]
        script = app / "tools" / "run_scheduled.py"
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
