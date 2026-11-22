"""Installer protocol checks; native focus behavior still needs Windows acceptance."""

from pathlib import Path
import shutil
import subprocess
import os

import pytest


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "tools/windows_installer/installer.nsi"


def block(script, declaration, terminator):
    return script.split(declaration, 1)[1].split(terminator, 1)[0]


def test_duplicate_wizard_guard_precedes_both_setup_and_removal_ui():
    script = INSTALLER.read_text(encoding="utf-8")
    assert '!define SETUP_INSTANCE_MUTEX "Local\\${APP_ID}.Setup.Instance"' in script
    guard = block(script, "!macro AcquireSetupInstance", "!macroend")
    assert 'CreateMutexW(p 0, i 0, w "${SETUP_INSTANCE_MUTEX}") p.r0 ?e' in guard
    assert guard.index("Pop $1") < guard.index("${If} $1 == 183")
    duplicate = block(guard, "${If} $1 == 183", "${EndIf}\n    SetErrorLevel")
    assert "CloseHandle(p r0)" in duplicate
    assert "${IfNot} ${Silent}" in duplicate
    assert "!insertmacro FocusExistingSetup" in duplicate
    assert "SetErrorLevel 1618" in guard and "Abort" in guard
    assert "WaitForSingleObject" not in guard
    for callback in (".onInit", "un.onInit"):
        body = block(script, "Function " + callback + "\n", "FunctionEnd")
        assert body.index("!insertmacro AcquireSetupInstance") < body.index(
            "!insertmacro CheckNotRunning"
        )


def test_wizard_lifetime_and_file_mutation_guards_are_independent():
    script = INSTALLER.read_text(encoding="utf-8")
    assert "${APP_ID}.Installed.StartInstall" in script
    for declaration in ('Section "${APP}" SEC_MAIN', 'Section "Uninstall"'):
        section = block(script, declaration, "SectionEnd")
        assert "!insertmacro AcquireInstallGate" in section
        assert "!insertmacro ReleaseInstallGate" in section
        assert "ReleaseSetupInstance" not in section
    for callback in (".onInstFailed", "un.onUninstFailed"):
        assert "ReleaseSetupInstance" not in block(
            script, "Function " + callback + "\n", "FunctionEnd"
        )
    for callback in (".onGUIEnd", "un.onGUIEnd"):
        body = block(script, "Function " + callback + "\n", "FunctionEnd")
        assert "!insertmacro ReleaseInstallGate" in body
        assert "!insertmacro ReleaseSetupInstance" in body
    release = block(script, "!macro ReleaseSetupInstance", "!macroend")
    assert "CloseHandle(p $SetupInstance)" in release
    assert "ReleaseMutex" not in release  # The UI guard owns a handle, not the mutex.


def test_duplicate_launch_targets_the_marked_window_without_opening_another_dialog():
    script = INSTALLER.read_text(encoding="utf-8")
    focus = block(script, "!macro FocusExistingSetup", "!macroend")
    assert 'GetPropW(p r3, w "${SETUP_WINDOW_PROPERTY}")' in focus
    assert "IsIconic" in focus and "ShowWindow(p r3, i 9)" in focus
    assert "GetLastActivePopup" in focus and "SetForegroundWindow" in focus
    assert "Sleep 100" in focus and "${LoopWhile} $2 < 20" in focus
    assert "MessageBox" not in focus and "Exec" not in focus
    assert "Function .onGUIInit\n" not in script
    assert "Function un.onGUIInit\n" not in script
    for define, callback in (
        ("MUI_CUSTOMFUNCTION_GUIINIT", "PublishInstallerWindow"),
        ("MUI_CUSTOMFUNCTION_UNGUIINIT", "un.PublishInstallerWindow"),
    ):
        declaration = f"!define {define} {callback}"
        assert declaration in script
        assert script.index(declaration) < script.index('!insertmacro MUI_LANGUAGE "English"')
        assert "!insertmacro PublishSetupWindow" in block(
            script, "Function " + callback + "\n", "FunctionEnd"
        )
    assert 'SetPropW(p $HWNDPARENT, w "${SETUP_WINDOW_PROPERTY}", p 1)' in script
    assert 'RemovePropW(p $HWNDPARENT, w "${SETUP_WINDOW_PROPERTY}")' in script


@pytest.mark.skipif(not shutil.which("makensis"), reason="NSIS compiler is not installed")
def test_installer_compiles_with_smoke_payload(tmp_path):
    """Syntax-check the real script without building or shipping a release."""
    payload = tmp_path / "payload"
    payload.mkdir()
    (payload / "payload-manifest.json").write_text("{}")
    (payload / "runtime").mkdir()
    (payload / "runtime/python.exe").write_bytes(b"compiler-only runtime placeholder")
    inventory = tmp_path / "uninstall.nsh"
    inventory.write_text('Delete "$INSTDIR\\payload-manifest.json"\n')
    output = tmp_path / "smoke-installer.exe"
    bootstrap = tmp_path / "compiler-only-bootstrap.exe"
    bootstrap.write_bytes(b"compiler-only bootstrap placeholder")
    definitions = {
        "PAYLOAD": payload,
        "OUTPUT": output,
        "APP_VERSION": "0.9.98",
        "APP_DISPLAY_VERSION": "0.9.98",
        "APP": "Shadowserver Eclipse",
        "APP_ID": "ShadowserverCompanionDarkMatter",
        "APP_EDITION": "chaos",
        "APP_VARIANT": "dark_matter",
        "DEMO_NAME": "Shadowserver Eclipse Demo",
        "RELEASE_NOTICE": "Compiler validation fixture",
        "UNINSTALL_INVENTORY": inventory,
        "BOOTSTRAP_SOURCE": bootstrap,
        "BOOTSTRAP_NAME": "launch-" + "0" * 64 + ".exe",
    }
    flag = "/" if os.name == "nt" else "-"
    result = subprocess.run(
        [
            shutil.which("makensis"),
            flag + "WX",
            flag + "V2",
            *[flag + "D" + key + "=" + str(value) for key, value in definitions.items()],
            str(INSTALLER),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=INSTALLER.parent,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert output.is_file() and output.stat().st_size > 0
