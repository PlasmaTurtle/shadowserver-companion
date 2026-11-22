"""Repair/uninstall cases that previously required manual Programs-folder deletion."""

import importlib.util
import json
from pathlib import Path

import pytest

from tests.filesystem_helpers import create_test_symlink

from tests.support.installation import digest, installation, inventory, upgrade, write_files


ROOT = Path(__file__).resolve().parents[1]


def canonical(tmp_path, monkeypatch):
    local = tmp_path / "LocalAppData"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    return local / "Programs" / "OutreachWorkbench"


def test_cache_only_old_uninstall_residue_is_repaired_without_old_python(tmp_path, monkeypatch):
    root = canonical(tmp_path, monkeypatch)
    write_files(
        root,
        {
            "runtime/Lib/site-packages/dns/__pycache__/resolver.cpython-314.pyc": b"old bytecode",
            "app/workbench/__pycache__/api.cpython-314.pyc": b"old bytecode",
            "app/data/important.pyc": b"misplaced case evidence",
            "notes.txt": b"user note",
        },
    )
    staged = tmp_path / "new.json"
    inventory(staged, {"app/run.py": b"new entry", "runtime/python.exe": b"new interpreter"})
    removed = upgrade.cleanup(root, staged)
    assert len(removed) == 2
    assert not (root / "runtime").exists()
    assert (root / "app/data/important.pyc").read_bytes() == b"misplaced case evidence"
    assert (root / "notes.txt").read_bytes() == b"user note"


def test_known_partial_install_with_broken_runtime_can_be_repaired(tmp_path, monkeypatch):
    root = canonical(tmp_path, monkeypatch)
    write_files(root, {"runtime/python.exe": b"truncated executable", "app/run.py": b"partial"})
    staged = tmp_path / "new.json"
    inventory(staged, {"runtime/python.exe": b"complete interpreter", "app/run.py": b"complete"})
    assert upgrade.cleanup(root, staged) == []
    # Preflight does not execute or delete the bad interpreter; NSIS overlays it.
    assert (root / "runtime/python.exe").read_bytes() == b"truncated executable"


def test_registered_custom_partial_install_requires_explicit_identity(tmp_path):
    root = tmp_path / "custom-program"
    write_files(root, {"runtime/python.exe": b"broken"})
    staged = tmp_path / "new.json"
    inventory(staged, {"runtime/python.exe": b"new"})
    with pytest.raises(upgrade.UpgradeError, match="no inventory or recognized"):
        upgrade.cleanup(root, staged)
    assert upgrade.cleanup(root, staged, known_installation=True) == []


def test_matching_release_identity_allows_custom_location_repair(tmp_path):
    root = tmp_path / "custom-program"
    release = json.dumps({"edition": "standard", "version": "0.7.0"}).encode()
    write_files(root, {"app/RELEASE.json": release, "runtime/python.exe": b"broken"})
    staged = tmp_path / "new.json"
    inventory(staged, {"app/RELEASE.json": release, "runtime/python.exe": b"new"})
    assert upgrade.cleanup(root, staged) == []


@pytest.mark.parametrize(
    "release,match",
    [
        (
            {"edition": "chaos", "variant": "dark_matter", "version": "0.7.0"},
            "Different application edition",
        ),
        ({"edition": "standard", "version": "99.0.0"}, "newer application"),
    ],
)
def test_repair_respects_edition_and_downgrade_even_without_inventory(
    tmp_path, monkeypatch, release, match
):
    root = canonical(tmp_path, monkeypatch)
    write_files(root, {"app/RELEASE.json": json.dumps(release).encode()})
    staged = tmp_path / "new.json"
    inventory(staged, {"app/RELEASE.json": b"new"})
    with pytest.raises(upgrade.UpgradeError, match=match):
        upgrade.cleanup(root, staged)
    assert json.loads((root / "app/RELEASE.json").read_text(encoding="utf-8")) == release


def test_unknown_runtime_code_is_retained_and_preflight_does_not_partially_clean(
    tmp_path, monkeypatch
):
    root = canonical(tmp_path, monkeypatch)
    files = {
        "runtime/Lib/site-packages/unrecognized.pyd": b"do not guess ownership",
        "runtime/Lib/site-packages/pkg/__pycache__/module.cpython-314.pyc": b"cache",
    }
    write_files(root, files)
    staged = tmp_path / "new.json"
    inventory(staged, {"runtime/python.exe": b"new"})
    with pytest.raises(upgrade.UpgradeError, match="unrecognized code"):
        upgrade.cleanup(root, staged)
    assert all((root / name).read_bytes() == data for name, data in files.items())


def test_uninstall_removes_generated_caches_without_local_inventory_or_runtime(tmp_path):
    root = tmp_path / "installed"
    files = {
        "app/workbench/__pycache__/api.cpython-314.pyc": b"cache",
        "runtime/Lib/site-packages/pkg/__pycache__/native.cpython-314.pyc": b"cache",
        "app/workbench/user-notes.txt": b"retain",
        "data/report.pdf": b"casework",
        "runtime/Lib/site-packages/data/source.pyc": b"protected data",
    }
    write_files(root, files)
    embedded = tmp_path / "embedded.json"
    inventory(
        embedded,
        {"app/modules/workspace/components/api.py": b"code", "runtime/python.exe": b"runtime"},
    )
    removed = upgrade.uninstall(root, embedded)
    assert len(removed) == 2
    for name in removed:
        assert not (root / name).exists()
    for name in files.keys() - set(removed):
        assert (root / name).read_bytes() == files[name]


def test_cache_link_fails_before_any_cache_is_removed(tmp_path):
    root, staged = installation(tmp_path)
    cache = root / "app/workbench/__pycache__"
    cache.mkdir()
    first = cache / "first.cpython-314.pyc"
    first.write_bytes(b"cache")
    outside = tmp_path / "outside"
    outside.write_bytes(b"protected")
    create_test_symlink(cache / "linked.cpython-314.pyc", outside)
    with pytest.raises(upgrade.UpgradeError, match="Linked/reparse"):
        upgrade.uninstall(root, staged)
    assert first.exists() and outside.read_bytes() == b"protected"


def test_uninstall_prunes_empty_generated_cache_directories(tmp_path):
    root = tmp_path / "installed"
    (root / "runtime/Lib/site-packages/pkg/__pycache__").mkdir(parents=True)
    (root / "app/data/__pycache__").mkdir(parents=True)
    embedded = tmp_path / "embedded.json"
    inventory(embedded, {"runtime/python.exe": b"runtime"})
    assert upgrade.uninstall(root, embedded) == []
    assert not (root / "runtime").exists()
    assert (root / "app/data/__pycache__").is_dir()


def test_task_removal_uses_staged_adapter_and_only_matching_workspace(tmp_path, monkeypatch):
    local = tmp_path / "LocalAppData"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    embedded = tmp_path / "embedded.json"
    inventory(embedded, {"runtime/python.exe": b"runtime"})
    metadata = json.loads(embedded.read_text(encoding="utf-8"))
    metadata["release"] = {"edition": "chaos", "variant": "dark_matter"}
    embedded.write_text(json.dumps(metadata))
    calls = []

    def load_adapter(path):
        assert Path(path) == Path(upgrade.__file__).with_name("windows_schedule.py")
        return {"configure": lambda workspace, enabled: calls.append((workspace, enabled))}

    monkeypatch.setattr(upgrade.runpy, "run_path", load_adapter)
    upgrade.remove_scheduled_task(embedded)
    assert calls == [(local / "ShadowserverCompanionDarkMatter" / "data", False)]


def test_only_reviewed_installer_brand_assets_are_distributed():
    from tools.release_policy import distributable

    for name in ("setup-sidebar", "setup-header", "uninstall-sidebar"):
        for extension in (".svg", ".bmp"):
            relative = Path("tools/windows_installer/assets") / (name + extension)
            assert (ROOT / relative).is_file()
            assert distributable(relative) and distributable(relative, installed=True)
    assert not distributable(Path("tools/windows_installer/assets/private-capture.bmp"))


def test_static_uninstall_inventory_aborts_before_directory_or_registry_cleanup(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "installer_build_0120", ROOT / "tools/windows_installer/build.py"
    )
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    payload = tmp_path / "payload"
    write_files(payload, {"runtime/python.exe": b"runtime"})
    script = build.uninstall_inventory(payload)
    assert (
        script.index('Delete "$INSTDIR\\runtime\\python.exe"')
        < script.index("SetErrorLevel 5")
        < script.index("RMDir")
    )
    installer = (ROOT / "tools/windows_installer/installer.nsi").read_text(encoding="utf-8")
    uninstall = installer.split('Section "Uninstall"', 1)[1]
    assert (
        uninstall.index('!include "${UNINSTALL_INVENTORY}"')
        < uninstall.index('StrCpy $5 "${KEY}"')
        < uninstall.index('DeleteRegKey HKCU "$5"')
        < uninstall.index('Delete "$INSTDIR\\Uninstall.exe"')
    )


def test_installer_maintenance_and_update_paths_do_not_depend_on_old_runtime():
    script = (ROOT / "tools/windows_installer/installer.nsi").read_text(encoding="utf-8")
    assert 'File "${PAYLOAD}\\runtime\\*.*"' in script
    assert '"$PLUGINSDIR\\maintenance-runtime\\python.exe" -I -S -B' in script
    assert '"$INSTDIR\\runtime\\python.exe" -I -S -B' not in script
    assert 'StrCpy $UpdateRequested "yes"' in script
    assert "Function WaitForUpdateExit" in script and "${LoopWhile} $5 < 120" in script
    assert "Function .onInstSuccess" in script
    assert "Keep its console window open" not in script
