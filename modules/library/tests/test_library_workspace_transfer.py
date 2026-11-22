"""Library history and research state survive the actual workspace lifecycle."""

from contextlib import closing
import sqlite3

import pytest

from modules.library.components.research import Research, SavedViewInput
from modules.library.components.services.content import ContentService
from modules.workspace.components.store import Store
from modules.workspace.components.workspace_data import apply_pending_workspace, export_workspace
from modules.workspace.databases import migrations
from modules.workspace.tests.support.workspace_data import manager
from tests.schema_helpers import restore_schema


def test_schema_22_upgrade_keeps_current_wording_and_starts_honest_history(tmp_path):
    store = Store(tmp_path / "workspace")
    with closing(store.connect()) as db:
        restore_schema(db, 22)
        db.execute(
            "UPDATE explainers SET revision=7,body='Retained analyst wording' WHERE id='cve'"
        )
        db.execute(
            "INSERT OR REPLACE INTO cache VALUES(?,?,?)",
            (
                "block-sources:cve:7",
                '[{"url":"https://example.test/reference","title":"Original citation"}]',
                "2026-11-21",
            ),
        )
        db.commit()
    before = store.all("SELECT * FROM explainers ORDER BY id")
    upgraded = Store(store.root)
    assert upgraded.all("SELECT * FROM explainers ORDER BY id") == before
    history = ContentService(upgraded).history("cve")
    assert [row["revision"] for row in history["items"]] == [7]
    assert history["items"][0]["action"] == "legacy_current"
    retained = ContentService(upgraded).revision("cve", 7)
    assert retained["body"] == "Retained analyst wording"
    assert retained["source_metadata"][0]["title"] == "Original citation"
    assert upgraded.one("PRAGMA user_version")["user_version"] == migrations.SCHEMA_VERSION


def test_interrupted_library_migration_rolls_back_then_retries(tmp_path, monkeypatch):
    store = Store(tmp_path / "workspace")
    with closing(store.connect()) as db:
        restore_schema(db, 22)
    before = store.all("SELECT * FROM explainers ORDER BY id")
    migration = migrations.MIGRATIONS[23]

    def interrupted(db):
        migration(db)
        raise RuntimeError("Synthetic interrupted Library migration")

    monkeypatch.setitem(migrations.MIGRATIONS, 23, interrupted)
    with pytest.raises(RuntimeError, match="interrupted Library"):
        Store(store.root)
    assert store.one("PRAGMA user_version")["user_version"] == 22
    assert store.one("SELECT name FROM sqlite_master WHERE name='explainer_revisions'") is None
    assert store.all("SELECT * FROM explainers ORDER BY id") == before
    monkeypatch.setitem(migrations.MIGRATIONS, 23, migration)
    assert Store(store.root).one("SELECT count(*) AS n FROM explainer_revisions")["n"] == len(
        before
    )


def test_export_restore_retains_views_full_history_archive_and_immutability(tmp_path):
    source = Store(tmp_path / "source")
    content = ContentService(source)
    block = content.create(
        {
            "title": "Synthetic reference",
            "body": "Original wording",
            "sources": "https://example.test/reference",
            "source_metadata": [
                {"url": "https://example.test/reference", "title": "Captured title"}
            ],
        }
    )
    content.update(
        block["id"],
        {"title": block["title"], "body": "Revised wording", "sources": block["sources"]},
        1,
    )
    content.archive(block["id"], 2, True)
    saved = Research(source, None).create_view(
        SavedViewInput(
            name="All severities", selection={"view": "cves", "cveSeverity": "", "cveQuery": "mail"}
        )
    )
    histories = source.all("SELECT * FROM explainer_revisions ORDER BY block_id,revision")
    archive = export_workspace(source)
    try:
        destination = Store(tmp_path / "restored")
        manager(destination).stage("import", archive)
        apply_pending_workspace(destination.root)
        reopened = Store(destination.root)
        assert Research(reopened, None).views() == [saved]
        assert (
            reopened.all("SELECT * FROM explainer_revisions ORDER BY block_id,revision")
            == histories
        )
        service = ContentService(reopened)
        assert all(item["id"] != block["id"] for item in service.list())
        assert service.get(block["id"])["archived_at"]
        restored = service.restore(block["id"], 1, 3)
        assert restored["revision"] == 4 and restored["body"] == "Original wording"
        assert service.revision(block["id"], 2)["body"] == "Revised wording"
        assert restored["source_metadata"] == block["source_metadata"]
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            with reopened.transaction() as db:
                db.execute("DELETE FROM explainer_revisions WHERE block_id=?", (block["id"],))
    finally:
        archive.unlink()
