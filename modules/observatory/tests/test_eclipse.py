"""ECLIPSE keeps the scan denominator and current work state independently."""

from tests.support.qualification import registry_factory, capture_website

import io
import json

from openpyxl import Workbook
import pytest

from modules.observatory.components.eclipse import Eclipse
from modules.investigations.components.cases import Cases
from modules.accretion.components.intake_service import IntakeService
from modules.workspace.components.store import Store
from modules.workspace.components.primitives import dump

from modules.observatory.tests.support.observations import (
    Registry,
    base,
    csv_data,
)


@pytest.fixture
def workspace(tmp_path):
    store = Store(tmp_path / "workspace")
    intake = IntakeService(
        store, attribution_factory=registry_factory(Registry), capture=capture_website
    )
    eclipse = Eclipse(store)
    return store, intake, eclipse


def add(intake, rows, process=True):
    result = intake.enqueue("observations.csv", csv_data(rows))
    if process:
        intake.process(result["id"])
    return result["id"]


def test_all_original_rows_are_retained_and_traceable(workspace):
    store, intake, eclipse = workspace
    rows = [
        base(),
        base(ip="10.1.2.3", latitude="", longitude=""),
        base(hostname=""),
        base(version=""),
        base(region="Virginia"),
        base(ip="not an IP"),
        base(ip="8.8.4.4", latitude="NaN"),
    ]
    import_id = add(intake, rows)
    data = eclipse.snapshot()
    assert data["counts"]["observations"] == len(rows)
    assert data["counts"]["findings"] == 1  # Only the qualified EOL condition becomes a finding.
    assert data["counts"]["qualified_rows"] == 3
    assert data["counts"]["dark_matter_observations"] == 4
    assert data["counts"]["unclassified_rows"] == 0
    assert data["coverage_complete"] and not data["warnings"]
    private = next(r for r in data["observations"] if r["ip"] == "10.1.2.3")
    assert private["nonpublic_ip"] and private["status"] == "qualified"
    assert private["latitude"] is None and private["location_basis"] == "unplaced"
    assert sum(r["individually_attributed"] for r in data["observations"]) == 1
    proof = json.loads(store.one("SELECT attribution FROM domain_groups")["attribution"])
    assert proof["evaluated_at"]
    assert all(
        r["attribution_validated_at"] == proof["evaluated_at"]
        for r in data["observations"]
        if r["admitted"]
    )
    assert all(
        r["attribution_validated_at"] is None for r in data["observations"] if r["dark_matter"]
    )
    invalid = [r for r in data["observations"] if r["ip"] == "not an IP" or not r["hostname"]]
    assert len(invalid) == 2
    assert all(r["dark_matter"] and not r["admitted"] for r in invalid)
    assert all(
        eclipse.observation(r["id"])["fields"]["extra_source_field"] == "preserved value"
        for r in invalid
    )
    residue = next(r for r in data["observations"] if not r["version"])
    assert residue["intake_reason"] == "missing_version"
    assert residue["dark_matter"] and not residue["admitted"]
    assert residue["entity_id"] is None and residue["finding_ids"] == []
    retained = eclipse.observation(residue["id"])
    assert retained["fields"]["extra_source_field"] == "preserved value"
    assert retained["fields"]["version"] == ""
    assert retained["source_available"] is True
    assert retained["original_url"] == f"/api/imports/{import_id}/original"
    representative = next(r for r in data["observations"] if r["ip"] == "8.8.8.8" and r["admitted"])
    detail = eclipse.observation(representative["id"])
    assert detail["fields"]["extra_source_field"] == "preserved value"
    assert detail["original_url"] == f"/api/imports/{import_id}/original"
    assert detail["source_available"] is True
    source = store.one("SELECT path FROM imports WHERE id=?", (import_id,))
    assert store.path(source["path"]).read_bytes() == csv_data(rows)
    assert eclipse.observation("missing") is None


def test_policy_reimports_do_not_duplicate_source_rows(workspace):
    store, intake, eclipse = workspace
    original = csv_data([base(), base(region="Virginia")])
    first = intake.enqueue("observations.csv", original)["id"]
    intake.process(first)
    with store.transaction() as db:
        settings = store.settings()
        settings["regions"].append("Virginia")
        db.execute("UPDATE settings SET value=? WHERE key=?", (dump(settings), "profile"))
    second = intake.enqueue("renamed.csv", original)["id"]
    intake.process(second)
    result = eclipse.snapshot()
    assert result["counts"]["observations"] == 1
    assert result["counts"]["qualified_rows"] == 1
    assert len(result["imports"]) == 2
    assert all(set(r["import_ids"]) == {first, second} for r in result["observations"])


def test_canonical_projection_stays_read_only_when_original_changes(workspace, monkeypatch):
    store, intake, eclipse = workspace
    import_id = add(intake, [base()])
    eclipse.snapshot()

    def forbidden(*args, **kwargs):
        raise AssertionError("Repeated snapshot should reuse verified source parse")

    monkeypatch.setattr("modules.accretion.components.intake.read_entries", forbidden)
    assert eclipse.snapshot()["counts"]["rows"] == 1
    item = store.one("SELECT * FROM imports WHERE id=?", (import_id,))
    store.path(item["path"]).write_bytes(csv_data([base(ip="1.1.1.1")]))
    result = eclipse.snapshot()
    assert result["coverage_complete"] is True
    assert result["warnings"] == []
    # The saved qualified observation survives, never the changed source row.
    assert [r["ip"] for r in result["observations"]] == ["8.8.8.8"]
    detail = eclipse.observation(result["observations"][0]["id"])
    assert detail["fields"]["ip"] == "8.8.8.8"
    assert detail["source"]["sha256"] == item["sha256"]


def test_workflow_refresh_does_not_rewrite_observation_time(workspace):
    store, intake, eclipse = workspace
    add(intake, [base()])
    queued = eclipse.snapshot()["observations"][0]
    assert queued["lead_id"] and queued["case_id"] is None
    case = Cases(store).create(queued["entity_id"])
    before = eclipse.snapshot()["observations"][0]
    case_id = before["case_id"]
    assert case_id == case["case_id"]
    assert before["lead_id"] is None
    with store.transaction() as db:
        db.execute(
            "UPDATE cases SET delivered_at='2026-11-06T13:00:00Z', stage='notification_completed' WHERE id=?",
            (case_id,),
        )
    after = eclipse.snapshot()["observations"][0]
    assert before["status"] == "qualified" and after["status"] == "delivered"
    assert before["observed_at"] == after["observed_at"] == "2026-11-04T01:02:03+00:00"
    assert after["observed_day"] == "2026-11-04"
    assert after["delivered_at"] == "2026-11-06T13:00:00Z"


def test_review_pending_and_excluded_stay_distinguishable(workspace):
    store, intake, eclipse = workspace
    import_id = add(intake, [base(), base(hostname=""), base(hostname="second.com")], process=False)
    data = eclipse.snapshot()
    # A queued import has not passed Associate and cannot invent map records.
    assert data["observations"] == []
    assert data["imports"][0]["status"] == "queued"
    intake.process(import_id)
    result = eclipse.snapshot()
    assert result["observations"]
    assert all(r["intake_disposition"] in {"lead", "dark_matter"} for r in result["observations"])
    invalid = [r for r in result["observations"] if not r["hostname"]]
    assert len(invalid) == 1 and invalid[0]["dark_matter"]
    assert invalid[0]["entity_id"] is None


def test_excel_sheets_have_distinct_identity_and_wholly_empty_rows_are_ignored(workspace):
    store, intake, eclipse = workspace
    book = Workbook()
    book.active.title = "First"
    book.create_sheet("Second")
    for sheet in book:
        sheet.append(list(base()))
        sheet.append(list(base().values()))
        sheet.append([None] * len(base()))
        sheet.append(list(base(hostname="", ip="1.1.1.1").values()))
    data = io.BytesIO()
    book.save(data)
    intake.process(intake.enqueue("source.xlsx", data.getvalue())["id"])
    with store.transaction() as db:
        settings = store.settings()
        settings["sheet"] = "Second"
        db.execute("UPDATE settings SET value=? WHERE key=?", (dump(settings), "profile"))
    intake.process(intake.enqueue("source.xlsx", data.getvalue())["id"])
    result = eclipse.snapshot()
    assert result["counts"]["observations"] == 3
    assert {r["sheet"] for r in store.all("SELECT sheet FROM awareness_sources")} == {
        "First",
        "Second",
    }
    assert {r["source"]["row"] for r in result["observations"]} == {2, 4}
    archived = [r for r in result["observations"] if r["dark_matter"]]
    assert {r["source"]["sheet"] for r in archived} == {"First", "Second"}
    assert len({r["id"] for r in archived}) == 2


def test_city_area_is_exact_sourced_and_never_a_server_location(workspace):
    store, intake, eclipse = workspace
    results = [
        eclipse._location(fields)
        for fields in [
            base(city="Charlotte", latitude="", longitude=""),
            base(city="Fairview", latitude="", longitude=""),
            base(city="Charlotte", latitude="", longitude="", geo="FR"),
            base(city="Charrlotte", latitude="", longitude=""),
            base(city="Charlotte"),
        ]
    ]
    assert results[0][2] == "city_area"
    assert "Census representative point" in results[0][3]
    assert results[0][4].startswith("https://www2.census.gov/")
    assert all(row[2] == "unplaced" for row in results[1:4])
    assert results[4][2] == "reported_coordinates"
    assert results[4][:2] == (35.2, -80.8)


def test_no_imports_is_an_honest_empty_workspace(workspace):
    store, intake, eclipse = workspace
    result = eclipse.snapshot()
    assert result["observations"] == [] and result["imports"] == []
    assert all(v == 0 for v in result["counts"].values())
    assert result["coverage_complete"]
    # Compact DTO must always be serializable by a strict JSON response.
    json.dumps(result, allow_nan=False)
