"""ECLIPSE routes retain the full source denominator and read-only evidence."""

import hashlib

from test_workbench import app, client, import_rows, observations


def test_empty_observatory_is_local_and_has_no_sample_records(client):
    response = client.get("/api/eclipse")
    assert response.status_code == 200
    assert response.json()["observations"] == []
    assert response.json()["counts"]["rows"] == 0
    assert response.headers["cache-control"] == "no-store"
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert client.get("/api/eclipse/observations/not-a-record").status_code == 404


def test_observatory_drilldown_preserves_original_rows_and_report_navigation(client, app):
    imported, original = import_rows(client, app)
    requests_before = list(app.state.fake.calls)
    result = client.get("/api/eclipse").json()
    assert result["counts"]["observations"] == 5
    assert result["counts"]["qualified_rows"] == 4
    assert len([r for r in result["observations"] if r["status"] == "excluded"]) == 1
    row = next(r for r in result["observations"] if r["hostname"] and r["status"] == "qualified")
    detail = client.get("/api/eclipse/observations/" + row["id"]).json()
    assert detail["fields"]["unknown_extension"] == "KEEP THIS FIELD"
    assert detail["source"]["row"] >= 2
    assert detail["source"]["sha256"] == hashlib.sha256(original).hexdigest()
    assert client.get(detail["original_url"]).content == original
    qualified = next(r for r in result["observations"] if r["status"] == "qualified")
    assert client.get("/api/cases/" + qualified["case_id"]).status_code == 200
    assert app.state.fake.calls == requests_before
    assert client.get("/api/imports/" + imported["id"] + "/original").content == original


def test_original_download_checks_fingerprint_without_reparsing_view(client, app):
    imported, original = import_rows(client, app)
    before = client.get("/api/eclipse").json()
    item = app.state.store.one("SELECT * FROM imports WHERE id=?", (imported["id"],))
    path = app.state.store.path(item["path"])
    path.write_bytes(original + b"changed")
    response = client.get("/api/imports/" + imported["id"] + "/original")
    assert response.status_code == 409
    assert "fingerprint" in response.json()["detail"]
    after = client.get("/api/eclipse").json()
    assert before["observations"] == after["observations"]
