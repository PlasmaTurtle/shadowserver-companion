from tests.support.qualification import registry_factory, capture_website
import hashlib
import io
import json
from modules.workspace.components import compact_json
import zipfile
from pathlib import Path

import pytest
from tests.session_helpers import TestClient
from PIL import Image

from modules.workspace.components.api import create_app
from modules.workspace.components.store import Store
from modules.workspace.components.primitives import now
from modules.library.components.intelligence.acquisition import CapturedSource

from tests.support.workbench import (
    FakeRegistry,
    app,
    client,
    import_rows,
    observations,
    ready,
    validate_sections,
)


def test_intake_preserves_all_fields_and_reorders_only_match(client, app):
    record, original = import_rows(client, app)
    report = client.get("/api/imports/" + record["id"]).json()
    assert (report["rows_read"], report["valid_rows"], report["qualified"]) == (9, 4, 1)
    assert app.state.fake.calls == ["1.1.1.1", "8.8.8.8"]
    lead = client.get("/api/leads").json()[0]
    data = client.get("/api/leads/" + lead["id"] + "/json").json()
    entries = data["validated_leads"][0]["entries"]
    assert [e["ip"] for e in entries] == ["8.8.8.8", "1.1.1.1", "10.1.2.3", "9.9.9.9"]
    assert entries[0]["source"]["fields"]["unknown_extension"] == "KEEP THIS FIELD"
    assert entries[0]["source"]["fields"]["empty_extension"] == ""
    assert entries[2]["private_ip"] is True
    assert data["whois"][0]["ip"] == entries[0]["ip"]
    assert client.get("/api/imports/" + record["id"] + "/original").content == original
    duplicate = client.post(
        "/api/imports", files=[("files", ("renamed.csv", original, "text/csv"))]
    ).json()[0]
    assert duplicate["duplicate"] and duplicate["id"] == record["id"]


def test_registry_error_is_retryable_not_discarded(client, app):
    app.state.fake.fail = True
    record, _ = import_rows(client, app)
    assert client.get("/api/imports/" + record["id"]).json()["status"] == "needs_retry"
    assert not client.get("/api/leads").json()
    app.state.fake.fail = False
    assert client.post("/api/imports/" + record["id"] + "/retry").status_code == 200
    app.state.intake.process(record["id"])
    assert client.get("/api/imports/" + record["id"]).json()["status"] == "done"
    assert len(client.get("/api/leads").json()) == 1


def test_draft_requires_session_and_detects_stale_revision(client, app):
    import_rows(client, app)
    lead_id = client.get("/api/leads").json()[0]["id"]
    lead = client.get("/api/leads/" + lead_id).json()
    payload = {"expected_revision": 0, "fields": lead["draft"]}
    assert (
        client.put(
            "/api/leads/" + lead_id + "/draft",
            json=payload,
            headers={"X-Workbench-Token": "invalid"},
        ).status_code
        == 403
    )
    assert (
        client.put(
            "/api/leads/" + lead_id + "/draft",
            json=payload,
            headers={"Origin": "https://evil.example"},
        ).status_code
        == 403
    )
    assert client.put("/api/leads/" + lead_id + "/draft", json=payload).status_code == 200
    assert client.put("/api/leads/" + lead_id + "/draft", json=payload).status_code == 409
    assert client.post("/api/leads/" + lead_id + "/finalize").status_code == 422


def test_full_notification_snapshot_and_new_observations(client, app):
    import_rows(client, app)
    lead_id = client.get("/api/leads").json()[0]["id"]
    ready(client, lead_id)
    preview = client.get("/api/leads/" + lead_id + "/preview.pdf")
    assert preview.status_code == 200 and preview.content.startswith(b"%PDF")
    response = client.post("/api/leads/" + lead_id + "/finalize")
    assert response.status_code == 200, response.text
    report = response.json()
    report_path = app.state.store.path(report["path"])
    pdf = (report_path / "notification.pdf").read_bytes()
    assert (report_path / "notification.docx").read_bytes().startswith(b"PK")
    manifest = json.loads((report_path / "manifest.json").read_text(encoding="utf-8"))
    assert all(
        hashlib.sha256((report_path / k).read_bytes()).hexdigest() == v
        for k, v in manifest["files"].items()
    )
    assert client.post("/api/leads/" + lead_id + "/finalize").status_code == 422
    rows = observations()
    for row in rows:
        row["timestamp"] = "2026-11-05 02:00:00"
        if row.get("version"):
            # A distinct affected release line creates new work; patch-version
            # changes to an already certified finding only add history.
            row["version"] = "8.0.1"
    import_rows(client, app, rows, name="next-day.csv")
    lead = client.get("/api/leads/" + lead_id).json()
    assert (
        lead["case"]["stage"] == "pending_notification"
        and lead["case"]["certified_report_id"] == report["id"]
    )
    assert lead["new_observations"] == 4
    assert len(client.get("/api/pending-leads").json()) == 1
    assert (report_path / "notification.pdf").read_bytes() == pdf
    saved_snapshot = compact_json.loads((report_path / "snapshot.json").read_text(encoding="utf-8"))
    recipient_rows = saved_snapshot["qualified_lead"]["validated_leads"][0]["entries"]
    retained_rows = saved_snapshot["scope_source_entries"]
    excluded = {
        identity: decision
        for identity, decision in saved_snapshot["draft"]["observation_scope"].items()
        if decision["decision"] == "exclude"
    }
    assert len(recipient_rows) == 3 and len(retained_rows) == 4 and len(excluded) == 1
    assert {row["id"] for row in recipient_rows} == {
        row["id"] for row in retained_rows
    } - excluded.keys()
    excluded_row = next(row for row in retained_rows if row["id"] in excluded)
    assert excluded_row["ip"] == "10.1.2.3"
    assert excluded[excluded_row["id"]]["reason"] and excluded[excluded_row["id"]]["actor"]
    assert len(lead["entries"]) == 3 and len(lead["scope_source_entries"]) == 4
    assert {row["id"] for row in lead["scope_source_entries"]} == {
        row["id"] for row in retained_rows
    }
    assert (
        next(r for r in lead["section_reviews"] if r["key"] == "vulnerabilities")["status"]
        == "validated"
    )
    assert client.get("/api/leads").json()[0]["unassigned_observations"] == 4
    assert (
        client.post(
            "/api/reports/" + report["id"] + "/delivery",
            json={"sent_at": now(), "note": "Manually delivered"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/reports/" + report["id"] + "/delivery",
            json={"sent_at": now(), "note": "Manually delivered", "recipient": "Test Director"},
        ).status_code
        == 200
    )
    zipresponse = client.get("/api/reports/" + report["id"] + "/zip")
    assert "manifest.json" in zipfile.ZipFile(io.BytesIO(zipresponse.content)).namelist()
    counts = client.get("/api/dashboard").json()["counts"]
    assert counts["completed"] == 1 and counts["sent"] == 1
    backup = client.post("/api/backup")
    names = zipfile.ZipFile(io.BytesIO(backup.content)).namelist()
    assert "data/workbench.sqlite3" in names
    assert any(n.endswith("notification.docx") for n in names)


def test_completed_files_control_metrics_and_recovery(client, app):
    import_rows(client, app)
    lead_id = client.get("/api/leads").json()[0]["id"]
    ready(client, lead_id)
    report = client.post("/api/leads/" + lead_id + "/finalize").json()
    folder = app.state.store.path(report["path"])
    expected_version = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))[
        "expected_version"
    ]
    with app.state.store.transaction() as db:
        db.execute(
            "UPDATE cases SET certified_report_id=NULL,stage='in_progress',version=? WHERE id=?",
            (expected_version, report["case_id"]),
        )
        from tests.artifact_helpers import remove_artifact_commit

        remove_artifact_commit(db, "report", report["id"])
    restarted = Store(app.state.store.root)
    assert len(restarted.all("SELECT * FROM reports")) == 1
    recovered_case = restarted.one(
        "SELECT stage,certified_report_id,version FROM cases WHERE id=?", (report["case_id"],)
    )
    assert recovered_case == {
        "stage": "pending_notification",
        "certified_report_id": report["id"],
        "version": expected_version + 1,
    }
    (folder / "notification.pdf").unlink()
    assert client.get("/api/dashboard").json()["counts"]["completed"] == 0
    assert client.get("/api/dashboard").json()["missing_packages"] == 1


def test_unresolved_cve_requires_text_disposition_not_image(client, app):
    rows = observations()
    rows[0]["tag"] = "cve-2021-41773;apache"
    import_rows(client, app, rows)
    lead_id = client.get("/api/leads").json()[0]["id"]
    lead = ready(client, lead_id, validate=False)
    assert not next(x for x in lead["readiness"] if x["key"] == "cve_reference")["ok"]
    assert client.post("/api/leads/" + lead_id + "/finalize").status_code == 422
    d = lead["draft"]
    d.update(
        reviewed=True,
        cve_dispositions={
            "CVE-2021-41773": {
                "action": "fallback",
                "reason": "Captured published source during source service outage.",
                "description": "Synthetic official-source fixture for this test.",
                "evidence_text": "Synthetic official-source fixture for this test.",
                "publisher": "Fixture publisher",
                "source_url": "https://example.com/advisory",
                "retrieved_at": now(),
            }
        },
    )
    saved = client.put(
        "/api/leads/" + lead_id + "/draft",
        json={"expected_revision": lead["draft_revision"], "fields": d},
    )
    assert saved.status_code == 200, saved.text
    # Adoption invalidates review; perform the required final review separately.
    lead = saved.json()
    d = lead["draft"]
    d["reviewed"] = True
    reviewed = client.put(
        "/api/leads/" + lead_id + "/draft",
        json={"expected_revision": lead["draft_revision"], "fields": d},
    )
    assert reviewed.status_code == 200
    validate_sections(client, reviewed.json())
    result = client.post("/api/leads/" + lead_id + "/finalize")
    assert result.status_code == 200, result.text


def test_invalid_uploads_and_paths_rejected(client, app):
    bad = client.post(
        "/api/imports", files=[("files", ("test.exe", b"MZ", "application/octet-stream"))]
    ).json()[0]
    assert "error" in bad
    with pytest.raises(ValueError):
        app.state.store.path("../outside")
    missing = client.get("/api/leads/unknown")
    assert missing.status_code == 404
    assert client.get("/", headers={"Host": "evil.example"}).status_code == 400


def test_workbook_and_startup_resume(client, app):
    fixture = Path(__file__).parent / "fixtures" / "intake_fixture.xlsx"
    record = client.post(
        "/api/imports",
        files=[("files", ("intake.xlsx", fixture.read_bytes(), "application/octet-stream"))],
    ).json()[0]
    app.state.intake.process(record["id"])
    result = client.get("/api/imports/" + record["id"]).json()
    assert result["status"] in ("done", "needs_retry"), result
    assert result["rows_read"] > 0 and result["valid_rows"] > 0
    with app.state.store.transaction() as db:
        db.execute("UPDATE imports SET status='running' WHERE id=?", (record["id"],))
    restarted = Store(app.state.store.root)
    assert (
        restarted.one("SELECT status FROM imports WHERE id=?", (record["id"],))["status"]
        == "queued"
    )


def test_demo_does_not_query_network(tmp_path, monkeypatch):
    import socket
    import subprocess
    from modules.workspace.components.demo import seed_demo
    from modules.investigations.components.observation_scope import address_issue

    monkeypatch.setattr(
        socket, "create_connection", lambda *a, **k: pytest.fail("Demo requested network access")
    )
    fake = FakeRegistry()
    app = create_app(
        tmp_path / "demo",
        worker=False,
        report_processes=False,
        demo=True,
        attribution_factory=registry_factory(lambda: fake),
        capture=capture_website,
    )
    with TestClient(app) as client:
        data = client.get("/api/dashboard").json()
        assert data["counts"] == {
            "new": 1,
            "in_progress": 1,
            "completed": 3,
            "sent": 2,
            "observations": 17,
            "assets": 17,
            "hostnames": 10,
            "review": 0,
        }
        assert {
            k: data["workflow"][k]
            for k in ("in_progress", "pending_notification", "notification_completed", "closed")
        } == {"in_progress": 1, "pending_notification": 1, "notification_completed": 1, "closed": 1}
        assert len(client.get("/api/pending-leads").json()) == 1
        assert fake.calls == []
        leads = client.get("/api/leads").json()
        assert all(lead_item["demo"] for lead_item in leads)
        for lead_item in leads:
            lead = client.get("/api/leads/" + lead_item["id"]).json()
            assert all(
                entry["source"]["fields"]["report_type"] == "scan_http_vulnerable"
                for entry in lead["entries"]
            )
            assert not any(address_issue(entry) for entry in lead["entries"])
            assert [p["id"] for p in lead["draft"]["report_explainer_snapshots"]] == [
                "vulnerable_http"
            ]
            assert [s["id"] for s in lead["draft"]["finding_explainer_snapshots"]] == [
                "http_eol_php"
            ]
        reports = app.state.store.all("SELECT * FROM reports ORDER BY id")
        files = {
            report["id"]: (app.state.store.path(report["path"]) / "notification.pdf").read_bytes()
            for report in reports
        }
        seed_demo(app.state.store, app.state.intake)
        assert app.state.store.all("SELECT * FROM reports ORDER BY id") == reports
        for report in reports:
            pdf = app.state.store.path(report["path"]) / "notification.pdf"
            assert pdf.read_bytes() == files[report["id"]]
            text = subprocess.check_output(
                ["pdftotext", "-f", "1", "-l", "1", str(pdf), "-"], text=True
            )
            assert "DEMONSTRATION WORKSPACE" in " ".join(text.split())
            assert "No real exposure assessed" in " ".join(text.split())
    restarted = create_app(
        tmp_path / "demo",
        worker=False,
        report_processes=False,
        attribution_factory=registry_factory(lambda: fake),
        capture=capture_website,
    )
    with TestClient(restarted) as client:
        assert client.get("/api/dashboard").status_code == 200
        assert restarted.state.store.all("SELECT * FROM reports ORDER BY id") == reports
        assert fake.calls == []


def test_policy_change_does_not_duplicate_original_rows(client, app):
    import_rows(client, app)
    settings = client.get("/api/bootstrap").json()["settings"]
    settings["regions"].append("South Carolina")
    assert client.put("/api/settings", json=settings).status_code == 200
    import_rows(client, app)
    assert client.get("/api/dashboard").json()["counts"]["observations"] == 4


def test_cve_sources_keep_unavailable_metrics_unknown(client, monkeypatch):
    import requests
    from modules.library.components.intelligence import service as cve_sources

    def unavailable(*args, **kwargs):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(cve_sources, "capture_json", unavailable)
    response = client.post("/api/cves/CVE-2021-41773/retrieve")
    result = response.json()
    assert result["cvss"] is None and result["epss"] is None and result["kev"] is None
    assert len(result["errors"]) == 4 and not result["sources"]
    assert client.post("/api/cves/not-a-cve/retrieve").status_code == 422


def test_cve_sources_preserve_probability_and_dates(client, monkeypatch):
    from modules.library.components.intelligence import service as cve_sources

    def source(store, key, url, **kwargs):
        if key.startswith("cve:"):
            data = {
                "cveMetadata": {"state": "PUBLISHED"},
                "containers": {
                    "cna": {
                        "providerMetadata": {"shortName": "TEST"},
                        "descriptions": [{"lang": "en", "value": "Synthetic test description"}],
                        "metrics": [
                            {
                                "cvssV3_1": {
                                    "baseScore": 9.1,
                                    "version": "3.1",
                                    "vectorString": "TEST",
                                }
                            }
                        ],
                    }
                },
            }
        elif key.startswith("epss:"):
            data = {"data": [{"cve": "CVE-2021-41773", "epss": "0.3", "date": "2026-11-04"}]}
        else:
            data = {
                "dateReleased": "2026-11-04",
                "catalogVersion": "2026.11.04",
                "count": 1,
                "vulnerabilities": [
                    {
                        "cveID": "CVE-2021-41773",
                        "vendorProject": "Example",
                        "product": "Example",
                        "vulnerabilityName": "Example issue",
                        "dateAdded": "2026-11-04",
                        "shortDescription": "Synthetic description",
                        "requiredAction": "Update",
                        "dueDate": "2026-11-20",
                    }
                ],
            }
        return data, "2026-11-05T00:00:00Z"

    monkeypatch.setattr(
        cve_sources,
        "verify",
        lambda *args, **kwargs: {
            "id": "CVE-2021-41773",
            "cvss": 9.1,
            "epss": None,
            "kev": None,
            "source": "CVE Program",
            "record": {"cveMetadata": {"cveId": "CVE-2021-41773", "state": "PUBLISHED"}},
            "sources": [{"publisher": "CVE Program"}],
            "errors": [],
        },
    )
    monkeypatch.setattr(
        cve_sources,
        "capture_json",
        lambda *a, **kw: CapturedSource(
            *source(*a, **kw),
            {},
            {"risk": None, "risk-proof": None, "risk-attempt": None, "risk-refresh": None},
        ),
    )
    result = client.post("/api/cves/CVE-2021-41773/retrieve").json()
    assert result["cvss"] == 9.1 and result["epss"] == 0.3 and result["kev"] is True
    assert result["epss_date"] == "2026-11-04" and len(result["sources"]) == 3


def test_heic_evidence_is_decoded_without_altering_original(client, app):
    import pillow_heif

    import_rows(client, app)
    lead_id = client.get("/api/leads").json()[0]["id"]
    buf = io.BytesIO()
    pillow_heif.from_pillow(Image.new("RGB", (320, 200), "navy")).save(buf)
    original = buf.getvalue()
    r = client.post(
        "/api/leads/" + lead_id + "/evidence",
        data={"kind": "website", "source_url": "https://example.com", "caption": "Synthetic HEIC"},
        files={"file": ("test.heic", original, "image/heic")},
    )
    assert r.status_code == 200, r.text
    evidence = next(e for e in r.json()["evidence"] if e["filename"] == "test.heic")
    assert app.state.store.path(evidence["path"]).read_bytes() == original
    assert client.get("/api/evidence/" + evidence["id"] + "/image").content.startswith(b"\x89PNG")
