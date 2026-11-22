"""Conservative installer upgrades never turn inventory files into deletion scripts."""

import importlib.util
import importlib.metadata
import json
import subprocess
import sys

import pytest

from tests.filesystem_helpers import create_test_symlink

from tests.support.installation import HELPER, digest, installation, inventory, upgrade, write_files


def test_upgrade_removes_only_unchanged_obsolete_program_files(tmp_path):
    old = {
        "app/workbench/old.py": b"obsolete",
        "runtime/Lib/site-packages/dnspython-2.8.0.dist-info/METADATA": b"Version: 2.8.0",
        "runtime/Lib/site-packages/dns/resolver.py": b"old resolver",
        "app/run.py": b"old entrypoint",
    }
    new = {"app/run.py": b"new entrypoint", "runtime/Lib/site-packages/dns/resolver.py": b"fixed"}
    root, staged = installation(tmp_path, old, new)
    preserved = {
        "app/workbench/unlisted.py": b"unlisted program",
        "data/evidence/source.bin": b"casework",
        "app/data/case.sqlite3": b"misplaced casework",
        "data-demo/case.json": b"demo workspace",
    }
    write_files(root, preserved)
    old_manifest_bytes = (root / "payload-manifest.json").read_bytes()
    removed = upgrade.cleanup(root, staged)
    assert set(removed) == {
        "app/workbench/old.py",
        "runtime/Lib/site-packages/dnspython-2.8.0.dist-info/METADATA",
    }
    for name in removed:
        assert not (root / name).exists()
    for name, data in {**preserved, **{k: v for k, v in old.items() if k not in removed}}.items():
        assert (root / name).read_bytes() == data
    assert not (root / "runtime/Lib/site-packages/dnspython-2.8.0.dist-info").exists()
    assert (root / "payload-manifest.json").read_bytes() == old_manifest_bytes


def test_modified_obsolete_file_stops_before_any_deletion(tmp_path):
    old = {"app/workbench/a.py": b"a", "app/workbench/z.py": b"z"}
    root, staged = installation(tmp_path, old)
    (root / "app/workbench/z.py").write_bytes(b"local change")
    with pytest.raises(upgrade.UpgradeError, match="modified; upgrade stopped"):
        upgrade.cleanup(root, staged)
    assert (root / "app/workbench/a.py").read_bytes() == b"a"
    assert (root / "app/workbench/z.py").read_bytes() == b"local change"


def test_obsolete_metadata_directories_do_not_shadow_new_distribution(tmp_path):
    old = {
        "runtime/Lib/site-packages/dnspython-2.8.0.dist-info/METADATA": b"Name: dnspython\nVersion: 2.8.0\n",
        "runtime/Lib/site-packages/dnspython-2.8.0.dist-info/licenses/LICENSE": b"license",
        "runtime/Lib/site-packages/outreach_attribution-0.2.1.dist-info/METADATA": b"Name: outreach-attribution\nVersion: 0.2.1\n",
        "app/modules/attribution/components/engine/obsolete.py": b"obsolete",
    }
    new = {
        "runtime/Lib/site-packages/dnspython-2.9.2.dist-info/METADATA": b"Name: dnspython\nVersion: 2.9.2\n",
        "runtime/Lib/site-packages/outreach_attribution-0.2.2.dist-info/METADATA": b"Name: outreach-attribution\nVersion: 0.2.2\n",
    }
    root, staged = installation(tmp_path, old, new)
    write_files(root, {"app/modules/attribution/components/engine/unlisted.txt": b"retain"})
    upgrade.cleanup(root, staged)
    write_files(root, new)
    site = root / "runtime/Lib/site-packages"
    distributions = list(importlib.metadata.distributions(path=[str(site)]))
    assert {d.metadata["Name"]: d.version for d in distributions} == {
        "dnspython": "2.9.2",
        "outreach-attribution": "0.2.2",
    }
    assert len(distributions) == 2
    assert not (site / "dnspython-2.8.0.dist-info").exists()
    assert not (site / "outreach_attribution-0.2.1.dist-info").exists()
    assert (
        root / "app/modules/attribution/components/engine/unlisted.txt"
    ).read_bytes() == b"retain"
    assert (root / "app").is_dir() and (root / "runtime").is_dir()


def test_missing_obsolete_files_still_allow_empty_owned_parent_cleanup(tmp_path):
    root, staged = installation(tmp_path)
    (root / "app/workbench/old.py").unlink()
    assert upgrade.cleanup(root, staged) == []
    assert not (root / "app/workbench").exists()
    assert (root / "app").is_dir()


@pytest.mark.parametrize(
    "name",
    [
        "../data/case.json",
        "/tmp/case.json",
        "app/../data/case.json",
        "app\\data\\case.json",
        "app/workbench/data/case.json",
        "app/modules/investigations/resources/data/case.json",
        "data/case.json",
        "app/data/case.json",
        "runtime/Lib/site-packages/data/case.json",
        "app/workbench/old.py:other",
        "app//run.py",
        "app/workbench/NUL.txt",
        "app/workbench/old.py.",
        "elsewhere/secret.py",
    ],
)
def test_tampered_inventory_cannot_authorize_workspace_or_unsafe_path_deletion(tmp_path, name):
    root, staged = installation(tmp_path)
    inventory(root / "payload-manifest.json", {name: b"case data"})
    with pytest.raises(upgrade.UpgradeError):
        upgrade.cleanup(root, staged)
    assert (root / "app/workbench/old.py").read_bytes() == b"old module"


def test_old_file_link_is_rejected_even_when_digest_matches(tmp_path):
    root, staged = installation(tmp_path)
    outside = tmp_path / "outside.py"
    outside.write_bytes(b"old module")
    target = root / "app/workbench/old.py"
    target.unlink()
    create_test_symlink(target, outside)
    with pytest.raises(upgrade.UpgradeError, match="Linked/reparse-point"):
        upgrade.cleanup(root, staged)
    assert target.is_symlink() and outside.read_bytes() == b"old module"


def test_new_overlay_directory_link_is_rejected_before_cleanup(tmp_path):
    root, staged = installation(tmp_path, new={"app/static/new.js": b"new"})
    outside = tmp_path / "outside"
    outside.mkdir()
    create_test_symlink(root / "app/static", outside, target_is_directory=True)
    with pytest.raises(upgrade.UpgradeError, match="Linked/reparse-point"):
        upgrade.cleanup(root, staged)
    assert (root / "app/workbench/old.py").exists()


def test_linked_installation_root_is_rejected(tmp_path):
    root, staged = installation(tmp_path)
    link = tmp_path / "link"
    create_test_symlink(link, root, target_is_directory=True)
    with pytest.raises(upgrade.UpgradeError, match="Linked/reparse-point"):
        upgrade.cleanup(link, staged)
    assert (root / "app/workbench/old.py").exists()


def test_clean_install_is_noop_but_existing_program_without_manifest_stops(tmp_path):
    staged = tmp_path / "staged.json"
    inventory(staged, {"app/run.py": b"entry"})
    root = tmp_path / "fresh"
    assert upgrade.cleanup(root, staged) == []
    assert not root.exists()
    write_files(root, {"app/run.py": b"entry"})
    with pytest.raises(upgrade.UpgradeError, match="no inventory"):
        upgrade.cleanup(root, staged)


def test_missing_obsolete_file_is_harmless_and_case_only_rename_is_retained(tmp_path):
    root, staged = installation(tmp_path, new={"app/workbench/OLD.py": b"new case"})
    (root / "app/run.py").unlink()
    assert upgrade.cleanup(root, staged) == []
    assert (root / "app/workbench/old.py").exists()


@pytest.mark.parametrize(
    "mutation", ["oversize", "duplicate", "digest", "casecollision", "schema", "filelimit"]
)
def test_malformed_manifests_stop_before_cleanup(tmp_path, monkeypatch, mutation):
    root, staged = installation(tmp_path)
    if mutation == "oversize":
        monkeypatch.setattr(upgrade, "MAX_MANIFEST_BYTES", 16)
    elif mutation == "duplicate":
        staged.write_text('{"files":{},"files":{}}')
    else:
        data = json.loads(staged.read_text(encoding="utf-8"))
        if mutation == "digest":
            data["files"]["app/run.py"] = "not a hash"
        elif mutation == "casecollision":
            data["files"]["app/workbench/M.py"] = digest(b"a")
            data["files"]["app/workbench/m.py"] = digest(b"a")
        elif mutation == "schema":
            data["distribution_policy"] = "unknown"
        elif mutation == "filelimit":
            monkeypatch.setattr(upgrade, "MAX_FILES", 0)
        staged.write_text(json.dumps(data))
    with pytest.raises(upgrade.UpgradeError):
        upgrade.cleanup(root, staged)
    assert (root / "app/workbench/old.py").exists()


def test_standalone_isolated_cli_reports_failure_without_traceback(tmp_path):
    root, staged = installation(tmp_path)
    (root / "app/workbench/old.py").write_bytes(b"local modifications")
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(HELPER),
            "--install-dir",
            str(root),
            "--next-manifest",
            str(staged),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "modified; upgrade stopped" in result.stderr
    assert "Traceback" not in result.stderr


def test_installer_runs_staged_cleanup_before_overlay():
    script = HELPER.with_name("installer.nsi").read_text(encoding="utf-8")
    assert script.index("nsExec::ExecToStack") < script.index('File /r "${PAYLOAD}\\*"')
    assert '-I -S -B "$PLUGINSDIR\\upgrade_cleanup.py"' in script
    assert 'File /oname=next-payload-manifest.json "${PAYLOAD}\\payload-manifest.json"' in script
    assert "RMDir" not in HELPER.read_text(encoding="utf-8")
