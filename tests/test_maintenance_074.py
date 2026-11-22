"""Maintenance boundaries, transactional failure cases and release labeling."""

import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from tools.program_map import analyze
from tools.check_release import verify
from modules.workspace.components.release import load_release, check_output_name
from modules.investigations.components.services.reviews import SectionReviewService
from modules.investigations.components.reviews.queries import SectionReviewQueries
from modules.investigations.components.cases import Cases
from tests.support.workbench import app, client
from modules.investigations.tests.support.section_reviews import prepared
from tests.support.stabilization import protected_state

ROOT = Path(__file__).resolve().parents[1]


def test_workspace_and_review_queries_do_not_load_command_services():
    code = """
import sys
import modules.workspace.components.workspace
import modules.entities.components.repositories.entities
import modules.investigations.components.repositories.reviews
import modules.investigations.components.repositories.cases
import modules.library.components.repositories.sources
import modules.investigations.components.reviews.queries
for module in ('modules.workspace.components.store', 'modules.workspace.components.api', 'modules.investigations.components.cases',
               'modules.investigations.components.services.reviews', 'modules.investigations.components.services.certification',
               'modules.investigations.components.services.recovery', 'modules.investigations.components.report_snapshot'):
    assert module not in sys.modules, module
"""
    subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True)


def test_lifecycle_cycle_exception_is_removed():
    data = analyze()
    assert data["errors"] == []
    assert data["cycles"] == []
    assert (
        json.loads((ROOT / "docs/components.json").read_text(encoding="utf-8"))["known_cycles"]
        == []
    )


@pytest.mark.parametrize("action", ["validate", "reopen", "revise"])
def test_review_action_rolls_back_history_when_case_write_fails(client, app, action):
    from tests.support.workbench import resolve_observation_scope

    lead = prepared(client, app, validate=action != "validate")
    if action == "validate":
        lead = resolve_observation_scope(client, lead)
    store = app.state.store
    if action == "revise":
        response = client.post("/api/leads/" + lead["id"] + "/finalize")
        assert response.status_code == 200, response.text
    # Fail after earlier writes so the complete command must roll back.
    with store.transaction() as db:
        if action == "revise":
            db.execute("""CREATE TRIGGER fail_case_write BEFORE INSERT ON events
                        WHEN NEW.action='case_revised'
                        BEGIN SELECT RAISE(ABORT, 'synthetic case write failure'); END""")
        else:
            db.execute("""CREATE TRIGGER fail_case_write BEFORE UPDATE ON cases
                        BEGIN SELECT RAISE(ABORT, 'synthetic case write failure'); END""")
    before = protected_state(store)
    case = store.one("SELECT * FROM cases WHERE id=?", (lead["case_id"],))
    service = SectionReviewService(store)
    with pytest.raises(sqlite3.IntegrityError, match="synthetic case write failure"):
        if action == "validate":
            service.validate(case["id"], "introduction", case["draft_revision"])
        elif action == "reopen":
            service.reopen(case["id"], "introduction", case["draft_revision"], "Correct date")
        else:
            Cases(store).revise(case["id"], case["version"], "Correct date")
    assert protected_state(store) == before


def test_reopen_rejects_stale_revision_without_history_changes(client, app):
    lead = prepared(client, app)
    store = app.state.store
    before = protected_state(store)
    with pytest.raises(ValueError, match="draft changed"):
        SectionReviewService(store).reopen(
            lead["case_id"], "introduction", lead["draft_revision"] - 1, "Correct date"
        )
    assert protected_state(store) == before
    assert SectionReviewQueries(store).repository.active(lead["case_id"])["introduction"]


def write_release(tmp_path, data):
    (tmp_path / "VERSION").write_text("0.7.4\n")
    (tmp_path / "RELEASE.json").write_text(json.dumps(data))


def test_release_gate_never_promotes_without_version_specific_confirmation(tmp_path):
    data = {"schema": 1, "version": "0.7.4", "channel": "unstable", "home_confirmation": None}
    write_release(tmp_path, data)
    assert load_release(tmp_path)["validation_status"] == "awaiting_home_validation"
    # Release checks also work in an installed layout without npm metadata.
    assert verify(tmp_path) == load_release(tmp_path)
    data["channel"] = "stable"
    write_release(tmp_path, data)
    with pytest.raises(ValueError, match="explicit home confirmation"):
        load_release(tmp_path)
    data["home_confirmation"] = {
        "version": "0.7.3",
        "confirmed_by": "Synthetic tester",
        "confirmed_at": "2026-11-07T12:00:00Z",
        "notes": "Synthetic test record; never used for release approval.",
    }
    write_release(tmp_path, data)
    with pytest.raises(ValueError, match="this version"):
        load_release(tmp_path)
    data["home_confirmation"]["version"] = "0.7.4"
    write_release(tmp_path, data)
    assert load_release(tmp_path)["channel"] == "stable"
    data["home_confirmation"]["confirmed_at"] = "2026-11-07T12:00:00"
    write_release(tmp_path, data)
    with pytest.raises(ValueError, match="timezone"):
        load_release(tmp_path)


def test_missing_metadata_and_unmarked_filenames_cannot_look_stable(tmp_path):
    (tmp_path / "VERSION").write_text("0.7.4")
    with pytest.raises(FileNotFoundError):
        load_release(tmp_path)
    release = verify(ROOT)
    # Exercise the unstable filename guard independently of the accepted release channel.
    release = {
        **release,
        "edition": "standard",
        "variant": "",
        "channel": "unstable",
        "home_confirmation": None,
    }
    with pytest.raises(ValueError, match="filenames"):
        check_output_name(Path("Companion-0.7.4.exe"), release)
    check_output_name(Path("Companion-0.7.4-unstable.exe"), release)


def test_runtime_exposes_same_release_identity(client):
    assert client.get("/api/health").json()["release"] == verify(ROOT)
    assert client.get("/api/bootstrap").json()["release"] == verify(ROOT)
