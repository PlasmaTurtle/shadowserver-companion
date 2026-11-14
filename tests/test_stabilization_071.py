"""Release-characterization contracts independent of the internal module layout."""

import hashlib
import io
from pathlib import Path
import zipfile

from session_helpers import TestClient
import pytest

from workbench import approved_template
from workbench.api import create_app


APPROVED_TEMPLATE_SHA256 = "3b139d987f9e83e97f289b45b69f8b755a06bda1b495452697c59bc8d494d1d3"


def test_approved_template_is_the_exact_accepted_source():
    """Approved copy remains exact apart from the separately pinned addressee."""
    from approved_copy_helpers import accepted_source_bytes

    assert hashlib.sha256(accepted_source_bytes()).hexdigest() == APPROVED_TEMPLATE_SHA256


def protected_state(store):
    tables = (
        "cases",
        "case_entries",
        "case_groups",
        "reports",
        "section_validations",
        "section_events",
        "contact_attempts",
        "case_closures",
    )
    return {
        "tables": {table: store.all(f"SELECT * FROM {table} ORDER BY rowid") for table in tables},
        "files": {
            file.relative_to(store.root).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
            for directory in ("originals", "evidence", "reports", "closures")
            for file in (store.root / directory).rglob("*")
            if file.is_file()
        },
    }


@pytest.fixture(scope="module")
def historical_workspace(tmp_path_factory):
    root = tmp_path_factory.mktemp("stabilization-history")
    app = create_app(root, worker=False, demo=True)
    with TestClient(app) as client:
        client.headers["X-Workbench-Token"] = client.get("/api/bootstrap").json()["token"]
        yield app, client


def test_historical_display_download_and_backup_preserve_certification(historical_workspace):
    app, client = historical_workspace
    store = app.state.store
    before = protected_state(store)
    reports = before["tables"]["reports"]
    assert len(reports) == 3
    for report in reports:
        # Repeated display and preview must use the captured certification,
        # even as the implementation behind these public endpoints changes.
        for _ in range(2):
            response = client.get(f"/api/cases/{report['case_id']}")
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["historical_report"]["snapshot_verified"] is True
            assert {review["status"] for review in data["section_reviews"]} == {"validated"}
            assert all(
                review["validated_at"] and review["validated_by"]
                for review in data["section_reviews"]
            )
            preview = client.get(
                f"/api/leads/{report['lead_id']}/preview.pdf", params={"case_id": report["case_id"]}
            )
            assert preview.status_code == 200, preview.text
            expected = before["files"][report["path"] + "/notification.pdf"]
            assert hashlib.sha256(preview.content).hexdigest() == expected
        for suffix, filename in (
            ("pdf", "notification.pdf"),
            ("docx", "notification.docx"),
            ("json", "snapshot.json"),
            ("work-log", "work-log.pdf"),
            ("chronology", "chronology.json"),
        ):
            response = client.get(f"/api/reports/{report['id']}/{suffix}")
            assert response.status_code == 200, response.text
            assert (
                hashlib.sha256(response.content).hexdigest()
                == before["files"][report["path"] + "/" + filename]
            )
    assert protected_state(store) == before
    response = client.post("/api/backup")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as backup:
        assert "data/workbench.sqlite3" in backup.namelist()
        for filename, expected in before["files"].items():
            assert hashlib.sha256(backup.read("data/" + filename)).hexdigest() == expected
    assert protected_state(store) == before


def test_entity_and_case_pairing_remains_explicit(historical_workspace):
    app, client = historical_workspace
    before = protected_state(app.state.store)
    reports = before["tables"]["reports"]
    first, second = reports[:2]
    assert first["lead_id"] != second["lead_id"]
    for endpoint in ("", "/json", "/preview.pdf"):
        response = client.get(
            f"/api/leads/{first['lead_id']}{endpoint}", params={"case_id": second["case_id"]}
        )
        assert response.status_code == 409, response.text
    assert protected_state(app.state.store) == before
