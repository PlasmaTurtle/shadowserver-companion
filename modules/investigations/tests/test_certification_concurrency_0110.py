"""Rendering permits other work but stale certification never publishes."""

from concurrent.futures import ThreadPoolExecutor
import json
from threading import Event

import pytest

from tests.support.workbench import app, client
from modules.investigations.tests.support.section_reviews import prepared
from modules.investigations.components import reporting
from modules.investigations.components.services import certification
from modules.investigations.components.repositories.reviews import SectionReviewRepository


@pytest.mark.parametrize("change_case", [False, True])
def test_other_writes_progress_during_render_and_case_changes_block_publication(
    client, app, monkeypatch, change_case
):
    lead = prepared(client, app)
    store = app.state.store
    entered, resume = Event(), Event()
    original = certification.prepare_package

    def paused(*args, **kwargs):
        entered.set()
        assert resume.wait(20), "Concurrent mutation did not finish while rendering was paused"
        return original(*args, **kwargs)

    monkeypatch.setattr(certification, "prepare_package", paused)
    with ThreadPoolExecutor(max_workers=2) as pool:
        result = pool.submit(reporting.finalize, store, lead["id"], lead["case_id"])
        assert entered.wait(20)

        def mutate():
            with store.transaction() as db:
                if change_case:
                    db.execute("UPDATE cases SET version=version+1 WHERE id=?", (lead["case_id"],))
                else:
                    db.execute("INSERT INTO settings VALUES('parallel-work','finished')")

        try:
            pool.submit(mutate).result(timeout=5)
        finally:
            resume.set()
        if change_case:
            with pytest.raises(ValueError, match="case changed"):
                result.result(timeout=40)
            assert not store.all("SELECT * FROM reports")
            assert not list((store.root / "reports").glob("*/v*/manifest.json"))
        else:
            report = result.result(timeout=40)
            assert (
                store.one("SELECT value FROM settings WHERE key='parallel-work'")["value"]
                == "finished"
            )
            assert store.one(
                "SELECT artifact_id FROM artifact_records WHERE report_id=?", (report["id"],)
            )


def test_changed_validation_cannot_publish_even_without_case_version_change(
    client, app, monkeypatch
):
    lead = prepared(client, app)
    store = app.state.store
    original = certification.prepare_package

    def reopen_after_render(*args, **kwargs):
        package = original(*args, **kwargs)
        with store.transaction() as db:
            SectionReviewRepository(store).event(
                db,
                lead["case_id"],
                "introduction",
                "reopened",
                "Test Analyst",
                "Concurrent review correction",
                1,
            )
        return package

    monkeypatch.setattr(certification, "prepare_package", reopen_after_render)
    with pytest.raises(ValueError, match="evidence changed"):
        reporting.finalize(store, lead["id"], lead["case_id"])
    assert not store.all("SELECT * FROM reports")
    assert not list((store.root / "reports").glob("*/v*/manifest.json"))


@pytest.mark.parametrize("change", ["operator", "source"])
def test_final_publication_rechecks_external_dependencies(client, app, monkeypatch, change):
    lead = prepared(client, app)
    store = app.state.store
    original = certification.prepare_package
    before_version = store.one("SELECT version FROM cases WHERE id=?", (lead["case_id"],))[
        "version"
    ]

    def changed_after_render(*args, **kwargs):
        package = original(*args, **kwargs)
        if change == "operator":
            with store.transaction() as db:
                profile = store.settings(db)
                profile["analyst_name"] = "Changed after render"
                db.execute(
                    "UPDATE settings SET value=? WHERE key='profile'", (json.dumps(profile),)
                )
        else:
            evidence = store.one("SELECT path FROM evidence WHERE case_id=?", (lead["case_id"],))
            store.path(evidence["path"]).write_bytes(b"Changed screenshot bytes")
        assert (
            store.one("SELECT version FROM cases WHERE id=?", (lead["case_id"],))["version"]
            == before_version
        )
        return package

    monkeypatch.setattr(certification, "prepare_package", changed_after_render)
    with pytest.raises(ValueError, match="evidence changed"):
        reporting.finalize(store, lead["id"], lead["case_id"])
    assert not store.all("SELECT * FROM reports")
    assert not store.all("SELECT * FROM artifact_records")
    assert not list((store.root / "reports").glob("*/v*/manifest.json"))
