"""Installed launch coordination without pretending Linux proves Windows APIs."""

from contextlib import contextmanager
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from modules.workspace.components import startup as workspace_startup
from modules.workspace.components.workspace_session import workspace_session
from tests.support.installation import helper
from modules.workspace.components.local_session import LocalSessions, write_instance


class Function:
    """ctypes-like callables permit the production argtypes/restype assignments."""

    def __init__(self, implementation):
        self.implementation = implementation

    def __call__(self, *args):
        return self.implementation(*args)


class Kernel:
    """Model named-object lifetime and thread ownership, not Windows execution."""

    def __init__(self):
        self.handles = {}
        self.objects = {}
        self.events = []
        self.next_handle = 10
        self.caller = "app"
        self.fail_create = None
        self.fail_wait = False
        self.CreateMutexW = Function(self.create)
        self.WaitForSingleObject = Function(self.wait)
        self.ReleaseMutex = Function(self.release)
        self.CloseHandle = Function(self.close)

    def create(self, security, owned, name):
        assert security is None and not owned
        self.events.append(("create", name, self.caller))
        if self.fail_create == name:
            return 0
        self.next_handle += 1
        handle = self.next_handle
        self.handles[handle] = name
        item = self.objects.setdefault(name, {"handles": set(), "owner": None, "abandoned": False})
        item["handles"].add(handle)
        return handle

    def wait(self, handle, milliseconds):
        self.events.append(("wait", self.handles[handle], self.caller, milliseconds))
        if self.fail_wait:
            return 0xFFFFFFFF
        item = self.objects[self.handles[handle]]
        if item["owner"] not in (None, self.caller):
            return 258
        item["owner"] = self.caller
        abandoned = item["abandoned"]
        item["abandoned"] = False
        return 128 if abandoned else 0

    def release(self, handle):
        item = self.objects[self.handles[handle]]
        assert item["owner"] == self.caller
        self.events.append(("release", self.handles[handle], self.caller))
        item["owner"] = None
        return 1

    def close(self, handle):
        name = self.handles.pop(handle)
        self.events.append(("close", name, self.caller))
        item = self.objects[name]
        item["handles"].remove(handle)
        if not item["handles"]:
            del self.objects[name]
        return 1


def windows_launcher(monkeypatch, kernel):
    desktop = helper("desktop")
    original = desktop.ctypes
    monkeypatch.setattr(desktop, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(
        desktop,
        "ctypes",
        SimpleNamespace(
            WinDLL=lambda *args, **kwargs: kernel,
            WinError=lambda code: OSError(code, "Synthetic Windows API failure"),
            get_last_error=lambda: 5,
            c_void_p=original.c_void_p,
            c_int=original.c_int,
            c_ulong=original.c_ulong,
            c_wchar_p=original.c_wchar_p,
        ),
    )
    exits = []
    monkeypatch.setattr(
        desktop, "atexit", SimpleNamespace(register=lambda *args: exits.append(args))
    )
    return desktop, exits


def test_registration_is_atomic_but_independent_workspaces_can_run(monkeypatch):
    kernel = Kernel()
    first, first_exits = windows_launcher(monkeypatch, kernel)
    first.hold_installation_mutex()
    assert first.INSTALL_GATE not in kernel.objects
    assert kernel.objects[first.RUNNING_MUTEX]["owner"] is None
    assert len(first_exits) == 1
    # Idempotent registration cannot leak additional lifetime handles.
    first.hold_installation_mutex()
    assert len(first_exits) == 1
    second, second_exits = windows_launcher(monkeypatch, kernel)
    kernel.caller = "demo-or-other-workspace"
    second.hold_installation_mutex()
    assert len(kernel.objects[first.RUNNING_MUTEX]["handles"]) == 2
    for launcher in ("app", "demo-or-other-workspace"):
        create_running = kernel.events.index(("create", first.RUNNING_MUTEX, launcher))
        release_gate = kernel.events.index(("release", first.INSTALL_GATE, launcher))
        assert create_running < release_gate
    # Setup can acquire the gate, but the legacy running object remains until
    # every app exits. It must refuse replacement, including older applications.
    kernel.caller = "installer"
    gate = kernel.create(None, False, first.INSTALL_GATE)
    assert kernel.wait(gate, 5000) == 0
    assert first.RUNNING_MUTEX in kernel.objects
    for callback, handle in first_exits + second_exits:
        callback(handle)
    assert first.RUNNING_MUTEX not in kernel.objects
    kernel.release(gate)
    kernel.close(gate)
    assert not kernel.handles


def test_installer_ownership_blocks_app_registration_without_releasing_its_mutex(monkeypatch):
    kernel = Kernel()
    desktop, exits = windows_launcher(monkeypatch, kernel)
    kernel.caller = "installer"
    gate = kernel.create(None, False, desktop.INSTALL_GATE)
    assert kernel.wait(gate, 0) == 0
    kernel.caller = "app"
    with pytest.raises(RuntimeError, match="Installation or removal is in progress"):
        desktop.hold_installation_mutex()
    assert kernel.objects[desktop.INSTALL_GATE]["owner"] == "installer"
    assert kernel.objects[desktop.INSTALL_GATE]["handles"] == {gate}
    assert desktop.RUNNING_MUTEX not in kernel.objects
    assert not exits
    # The same process can retry after installation has completed.
    kernel.caller = "installer"
    kernel.release(gate)
    kernel.close(gate)
    kernel.caller = "app"
    desktop.hold_installation_mutex()
    assert len(exits) == 1


def test_abandoned_gate_grants_ownership_and_is_released(monkeypatch):
    kernel = Kernel()
    desktop, _ = windows_launcher(monkeypatch, kernel)
    old = kernel.create(None, False, desktop.INSTALL_GATE)
    kernel.objects[desktop.INSTALL_GATE]["abandoned"] = True
    desktop.hold_installation_mutex()
    assert kernel.objects[desktop.INSTALL_GATE]["owner"] is None
    assert kernel.objects[desktop.INSTALL_GATE]["handles"] == {old}


@pytest.mark.parametrize("failure", ["gate-create", "wait", "running-create"])
def test_windows_api_failures_do_not_publish_a_running_handle_or_leak_gate(monkeypatch, failure):
    kernel = Kernel()
    desktop, exits = windows_launcher(monkeypatch, kernel)
    if failure == "wait":
        kernel.fail_wait = True
    else:
        kernel.fail_create = (
            desktop.INSTALL_GATE if failure == "gate-create" else desktop.RUNNING_MUTEX
        )
    with pytest.raises(OSError, match="Windows API failure"):
        desktop.hold_installation_mutex()
    assert not kernel.handles and not exits
    assert desktop._installation_handle is None
    released = any(event[0] == "release" for event in kernel.events)
    assert released is (failure == "running-create")


class Clock:
    def __init__(self):
        self.now = 0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


@contextmanager
def separate_workspace_owner(workspace):
    """Hold the production workspace guard in a real independent process."""
    script = (
        "from pathlib import Path\n"
        "import sys\n"
        "from modules.workspace.components.workspace_session import workspace_session\n"
        "root = Path(sys.argv[1])\n"
        "with workspace_session(root):\n"
        "    (root / 'owner-ready').write_text('ready')\n"
        "    sys.stdin.buffer.read()\n"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(workspace)],
        cwd=Path(__file__).resolve().parents[1],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        deadline = time.monotonic() + 5
        while not (workspace / "owner-ready").exists():
            assert process.poll() is None, "Workspace owner exited before acquiring its lock"
            assert time.monotonic() < deadline, "Workspace owner did not acquire its lock"
            time.sleep(0.02)
        yield
    finally:
        try:
            _, errors = process.communicate(input=b"done", timeout=5)
            assert process.returncode == 0, errors.decode(errors="replace")
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise


@pytest.fixture
def launcher(monkeypatch):
    desktop = helper("desktop")
    clock = Clock()
    monkeypatch.setattr(desktop, "configure_logging", lambda workspace: None)
    monkeypatch.setattr(desktop, "hold_installation_mutex", lambda: None)
    monkeypatch.setattr(desktop, "time", clock)
    monkeypatch.setattr(desktop.sys, "dont_write_bytecode", desktop.sys.dont_write_bytecode)
    opened = []
    monkeypatch.setattr(desktop.webbrowser, "open", opened.append)
    return desktop, clock, opened


def test_simultaneous_launch_uses_real_workspace_exclusion_then_waits_for_matching_session(
    launcher, tmp_path, monkeypatch, caplog
):
    desktop, clock, opened = launcher
    calls = []
    token = "synthetic-credential-not-for-logs-123456"
    url = f"http://127.0.0.1:8881/#launch={token}"

    def lookup(port, workspace, demo, **kwargs):
        calls.append((port, workspace, demo, kwargs))
        return url if len(calls) == 4 else None

    def second_server():
        with workspace_session(tmp_path):
            pytest.fail("The second launch must not acquire the first process's workspace")

    monkeypatch.setattr(desktop, "existing_instance", lookup)
    monkeypatch.setattr(workspace_startup, "main", second_server)
    previous_argv = list(desktop.sys.argv)
    with separate_workspace_owner(tmp_path):
        assert desktop.main(["--data-dir", str(tmp_path), "--port", "8881"]) == 0
    assert opened == [url]
    assert len(calls) == 4 and clock.now == pytest.approx(0.4)
    assert all(item[:3] == (8881, tmp_path, False) for item in calls)
    assert all(0 < item[3]["timeout"] <= 1 for item in calls[1:])
    assert desktop.sys.argv == previous_argv
    assert token not in caplog.text


def test_unmatched_busy_workspace_times_out_without_guessing_url_or_starting_again(
    launcher, tmp_path, monkeypatch
):
    desktop, clock, opened = launcher
    monkeypatch.setattr(desktop, "REOPEN_SECONDS", 0.45)
    monkeypatch.setattr(desktop, "existing_instance", lambda *args, **kwargs: None)
    starts = []

    def second_server():
        starts.append(True)
        with workspace_session(tmp_path):
            pytest.fail("An already-owned workspace must not start")

    monkeypatch.setattr(workspace_startup, "main", second_server)
    with (
        workspace_session(tmp_path),
        pytest.raises(RuntimeError, match="matching browser session"),
    ):
        desktop.main(["--data-dir", str(tmp_path), "--port", "8882", "--demo"])
    assert starts == [True] and not opened
    assert clock.now == pytest.approx(0.45)


@pytest.mark.parametrize("exit_code", [2, "Different startup failure"])
def test_unrelated_startup_errors_are_not_retried(launcher, tmp_path, monkeypatch, exit_code):
    desktop, clock, opened = launcher
    monkeypatch.setattr(desktop, "existing_instance", lambda *args: None)

    def fail():
        raise SystemExit(exit_code)

    monkeypatch.setattr(workspace_startup, "main", fail)
    with pytest.raises(SystemExit) as failure:
        desktop.main(["--data-dir", str(tmp_path)])
    assert failure.value.code == exit_code
    assert not clock.sleeps and not opened


@pytest.mark.parametrize("mismatch", ["workspace", "port", "demo"])
def test_reuse_never_sends_credential_for_another_workspace_port_or_mode(
    tmp_path, monkeypatch, mismatch
):
    desktop = helper("desktop")
    sessions = LocalSessions()
    write_instance(tmp_path, 8881, False, sessions)
    posts = []

    def read(url, *, launcher_key=None, **kwargs):
        if launcher_key:
            posts.append(launcher_key)
            return {"launch": sessions.issue_launch()}
        return {"app": "notification-workbench", "demo": False}

    monkeypatch.setattr(desktop, "read_local_json", read)
    path = tmp_path / "other" if mismatch == "workspace" else tmp_path
    port = 8882 if mismatch == "port" else 8881
    assert desktop.existing_instance(port, path, mismatch == "demo") is None
    assert posts == []


def test_reuse_requires_valid_authenticated_launch_token_and_shares_timeout_budget(
    tmp_path, monkeypatch
):
    desktop = helper("desktop")
    sessions = LocalSessions()
    write_instance(tmp_path, 8881, False, sessions)
    clock = Clock()
    monkeypatch.setattr(desktop, "time", clock)
    calls = []
    token = "trusted-launch-credential-1234567890"

    def read(url, *, launcher_key=None, timeout):
        calls.append((url, launcher_key, timeout))
        if launcher_key:
            assert sessions.launcher_authorized(launcher_key)
            return {"launch": token}
        clock.now += 0.6
        return {"app": "notification-workbench", "demo": False}

    monkeypatch.setattr(desktop, "read_local_json", read)
    assert (
        desktop.existing_instance(8881, tmp_path, False) == f"http://127.0.0.1:8881/#launch={token}"
    )
    assert calls[0][2] == 1 and calls[1][2] == pytest.approx(0.4)
    token = "https://untrusted.invalid/"
    assert desktop.existing_instance(8881, tmp_path, False) is None


def test_nsis_owns_gate_for_all_replacement_and_uninstall_mutations():
    script = (
        Path(__file__).resolve().parents[1] / "tools/windows_installer/installer.nsi"
    ).read_text(encoding="utf-8")
    desktop = helper("desktop")
    assert desktop.INSTALL_GATE == f"Local\\{desktop.IDENTITY['app_id']}.Installed.StartInstall"
    assert '!define START_INSTALL_MUTEX "Local\\${APP_ID}.Installed.StartInstall"' in script
    install = script.split('Section "${APP}" SEC_MAIN', 1)[1].split("SectionEnd", 1)[0]
    uninstall = script.split('Section "Uninstall"', 1)[1].split("SectionEnd", 1)[0]
    for section in (install, uninstall):
        assert section.index("!insertmacro AcquireInstallGate") < section.index(
            "!insertmacro CheckNotRunning"
        )
        assert section.rstrip().endswith("!insertmacro ReleaseInstallGate")
    assert install.index("!insertmacro CheckNotRunning") < install.index('File /r "${PAYLOAD}\\*"')
    assert uninstall.index("!insertmacro CheckNotRunning") < uninstall.index(
        '!include "${UNINSTALL_INVENTORY}"'
    )
    for callback in (".onInstFailed", ".onGUIEnd", "un.onUninstFailed", "un.onGUIEnd"):
        body = script.split("Function " + callback, 1)[1].split("FunctionEnd", 1)[0]
        assert "!insertmacro ReleaseInstallGate" in body
    running_check = script.split("!macro CheckNotRunning", 1)[1].split("!macroend", 1)[0]
    assert 'w "${MUTEX}"' in running_check  # Older running releases remain protected.
    assert "p.r0 ?e" in running_check and "Pop $1" in running_check
    assert "${If} $1 != 2" in running_check


def test_public_rename_replaces_only_legacy_darkmatter_shortcuts_after_new_links_exist():
    script = (
        Path(__file__).resolve().parents[1] / "tools/windows_installer/installer.nsi"
    ).read_text(encoding="utf-8")
    marker = (
        '!if "${APP_VARIANT}" == "dark_matter"\n!if "${APP}" != "Shadowserver Companion DarkMatter"'
    )
    cleanup = script.split(marker, 1)[1].split("!endif", 1)[0]
    expected = {
        "$DESKTOP\\Shadowserver Companion DarkMatter.lnk",
        "$SMPROGRAMS\\Shadowserver Companion DarkMatter\\Shadowserver Companion DarkMatter.lnk",
        "$SMPROGRAMS\\Shadowserver Companion DarkMatter\\Companion DarkMatter Demo.lnk",
        *{
            "$SMPROGRAMS\\Shadowserver Companion DarkMatter\\" + name + ".lnk"
            for name in (
                "Check installation",
                "Application logs",
                "Working data",
                "Getting started",
                "Uninstall",
            )
        },
    }
    removed = {
        line.strip().removeprefix('Delete "').removesuffix('"')
        for line in cleanup.splitlines()
        if line.strip().startswith("Delete ")
    }
    assert removed == expected
    assert 'RMDir "$SMPROGRAMS\\Shadowserver Companion DarkMatter"' in cleanup
    assert "RMDir /r" not in cleanup and "$LOCALAPPDATA" not in cleanup
    assert "Shadowserver Companion Chaos" not in cleanup and "OutreachWorkbench" not in cleanup
    # Required shortcut failure now aborts setup before legacy links are touched.
    guard = script.split('CreateShortCut "$DESKTOP\\${APP}.lnk"', 1)[1].split(marker, 1)[0]
    assert guard.index("${If} ${Errors}") < guard.index("Abort") < guard.index("${EndIf}")
    assert (
        'ClearErrors\n  CreateDirectory "$LOCALAPPDATA\\${APP_ID}\\data"\n'
        '  CreateDirectory "$SMPROGRAMS\\${APP}"'
    ) in script
    assert script.index(marker) > script.index('CreateShortCut "$DESKTOP\\${APP}.lnk"')
    assert script.index(marker) > script.index(
        'CreateShortCut "$SMPROGRAMS\\${APP}\\${DEMO_NAME}.lnk"'
    )
