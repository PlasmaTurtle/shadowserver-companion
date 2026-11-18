"""Maintenance boundaries, transactional failure cases and release labeling."""

import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from tools.program_map import analyze
from tools.check_release import verify
from workbench.release import load_release, check_output_name
from workbench.services.reviews import SectionReviewService
from workbench.reviews.queries import SectionReviewQueries
from workbench.cases import Cases
from test_workbench import app, client
from test_section_validation_050 import prepared
from test_stabilization_071 import protected_state

ROOT = Path(__file__).resolve().parents[1]


def test_workspace_and_review_queries_do_not_load_command_services():
    code = """
import sys
import workbench.workspace
import workbench.repositories.entities
import workbench.repositories.reviews
import workbench.repositories.cases
import workbench.repositories.sources
import workbench.reviews.queries
for module in ('workbench.store', 'workbench.api', 'workbench.cases',
               'workbench.services.reviews', 'workbench.services.certification',
               'workbench.services.recovery', 'workbench.report_snapshot'):
    assert module not in sys.modules, module
"""
    subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True)


def test_lifecycle_cycle_exception_is_removed():
    data = analyze()
    assert data["errors"] == []
    assert data["cycles"] == []
    assert json.loads((ROOT / "docs/components.json").read_text())["known_cycles"] == []


@pytest.mark.parametrize("action", ["validate", "reopen", "revise"])
def test_review_action_rolls_back_history_when_case_write_fails(client, app, action):
    from test_workbench import resolve_observation_scope

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
