"""Publication guards protect stale work and keep transaction ownership explicit."""

import pytest

from modules.investigations.components.repositories.report_publication import activate_report
from modules.workspace.components.workspace import Workspace
from modules.entities.tests.support.contacts import entity_only


@pytest.fixture
def workspace(tmp_path):
    store = Workspace(tmp_path / "data")
    for entity_id in ("entity", "other"):
        entity_only(store, entity_id, entity_id + ".example")
    with store.transaction() as db:
        db.execute("UPDATE leads SET status='in_progress',updated_at='before',new_observations=7")
        db.execute(
            """INSERT INTO cases(id,entity_id,title,created_at,updated_at,draft_revision,version)
               VALUES('case','entity','Synthetic publication','before','before',3,4)"""
        )
        db.execute(
            """INSERT INTO reports(id,lead_id,entity_id,case_id,revision,created_at,path)
               VALUES('report','entity','entity','case',1,'before','reports/synthetic')"""
        )
    return store


def transition(db, **changes):
    return activate_report(
        db,
        **{
            "case_id": "case",
            "entity_id": "entity",
            "report_id": "report",
            "draft_revision": 3,
            "expected_version": 4,
            "updated_at": "after",
            **changes,
        },
    )


def records(store):
    return store.all("SELECT * FROM cases"), store.all("SELECT * FROM leads ORDER BY id")


@pytest.mark.parametrize(
    "changes",
    [
        {"case_id": "missing"},
        {"entity_id": "other"},
        {"draft_revision": 2},
        {"expected_version": 3},
    ],
)
def test_mismatched_publication_never_changes_case_or_either_entity(workspace, changes):
    before = records(workspace)
    with workspace.transaction() as db:
        assert transition(db, **changes) is False
    assert records(workspace) == before


@pytest.mark.parametrize("stage", ["pending_notification", "notification_completed", "closed"])
def test_legacy_publication_retains_stage_guard(workspace, stage):
    with workspace.transaction() as db:
        db.execute("UPDATE cases SET stage=?", (stage,))
    before = records(workspace)
    with workspace.transaction() as db:
        assert transition(db, expected_version=None) is False
    assert records(workspace) == before


def test_legacy_publication_has_no_version_requirement_and_is_idempotent(workspace):
    with workspace.transaction() as db:
        db.execute("UPDATE cases SET version=19")
        assert transition(db, expected_version=None) is True
    case = workspace.one("SELECT * FROM cases WHERE id='case'")
    entity = workspace.one("SELECT * FROM leads WHERE id='entity'")
    other = workspace.one("SELECT * FROM leads WHERE id='other'")
    assert case["version"] == 20 and case["stage"] == "pending_notification"
    assert case["certified_report_id"] == "report"
    assert entity["status"] == "completed" and entity["new_observations"] == 0
    assert case["updated_at"] == entity["updated_at"] == "after"
    assert other["status"] == "in_progress" and other["new_observations"] == 7
    assert other["updated_at"] == "before"
    before = records(workspace)
    with workspace.transaction() as db:
        assert transition(db, expected_version=None, updated_at="later") is False
    assert records(workspace) == before


def test_publication_transition_remains_in_the_callers_transaction(workspace):
    before = records(workspace)
    with pytest.raises(RuntimeError, match="later publication step"):
        with workspace.transaction() as db:
            assert transition(db) is True
            raise RuntimeError("later publication step failed")
    assert records(workspace) == before
