"""Exercise the real Windows bootstrap in a fresh synthetic installation only."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from uuid import uuid4
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from build import build_bootstrap


CHILD = """import json, os, sys, time
from pathlib import Path
folder = Path(sys.argv[sys.argv.index('--data-dir') + 1])
version = Path(__file__).resolve().parents[4] / 'version.txt'
if not version.is_file():
    version = Path(__file__).with_name('version.txt')
(folder / 'child.json').write_text(json.dumps({'pid':os.getpid(),'argv':sys.argv,
    'version':version.read_text(encoding='utf-8')}), encoding='utf-8')
while not (folder / 'stop').exists():
    time.sleep(0.02)
raise SystemExit(7)
"""


def wait_for(predicate, seconds=5):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.02)
    raise TimeoutError("Synthetic bootstrap probe did not finish within its deadline")


def verify(output: Path, makensis: str, python_home: Path, *, baseline: Path | None = None) -> dict:
    if os.name != "nt":
        raise RuntimeError("Native bootstrap verification requires Windows")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    identity = "CompanionBootstrapProbe-" + uuid4().hex
    gate_name = f"Local\\{identity}.Installed.StartInstall"
    running_name = f"Local\\{identity}.Installed.Running"
    artifact, descriptor = build_bootstrap(output / "build", identity, makensis)
    install = output / "synthetic installation \u00e9\u5b89"
    runtime = install / "runtime"
    app = install / "app"
    runtime.mkdir(parents=True)
    app.mkdir()
    launcher = install / descriptor["path"]
    launcher.parent.mkdir()
    shutil.copyfile(artifact, launcher)
    for name in (
        "python.exe",
        "pythonw.exe",
        "python3.dll",
        "python314.dll",
        "vcruntime140.dll",
        "vcruntime140_1.dll",
    ):
        shutil.copyfile(python_home / name, runtime / name)
    (runtime / "python314._pth").write_text(
        "\n".join(map(str, (python_home / "Lib", python_home / "DLLs", python_home, ROOT))) + "\n",
        encoding="utf-8",
    )
    (app / "desktop.py").write_text(CHILD, encoding="utf-8")
    scheduled = app / "modules/accretion/tools/run_scheduled.py"
    scheduled.parent.mkdir(parents=True)
    scheduled.write_text(CHILD, encoding="utf-8")
    (app / "version.txt").write_text("old", encoding="utf-8")
    # The child resolves this common synthetic version independently of mode.
    (install / "version.txt").write_text("old", encoding="utf-8")
    marker = install / "installation-ready.ini"
    marker_text = f"[installation]\napp_id={identity}\nprotocol=1\n"
    marker.write_text(marker_text, encoding="utf-8")
    data = output / "working-records-sentinel.txt"
    data.write_bytes(b"Synthetic retained records: never part of program replacement.\n")
    sentinel = hashlib.sha256(data.read_bytes()).hexdigest()

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p)
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.OpenMutexW.argtypes = (ctypes.c_ulong, ctypes.c_int, ctypes.c_wchar_p)
    kernel.OpenMutexW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
    kernel.ReleaseMutex.argtypes = (ctypes.c_void_p,)
    kernel.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_ulong)
    kernel.OpenProcess.argtypes = (ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.TerminateProcess.argtypes = (ctypes.c_void_p, ctypes.c_uint)
    processes = []
    child_handles = []
    held_gates = []
    results = {
        "identity": identity,
        "bootstrap": descriptor,
        "compiler": makensis,
        "python": sys.version,
        "cases": [],
        "output": str(output),
    }

    def present():
        handle = kernel.OpenMutexW(0x00100000, False, running_name)
        if handle:
            kernel.CloseHandle(handle)
            return True
        assert ctypes.get_last_error() == 2
        return False

    def launch(name, *, interactive=False):
        folder = output / name
        folder.mkdir()
        command = [str(launcher)]
        if not interactive:
            command.append("--scheduled")
        command.extend(["--data-dir", str(folder)])
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        processes.append(process)
        return process, folder

    def child(folder):
        path = folder / "child.json"
        wait_for(path.is_file)
        record = json.loads(path.read_text(encoding="utf-8"))
        handle = kernel.OpenProcess(0x00100001, False, record["pid"])
        assert handle
        child_handles.append(handle)
        return record, handle

    def stop(process, folder):
        (folder / "stop").touch()
        assert process.wait(timeout=5) == 7
        wait_for(lambda: not present())

    def acquire():
        handle = kernel.CreateMutexW(None, False, gate_name)
        assert handle and kernel.WaitForSingleObject(handle, 1000) in (0, 128)
        held_gates.append(handle)
        return handle

    def release(handle):
        assert kernel.ReleaseMutex(handle)
        kernel.CloseHandle(handle)
        held_gates.remove(handle)

    try:
        if baseline is not None:
            with zipfile.ZipFile(baseline / "source.zip") as archive:
                legacy = archive.read("tools/windows_installer/desktop.py")
            manifest = json.loads((baseline / "sha256.json").read_text(encoding="utf-8"))
            legacy_hash = hashlib.sha256(legacy).hexdigest()
            assert legacy_hash == manifest["tools/windows_installer/desktop.py"]
            legacy_path = app / "legacy_desktop.py"
            legacy_path.write_bytes(legacy)
            folder = output / "legacy-before-gate"
            folder.mkdir()
            preamble = app / "legacy_import_probe.py"
            preamble.write_text(
                """import json, runpy, sys
from pathlib import Path
from modules.workspace.components import release
identity = sys.argv[3]
release.installation_identity = lambda *args: {'app_id':identity,'app_name':'Synthetic probe',
    'running_mutex':'Local\\\\'+identity+'.Installed.Running'}
values = runpy.run_path(sys.argv[1], run_name='legacy_import_probe')
Path(sys.argv[2]).write_text(json.dumps({'release_loaded':bool(values['RELEASE']),
    'modules_loaded':len(sys.modules),'registered':values['_installation_handle'] is not None}),encoding='utf-8')
values['hold_installation_mutex']()
""",
                encoding="utf-8",
            )
            gate = acquire()
            legacy_process = subprocess.Popen(
                [
                    str(runtime / "python.exe"),
                    "-I",
                    "-B",
                    str(preamble),
                    str(legacy_path),
                    str(folder / "preamble.json"),
                    identity,
                ],
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            processes.append(legacy_process)
            wait_for((folder / "preamble.json").is_file)
            observed = json.loads((folder / "preamble.json").read_text(encoding="utf-8"))
            assert observed["release_loaded"] and not observed["registered"] and not present()
            assert legacy_process.poll() is None
            legacy_process.kill()
            legacy_process.wait(timeout=5)
            release(gate)
            results["cases"].append(
                {
                    "case": "baseline_loaded_release_and_python_modules_before_gate",
                    "passed": True,
                    "observed": observed,
                    "source_sha256": legacy_hash,
                }
            )

        process, folder = launch("normal workspace \u00e9\u5b89")
        record, _ = child(folder)
        assert record["argv"][-2:] == ["--data-dir", str(folder)]
        assert present()
        handle = acquire()
        assert present()  # The same installer gate/check refuses an existing child.
        release(handle)
        stop(process, folder)
        results["cases"].append(
            {"case": "running_child_blocks_replacement", "passed": True, "child": record}
        )

        gate = acquire()
        process, folder = launch("overlap")
        time.sleep(0.2)
        assert process.poll() is None and not (folder / "child.json").exists() and not present()
        # A mapped immutable launcher can be waiting before Running exists.
        try:
            with launcher.open("r+b") as stream:
                stream.write(b"M")  # Preserve bytes even if a host unexpectedly permits the open.
        except PermissionError:
            locked = True
        else:
            locked = False
        assert locked
        (install / "version.txt").write_text("new", encoding="utf-8")
        release(gate)
        record, _ = child(folder)
        assert record["version"] == "new"
        stop(process, folder)
        results["cases"].append(
            {"case": "gate_precedes_child_and_loaded_launcher_is_immutable", "passed": True}
        )

        gate = acquire()
        process, folder = launch("interactive-busy-gate", interactive=True)
        started = time.monotonic()
        assert process.wait(timeout=7) == 6
        assert not (folder / "child.json").exists() and not present()
        release(gate)
        results["cases"].append(
            {
                "case": "interactive_busy_gate_exits_without_persistent_image_lock",
                "passed": True,
                "elapsed_seconds": time.monotonic() - started,
            }
        )

        marker.unlink()
        process, folder = launch("incomplete")
        assert (
            process.wait(timeout=5) == 6 and not (folder / "child.json").exists() and not present()
        )
        marker.write_text(marker_text, encoding="utf-8")
        results["cases"].append(
            {"case": "missing_ready_marker_refuses_partial_installation", "passed": True}
        )

        long_arguments = subprocess.Popen(
            [str(launcher), "--scheduled", "--data-dir", "x" * 1200],
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        processes.append(long_arguments)
        assert long_arguments.wait(timeout=5) == 6 and not present()
        results["cases"].append(
            {"case": "long_scheduled_arguments_fail_without_dialog_or_truncation", "passed": True}
        )

        process, folder = launch("bootstrap-crash")
        record, child_handle = child(folder)
        process.kill()
        process.wait(timeout=5)
        assert kernel.WaitForSingleObject(child_handle, 0) == 258 and present()
        (folder / "stop").touch()
        assert kernel.WaitForSingleObject(child_handle, 5000) == 0
        wait_for(lambda: not present())
        results["cases"].append(
            {"case": "child_keeps_registration_after_bootstrap_death", "passed": True}
        )

        # Keep a waiting bootstrap's gate handle alive while a synthetic installer
        # owner dies, so Windows supplies WAIT_ABANDONED rather than a new mutex.
        holder_code = """import ctypes, pathlib, sys, time
k=ctypes.WinDLL('kernel32',use_last_error=True)
k.CreateMutexW.argtypes=(ctypes.c_void_p,ctypes.c_int,ctypes.c_wchar_p)
k.CreateMutexW.restype=ctypes.c_void_p
h=k.CreateMutexW(None,True,sys.argv[1]); assert h
pathlib.Path(sys.argv[2]).touch()
time.sleep(30)
"""
        ready = output / "installer-owned"
        holder = subprocess.Popen(
            [sys.executable, "-c", holder_code, gate_name, str(ready)],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        processes.append(holder)
        wait_for(ready.is_file)
        process, folder = launch("abandoned-install")
        time.sleep(0.2)
        assert not (folder / "child.json").exists()
        marker.unlink()
        holder.kill()
        holder.wait(timeout=5)
        assert process.wait(timeout=5) == 6 and not (folder / "child.json").exists()
        marker.write_text(marker_text, encoding="utf-8")
        results["cases"].append(
            {"case": "abandoned_install_gate_does_not_authorize_partial_runtime", "passed": True}
        )

        # Exercise the actual Workspace helper from an installed-layout parent.
        # Its release identity is replaced only inside this synthetic child so
        # no real installed application's named object can be opened or created.
        folder = output / "renderer-parent-crash"
        folder.mkdir()
        render_script = app / "render_child.py"
        render_script.write_text(
            "import time\nfrom pathlib import Path\n"
            f"while not Path({str(folder / 'continue')!r}).exists(): time.sleep(0.02)\n" + CHILD,
            encoding="utf-8",
        )
        parent_script = app / "render_parent.py"
        parent_script.write_text(
            """import ctypes, json, subprocess, sys, time
from pathlib import Path
from modules.workspace.components import release
from modules.workspace.helpers.installed_process import installed_child_options
app, folder, name = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
release.load_release = lambda root: {'edition':'standard'}
release.installation_identity = lambda *args: {'running_mutex':name}
k=ctypes.WinDLL('kernel32',use_last_error=True)
k.CreateMutexW.argtypes=(ctypes.c_void_p,ctypes.c_int,ctypes.c_wchar_p)
k.CreateMutexW.restype=ctypes.c_void_p
h=k.CreateMutexW(None,False,name); assert h
with installed_child_options(app) as inherited:
    child=subprocess.Popen([sys.executable,'-I','-B',str(app/'render_child.py'),
        '--data-dir',str(folder)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW,**inherited)
(folder/'parent.json').write_text(json.dumps({'child_pid':child.pid}),encoding='utf-8')
time.sleep(30)
""",
            encoding="utf-8",
        )
        parent = subprocess.Popen(
            [
                str(runtime / "python.exe"),
                "-I",
                "-B",
                str(parent_script),
                str(app),
                str(folder),
                running_name,
            ],
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        processes.append(parent)
        wait_for((folder / "parent.json").is_file)
        pid = json.loads((folder / "parent.json").read_text(encoding="utf-8"))["child_pid"]
        child_handle = kernel.OpenProcess(0x00100001, False, pid)
        assert child_handle
        child_handles.append(child_handle)
        assert not (folder / "child.json").exists()
        parent.kill()
        parent.wait(timeout=5)
        assert present() and kernel.WaitForSingleObject(child_handle, 0) == 258
        (folder / "continue").touch()
        wait_for((folder / "child.json").is_file)
        (folder / "stop").touch()
        assert kernel.WaitForSingleObject(child_handle, 5000) == 0
        wait_for(lambda: not present())
        results["cases"].append(
            {"case": "renderer_inherits_guard_before_imports_and_parent_death", "passed": True}
        )
        assert hashlib.sha256(launcher.read_bytes()).hexdigest() == descriptor["sha256"]
        assert hashlib.sha256(data.read_bytes()).hexdigest() == sentinel
        results["retained_sentinel_sha256"] = sentinel
        results["source_sha256"] = {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "tools/windows_installer/bootstrap.nsi",
                "tools/windows_installer/build.py",
                "tools/windows_installer/verify_bootstrap.py",
                "modules/workspace/helpers/installed_process.py",
            )
        }
        results["success"] = True
    except BaseException as error:
        results["failure"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        for handle in held_gates:
            kernel.ReleaseMutex(handle)
            kernel.CloseHandle(handle)
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
        children_stopped = True
        for handle in child_handles:
            if kernel.WaitForSingleObject(handle, 0) == 258:
                kernel.TerminateProcess(handle, 90)
            children_stopped = kernel.WaitForSingleObject(handle, 5000) == 0 and children_stopped
            kernel.CloseHandle(handle)
        results["all_child_processes_stopped"] = children_stopped
        results["all_owned_processes_stopped"] = all(
            process.poll() is not None for process in processes
        )
        (output / "native-bootstrap-result.json").write_text(
            json.dumps(results, indent=2), encoding="utf-8"
        )
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="Fresh synthetic evidence directory"
    )
    parser.add_argument("--makensis", required=True)
    parser.add_argument(
        "--python-home", type=Path, required=True, help="Existing Python 3.14 tools directory"
    )
    parser.add_argument(
        "--baseline", type=Path, help="Optional immutable source.zip/sha256.json baseline"
    )
    args = parser.parse_args()
    print(
        json.dumps(
            verify(args.output, args.makensis, args.python_home, baseline=args.baseline), indent=2
        )
    )


if __name__ == "__main__":
    main()
