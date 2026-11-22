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
import modules.accretion.components.intake
import modules.library.components.intelligence.adapters
import modules.library.components.intelligence.identifiers
for module in ("modules.workspace.components.store", "modules.workspace.components.api", "modules.investigations.components.cases", "modules.accretion.components.intake_service", "modules.library.components.intelligence.service", "modules.library.components.intelligence.acquisition"):
    assert module not in sys.modules, module
"""
    subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True)


def test_existing_imports_reexport_same_implementations():
    from modules.accretion.components.intake import (
        ExcelReader,
        EntryValidator,
        SourceObservation,
    )
    from modules.accretion.components.intake import files, validation, records
    from modules.library.components import cve_sources
    from modules.library.components.intelligence import service, adapters

    assert ExcelReader is files.ExcelReader
    assert EntryValidator is validation.EntryValidator
    assert SourceObservation is records.SourceObservation
    assert cve_sources.verify is service.verify
    assert cve_sources.summarize is adapters.summarize


def test_current_component_ownership_and_boundaries_are_valid():
    assert analyze()["errors"] == []


def test_each_module_has_a_discoverable_changelog():
    registry = json.loads((ROOT / "docs/components.json").read_text(encoding="utf-8"))
    index = (ROOT / "docs/README.md").read_text(encoding="utf-8")
    for component in registry["components"]:
        guide = ROOT / component["entry"]
        changelog = guide.with_name("CHANGELOG.md")
        assert changelog.is_file(), changelog
        assert "## Unreleased" in changelog.read_text(encoding="utf-8").splitlines(), changelog
        assert "](CHANGELOG.md)" in guide.read_text(encoding="utf-8"), guide
        assert f"](../{changelog.relative_to(ROOT).as_posix()})" in index, changelog


def miniature(tmp_path, *, bad_import=False):
    (tmp_path / "docs").mkdir()
    (tmp_path / "modules/workspace/components").mkdir(parents=True)
    (tmp_path / "tools").mkdir()
    (tmp_path / "run.py").write_text("")
    (tmp_path / "VERSION").write_text("0.7.3")
    (tmp_path / "modules/workspace/components/api.py").write_text("def create_app(): pass\n")
    (tmp_path / "modules/workspace/components/adapter.py").write_text(
        "def normalize():\n    from .api import create_app\n"
        if bad_import
        else "def normalize(): pass\n"
    )
    registry = {
        "description": "synthetic boundary test",
        "components": [{"id": "all", "paths": ["*.py", "modules/**"], "tests": []}],
        "rules": [
            {
                "name": "adapter stays offline",
                "source": ["modules.workspace.components.adapter"],
                "deny": ["modules.workspace.components.api"],
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
    assert any(
        "adapter stays offline: modules.workspace.components.adapter -> modules.workspace.components.api"
        in e
        for e in errors
    )


def test_checker_rejects_missing_or_ambiguous_ownership(tmp_path):
    root = miniature(tmp_path)
    registry = json.loads((root / "docs/components.json").read_text(encoding="utf-8"))
    registry["components"].append(
        {"id": "duplicate", "paths": ["modules/workspace/components/adapter.py"], "tests": []}
    )
    (root / "docs/components.json").write_text(json.dumps(registry))
    assert any("expected one owner" in e for e in analyze(root)["errors"])


def test_build_verification_rejects_stale_map(tmp_path):
    root = miniature(tmp_path)
    with pytest.raises(ValueError, match="is stale"):
        verify(root)


def test_import_graph_captures_relative_javascript_and_python_imports():
    assert "modules/ui/static/state.js" in imports(
        Path("modules/ui/static/app.js"), "import {createState} from './state.js';"
    )
    assert "modules.library.components.intelligence.adapters" in imports(
        Path("modules/library/components/intelligence/service.py"),
        "def run():\n    from .adapters import summarize\n",
    )
    assert cycles({"a": {"b"}, "b": {"a", "c"}, "c": set()}) == [["a", "b"]]


def test_checker_rejects_provider_import_even_without_internal_edge(tmp_path):
    root = miniature(tmp_path)
    (root / "modules/workspace/components/adapter.py").write_text(
        "def normalize():\n    import requests\n"
    )
    path = root / "docs/components.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    registry["rules"][0]["deny_external"] = ["requests"]
    path.write_text(json.dumps(registry))
    assert any("prohibited provider/persistence import" in e for e in analyze(root)["errors"])


def test_checker_enforces_stdlib_only_shared_helpers(tmp_path):
    root = miniature(tmp_path)
    path = root / "docs/components.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    registry["rules"][0].update(
        stdlib_only=True, allow_internal=["modules.workspace.components.adapter"]
    )
    path.write_text(json.dumps(registry))
    (root / "modules/workspace/components/adapter.py").write_text("import json\nimport ctypes\n")
    assert analyze(root)["errors"] == []
    (root / "modules/workspace/components/adapter.py").write_text("import pydantic\n")
    assert any(
        "non-stdlib import modules.workspace.components.adapter -> pydantic" in e
        for e in analyze(root)["errors"]
    )


def test_checker_rejects_programs_outside_named_modules(tmp_path):
    root = miniature(tmp_path)
    loose = root / "unowned" / "feature.py"
    loose.parent.mkdir()
    loose.write_text("def feature(): pass\n")
    assert any(
        "unowned" in error and "expected one owner" in error for error in analyze(root)["errors"]
    )


def test_checker_rejects_missing_module_structure_and_unregistered_modules(tmp_path):
    root = miniature(tmp_path)
    path = root / "docs/components.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    registry["project_paths"] = ["run.py", "tools/**"]
    registry["components"] = [{"id": "workspace", "paths": ["modules/workspace/**"], "tests": []}]
    path.write_text(json.dumps(registry))
    (root / "modules/unregistered").mkdir()
    errors = analyze(root)["errors"]
    assert "modules/workspace/static: missing module folder" in errors
    assert "modules/unregistered: module has no registered owner" in errors


def source(root, path, text=""):
    destination = root / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")
    return destination


def use_production_rule(root, name):
    registry_path = root / "docs/components.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    rules = json.loads((ROOT / "docs/components.json").read_text(encoding="utf-8"))["rules"]
    registry["rules"] = [rule for rule in rules if rule["name"] == name]
    assert registry["rules"], name
    registry_path.write_text(json.dumps(registry))


@pytest.mark.parametrize(
    "statement, target",
    [
        ("import modules.workspace.databases.deleted", "modules.workspace.databases.deleted"),
        ("from ..databases.deleted import migrate", "modules.workspace.databases.deleted"),
        ("from .deleted import migrate", "modules.workspace.components.deleted"),
    ],
)
def test_checker_reports_missing_local_python_module_bases(tmp_path, statement, target):
    root = miniature(tmp_path)
    source(root, "modules/workspace/components/adapter.py", f"def deferred():\n    {statement}\n")
    assert any(
        f":2: missing local Python module {target}" in error for error in analyze(root)["errors"]
    )


def test_checker_preserves_symbols_namespace_packages_and_external_imports(tmp_path):
    root = miniature(tmp_path)
    source(root, "modules/workspace/helpers/leaf.py", "value = 1\n")
    # Vendor/generated files can exist outside the source graph.
    source(root, "modules/workspace/vendor/generated.py", "value = 1\n")
    source(
        root,
        "modules/workspace/components/adapter.py",
        """
import json
import optional_third_party.subpackage
from modules.workspace.helpers import leaf
from modules.workspace.helpers.leaf import value, not_statically_checked
from modules.workspace.vendor.generated import value
from . import exported_symbol
""",
    )
    data = analyze(root)
    assert data["errors"] == []
    adapter = next(file for file in data["files"] if file["path"].endswith("/adapter.py"))
    assert "modules.workspace.helpers.leaf" in adapter["imports"]
    assert "modules.workspace.helpers.leaf.value" not in adapter["imports"]
    assert "modules.workspace.vendor.generated" not in adapter["imports"]


@pytest.mark.parametrize(
    "code, diagnostic",
    [
        ("from ....deleted import migrate\n", "relative Python import escapes package root"),
        ("def broken(:\n", "invalid Python syntax"),
    ],
)
def test_checker_reports_invalid_python_without_crashing(tmp_path, code, diagnostic):
    root = miniature(tmp_path)
    source(root, "modules/workspace/components/adapter.py", code)
    assert any(diagnostic in error for error in analyze(root)["errors"])


@pytest.mark.parametrize(
    "statement",
    [
        "import './missing.js';",
        "import {value} from './missing.js';",
        "export {value} from './missing.js';",
        "export * from './missing.js';",
        "async function load() { return import('./missing.js'); }",
        "import('/modules/ui/static/missing.js', {with: {type: 'json'}});",
    ],
)
def test_checker_reports_missing_literal_javascript_targets(tmp_path, statement):
    root = miniature(tmp_path)
    source(root, "modules/ui/static/app.js", statement)
    assert any(
        "missing local JavaScript module modules/ui/static/missing.js" in error
        for error in analyze(root)["errors"]
    )


def test_javascript_scanner_ignores_nonlocal_computed_and_quoted_imports():
    assert (
        imports(
            Path("modules/ui/static/app.js"),
            r"""
// import './comment.js';
/* export * from './comment.js'; */
const example = "import('./quoted.js')";
const pattern = /import\('\.\/regex.js'\)/;
const template = `import('./template.js') ${import('./interpolation.js')}`;
import(name);
import('./computed-' + name + '.js');
import(`./template-${name}.js`);
object.import('./method.js');
import('https://example.test/remote.js');
import('data:text/javascript,export default 1');
import('/api/runtime-module');
import 'third-party';
""",
        )
        == []
    )


def test_javascript_scanner_does_not_cross_declaration_boundaries():
    # Malformed/incomplete import declarations must not borrow another statement's string.
    assert imports(
        Path("modules/ui/static/app.js"),
        """
import unfinished
export const from = './not-a-module.js';
import('./real.js');
""",
    ) == ["modules/ui/static/real.js"]


def test_javascript_scanner_distinguishes_arrow_regex_literals_from_imports():
    assert (
        imports(
            Path("modules/ui/static/app.js"),
            "const pattern = () => /[import('./missing.js')]/;",
        )
        == []
    )


def test_javascript_scanner_accepts_escaped_slashes_without_changing_backslashes(tmp_path):
    root = miniature(tmp_path)
    source(root, "modules/ui/static/folder/leaf.js", "export const value = 1;")
    script = source(root, "modules/ui/static/app.js", r"import './folder\/leaf.js';")
    assert analyze(root)["errors"] == []
    script.write_text(r"import './folder\\/leaf.js';")
    assert any("must use URL path separators" in error for error in analyze(root)["errors"])


def test_javascript_scanner_accepts_reserved_export_names():
    assert imports(
        Path("modules/ui/static/app.js"),
        "export {function as fn, class as cls} from './leaf.js';",
    ) == ["modules/ui/static/leaf.js"]


def test_literal_dynamic_root_url_imports_participate_in_cycle_checks(tmp_path):
    root = miniature(tmp_path)
    source(root, "modules/ui/static/app.js", "import('/modules/ui/static/other.js?v=1#loaded');")
    source(root, "modules/ui/static/other.js", "export {value} from './app.js';")
    data = analyze(root)
    assert data["cycles"] == [["modules/ui/static/app.js", "modules/ui/static/other.js"]]
    assert len(data["errors"]) == 1
    assert data["errors"][0].startswith("New dependency cycle:")


@pytest.mark.parametrize(
    "statement, diagnostic",
    [
        ("import '../../../../outside.js';", "JavaScript import escapes source root"),
        (r"import './..\\..\\outside.js';", "must use URL path separators"),
        ("import './%5C%5Coutside.js';", "must use URL path separators"),
    ],
)
def test_javascript_path_errors_are_diagnostics(tmp_path, statement, diagnostic):
    root = miniature(tmp_path)
    source(root, "modules/ui/static/app.js", statement)
    assert any(diagnostic in error for error in analyze(root)["errors"])


@pytest.mark.parametrize("folder", ["components", "helpers", "databases"])
def test_standalone_attribution_cannot_import_any_application_package(tmp_path, folder):
    root = miniature(tmp_path)
    use_production_rule(root, "Standalone attribution cannot import application modules")
    source(root, f"modules/ui/{folder}/leaf.py", "value = 1\n")
    source(
        root,
        "modules/attribution/components/engine/src/attribution/engine.py",
        f"from modules.ui.{folder} import leaf\n",
    )
    errors = analyze(root)["errors"]
    assert any(
        "Standalone attribution cannot import application modules: attribution.engine" in error
        for error in errors
    )


def test_standalone_boundary_applies_to_namespace_package_without_file_edge(tmp_path):
    root = miniature(tmp_path)
    use_production_rule(root, "Standalone attribution cannot import application modules")
    (root / "modules/ui/helpers").mkdir(parents=True)
    source(
        root,
        "modules/attribution/components/engine/src/attribution/engine.py",
        "import modules.ui.helpers\n",
    )
    assert any(
        "Standalone attribution cannot import application modules: attribution.engine" in error
        for error in analyze(root)["errors"]
    )


def test_shared_ui_helpers_can_reuse_helpers_but_not_workflow(tmp_path):
    root = miniature(tmp_path)
    use_production_rule(root, "Shared UI helpers stay below application workflow")
    source(root, "modules/ui/helpers/leaf.py", "value = 1\n")
    helper = source(
        root, "modules/ui/helpers/fonts.py", "from .leaf import value\nfrom docx import Document\n"
    )
    assert analyze(root)["errors"] == []
    helper.write_text("from modules.workspace.components.api import create_app\n")
    assert any(
        "Shared UI helpers stay below application workflow:" in error
        for error in analyze(root)["errors"]
    )


def test_checker_reports_missing_component_entry(tmp_path):
    root = miniature(tmp_path)
    registry_path = root / "docs/components.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["components"][0]["entry"] = "modules/workspace/docs/deleted.md"
    registry_path.write_text(json.dumps(registry))
    assert (
        "all: missing component entry modules/workspace/docs/deleted.md" in analyze(root)["errors"]
    )
