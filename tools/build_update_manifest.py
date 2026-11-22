"""Create edition-bound public update metadata for a verified Windows installer.

Upload this JSON and the exact installer to the same GitHub release. This tool
does not publish, sign or execute either artifact. GitHub's asset digest must
match both files before the in-app client offers them.
"""

from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from modules.workspace.components.release import installation_identity, load_release
from modules.settings.components.software_updates import (
    bundled_notes,
    MAX_INSTALLER,
    validate_installer_name,
)


def build_manifest(installer, output, *, root=ROOT):
    release = load_release(root)
    identity = installation_identity(release["edition"], release.get("variant", ""))
    installer = Path(installer)
    validate_installer_name(installer.name, release)
    if (
        not installer.is_file()
        or installer.is_symlink()
        or not 0 < installer.stat().st_size <= MAX_INSTALLER
    ):
        raise ValueError("Choose a regular installer within the supported size limit")
    digest = hashlib.sha256()
    with installer.open("rb") as source:
        if source.read(2) != b"MZ":
            raise ValueError("Expected a Windows executable installer")
        source.seek(0)
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    expected = f"software-update-{identity['app_id']}.json"
    output = Path(output)
    if output.name != expected:
        raise ValueError(f"Update manifest must be named {expected}")
    notes = bundled_notes(root, release)
    payload = {
        "schema": 1,
        "version": release["version"],
        "channel": release["channel"],
        "edition": release["edition"],
        "variant": release.get("variant", ""),
        "app_id": identity["app_id"],
        "title": notes["title"],
        "highlights": notes["highlights"],
        "installer": {
            "name": installer.name,
            "size": installer.stat().st_size,
            "sha256": digest.hexdigest(),
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("installer", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = build_manifest(args.installer, args.output)
    print(
        json.dumps(
            {"file": str(args.output.resolve()), "installer_sha256": result["installer"]["sha256"]},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
