"""Verify a source upgrade and backup restoration against synthetic saved records.

Run with application dependencies available to the current Python interpreter::

    python modules/workspace/tools/verify_upgrade.py --baseline ../baseline --output ../upgrade-qa

Both versions run in fresh subprocesses. The baseline source is never modified;
all synthetic records and results stay under the new, initially empty output
folder. This checks application compatibility, not the native Windows installer.
"""

from pathlib import Path
import argparse
import hashlib
import importlib
from ipaddress import ip_address
import io
import json
import os
import subprocess
import sys
import socket
import zipfile

PROTECTED_TABLES = (
    "leads",
    "cases",
    "entries",
    "case_entries",
    "case_groups",
    "evidence",
    "reports",
    "section_validations",
    "section_events",
    "contact_attempts",
    "case_closures",
    "entity_profiles",
)
APPROVED_TEMPLATE_HASHES = {
    # Historical approved copy and the separately accepted 0.9.5 addressee revision.
    "3b139d987f9e83e97f289b45b69f8b755a06bda1b495452697c59bc8d494d1d3",
    "fcb2d2143887b7a775c4b81845d4ec1160cebac94ee679ca2eb38a43c5c4570b",
}


def fingerprint_files(root):
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in ("originals", "evidence", "reports", "closures")
        for p in (root / folder).rglob("*")
        if p.is_file()
    }


def table_records(store, table, order="rowid"):
    return store.all("SELECT * FROM " + table + " ORDER BY " + order)


def capture(store):
    return {
        "settings": store.settings(),
        "files": fingerprint_files(store.root),
        "leads": table_records(store, "leads", "id"),
        "cases": table_records(store, "cases", "id"),
        "entries": table_records(store, "entries", "id"),
        "case_entries": table_records(store, "case_entries", "case_id,entry_id"),
        "case_groups": table_records(store, "case_groups", "case_id,root_domain"),
        "evidence": table_records(store, "evidence", "id"),
        "reports": table_records(store, "reports", "id"),
        "section_validations": table_records(store, "section_validations", "id"),
        "section_events": table_records(store, "section_events", "id"),
        "contact_attempts": table_records(store, "contact_attempts", "id"),
        "case_closures": table_records(store, "case_closures", "case_id"),
        "entity_profiles": table_records(store, "entity_profiles", "entity_id"),
    }


def unchanged_records(key, before, after):
    """Permit only the documented additive case snapshot column, not changed data."""
    if key != "cases":
        return before == after
    if len(before) != len(after):
        return False
    for old, new in zip(before, after):
        additions = set(new) - set(old)
        if additions - {"entity_snapshot", "intake_score"}:
            return False
        if "intake_score" in additions and new["intake_score"] != "{}":
            return False
        if old != {name: new.get(name) for name in old}:
            return False
    return True


def verify_entity_snapshots(before, after):
    entities = {r["id"]: r for r in before["leads"]}
    profiles = {r["entity_id"]: json.loads(r["payload"]) for r in before["entity_profiles"]}
    prior_cases = {r["id"]: r for r in before["cases"]}
    for case in after["cases"]:
        if "entity_snapshot" not in case:
            continue
        if "entity_snapshot" in prior_cases[case["id"]]:
            assert case["entity_snapshot"] == prior_cases[case["id"]]["entity_snapshot"], (
                "Pinned report identity changed during upgrade"
            )
            continue
        entity = entities[case["entity_id"]]
        assert json.loads(case["entity_snapshot"]) == {
            "entity_id": entity["id"],
            "company": entity["company"],
            "domain": entity["domain"],
            "entity_profile": profiles.get(entity["id"], {}),
        }, "Migrated report identity differs from the original entity projection"


def loopback_only(connect):
    """Keep offline QA compatible with Windows asyncio's local socket pair."""

    def guarded(sock, address):
        try:
            allowed = isinstance(address, tuple) and ip_address(address[0]).is_loopback
        except (ValueError, TypeError, IndexError):
            allowed = False
        if not allowed:
            raise AssertionError("Upgrade QA must remain offline")
        return connect(sock, address)

    return guarded


def phase(name, output):
    import requests

    def no_network(*args, **kwargs):
        raise AssertionError("Upgrade QA must remain offline")

    requests.get = no_network
    socket.create_connection = no_network
    socket.socket.connect = loopback_only(socket.socket.connect)
    socket.socket.connect_ex = loopback_only(socket.socket.connect_ex)
    from fastapi.testclient import TestClient

    # Each subprocess imports the selected checkout, including pre-module releases.
    modular = (Path.cwd() / "modules/workspace/components/api.py").is_file()
    package = "modules" if modular else "workbench"
    api_module = "modules.workspace.components.api" if modular else "workbench.api"
    approved_module = (
        "modules.investigations.components.approved_template"
        if modular
        else "workbench.approved_template"
    )
    create_app = importlib.import_module(api_module).create_app
    __version__ = importlib.import_module(package).__version__

    if name == "baseline":
        workspace = output / "workspace"
        app = create_app(workspace, worker=False, demo=True)
        with TestClient(app, base_url="http://127.0.0.1") as client:
            if hasattr(app.state, "sessions"):
                response = client.post(
                    "/api/session/exchange",
                    headers={"X-Workbench-Launch": app.state.sessions.issue_launch()},
                )
                assert response.status_code == 200
            client.headers["X-Workbench-Token"] = client.get("/api/bootstrap").json()["token"]
            store = app.state.store
            with store.transaction() as db:
                settings = store.settings()
                settings.update(appearance="dark", watch_inbox=False)
                db.execute(
                    "UPDATE settings SET value=? WHERE key=?", (json.dumps(settings), "profile")
                )
            before = capture(store)
            assert (
                hashlib.sha256(
                    (Path(importlib.import_module(approved_module).__file__)).read_bytes()
                ).hexdigest()
                in APPROVED_TEMPLATE_HASHES
            )
            assert len(before["reports"]) == 3 and len(before["section_validations"]) == 15
            reported_cases = {r["case_id"] for r in before["reports"]}
            captured_cases = {r["case_id"] for r in before["evidence"] if r["kind"] == "website"}
            assert reported_cases <= captured_cases, "Baseline report lacks website evidence"
            for item in before["evidence"]:
                assert before["files"][item["path"]] == item["sha256"]
                assert item["preview_path"] in before["files"]
            before["version"] = __version__
            (output / "baseline-manifest.json").write_text(
                json.dumps(before, indent=2), encoding="utf-8"
            )
            backup = client.post("/api/backup")
            assert backup.status_code == 200
            (output / "baseline-backup.zip").write_bytes(backup.content)
        print(
            json.dumps(
                {
                    "phase": name,
                    "version": __version__,
                    "report_count": 3,
                    "validation_count": 15,
                    "protected_file_count": len(before["files"]),
                }
            )
        )
        return
    workspace = output / ("restored/data" if name == "restore" else "workspace")
    before = json.loads((output / "baseline-manifest.json").read_text(encoding="utf-8"))
    app = create_app(workspace, worker=False)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        if hasattr(app.state, "sessions"):
            response = client.post(
                "/api/session/exchange",
                headers={"X-Workbench-Launch": app.state.sessions.issue_launch()},
            )
            assert response.status_code == 200
        bootstrap = client.get("/api/bootstrap").json()
        client.headers["X-Workbench-Token"] = bootstrap["token"]
        after = capture(app.state.store)
        checks = {}
        for key in ("files", *PROTECTED_TABLES):
            checks[key + "_unchanged"] = unchanged_records(key, before[key], after[key])
            assert checks[key + "_unchanged"], key + " changed while opening existing workspace"
        verify_entity_snapshots(before, after)
        checks["migrated_entity_snapshots_match_original_projection"] = True
        assert bootstrap["settings"]["appearance"] == "dark"
        checks["appearance_preserved"] = True
        checks["legacy_download_hashes"] = []
        for report in before["reports"]:
            for format, filename in (
                ("pdf", "notification.pdf"),
                ("docx", "notification.docx"),
                ("json", "snapshot.json"),
                ("work-log", "work-log.pdf"),
                ("chronology", "chronology.json"),
            ):
                path = report["path"] + "/" + filename
                if path not in before["files"]:
                    continue
                response = client.get("/api/reports/" + report["id"] + "/" + format)
                assert response.status_code == 200, response.text
                digest = hashlib.sha256(response.content).hexdigest()
                assert digest == before["files"][path]
                checks["legacy_download_hashes"].append(
                    {"report_id": report["id"], "format": format, "sha256": digest}
                )
        statuses = {}
        for case in before["cases"]:
            if case["stage"] == "in_progress":
                continue
            response = client.get("/api/cases/" + case["id"])
            assert response.status_code == 200, response.text
            value = response.json()
            assert value["case"]["stage"] == case["stage"]
            assert value["case"]["certified_report_id"] == case["certified_report_id"]
            statuses[case["id"]] = {
                item["key"]: item["status"] for item in value["section_reviews"]
            }
            assert len(statuses[case["id"]]) == 5 and set(statuses[case["id"]].values()) == {
                "validated"
            }
            assert value["historical_report"]["app_version"] == before["version"]
            assert value["historical_report"]["handling_label"] == "TLP:AMBER"
            assert value["historical_report"]["snapshot_verified"] is True
            report = next(r for r in before["reports"] if r["id"] == case["certified_report_id"])
            preview = client.get(
                "/api/leads/" + case["entity_id"] + "/preview.pdf", params={"case_id": case["id"]}
            )
            assert preview.status_code == 200
            assert (
                hashlib.sha256(preview.content).hexdigest()
                == before["files"][report["path"] + "/notification.pdf"]
            )
        checks["historical_review_display"] = statuses
        after_reads = capture(app.state.store)
        for key in ("files", *PROTECTED_TABLES):
            assert unchanged_records(key, before[key], after_reads[key]), (
                key + " changed during historical reads"
            )
        assert after["cases"] == after_reads["cases"], (
            "Pinned entity snapshots changed during reads"
        )
        checks["history_bytes_after_read_unchanged"] = True
        backup = client.post("/api/backup")
        assert backup.status_code == 200
        (output / (name + "-backup.zip")).write_bytes(backup.content)
        with zipfile.ZipFile(io.BytesIO(backup.content)) as archive:
            assert "data/workbench.sqlite3" in archive.namelist()
            for path, digest in before["files"].items():
                assert hashlib.sha256(archive.read("data/" + path)).hexdigest() == digest
        checks["backup_original_report_source_hashes_match"] = True
        checks["version"] = __version__
        checks["native_windows_installer_test"] = False
        (output / (name + "-result.json")).write_text(
            json.dumps(checks, indent=2), encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "phase": name,
                    "version": __version__,
                    "checks_passed": True,
                    "legacy_downloads_verified": len(checks["legacy_download_hashes"]),
                    "historical_review_display": statuses,
                }
            )
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline",
        type=Path,
        required=True,
        help="Untouched baseline source checkout or extracted source distribution",
    )
    parser.add_argument("--current", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New or empty directory for synthetic workspace, backups and result JSON",
    )
    parser.add_argument(
        "--phase", choices=("baseline", "upgrade", "restore"), help=argparse.SUPPRESS
    )
    args = parser.parse_args()
    baseline, current, output = (p.resolve() for p in (args.baseline, args.current, args.output))
    for code in (baseline, current):
        if not any(
            (code / entry).is_file()
            for entry in ("modules/workspace/components/api.py", "workbench/api.py")
        ):
            parser.error(f"Application source was not found at {code}")
    if args.phase:
        phase(args.phase, output)
        return
    if output.exists() and any(output.iterdir()):
        parser.error("Choose an empty output directory; existing QA evidence is never overwritten.")
    if (
        output == baseline
        or output == current
        or baseline in output.parents
        or current in output.parents
    ):
        parser.error("Place the output outside both source trees.")
    output.mkdir(parents=True, exist_ok=True)

    def run(name, code):
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONPATH"] = os.pathsep.join(
            (
                str(code),
                str(code / "modules/attribution/components/engine/src"),
                str(code / "components/attribution/src"),
                env.get("PYTHONPATH", ""),
            )
        )
        subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--baseline",
                str(baseline),
                "--current",
                str(current),
                "--output",
                str(output),
                "--phase",
                name,
            ],
            env=env,
            cwd=code,
            check=True,
        )

    run("baseline", baseline)
    run("upgrade", current)
    with zipfile.ZipFile(output / "upgrade-backup.zip") as archive:
        assert all(not n.startswith("/") and ".." not in Path(n).parts for n in archive.namelist())
        archive.extractall(output / "restored")
    run("restore", current)
    baseline_manifest = json.loads((output / "baseline-manifest.json").read_text(encoding="utf-8"))
    summary = {
        "baseline_version": baseline_manifest["version"],
        "upgrade_version": (current / "VERSION").read_text(encoding="utf-8").strip(),
        "host": sys.platform,
        "method": "Baseline source creates a synthetic saved workspace; current source opens it offline, verifies historical artifacts and API downloads, then reopens a backup restored into a different folder.",
        "native_windows_installer_test": False,
        "results": [
            json.loads((output / (name + "-result.json")).read_text(encoding="utf-8"))
            for name in ("upgrade", "restore")
        ],
    }
    destination = output / "upgrade-acceptance-result.json"
    destination.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({"result": str(destination), "passed": True}))


if __name__ == "__main__":
    main()
