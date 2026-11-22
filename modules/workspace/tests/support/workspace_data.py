"""Reusable synthetic workspace data fixtures and builders."""

from tests.support.qualification import registry_factory, capture_website

import hashlib
import json
from types import SimpleNamespace

from modules.accretion.components.intake_service import IntakeService
from modules.investigations.components.cases import Cases
from modules.library.components.repositories.sources import SourceRepository
from modules.observatory.tests.support.observations import Registry, base, csv_data
from modules.workspace.components.primitives import dump
from modules.workspace.components.store import Store
from modules.workspace.components.workspace_data import WorkspaceData


def label(store, name):
    settings = {**store.settings(), "office": name}
    with store.transaction() as db:
        db.execute("UPDATE settings SET value=? WHERE key='profile'", (dump(settings),))


def manager(store):
    return WorkspaceData(SimpleNamespace(state=SimpleNamespace()), store)


def login(client, app):
    launch = app.state.sessions.issue_launch()
    assert (
        client.post("/api/session/exchange", headers={"X-Workbench-Launch": launch}).status_code
        == 200
    )
    client.headers["X-Workbench-Token"] = client.get("/api/bootstrap").json()["token"]


def workspace_with_report(tmp_path, snapshot, *, register=True, persist=True):
    store = Store(tmp_path / "workspace")
    intake = IntakeService(
        store, attribution_factory=registry_factory(Registry), capture=capture_website
    )
    imported = intake.enqueue("scan-http_vulnerable.csv", csv_data([base()]))
    intake.process(imported["id"])
    lead = store.one("SELECT * FROM leads")
    Cases(store).create(lead["id"])
    case = store.one("SELECT * FROM cases WHERE entity_id=?", (lead["id"],))
    relative = f"reports/{lead['id']}/v001"
    folder = store.path(relative)
    folder.mkdir(parents=True)
    files = {
        "notification.pdf": b"SYNTHETIC PDF",
        "notification.docx": b"SYNTHETIC DOCX",
        "snapshot.json": snapshot,
    }
    for name, content in files.items():
        (folder / name).write_bytes(content)
    manifest = {
        "files": {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}
    }
    (folder / "manifest.json").write_text(json.dumps(manifest))
    if persist:
        with store.transaction() as db:
            db.execute(
                "INSERT INTO reports(id,lead_id,entity_id,case_id,revision,created_at,path) VALUES(?,?,?,?,?,?,?)",
                ("synthetic-report", lead["id"], lead["id"], case["id"], 1, "2026-11-08", relative),
            )
            if register:
                from modules.investigations.components.artifact_registry import register_artifact

                register_artifact(db, store.root, "report", "synthetic-report", legacy=True)
    return store, folder


def captured(store, *, body=b'{"fixture":"original source"}'):
    relative = "evidence/cve/fixture-response.json"
    path = store.root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return {"record_path": relative, "sha256": hashlib.sha256(body).hexdigest()}


def bank_record(store, key, value):
    with store.transaction() as db:
        SourceRepository.put(db, key, value)
