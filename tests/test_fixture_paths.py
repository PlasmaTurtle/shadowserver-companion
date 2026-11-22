"""Explicit package paths and unambiguous filenames for browser fixtures and pytest."""

import os
from pathlib import Path
import subprocess
import sys

import pytest

from tests.fixture_paths import configure_fixture_imports, validate_fixture_imports

ROOT = Path(__file__).resolve().parents[1]


def write_files(root: Path, *names: str) -> None:
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Synthetic test helper\n", encoding="utf-8")


def test_fixture_import_paths_keep_order_and_are_idempotent(tmp_path, monkeypatch):
    write_files(
        tmp_path,
        "tests/shared_fixture.py",
        "modules/entities/tests/entity_fixture.py",
        "modules/workspace/tests/workspace_fixture.py",
    )
    monkeypatch.setattr(sys, "path", ["existing-path"])
    configure_fixture_imports(tmp_path)
    expected = [
        str(tmp_path),
        str(tmp_path / "modules/attribution/components/engine/src"),
        "existing-path",
    ]
    assert sys.path == expected
    configure_fixture_imports(tmp_path)
    assert sys.path == expected


@pytest.mark.parametrize(
    "names",
    [
        ("tests/shared_fixture.py", "modules/entities/tests/shared_fixture.py"),
        ("modules/entities/tests/test_review.py", "modules/leads/tests/test_review.py"),
        ("tests/Shared_Fixture.py", "modules/entities/tests/shared_fixture.py"),
    ],
)
def test_ambiguous_fixture_names_fail_before_sys_path_changes(tmp_path, monkeypatch, names):
    write_files(tmp_path, *names)
    monkeypatch.setattr(sys, "path", ["existing-path"])
    with pytest.raises(ValueError, match="Ambiguous test-helper import") as caught:
        configure_fixture_imports(tmp_path)
    for name in names:
        assert name in str(caught.value)
    assert sys.path == ["existing-path"]


def test_local_pytest_configuration_and_packages_may_repeat(tmp_path):
    write_files(
        tmp_path,
        "tests/conftest.py",
        "tests/__init__.py",
        "modules/entities/tests/conftest.py",
        "modules/entities/tests/__init__.py",
        "modules/entities/tests/nested/shared_fixture.py",
        "modules/leads/tests/nested/shared_fixture.py",
    )
    validate_fixture_imports(tmp_path)


def test_pytest_rejects_ambiguous_helpers_before_collection(tmp_path):
    write_files(tmp_path, "tests/shared_fixture.py", "modules/entities/tests/shared_fixture.py")
    (tmp_path / "tests/__init__.py").write_bytes((ROOT / "tests/__init__.py").read_bytes())
    (tmp_path / "conftest.py").write_bytes((ROOT / "conftest.py").read_bytes())
    (tmp_path / "tests/fixture_paths.py").write_bytes(
        (ROOT / "tests/fixture_paths.py").read_bytes()
    )
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\npythonpath = ["."]\n', encoding="utf-8"
    )
    (tmp_path / "tests/test_not_collected.py").write_text(
        'raise RuntimeError("collection must not start")\n', encoding="utf-8"
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=tmp_path,
        env={**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == pytest.ExitCode.USAGE_ERROR
    assert "Ambiguous test-helper import 'shared_fixture'" in result.stderr
    assert "collection must not start" not in result.stdout + result.stderr
