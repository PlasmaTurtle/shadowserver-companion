"""Build a source + offline Windows dependency ZIP without working records."""

from pathlib import Path
import argparse
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
from release_policy import distributable
from check_dependencies import verify as verify_dependencies
from program_map import verify as verify_architecture
from check_release import verify as verify_release, check_output_name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    release = verify_release(ROOT)
    check_output_name(args.output, release)
    verify_dependencies(ROOT)
    verify_architecture(ROOT)
    prefix = (
        "shadowserver-eclipse"
        if release.get("variant") == "dark_matter"
        else "shadowserver-companion-chaos"
        if release.get("edition") == "chaos"
        else "shadowserver-companion"
    )
    paths = []
    for path in sorted(ROOT.rglob("*")):
        rel = path.relative_to(ROOT)
        if not path.is_file() or path.is_symlink():
            continue
        if not distributable(rel):
            continue
        paths.append(path)
    hashes = {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
    }
    manifest = {
        "handling": "TLP:AMBER",
        "distribution_policy": "program-assets-and-synthetic-fixtures-v1",
        "version": (ROOT / "VERSION").read_text().strip(),
        "release": release,
        "files": hashes,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(path, Path(prefix) / path.relative_to(ROOT))
        archive.writestr(prefix + "/release-manifest.json", json.dumps(manifest, indent=2) + "\n")
    with zipfile.ZipFile(args.output) as archive:
        assert archive.testzip() is None
        for name, digest in hashes.items():
            assert hashlib.sha256(archive.read(prefix + "/" + name)).hexdigest() == digest
    print(
        json.dumps(
            {
                "file": str(args.output.resolve()),
                "files": len(paths) + 1,
                "bytes": args.output.stat().st_size,
                "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
