"""Build a self-contained Windows x64 installer from verified distribution files."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from email.parser import BytesParser
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TOP_FILES = (
    "run.py",
    "excel_intake.py",
    "VERSION",
    "RELEASE.json",
    "HOME_VALIDATION.md",
    "README.md",
    "CHANGELOG.md",
    "VALIDATION.md",
    "DEPENDENCIES.md",
    "REPORT_REQUIREMENTS.md",
    "ARCHITECTURE.md",
    "DEVELOPMENT.md",
    "SECURITY.md",
    "requirements-constraints.txt",
)
FOLDERS = (
    "workbench",
    "static",
    "schemas",
    "fonts",
    "examples",
    "tools",
    "components",
    "docs",
    "resources",
)
sys.path.insert(0, str(HERE.parent))
from release_policy import distributable
from check_dependencies import verify as verify_dependencies
from program_map import verify as verify_architecture
from check_release import verify as verify_release, check_output_name
from workbench.release import installation_identity

IGNORED = {"__pycache__", ".pytest_cache", ".git", ".venv", "build", "dist"}
EXAMPLES = {
    "Sample_Notification.pdf",
    "Sample_Notification.docx",
    "qualified-lead.json",
    "intake_fixture.xlsx",
    "Multiple_CVE_Notification.pdf",
    "Multiple_CVE_Notification.docx",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_source(target: Path) -> None:
    target.mkdir(parents=True)
    for name in TOP_FILES:
        shutil.copy2(ROOT / name, target / name)
    for name in FOLDERS:
        for path in sorted((ROOT / name).rglob("*")):
            relative = path.relative_to(ROOT)
            if not path.is_file() or path.is_symlink():
                continue
            if not distributable(relative, installed=True):
                continue
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
    shutil.copy2(HERE / "desktop.py", target / "desktop.py")


def extract_runtime(archive: Path, target: Path, python_tag: str) -> None:
    target.mkdir(parents=True)
    with zipfile.ZipFile(archive) as source:
        for item in source.infolist():
            path = Path(item.filename)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"Unsafe runtime archive member: {item.filename}")
        if source.testzip() is not None:
            raise ValueError("Runtime archive integrity check failed")
        source.extractall(target)
    # An explicit isolated import path; no global Python or user site packages.
    (target / f"{python_tag}._pth").write_text(
        f"{python_tag}.zip\n.\nLib/site-packages\n../app\nimport site\n", encoding="utf-8"
    )


def validate_wheels(folder: Path) -> list[dict]:
    expected = json.loads((ROOT / "wheelhouse-sha256.json").read_text(encoding="utf-8"))
    records = []
    for name, digest in expected.items():
        path = folder / name
        if not path.is_file() or sha256(path) != digest:
            raise ValueError(f"Missing or changed dependency artifact: {name}")
        with zipfile.ZipFile(path) as wheel:
            bad = wheel.testzip()
            if bad:
                raise ValueError(f"Corrupt wheel member: {name}/{bad}")
            metadata = next(n for n in wheel.namelist() if n.endswith(".dist-info/METADATA"))
            meta = BytesParser().parsebytes(wheel.read(metadata))
        records.append(
            {"name": meta["Name"], "version": meta["Version"], "artifact": name, "sha256": digest}
        )
    return records


def uninstall_inventory(payload: Path) -> str:
    def escape(path: Path) -> str:
        value = str(path.relative_to(payload)).replace("/", "\\")
        if any(c in value for c in ('"', "\r", "\n")):
            raise ValueError("Unsupported filename in payload")
        return value.replace("$", "$$")

    files = sorted(path for path in payload.rglob("*") if path.is_file())
    folders = sorted(
        (path for path in payload.rglob("*") if path.is_dir()),
        key=lambda path: (-len(path.parts), str(path)),
    )
    return (
        "\n".join(
            ["ClearErrors"]
            + [f'Delete "$INSTDIR\\{escape(path)}"' for path in files]
            + [
                "${If} ${Errors}",
                '  MessageBox MB_OK|MB_ICONSTOP "Some application files are still in use or could not be removed. Close the application and retry uninstall. Working records are retained." /SD IDOK',
                "  SetErrorLevel 5",
                "  Abort",
                "${EndIf}",
            ]
            + [f'RMDir "$INSTDIR\\{escape(path)}"' for path in folders]
        )
        + "\n"
    )


def installer_definitions(release):
    identity = installation_identity(release["edition"], release.get("variant", ""))
    return {
        "APP": identity["app_name"],
        "APP_ID": identity["app_id"],
        "APP_EDITION": release["edition"],
        "APP_VARIANT": release.get("variant", ""),
        "DEMO_NAME": "Shadowserver Eclipse Demo"
        if release.get("variant") == "dark_matter"
        else "Companion Chaos Demo"
        if release["edition"] == "chaos"
        else "Companion Demo",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--build-dir", type=Path, default=ROOT / "build" / "windows-installer")
    parser.add_argument("--makensis", default="makensis")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    release = verify_release(ROOT)
    verify_dependencies(ROOT)
    verify_architecture(ROOT)
    build = args.build_dir.resolve()
    version = (ROOT / "VERSION").read_text().strip()
    identity = installation_identity(release["edition"], release.get("variant", ""))
    definitions = installer_definitions(release)
    label = (
        version + {"unstable": "-unstable", "candidate": "-rc", "stable": ""}[release["channel"]]
    )
    if release["edition"] == "chaos" and not release.get("variant"):
        label += "-chaos"
    if release.get("review_name"):
        label += "-" + release["review_name"].lower().replace(" ", "-")
    product = (
        "ShadowserverEclipse"
        if release.get("variant") == "dark_matter"
        else "ShadowserverCompanion"
    )
    output = (args.output or ROOT / f"{product}-{label}-Setup-x64.exe").resolve()
    check_output_name(output, release)
    build.mkdir(parents=True, exist_ok=True)
    downloads = build / "downloads"
    wheels = build / "wheelhouse"
    downloads.mkdir(exist_ok=True)
    wheels.mkdir(exist_ok=True)
    runtime_lock = json.loads((HERE / "runtime-lock.json").read_text(encoding="utf-8"))
    python_version = ".".join(runtime_lock["version"].split(".")[:2])
    abi = "cp" + python_version.replace(".", "")
    python_tag = "python" + python_version.replace(".", "")
    archive = downloads / runtime_lock["filename"]
    if not archive.is_file():
        if args.offline:
            raise ValueError("Embedded runtime is missing from the offline build cache")
        temporary = archive.with_suffix(".download")
        with (
            urllib.request.urlopen(runtime_lock["url"], timeout=60) as source,
            temporary.open("wb") as destination,
        ):
            shutil.copyfileobj(source, destination)
        temporary.replace(archive)
    if sha256(archive) != runtime_lock["sha256"]:
        raise ValueError("Embedded runtime does not match its official SHA-256")
    if not args.offline:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "download",
                "--dest",
                str(wheels),
                "--platform",
                "win_amd64",
                "--python-version",
                python_version,
                "--implementation",
                "cp",
                "--abi",
                abi,
                "--only-binary=:all:",
                "--require-hashes",
                "-r",
                str(ROOT / "requirements-windows.txt"),
                "--find-links",
                str(ROOT / "wheelhouse"),
            ],
            check=True,
        )
    packages = validate_wheels(wheels)
    payload = build / "payload"
    marker = build / ".workbench-installer-build"
    if payload.exists():
        if not marker.is_file():
            raise ValueError(
                "Refusing to replace an unrecognized payload directory; choose a fresh build directory"
            )
        shutil.rmtree(payload)
    marker.write_text("Shadowserver Companion installer build intermediates\n")
    payload.mkdir()
    copy_source(payload / "app")
    extract_runtime(archive, payload / "runtime", python_tag)
    site_packages = payload / "runtime" / "Lib" / "site-packages"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--quiet",
            "--target",
            str(site_packages),
            "--platform",
            "win_amd64",
            "--python-version",
            python_version,
            "--implementation",
            "cp",
            "--abi",
            abi,
            "--only-binary=:all:",
            "--no-compile",
            "--no-index",
            "--require-hashes",
            "--find-links",
            str(wheels),
            "-r",
            str(ROOT / "requirements-windows.txt"),
        ],
        check=True,
    )
    # pip cross-installs libraries correctly, but generates console wrappers for
    # the build host. The installed application imports these libraries directly.
    for folder in ("bin", "Scripts"):
        generated_scripts = site_packages / folder
        if generated_scripts.is_dir():
            shutil.rmtree(generated_scripts)
    release_notice = {
        "unstable": "Development release. Workstation acceptance is pending.",
        "candidate": "Release candidate. Automated verification and workstation acceptance are recorded separately.",
        "stable": "Release accepted for this version.",
    }[release["channel"]]
    guide = (HERE / "Getting-started.txt").read_text(encoding="utf-8")
    guide_values = {
        "APP_DISPLAY_VERSION": release["display_version"],
        "RELEASE_NOTICE": release_notice,
        "REVIEW_NAME": release.get("review_name", ""),
        "APP_NAME": identity["app_name"],
        "APP_ID": identity["app_id"],
        "APP_PORT": str(identity["port"]),
        "DEMO_PORT": str(identity["demo_port"]),
        "DEMO_NAME": definitions["DEMO_NAME"],
        "EDITION_NOTICE": (
            "Shadowserver Eclipse uses the existing installation and data folders. "
            "Upgrades retain your working records by default; uninstall also retains those records. "
            "Use Settings > Data for backup and restore."
            if release.get("variant") == "dark_matter"
            else f"EXPERIMENTAL COMPARISON: {identity['app_name']} installs separately from the standard "
            "application and other experimental variants. It does not automatically copy existing "
            "records. In your existing installation, export a backup from Settings > Data. "
            f"Import that copy in {identity['app_name']} from Settings > Data and restart when prompted. "
            "Keep the original export and workspace for comparison. Fresh-start and uninstall "
            "affect only this separate installation; uninstall retains its working records."
            if release["edition"] == "chaos"
            else ""
        ),
    }
    for key, value in guide_values.items():
        guide = guide.replace("{" + key + "}", value)
    (payload / "Getting started.txt").write_text(guide, encoding="utf-8")
    notices = [
        f"{identity['app_name']} {version} - third-party components",
        "",
        f"Python {runtime_lock['version']} (Python Software Foundation): runtime/LICENSE.txt",
        "Bundled report fonts: app/fonts/LICENSE.txt and NotoSansSC-OFL.txt",
        "Noto Sans SC static derivative: app/fonts/NotoSansSC-Provenance.json",
        "D3 7.9.0 (ISC): app/static/vendor/D3-LICENSE.txt",
        "U.S. Census Bureau geography: app/static/geo/README.txt and source metadata in places.json/states.json",
        "Shadowserver field inventory: app/schemas/shadowserver-reports.meta.json",
        "Bundled timezone data: app/resources/timezones/provenance.json and LICENSE*",
        "NSIS installer engine: https://nsis.sourceforge.io/License",
        "Python package licenses are retained in runtime/Lib/site-packages/*.dist-info.",
        "Transitive/native-library license notices bundled inside wheels are retained.",
        "",
        "Bundled Python distributions:",
        *[f"  {p['name']} {p['version']}" for p in packages],
        "",
    ]
    (payload / "Third-party notices.txt").write_text("\n".join(notices), encoding="utf-8")
    manifest = {
        "handling": "TLP:AMBER",
        "signing_status": "unsigned",
        "native_windows_acceptance": "not_executed_by_cross_platform_build",
        "distribution_policy": "program-assets-and-synthetic-fixtures-v1",
        "application_version": version,
        "database_schema_max": int(
            re.search(
                r"^SCHEMA_VERSION\s*=\s*(\d+)",
                (ROOT / "workbench/migrations.py").read_text(),
                re.MULTILINE,
            ).group(1)
        ),
        "release": release,
        "installer_build": 1,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "runtime": runtime_lock,
        "packages": packages,
        "files": {
            p.relative_to(payload).as_posix(): sha256(p)
            for p in sorted(payload.rglob("*"))
            if p.is_file()
        },
    }
    (payload / "payload-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    inventory = build / "uninstall-files.nsh"
    inventory.write_text(uninstall_inventory(payload), encoding="utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    flag = "/" if os.name == "nt" else "-"
    command = [
        args.makensis,
        flag + "WX",
        flag + "V2",
        flag + "DPAYLOAD=" + str(payload),
        flag + "DOUTPUT=" + str(output),
        flag + "DAPP_VERSION=" + version,
        flag + "DAPP_DISPLAY_VERSION=" + release["display_version"],
        flag + "DRELEASE_NOTICE=" + release_notice,
        flag + "DUNINSTALL_INVENTORY=" + str(inventory),
        *[flag + "D" + key + "=" + value for key, value in definitions.items()],
        str(HERE / "installer.nsi"),
    ]
    subprocess.run(command, check=True)
    print(
        json.dumps(
            {
                "installer": str(output),
                "bytes": output.stat().st_size,
                "sha256": sha256(output),
                "payload_files": len(manifest["files"]) + 1,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
