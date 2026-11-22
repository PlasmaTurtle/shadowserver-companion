"""Only installed child processes inherit the parent's installation guard."""

import ctypes
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from modules.workspace.helpers import installed_process
from modules.workspace.components import release


def test_source_child_needs_no_windows_guard(monkeypatch, tmp_path):
    monkeypatch.setattr(
        installed_process, "sys", SimpleNamespace(executable=str(tmp_path / "venv/python.exe"))
    )
    forbidden = Mock(side_effect=AssertionError("Source child must not open installed handles"))
    monkeypatch.setattr(ctypes, "WinDLL", forbidden, raising=False)
    with installed_process.installed_child_options(tmp_path / "source") as options:
        assert options == {}
    forbidden.assert_not_called()


@pytest.fixture
def installed(monkeypatch, tmp_path):
    kernel = SimpleNamespace(OpenMutexW=Mock(return_value=123), CloseHandle=Mock())
    monkeypatch.setattr(installed_process, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(
        installed_process, "sys", SimpleNamespace(executable=str(tmp_path / "runtime/python.exe"))
    )
    monkeypatch.setattr(
        installed_process, "subprocess", SimpleNamespace(STARTUPINFO=SimpleNamespace)
    )
    monkeypatch.setattr(ctypes, "WinDLL", lambda *args, **kwargs: kernel, raising=False)
    monkeypatch.setattr(release, "load_release", lambda root: {"edition": "standard"})
    monkeypatch.setattr(
        release,
        "installation_identity",
        lambda *args: {"running_mutex": "Local\\Synthetic.Running"},
    )
    return tmp_path / "app", kernel


def test_installed_child_inherits_only_guard_and_parent_duplicate_closes(installed):
    root, kernel = installed
    with installed_process.installed_child_options(root) as options:
        kernel.OpenMutexW.assert_called_once_with(0x00100000, True, "Local\\Synthetic.Running")
        assert options["close_fds"] is True
        assert options["startupinfo"].lpAttributeList == {"handle_list": [123]}
        kernel.CloseHandle.assert_not_called()
    kernel.CloseHandle.assert_called_once_with(123)


def test_failed_process_creation_releases_parent_duplicate(installed):
    root, kernel = installed
    with pytest.raises(OSError, match="synthetic process failure"):
        with installed_process.installed_child_options(root):
            raise OSError("synthetic process failure")
    kernel.CloseHandle.assert_called_once_with(123)


def test_installed_child_refuses_missing_registration(installed):
    root, kernel = installed
    kernel.OpenMutexW.return_value = 0
    with pytest.raises(RuntimeError, match="installation guard"):
        with installed_process.installed_child_options(root):
            pytest.fail("Unregistered installed child cannot start")
    kernel.CloseHandle.assert_not_called()
