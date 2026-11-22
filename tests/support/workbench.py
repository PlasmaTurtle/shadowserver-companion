"""Reusable synthetic workbench fixtures and builders."""

from tests.support.qualification import registry_factory, capture_website

import csv
import io
import json

import pytest
from PIL import Image

from tests.support.qualification import WhoisLookupError, WhoisRecord
from modules.workspace.components.api import create_app
from modules.workspace.components.primitives import now
from tests.session_helpers import TestClient


class FakeRegistry:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def lookup(self, ip):
        self.calls.append(ip)
        if self.fail:
            raise WhoisLookupError("Temporary registry outage")
        domain = "example.com" if ip == "8.8.8.8" else "unrelated.com"
        return WhoisRecord(
            ip,
            "TEST REGISTRY",
            "https://rdap.arin.net/registry/ip/" + ip,
            now(),
            {
                "contact": "abuse@" + domain,
                "startAddress": ip,
                "endAddress": ip,
                "notice": "Synthetic test registry response; no network lookup performed.",
            },
        )

    def close(self):
        pass


def csv_bytes(rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue().encode()


def observations():
    base = {
        "report_type": "scan_http_vulnerable",
        "severity": "critical",
        "http_code": "200",
        "hostname": "mail.example.com",
        "ip": "1.1.1.1",
        "tag": "eol-php",
        "version": "7.3.25",
        "region": "North Carolina",
        "timestamp": "2026-11-04 01:02:03",
        "protocol": "tcp",
        "port": "443",
        "asn": "15169",
        "city": "Charlotte",
        "geo": "US",
        "unknown_extension": "KEEP THIS FIELD",
        "empty_extension": "",
    }
    return [
        base,
        {**base, "ip": "10.1.2.3"},
        {**base, "ip": "8.8.8.8"},
        {**base, "ip": "9.9.9.9"},
        {**base, "hostname": ""},
        {**base, "version": ""},
        {**base, "hostname": "brand_123.com"},
        {**base, "region": "Virginia"},
        {**base, "hostname": "example..org"},
    ]


@pytest.fixture
def app(tmp_path):
    fake = FakeRegistry()
    app = create_app(
        tmp_path / "data",
        worker=False,
        report_processes=False,
        attribution_factory=registry_factory(lambda: fake),
        capture=capture_website,
    )
    app.state.fake = fake
    # Sender belongs to Settings in 0.4.1, not the report draft.
    with app.state.store.transaction() as db:
        profile = app.state.store.settings()
        profile["analyst_name"] = "Test Analyst"
        db.execute("UPDATE settings SET value=? WHERE key=?", (json.dumps(profile), "profile"))
    return app


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        client.headers["X-Workbench-Token"] = client.get("/api/bootstrap").json()["token"]
        yield client


def import_rows(client, app, rows=None, name="report.csv", *, start_notifications=True):
    body = csv_bytes(rows or observations())
    response = client.post("/api/imports", files=[("files", (name, body, "text/csv"))])
    assert response.status_code == 200, response.text
    record = response.json()[0]
    app.state.intake.process(record["id"])
    if start_notifications:
        # Legacy workflow fixtures explicitly open work; production intake does not.
        from modules.investigations.components.cases import Cases

        cases = Cases(app.state.store)
        for entity in app.state.store.all("SELECT id FROM leads WHERE merged_into IS NULL"):
            if cases.default_id(entity["id"]) is None:
                cases.create(entity["id"])
    return record, body


def attach(client, lead_id, kind="website"):
    stream = io.BytesIO()
    Image.new("RGB", (600, 300), "white").save(stream, "PNG")
    response = client.post(
        f"/api/leads/{lead_id}/evidence",
        data={
            "kind": kind,
            "caption": "Test screenshot",
            "source_url": "https://example.com/contact",
            "captured_at": now(),
        },
        files={"file": ("evidence.png", stream.getvalue(), "image/png")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def resolve_observation_scope(client, lead):
    """Model the analyst's explicit anomaly decision in certification fixtures."""
    lead = client.get("/api/cases/" + lead["case_id"]).json()
    ids = [
        row["entry_id"]
        for row in lead.get("observation_scope", {}).get("rows", [])
        if row.get("requires_review")
    ]
    if ids:
        response = client.post(
            "/api/cases/" + lead["case_id"] + "/observation-scope",
            json={
                "expected_version": lead["case"]["version"],
                "expected_revision": lead["draft_revision"],
                "entry_ids": ids,
                "decision": "exclude",
                "reason": "Synthetic analyst review: nonpublic source rows retained internally, excluded from recipient notification.",
                "reopen_affected": True,
            },
        )
        assert response.status_code == 200, response.text
        lead = response.json()
    return lead


def validate_sections(client, lead):
    """Explicitly review each current section before report certification."""
    lead = resolve_observation_scope(client, lead)
    for key in ("introduction", "vulnerabilities", "attribution", "information", "closing"):
        review = next(item for item in lead["section_reviews"] if item["key"] == key)
        assert review["status"] != "stale", f"{key} requires an explicit reasoned reopen"
        if review["status"] == "draft":
            assert review["can_validate"], review["issues"]
            result = client.post(
                "/api/cases/" + lead["case_id"] + "/sections/" + key + "/validate",
                json={"expected_revision": lead["draft_revision"]},
            )
            assert result.status_code == 200, result.text
            lead = result.json()
        reviewed = next(item for item in lead["section_reviews"] if item["key"] == key)
        assert reviewed["status"] == "validated"
        assert reviewed["validated_at"] and reviewed["validated_by"]
    return lead


def reopen_sections(client, lead, reason, keys=None):
    """Tests must name why a frozen section is being reopened."""
    assert reason.strip()
    lead = client.get("/api/cases/" + lead["case_id"]).json()
    keys = keys or ("introduction", "vulnerabilities", "attribution", "information", "closing")
    for key in keys:
        review = next(item for item in lead["section_reviews"] if item["key"] == key)
        if review["status"] == "draft":
            continue
        result = client.post(
            "/api/cases/" + lead["case_id"] + "/sections/" + key + "/reopen",
            json={"expected_revision": lead["draft_revision"], "reason": reason},
        )
        assert result.status_code == 200, result.text
        lead = result.json()
        assert (
            next(item for item in lead["section_reviews"] if item["key"] == key)["status"]
            == "draft"
        )
    return lead


def ready(client, lead_id, *, validate=True):
    profile = client.get("/api/bootstrap").json()["settings"]
    profile["analyst_name"] = "Test Analyst"
    assert client.put("/api/settings", json=profile).status_code == 200
    lead = client.get("/api/leads/" + lead_id).json()
    if not lead.get("case_id"):
        opened = client.post("/api/leads/" + lead_id + "/start")
        assert opened.status_code == 200, opened.text
        lead = opened.json()
    assert (
        client.put(
            "/api/entities/" + lead_id + "/name",
            json={"name": "Example Company", "expected_revision": lead["entity_revision"]},
        ).status_code
        == 200
    )
    lead = client.get("/api/leads/" + lead_id).json()
    changed = client.post(
        "/api/cases/" + lead["case_id"] + "/entity-details",
        json={"expected_version": lead["case"]["version"]},
    )
    assert changed.status_code == 200, changed.text
    lead = changed.json()
    if not lead["evidence"]:
        lead = attach(client, lead_id)
    d = lead["draft"]
    d.update(
        company="Example Company",
        contact_name="Technology Team",
        sender_name="Test Analyst",
        website_verified=True,
        reviewed=True,
    )
    r = client.put(
        f"/api/leads/{lead_id}/draft",
        json={"expected_revision": lead["draft_revision"], "fields": d},
    )
    assert r.status_code == 200, r.text
    return validate_sections(client, r.json()) if validate else r.json()
