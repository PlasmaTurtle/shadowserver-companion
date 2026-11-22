"""Planner status publication preserves encoding and successful workspace commits."""

import json

from modules.tools.components import filesystem
from modules.workspace.components import planner_maintenance
from modules.workspace.components.workspace import Workspace


def test_planner_status_preserves_existing_text_encoding(tmp_path):
    store = Workspace(tmp_path / "workspace")
    result = planner_maintenance.run(store, force=True)
    reference = tmp_path / "reference.json"
    reference.write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
    assert (store.root / "planner-maintenance.json").read_bytes() == reference.read_bytes()
    assert planner_maintenance.status(store.root) == result


def test_status_replace_failure_keeps_committed_data_and_cleans_temporary_file(
    tmp_path, monkeypatch
):
    store = Workspace(tmp_path / "workspace")
    destination = store.root / "planner-maintenance.json"
    previous = destination.read_bytes()
    replace = filesystem.os.replace

    def fail_status(source, target):
        if target == destination:
            raise OSError("Synthetic status replacement failure")
        return replace(source, target)

    monkeypatch.setattr(filesystem.os, "replace", fail_status)
    store._planner_changes = 10000
    with store.transaction() as db:
        db.execute("INSERT INTO settings VALUES ('planner-fixture','retained committed value')")
    assert store.one("SELECT value FROM settings WHERE key='planner-fixture'")["value"] == (
        "retained committed value"
    )
    assert destination.read_bytes() == previous
    assert not list(store.root.glob("*.tmp"))
