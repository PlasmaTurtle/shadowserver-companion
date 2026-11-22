"""Distribution/runtime contracts shared by the source and installed editions."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace
import venv
import zipfile

import pytest
from packaging.utils import parse_wheel_filename

ROOT = Path(__file__).resolve().parents[1]


def load_tool(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bootstrap = load_tool("setup_environment_071", "tools/setup_environment.py")
builder = load_tool("installer_build_071", "tools/windows_installer/build.py")


def test_source_and_installer_use_one_complete_verified_dependency_set():
    version = bootstrap.runtime_version()
    abi = "cp" + "".join(map(str, version))
    packages = builder.validate_wheels(ROOT / "wheelhouse")
    inventory = {p["artifact"]: p["sha256"] for p in packages}
    assert set(inventory) == {p.name for p in (ROOT / "wheelhouse").glob("*.whl")}
    requirements = (ROOT / "requirements-windows.txt").read_text(encoding="utf-8")
    for filename, digest in inventory.items():
        assert hashlib.sha256((ROOT / "wheelhouse" / filename).read_bytes()).hexdigest() == digest
        assert "--hash=sha256:" + digest in requirements
        _, _, _, tags = parse_wheel_filename(filename)
        assert any(t.platform == "any" or t.platform == "win_amd64" for t in tags)
        assert any(t.interpreter in {abi, "py3"} or t.abi == "abi3" for t in tags)
    assert not (ROOT / "tools/windows_installer/wheel-lock.json").exists()
    assert not (ROOT / "tools/windows_installer/requirements-cp314.txt").exists()
    assert not (ROOT / "wheelhouse-sha256.json").exists()


def test_isolated_runtime_path_matches_selected_interpreter(tmp_path):
    tag = "python" + "".join(map(str, bootstrap.runtime_version()))
    archive = tmp_path / "runtime.zip"
    with zipfile.ZipFile(archive, "w") as out:
        out.writestr(tag + "._pth", "old configuration\n")
        out.writestr(tag + ".zip", b"synthetic runtime fixture")
    target = tmp_path / "runtime"
    builder.extract_runtime(archive, target, tag)
    assert (target / (tag + "._pth")).read_text(encoding="utf-8").splitlines() == [
        tag + ".zip",
        ".",
        "Lib/site-packages",
        "../app",
        "import site",
    ]
    assert len(list(target.glob("*._pth"))) == 1


def test_source_setup_refuses_incompatible_environment_without_touching_casework(
    tmp_path, monkeypatch
):
    version = bootstrap.runtime_version()
    (tmp_path / "tools/windows_installer").mkdir(parents=True)
    (tmp_path / "tools/windows_installer/runtime-lock.json").write_text(
        json.dumps({"version": ".".join(map(str, version)) + ".0"})
    )
    (tmp_path / "VERSION").write_text("0.7.1\n")
    (tmp_path / ".venv/Scripts").mkdir(parents=True)
    (tmp_path / ".venv/Scripts/python.exe").write_bytes(b"wrong interpreter fixture")
    (tmp_path / "data").mkdir()
    record = tmp_path / "data/case.json"
    record.write_bytes(b'{"keep":"unchanged"}')
    monkeypatch.setattr(bootstrap, "ROOT", tmp_path)
    monkeypatch.setattr(bootstrap, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(bootstrap, "compatible", lambda *args: False)
    calls = []
    monkeypatch.setattr(bootstrap.subprocess, "run", lambda *args, **kwargs: calls.append(args))
    with pytest.raises(RuntimeError, match="rename .venv"):
        bootstrap.main()
    assert not calls
    assert record.read_bytes() == b'{"keep":"unchanged"}'
    assert not (tmp_path / ".venv/workbench-version.txt").exists()


LAUNCHERS = (
    "Start Workbench.cmd",
    "Start Demo.cmd",
    "modules/attribution/tools/Attribution.cmd",
)


def source_launcher_fixture(tmp_path, *, interpreter=False, setup_exit=0):
    root = tmp_path / "source checkout with spaces"
    for filename in (*LAUNCHERS, "tools/ensure_environment.cmd"):
        target = root / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / filename, target)
    (root / "VERSION").write_text("123.456.789\n", encoding="utf-8")
    if interpreter:
        venv.EnvBuilder(with_pip=False).create(root / ".venv")
    else:
        (root / ".venv/Scripts").mkdir(parents=True)
        (root / ".venv/Scripts/python.exe").write_bytes(b"not executed by bootstrap")
    (root / ".venv/workbench-version.txt").write_text("123.456.789\n", encoding="utf-8")
    (root / "Setup.cmd").write_text(
        f"@echo off\n>setup-called.txt echo %CD%\nexit /b {setup_exit}\n", encoding="utf-8"
    )
    return root


def run_source_command(tmp_path, script, arguments=""):
    # Launch from an unrelated directory, as an Explorer shortcut or terminal may.
    working = tmp_path / "unrelated working directory"
    working.mkdir(exist_ok=True)
    (working / "driver.cmd").write_text(
        f'@echo off\ncall "{script}" {arguments}\nexit /b %errorlevel%\n', encoding="utf-8"
    )
    return subprocess.run(
        [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", "driver.cmd"],
        cwd=working,
        input="\n",
        capture_output=True,
        text=True,
        timeout=20,
    )


def write_source_launch_probe(root, app_exit=0):
    program = (
        "import json, sys\nfrom pathlib import Path\n"
        'Path("launch.json").write_text(json.dumps({"arguments": sys.argv[1:], '
        '"cwd": str(Path.cwd())}))\n'
        f"raise SystemExit({app_exit})\n"
    )
    (root / "run.py").write_text(program, encoding="utf-8")
    (root / "attribution").mkdir()
    (root / "attribution/__init__.py").write_text("", encoding="utf-8")
    (root / "attribution/__main__.py").write_text(program, encoding="utf-8")


@pytest.mark.skipif(os.name != "nt", reason="Executes the native Windows source bootstrap")
@pytest.mark.parametrize(
    "state,setup_exit,expected_exit",
    [
        ("current", 7, 0),
        ("missing-python", 0, 0),
        ("missing-version", 0, 0),
        ("stale", 0, 0),
        ("stale", 7, 7),
    ],
)
def test_shared_source_bootstrap_checks_version_and_preserves_setup_result(
    tmp_path, state, setup_exit, expected_exit
):
    root = source_launcher_fixture(tmp_path, setup_exit=setup_exit)
    if state == "missing-python":
        (root / ".venv/Scripts/python.exe").unlink()
    elif state == "missing-version":
        (root / ".venv/workbench-version.txt").unlink()
    elif state == "stale":
        (root / ".venv/workbench-version.txt").write_text("123.456.788\n", encoding="utf-8")
    result = run_source_command(tmp_path, root / "tools/ensure_environment.cmd")
    assert result.returncode == expected_exit, result.stdout + result.stderr
    called = root / "setup-called.txt"
    assert called.exists() is (state != "current")
    if called.exists():
        assert Path(called.read_text().strip()) == root


@pytest.mark.skipif(os.name != "nt", reason="Executes native Windows source launchers")
@pytest.mark.parametrize("filename", LAUNCHERS)
def test_source_launchers_stop_when_shared_setup_fails(tmp_path, filename):
    root = source_launcher_fixture(tmp_path, interpreter=True, setup_exit=7)
    write_source_launch_probe(root)
    (root / ".venv/workbench-version.txt").unlink()
    result = run_source_command(tmp_path, root / filename)
    assert result.returncode == 1, result.stdout + result.stderr
    assert (root / "setup-called.txt").exists()
    assert not (root / "launch.json").exists()
    assert result.stdout.strip()  # The failure remains visible at the launcher's pause.


@pytest.mark.skipif(os.name != "nt", reason="Executes native Windows source launchers")
@pytest.mark.parametrize("app_exit", [0, 17])
@pytest.mark.parametrize(
    "filename,arguments,expected_arguments,interactive",
    [
        (LAUNCHERS[0], "", [], False),
        (LAUNCHERS[1], "", ["--demo"], False),
        (LAUNCHERS[2], 'lookup "two words"', ["lookup", "two words"], False),
        (LAUNCHERS[2], "", ["interactive"], True),
    ],
)
def test_source_launchers_preserve_arguments_working_directory_and_exit_status(
    tmp_path, filename, arguments, expected_arguments, interactive, app_exit
):
    root = source_launcher_fixture(tmp_path, interpreter=True, setup_exit=7)
    write_source_launch_probe(root, app_exit)
    result = run_source_command(tmp_path, root / filename, arguments)
    expected_exit = (
        0 if interactive else app_exit if filename == LAUNCHERS[2] else int(bool(app_exit))
    )
    assert result.returncode == expected_exit, result.stdout + result.stderr
    assert json.loads((root / "launch.json").read_text(encoding="utf-8")) == {
        "arguments": expected_arguments,
        "cwd": str(root),
    }
    assert not (root / "setup-called.txt").exists()
    assert bool(result.stdout.strip()) is (
        interactive or (filename != LAUNCHERS[2] and bool(app_exit))
    )
