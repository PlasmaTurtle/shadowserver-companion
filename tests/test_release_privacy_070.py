"""Both distributions share an explicit source/fixture inclusion policy."""

import importlib.util
from datetime import datetime, timezone
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from release_policy import distributable


def test_release_policy_includes_profile_inventory_and_synthetic_fixtures():
    for name in (
        "schemas/shadowserver-reports.json",
        "schemas/shadowserver-reports.meta.json",
        "workbench/report_profiles.py",
        "static/theme.js",
        "tools/release_policy.py",
        "tests/fixtures/selection_policy_sample.csv",
        "tests/fixtures/intake_fixture.xlsx",
    ):
        assert distributable(Path(name)), name
    assert distributable(Path("schemas/shadowserver-reports.json"), installed=True)
    assert not distributable(Path("tests/fixtures/selection_policy_sample.csv"), installed=True)


def test_release_policy_never_includes_workspace_or_unreviewed_source_attachments():
    names = [
        "data/workbench.sqlite3",
        "data/originals/scan.xlsx",
        "reports/case/notification.pdf",
        "tests/fixtures/shadowserver_labeled_sample_2026-11-05.csv",
        "tests/fixtures/new-unreviewed.xlsx",
        "components/attribution/examples/sample-evidence/attribution.json",
        "workbench/private.xlsx",
        "tools/application.log",
        "workbench/__pycache__/store.pyc",
        "../secrets.json",
        "schemas/unreviewed.json",
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
    assert (target / "schemas/shadowserver-reports.json").is_file()
    assert not (target / "tests").exists()
    assert not (target / "components/attribution/examples").exists()
    assert (target / "VERSION").read_text() == (ROOT / "VERSION").read_text()
    for name in ("favicon.svg", "favicon.png", "favicon.ico"):
        assert (target / "static" / name).read_bytes() == (ROOT / "static" / name).read_bytes()
        assert distributable(Path("static") / name)
    assert (target / "docs/DATA_MANAGEMENT.md").read_bytes() == (
        ROOT / "docs/DATA_MANAGEMENT.md"
    ).read_bytes()
    # Windows' embedded runtime has no system IANA database. Test the actual
    # copied payload, not only the source-distribution allowlist.
    resources = Path("resources/timezones")
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
