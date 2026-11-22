"""Pre-case website evidence participates in ordinary health and maintenance."""

import pytest

from modules.investigations.components import website_evidence
from modules.investigations.tests.support.website_capture import captured
from modules.workspace.components.store import Store
from modules.workspace.components.workspace_health import inspect_workspace
from modules.workspace.components.workspace_maintenance import plan, cleanup
from modules.workspace.components.workspace_recovery import compact


def test_precase_screenshot_survives_cleanup_compaction_and_restore_point(tmp_path):
    store = Store(tmp_path / "workspace")
    capture = website_evidence.retain(store, *captured(), root_domain="example.com")
    before = website_evidence.get(store, capture["id"])
    assert not store.all("SELECT * FROM evidence")
    assert not store.all("SELECT * FROM leads")
    assert inspect_workspace(store.root)["ok"]
    reviewed = plan(store.root)
    result = cleanup(store.root, cutoff=reviewed["cutoff"], token=reviewed["token"])
    assert result["files_removed"] == 0
    assert website_evidence.get(store, capture["id"]) == before
    result = compact(store.root, confirmation="COMPACT")
    assert result["ok"] and result["restore_point"]
    assert website_evidence.get(Store(store.root), capture["id"]) == before
    assert inspect_workspace(store.root)["ok"]


@pytest.mark.parametrize("damaged", ["path", "preview_path", "metadata_path"])
def test_health_detects_tampered_precase_capture_and_compaction_refuses_it(tmp_path, damaged):
    store = Store(tmp_path / "workspace")
    capture = website_evidence.retain(store, *captured(), root_domain="example.com")
    store.path(capture[damaged]).write_bytes(b"changed retained website evidence")
    health = inspect_workspace(store.root)
    assert not health["ok"]
    assert (
        next(item for item in health["stores"] if item["store"] == "workspace")["status"] == "error"
    )
    with pytest.raises(ValueError, match="integrity and references"):
        compact(store.root, confirmation="COMPACT")
