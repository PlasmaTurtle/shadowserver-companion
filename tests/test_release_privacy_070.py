"""Both distributions share an explicit source/fixture inclusion policy."""

import importlib.util
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from release_policy import distributable


def test_release_policy_includes_profile_inventory_and_synthetic_fixtures():
    for name in (
        "modules/accretion/schemas/shadowserver-reports.json",
        "modules/accretion/schemas/shadowserver-reports.meta.json",
        "modules/accretion/components/report_profiles.py",
        "modules/ui/static/theme.js",
        "tools/release_policy.py",
        "tests/fixtures/selection_policy_sample.csv",
        "tests/fixtures/intake_fixture.xlsx",
    ):
        assert distributable(Path(name)), name
    assert distributable(
        Path("modules/accretion/schemas/shadowserver-reports.json"), installed=True
    )
    assert not distributable(Path("tests/fixtures/selection_policy_sample.csv"), installed=True)
    for name in (
        "tools/ensure_environment.cmd",
        "modules/attribution/tools/Attribution.cmd",
        "modules/accretion/tests/fixtures/windows_schedule_normalization.json",
        "modules/tools/tests/fixtures/website_capture_live_urls.json",
        "modules/tools/tests/fixtures/website_capture_green.webm",
    ):
        assert (ROOT / name).is_file(), name
        assert distributable(Path(name))
        assert not distributable(Path(name), installed=True)


def test_release_policy_never_includes_workspace_or_unreviewed_source_attachments():
    names = [
        "data/workbench.sqlite3",
        "data/originals/scan.xlsx",
        "reports/case/notification.pdf",
        "tests/fixtures/shadowserver_labeled_sample_2026-11-05.csv",
        "tests/fixtures/new-unreviewed.xlsx",
        "modules/attribution/components/engine/examples/sample-evidence/attribution.json",
        "workbench/private.xlsx",
        "tools/application.log",
        "workbench/__pycache__/store.pyc",
        "../secrets.json",
        "modules/accretion/schemas/unreviewed.json",
        "modules/accretion/tests/fixtures/unreviewed-task-export.json",
        "modules/tools/tests/fixtures/private-capture.webm",
        "modules/tools/components/website_capture/data/capture.sqlite3",
        "tests/raw-output.pdf",
        "static/unreviewed.png",
        "static/private.ico",
    ]
    for name in names:
        assert not distributable(Path(name)), name
        assert not distributable(Path(name), installed=True), name


def test_installer_payload_copy_uses_same_policy_and_pinned_inventory(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "installer_build_test", ROOT / "tools/windows_installer/build.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    target = tmp_path / "app"
    module.copy_source(target)
    assert (target / "modules/accretion/schemas/shadowserver-reports.json").is_file()
    assert not (target / "tests").exists()
    assert not (target / "modules/attribution/components/engine/examples").exists()
    assert not (target / "modules/tools/tests").exists()
    capture = Path("modules/tools/components/website_capture")
    for source in (ROOT / capture).glob("*.py"):
        assert (target / capture / source.name).read_bytes() == source.read_bytes()
    # The actual installed layout must import the tool and its case adapter
    # without relying on a second source checkout or starting a capture.
    subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            "from pathlib import Path; "
            "from modules import __version__; "
            "assert __version__ == Path('VERSION').read_text(encoding='utf-8').strip(); "
            "from modules.tools.components.website_capture import capture_website; "
            "from modules.investigations.components import website_jobs; "
            "assert website_jobs.capture_website is capture_website; "
            "assert Path(capture_website.__code__.co_filename).is_relative_to(Path.cwd()); "
            "assert capture_website.__module__ == 'modules.tools.components.website_capture.browser'; "
            "from modules.library.resources.defaults import EXPLAINERS; assert EXPLAINERS; "
            "from modules.library.resources.report_explainer_data import BANK; assert BANK; "
            "from modules.library.resources.finding_explainer_data import BANK; assert BANK",
        ],
        cwd=target,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert (target / "VERSION").read_text(encoding="utf-8") == (ROOT / "VERSION").read_text(
        encoding="utf-8"
    )
    for relative in (
        "docs/ARCHITECTURE.md",
        "docs/DEVELOPMENT.md",
        "docs/DEPENDENCIES.md",
        "docs/WINDOWS_ACCEPTANCE.md",
        "docs/history/validation/VALIDATION_0120.md",
        "docs/USER_GUIDE.md",
    ):
        assert (target / relative).read_bytes() == (ROOT / relative).read_bytes()
        assert distributable(Path(relative))
    for name in (
        "AGENTS.md",
        "CONTRIBUTING.md",
        "requirements-constraints.txt",
        "ARCHITECTURE.md",
        "DEVELOPMENT.md",
        "DEPENDENCIES.md",
        "HOME_VALIDATION.md",
        "VALIDATION.md",
        "SUPPORT.md",
        "MODULES.md",
        "Setup.cmd",
        "Start Workbench.cmd",
        "Start Demo.cmd",
        "tools/ensure_environment.cmd",
        "modules/attribution/tools/Attribution.cmd",
    ):
        assert not (target / name).exists(), name
        assert not distributable(Path(name), installed=True), name
    for name in ("favicon.svg", "favicon.png", "favicon.ico"):
        assert (target / "modules/ui/static" / name).read_bytes() == (
            ROOT / "modules/ui/static" / name
        ).read_bytes()
        assert distributable(Path("modules/ui/static") / name)
    assert (target / "modules/workspace/docs/DATA_MANAGEMENT.md").read_bytes() == (
        ROOT / "modules/workspace/docs/DATA_MANAGEMENT.md"
    ).read_bytes()
    for relative in (
        "modules/library/resources/defaults.py",
        "modules/library/resources/report_explainer_data.py",
        "modules/library/resources/finding_explainer_data.py",
        "modules/accretion/components/shadowserver_api/credentials.py.patch",
        "modules/accretion/components/shadowserver_api/baseline-0.1.1/credentials.py.txt",
        "modules/accretion/resources/examples/intake_fixture.xlsx",
        "modules/leads/resources/examples/qualified-lead.json",
        "modules/investigations/resources/examples/Sample_Notification.pdf",
        "modules/investigations/resources/examples/Sample_Notification.docx",
        "modules/investigations/resources/examples/Multiple_CVE_Notification.pdf",
        "modules/investigations/resources/examples/Multiple_CVE_Notification.docx",
    ):
        assert (target / relative).read_bytes() == (ROOT / relative).read_bytes()
        assert distributable(Path(relative))
    # Windows' embedded runtime has no system IANA database. Test the actual
    # copied payload, not only the source-distribution allowlist.
    resources = Path("modules/investigations/resources/timezones")
    for name in ("America_New_York.tzif", "LICENSE", "LICENSE_APACHE", "provenance.json"):
        assert (target / resources / name).read_bytes() == (ROOT / resources / name).read_bytes()
    with (target / resources / "America_New_York.tzif").open("rb") as stream:
        zone = ZoneInfo.from_file(stream, key="America/New_York")
    assert (
        datetime(2026, 11, 5, 5, 58, tzinfo=timezone.utc).astimezone(zone).strftime("%H:%M %Z")
        == "00:58 EST"
    )
    assert (
        datetime(2026, 7, 5, 5, 58, tzinfo=timezone.utc).astimezone(zone).strftime("%H:%M %Z")
        == "01:58 EDT"
    )
    assert all(
        distributable(p.relative_to(target), installed=True) or p.name == "desktop.py"
        for p in target.rglob("*")
        if p.is_file()
    )
    # A packaged asset must also be accepted by the upgrade inventory policy;
    # otherwise installing over any prior version stops before the overlay.
    upgrade_spec = importlib.util.spec_from_file_location(
        "installer_upgrade_policy_test", ROOT / "tools/windows_installer/upgrade_cleanup.py"
    )
    upgrade = importlib.util.module_from_spec(upgrade_spec)
    upgrade_spec.loader.exec_module(upgrade)
    for path in target.rglob("*"):
        if path.is_file():
            upgrade.member_parts("app/" + path.relative_to(target).as_posix())


def test_module_release_policy_rejects_unknown_owners_and_live_data():
    for name in (
        "modules/unknown/components/feature.py",
        "modules/workspace/databases/working.sqlite3",
        "modules/workspace/databases/records.json",
        "modules/accretion/tests/private.xlsx",
        "modules/ui/static/private.png",
        "modules/attribution/components/engine/examples/live.json",
        "modules/settings/examples/qualified-lead.json",
        "modules/leads/examples/qualified-lead.json",
        "modules/settings/resources/examples/qualified-lead.json",
    ):
        assert not distributable(Path(name)), name
        assert not distributable(Path(name), installed=True), name
    assert distributable(Path("modules/entities/tests/test_entities.py"))
    assert not distributable(Path("modules/entities/tests/test_entities.py"), installed=True)
    assert distributable(Path("modules/workspace/components/store.py"), installed=True)


def test_module_cleanup_retains_nested_workspaces_and_legacy_paths(tmp_path):
    import pytest

    spec = importlib.util.spec_from_file_location(
        "module_cleanup_policy_test", ROOT / "tools/windows_installer/upgrade_cleanup.py"
    )
    upgrade = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(upgrade)
    for name in (
        "app/workbench/store.py",
        "app/fonts/DejaVuSans.ttf",
        "app/resources/timezones/America_New_York.tzif",
        "app/excel_intake.py",
        "app/REPORT_REQUIREMENTS.md",
        "app/modules/workspace/components/store.py",
        "app/modules/tools/components/website_capture/browser.py",
        "app/modules/leads/examples/qualified-lead.json",
        "app/examples/qualified-lead.json",
    ):
        assert upgrade.member_parts(name)
    for name in (
        "app/modules/workspace/components/data/records.json",
        "app/modules/tools/components/website_capture/data/records.json",
        "app/modules/workspace/workspace/records.py",
        "app/modules/unknown/components/code.py",
        "app/workspace/records.py",
    ):
        with pytest.raises(upgrade.UpgradeError):
            upgrade.member_parts(name)
    cache = tmp_path / "app/modules/workspace/components/__pycache__/store.cpython-314.pyc"
    cache.parent.mkdir(parents=True)
    cache.write_bytes(b"synthetic cache")
    private = tmp_path / "app/modules/workspace/components/data/__pycache__/private.pyc"
    private.parent.mkdir(parents=True)
    private.write_bytes(b"retain user data")
    assert upgrade.generated_caches(tmp_path) == [cache]
    upgrade.remove_caches(tmp_path, [cache])
    assert private.read_bytes() == b"retain user data"
