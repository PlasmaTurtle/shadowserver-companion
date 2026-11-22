"""A verified restore must be able to interpret certified compact and legacy models."""

import json

import pytest

from modules.workspace.components import compact_json, workspace_data

from modules.workspace.tests.support.workspace_data import (
    workspace_with_report,
)


@pytest.mark.parametrize("compact", [False, True])
def test_restore_accepts_legacy_and_compact_without_rewriting(tmp_path, compact):
    model = {"draft": {"notes": "SYNTHETIC" * 300}, "evidence": []}
    raw = (compact_json.dumps(model) if compact else json.dumps(model, indent=2)).encode()
    store, folder = workspace_with_report(tmp_path, raw)
    workspace_data.validate_workspace(store.root)
    assert (folder / "snapshot.json").read_bytes() == raw


@pytest.mark.parametrize(
    "mutation",
    ["format", "resource", "missing-reference", "not-object", "bad-draft", "bad-evidence"],
)
def test_restore_rejects_hash_consistent_unreadable_snapshot(tmp_path, mutation):
    model = compact_json.pack({"draft": {"notes": "SYNTHETIC" * 300}})
    digest = next(iter(model["strings"]))
    if mutation == "format":
        model["storage_format"] = "shadowserver-shared-strings-v999"
    elif mutation == "resource":
        model["strings"][digest] = "changed"
    elif mutation == "missing-reference":
        model["strings"].clear()
    elif mutation == "not-object":
        model = []
    elif mutation == "bad-draft":
        model = {"draft": []}
    else:
        model = {"draft": {}, "evidence": {}}
    raw = json.dumps(model).encode()
    store, _ = workspace_with_report(tmp_path, raw)
    with pytest.raises(ValueError, match="Backup report snapshot"):
        workspace_data.validate_workspace(store.root)


def test_restore_rejects_oversized_raw_snapshot_before_json_decode(tmp_path, monkeypatch):
    raw = json.dumps({"draft": {"notes": "SYNTHETIC" * 50}}).encode()
    store, _ = workspace_with_report(tmp_path, raw)
    monkeypatch.setattr(workspace_data, "MAX_REPORT_SNAPSHOT_BYTES", 100)
    monkeypatch.setattr(
        compact_json, "loads", lambda _: pytest.fail("Oversized snapshot was decoded")
    )
    with pytest.raises(ValueError, match="read limit"):
        workspace_data.validate_workspace(store.root)


def test_oversized_orphan_is_rejected_before_startup_recovery(tmp_path, monkeypatch):
    import modules.workspace.components.store as store_module

    raw = json.dumps({"draft": {"notes": "SYNTHETIC" * 50}}).encode()
    store, _ = workspace_with_report(tmp_path, raw, persist=False)
    monkeypatch.setattr(workspace_data, "MAX_REPORT_SNAPSHOT_BYTES", 100)
    monkeypatch.setattr(
        store_module, "Store", lambda _: pytest.fail("Startup recovery ran before size preflight")
    )
    with pytest.raises(ValueError, match="read limit"):
        workspace_data.validate_workspace(store.root)
