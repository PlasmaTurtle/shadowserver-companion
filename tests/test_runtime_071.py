"""Distribution/runtime contracts shared by the source and installed editions."""

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
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
    inventory = json.loads((ROOT / "wheelhouse-sha256.json").read_text())
    assert set(inventory) == {p.name for p in (ROOT / "wheelhouse").glob("*.whl")}
    packages = builder.validate_wheels(ROOT / "wheelhouse")
    assert {p["artifact"] for p in packages} == set(inventory)
    requirements = (ROOT / "requirements-windows.txt").read_text()
    for filename, digest in inventory.items():
        assert hashlib.sha256((ROOT / "wheelhouse" / filename).read_bytes()).hexdigest() == digest
        assert "--hash=sha256:" + digest in requirements
        _, _, _, tags = parse_wheel_filename(filename)
        assert any(t.platform == "any" or t.platform == "win_amd64" for t in tags)
        assert any(t.interpreter in {abi, "py3"} or t.abi == "abi3" for t in tags)
    assert not (ROOT / "tools/windows_installer/wheel-lock.json").exists()
    assert not (ROOT / "tools/windows_installer/requirements-cp314.txt").exists()


def test_isolated_runtime_path_matches_selected_interpreter(tmp_path):
    tag = "python" + "".join(map(str, bootstrap.runtime_version()))
    archive = tmp_path / "runtime.zip"
    with zipfile.ZipFile(archive, "w") as out:
        out.writestr(tag + "._pth", "old configuration\n")
        out.writestr(tag + ".zip", b"synthetic runtime fixture")
    target = tmp_path / "runtime"
    builder.extract_runtime(archive, target, tag)
    assert (target / (tag + "._pth")).read_text().splitlines() == [
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


def test_launchers_read_version_instead_of_embedding_a_release():
    for filename in ["Start Workbench.cmd", "Start Demo.cmd", "Attribution.cmd"]:
        text = (ROOT / filename).read_text()
        assert "set /p WORKBENCH_VERSION=<VERSION" in text
        assert 'findstr /x /c:"%WORKBENCH_VERSION%"' in text
        assert "0.6.0" not in text
