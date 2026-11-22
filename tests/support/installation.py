"""Reusable synthetic installation fixtures and builders."""

import hashlib
import importlib.util
import json
from pathlib import Path

HELPER = Path(__file__).resolve().parents[2] / "tools/windows_installer/upgrade_cleanup.py"


spec = importlib.util.spec_from_file_location("upgrade_cleanup_072", HELPER)


upgrade = importlib.util.module_from_spec(spec)


spec.loader.exec_module(upgrade)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inventory(path, files):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "distribution_policy": upgrade.POLICY,
                "application_version": "0.7.1",
                "files": {name: digest(data) for name, data in files.items()},
            }
        )
    )


def write_files(root, files):
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def installation(tmp_path, old=None, new=None):
    old = old or {"app/workbench/old.py": b"old module", "app/run.py": b"entry"}
    new = new or {"app/run.py": b"entry"}
    root = tmp_path / "installed"
    write_files(root, old)
    inventory(root / "payload-manifest.json", old)
    next_manifest = tmp_path / "staged/next-payload-manifest.json"
    inventory(next_manifest, new)
    return root, next_manifest


ROOT = Path(__file__).resolve().parents[2]


def helper(name):
    spec = importlib.util.spec_from_file_location(
        "chaos_installer_" + name, ROOT / "tools/windows_installer" / (name + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tree_bytes(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
