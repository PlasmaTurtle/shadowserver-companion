"""Behavioral and architectural checks for internal component boundaries."""

import json
from pathlib import Path
import subprocess
import sys

import pytest
from tools.program_map import analyze, cycles, imports, verify

ROOT = Path(__file__).resolve().parents[1]


def test_intake_and_adapter_imports_do_not_load_application_services():
    code = """
import sys
import workbench.intake
import workbench.intelligence.adapters
import workbench.intelligence.identifiers
for module in ("workbench.store", "workbench.api", "workbench.cases", "workbench.intake_service", "workbench.intelligence.service", "workbench.intelligence.acquisition", "excel_intake"):
    assert module not in sys.modules, module
"""
    subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True)


def test_existing_imports_reexport_same_implementations():
    from excel_intake import ExcelReader, EntryValidator, UnvalidatedEntry
    from workbench.intake import files, validation, records
    from workbench import cve_sources, store, primitives
    from workbench.intelligence import service, adapters

    assert ExcelReader is files.ExcelReader
    assert EntryValidator is validation.EntryValidator
    assert UnvalidatedEntry is records.UnvalidatedEntry
    assert cve_sources.verify is service.verify
    assert cve_sources.summarize is adapters.summarize
    assert store.now is primitives.now
    assert store.dump is primitives.dump


def test_current_component_ownership_and_boundaries_are_valid():
    assert analyze()["errors"] == []


def miniature(tmp_path, *, bad_import=False):
    (tmp_path / "docs").mkdir()
    (tmp_path / "workbench").mkdir()
    (tmp_path / "tools").mkdir()
    (tmp_path / "run.py").write_text("")
    (tmp_path / "excel_intake.py").write_text("")
    (tmp_path / "VERSION").write_text("0.7.3")
    (tmp_path / "workbench/api.py").write_text("def create_app(): pass\n")
    (tmp_path / "workbench/adapter.py").write_text(
        "def normalize():\n    from .api import create_app\n"
        if bad_import
        else "def normalize(): pass\n"
    )
    registry = {
        "description": "synthetic boundary test",
        "components": [{"id": "all", "paths": ["*.py", "workbench/*.py"], "tests": []}],
        "rules": [
            {
                "name": "adapter stays offline",
                "source": ["workbench.adapter"],
                "deny": ["workbench.api"],
            }
        ],
        "known_cycles": [],
    }
    (tmp_path / "docs/components.json").write_text(json.dumps(registry))
    (tmp_path / "tools/program_map_template.html").write_text("/*PROGRAM_DATA*/null")
    return tmp_path


def test_checker_rejects_deferred_import_across_boundary(tmp_path):
    root = miniature(tmp_path, bad_import=True)
    errors = analyze(root)["errors"]
    assert any("adapter stays offline: workbench.adapter -> workbench.api" in e for e in errors)


def test_checker_rejects_missing_or_ambiguous_ownership(tmp_path):
    root = miniature(tmp_path)
    registry = json.loads((root / "docs/components.json").read_text())
    registry["components"].append(
        {"id": "duplicate", "paths": ["workbench/adapter.py"], "tests": []}
    )
    (root / "docs/components.json").write_text(json.dumps(registry))
    assert any("expected one owner" in e for e in analyze(root)["errors"])


def test_build_verification_rejects_stale_map(tmp_path):
    root = miniature(tmp_path)
    with pytest.raises(ValueError, match="is stale"):
        verify(root)


def test_import_graph_captures_relative_javascript_and_python_imports():
    assert "static/modules/state.js" in imports(
        Path("static/app.js"), "import {createState} from './modules/state.js';"
    )
    assert "workbench.intelligence.adapters" in imports(
        Path("workbench/intelligence/service.py"),
        "def run():\n    from .adapters import summarize\n",
    )
    assert cycles({"a": {"b"}, "b": {"a", "c"}, "c": set()}) == [["a", "b"]]


def test_checker_rejects_provider_import_even_without_internal_edge(tmp_path):
    root = miniature(tmp_path)
    (root / "workbench/adapter.py").write_text("def normalize():\n    import requests\n")
    path = root / "docs/components.json"
    registry = json.loads(path.read_text())
    registry["rules"][0]["deny_external"] = ["requests"]
    path.write_text(json.dumps(registry))
    assert any("prohibited provider/persistence import" in e for e in analyze(root)["errors"])


def test_checker_enforces_stdlib_only_shared_helpers(tmp_path):
    root = miniature(tmp_path)
    path = root / "docs/components.json"
    registry = json.loads(path.read_text())
    registry["rules"][0].update(stdlib_only=True, allow_internal=["workbench.adapter"])
    path.write_text(json.dumps(registry))
    (root / "workbench/adapter.py").write_text("import json\nimport ctypes\n")
    assert analyze(root)["errors"] == []
    (root / "workbench/adapter.py").write_text("import pydantic\n")
    assert any(
        "non-stdlib import workbench.adapter -> pydantic" in e for e in analyze(root)["errors"]
    )
