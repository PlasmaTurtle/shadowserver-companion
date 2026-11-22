"""v0.7 API regression boundaries: pinned records, presentation, and jobs."""

from tests.support.qualification import registry_factory, capture_website

from copy import deepcopy
import threading
import time

import pytest
from tests.session_helpers import TestClient

from modules.workspace.components import api as api_module
from modules.library.components.cve_sources import SourceCancelled
from modules.library.components.intelligence_index import bank_index, flags
from modules.workspace.components.primitives import now, dump
from tests.support.workbench import (
    FakeRegistry,
    import_rows,
    observations,
    ready,
    reopen_sections,
    validate_sections,
)

ID = "CVE-2025-12345"
OTHER = "CVE-2025-98765"


def source_record(
    identifier=ID, revision="one", state="published", captured_at="2026-11-07T10:00:00Z"
):
    stamp = captured_at
    return {
        "id": identifier,
        "state": state.upper(),
        "verification_status": state,
        "description": "Synthetic published source wording." if state == "published" else "",
        "source": "CVE Program",
        "cvss": 9.8 if state == "published" else None,
        "cvss_assessments": [],
        "epss": 0,
        "epss_percentile": 0,
        "epss_date": "2026-11-06",
        "kev": True,
        "revision_id": revision,
        "intelligence_revision_id": "intelligence-" + revision,
        "retrieved_at": stamp,
        "public_url": "https://www.cve.org/CVERecord?id=" + identifier,
        "sources": [
            {
                "publisher": "CVE Program",
                "url": "https://cveawg.mitre.org/api/cve/" + identifier,
                "public_url": "https://www.cve.org/CVERecord?id=" + identifier,
                "retrieved_at": stamp,
                "revision_id": revision,
            }
        ],
        "ssvc_assessments": [
            {
                "id": "ssvc-" + identifier + "-" + revision,
                "publisher": "CISA-ADP",
                "assessed_at": "2026-11-06T08:00:00Z",
                "exploitation": "active",
                "label": "Active exploitation reported",
                "source_revision_id": revision,
            }
        ],
        "ransomware": {"status": "known", "raw": "Known", "label": "Known ransomware use"},
        "errors": [],
    }


@pytest.fixture
def app(tmp_path, monkeypatch):
    from modules.library.components.intelligence import acquisition

    monkeypatch.setattr(acquisition, "_wait_for_nvd", lambda store: None)
    control = {"record": source_record(), "block": False, "entered": threading.Event(), "calls": []}

    def fetch(store, identifier, *, refresh=False, cancel_event=None):
        control["calls"].append(identifier)
        control["entered"].set()
        if control["block"]:
            if cancel_event is not None and cancel_event.wait(3):
                raise SourceCancelled("Cancelled during the synthetic provider boundary")
        result = deepcopy(control["record"])
        result["id"] = identifier
        return result

    monkeypatch.setattr(api_module, "enrich", fetch)
    registry = FakeRegistry()
    result = api_module.create_app(
        tmp_path / "data",
        worker=False,
        attribution_factory=registry_factory(lambda: registry),
        capture=capture_website,
    )
    result.state.fake = registry

    result.state.source_control = control
    with result.state.store.transaction() as db:
        settings = result.state.store.settings()
        settings["analyst_name"] = "Test Analyst"
        db.execute("UPDATE settings SET value=? WHERE key=?", (dump(settings), "profile"))
    return result


@pytest.fixture
def client(app):
    with TestClient(app) as value:
        value.headers["X-Workbench-Token"] = value.get("/api/bootstrap").json()["token"]
        yield value


def lead_with_cve(client, app, identifier=ID):
    row = {**observations()[0], "ip": "8.8.8.8", "tag": identifier}
    import_rows(client, app, [row])
    return client.get("/api/leads/" + client.get("/api/leads").json()[0]["id"]).json()


def save(client, lead, fields):
    return client.put(
        "/api/leads/" + lead["id"] + "/draft?case_id=" + lead["case_id"],
        json={"expected_revision": lead["draft_revision"], "fields": fields},
    )


def adopt_source(client, app, lead, record):
    app.state.source_control["record"] = record
    response = client.post("/api/cves/" + record["id"] + "/retrieve")
    assert response.status_code == 200, response.text
    fields = deepcopy(lead["draft"])
    fields["cve_records"] = [response.json()]
    result = save(client, lead, fields)
    assert result.status_code == 200, result.text
    return result.json()


def poll_job(client, identifier):
    until = time.monotonic() + 3
    while time.monotonic() < until:
        response = client.get("/api/source-jobs/" + identifier)
        assert response.status_code == 200, response.text
        job = response.json()
        if job["status"] not in ("running", "queued"):
            return job
        time.sleep(0.01)
    pytest.fail("Synthetic source job did not complete promptly")


def test_settings_preserve_explicit_appearance_for_legacy_payload(client):
    profile = client.get("/api/bootstrap").json()["settings"]
    profile["appearance"] = "dark"
    profile["brand_profile"] = "usss"
    assert client.put("/api/settings", json=profile).status_code == 200
    legacy = {
        key: value
        for key, value in profile.items()
        if key not in ("appearance", "brand_profile", "brand_profile_version")
    }
    legacy["sheet"] = "Data"
    assert client.put("/api/settings", json=legacy).status_code == 200
    bootstrap = client.get("/api/bootstrap").json()
    assert bootstrap["settings"]["appearance"] == "dark"
    assert bootstrap["settings"]["brand_profile"] == "usss"
    assert bootstrap["presentation"]["handling_policy"]["label"] == "TLP:AMBER"


def test_appearance_and_workspace_brand_do_not_rewrite_frozen_document(client, app):
    import_rows(client, app)
    lead = ready(client, client.get("/api/leads").json()[0]["id"])
    before = {r["key"]: (r["content_hash"], r["validation_id"]) for r in lead["section_reviews"]}
    policy = deepcopy(lead["draft"]["document_policy"])
    settings = client.get("/api/bootstrap").json()["settings"]
    settings.update(appearance="dark", brand_profile="usss")
    assert client.put("/api/settings", json=settings).status_code == 200
    after = client.get("/api/cases/" + lead["case_id"]).json()
    assert after["draft"]["document_policy"] == policy
    assert after["presentation_update_available"] is True
    assert all(r["status"] == "validated" for r in after["section_reviews"])
    assert {
        r["key"]: (r["content_hash"], r["validation_id"]) for r in after["section_reviews"]
    } == before


def test_document_profile_adoption_requires_reason_reopen_and_current_revision(client, app):
    import_rows(client, app)
    lead = ready(client, client.get("/api/leads").json()[0]["id"])
    settings = client.get("/api/bootstrap").json()["settings"]
    settings["brand_profile"] = "usss"
    assert client.put("/api/settings", json=settings).status_code == 200
    url = "/api/cases/" + lead["case_id"] + "/presentation/adopt"
    assert (
        client.post(
            url, json={"expected_revision": lead["draft_revision"], "reason": " "}
        ).status_code
        == 422
    )
    blocked = client.post(
        url, json={"expected_revision": lead["draft_revision"], "reason": "Adopt agency palette"}
    )
    assert blocked.status_code == 422 and "Reopen" in blocked.text
    opened = reopen_sections(client, lead, "Adopt the USSS print palette")
    assert (
        client.post(
            url, json={"expected_revision": lead["draft_revision"], "reason": "Stale attempt"}
        ).status_code
        == 422
    )
    result = client.post(
        url,
        json={
            "expected_revision": opened["draft_revision"],
            "reason": "Adopt the USSS print palette",
        },
    )
    assert result.status_code == 200, result.text
    updated = result.json()
    assert updated["draft"]["document_policy"]["brand_profile"]["id"] == "usss"
    assert updated["draft"]["reviewed"] is False
    assert all(r["status"] == "draft" for r in updated["section_reviews"])
    assert updated["draft"]["document_policy"]["handling"]["label"] == "TLP:AMBER"
    events = app.state.store.all(
        "SELECT * FROM events WHERE case_id=? AND action='document_presentation_adopted'",
        (lead["case_id"],),
    )
    assert events


@pytest.mark.parametrize(
    "mutate",
    [
        lambda fields: fields["document_policy"]["handling"].update(label="TLP:CLEAR"),
        lambda fields: fields["document_policy"]["handling"].update(minimum_font_pt=1),
        lambda fields: fields["document_policy"]["brand_profile"]["palette"].update(ink="#ffffff"),
        lambda fields: fields.update(source_restrictions=["TLP:CLEAR"]),
    ],
)
def test_document_tlp_and_print_policy_cannot_be_forged(client, app, mutate):
    lead = lead_with_cve(client, app)
    fields = deepcopy(lead["draft"])
    mutate(fields)
    result = save(client, lead, fields)
    assert result.status_code == 422, result.text
    after = client.get("/api/cases/" + lead["case_id"]).json()
    assert after["draft_revision"] == lead["draft_revision"]
    assert after["draft"]["document_policy"]["handling"]["label"] == "TLP:AMBER"


def test_forged_record_metrics_or_source_url_rejected(client, app):
    lead = lead_with_cve(client, app)
    lead = adopt_source(client, app, lead, source_record())
    fields = deepcopy(lead["draft"])
    fields["cve_records"][0]["epss"] = 0.99
    result = save(client, lead, fields)
    assert result.status_code == 422 and "read-only" in result.text
    fields = deepcopy(lead["draft"])
    fields["cve_records"][0]["sources"][0]["url"] = "javascript:alert(1)"
    assert save(client, lead, fields).status_code == 422


def test_source_job_retrieval_does_not_adopt_or_revise_case(client, app):
    lead = lead_with_cve(client, app)
    before = app.state.store.one(
        "SELECT draft,draft_revision FROM cases WHERE id=?", (lead["case_id"],)
    )
    started = client.post("/api/source-jobs", json={"cve_ids": [ID]})
    assert started.status_code == 200
    job = poll_job(client, started.json()["id"])
    assert job["status"] == "completed" and job["completed"] == 1 and len(job["results"]) == 1
    assert (
        app.state.store.one("SELECT draft,draft_revision FROM cases WHERE id=?", (lead["case_id"],))
        == before
    )
    # Polling captures a selectable immutable value, but the analyst must adopt it.
    fields = deepcopy(lead["draft"])
    fields["cve_records"] = job["results"]
    adopted = save(client, lead, fields)
    assert adopted.status_code == 200, adopted.text
    assert adopted.json()["draft"]["cve_records"][0]["revision_id"] == "one"
    assert adopted.json()["draft"]["reviewed"] is False


def test_source_job_cancel_keeps_case_unchanged(client, app):
    lead = lead_with_cve(client, app)
    before = app.state.store.one(
        "SELECT draft,draft_revision FROM cases WHERE id=?", (lead["case_id"],)
    )
    control = app.state.source_control
    control["block"] = True
    start = client.post("/api/source-jobs", json={"cve_ids": [ID, OTHER]}).json()
    assert control["entered"].wait(1)
    cancel = client.post("/api/source-jobs/" + start["id"] + "/cancel")
    assert cancel.status_code == 200
    job = poll_job(client, start["id"])
    assert job["status"] == "cancelled"
    assert len(control["calls"]) == 1
    assert (
        app.state.store.one("SELECT draft,draft_revision FROM cases WHERE id=?", (lead["case_id"],))
        == before
    )


def test_source_job_rejects_bad_id_and_requires_session(client):
    for bad in ("CVE-2025-12345 extra", "cve-2025-12345", "javascript:alert(1)"):
        assert client.post("/api/source-jobs", json={"cve_ids": [bad]}).status_code == 422
    assert (
        client.post(
            "/api/source-jobs", json={"cve_ids": [ID]}, headers={"X-Workbench-Token": "bad"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/source-jobs", json={"cve_ids": [ID]}, headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )


def test_case_ssvc_selection_must_belong_to_pinned_revision(client, app):
    lead = lead_with_cve(client, app)
    lead = adopt_source(client, app, lead, source_record(revision="one"))
    app.state.source_control["record"] = source_record(revision="two")
    latest = client.post("/api/cves/" + ID + "/retrieve").json()
    fields = deepcopy(lead["draft"])
    fields["selected_ssvc_assessments"] = {ID: latest["ssvc_assessments"][0]["id"]}
    result = save(client, lead, fields)
    assert result.status_code == 422 and "pinned" in result.text
    fields["selected_ssvc_assessments"] = {
        ID: fields["cve_records"][0]["ssvc_assessments"][0]["id"]
    }
    result = save(client, lead, fields)
    assert result.status_code == 200, result.text
    assert result.json()["draft"]["cve_records"][0]["revision_id"] == "one"


def test_other_case_cve_record_and_assessment_cannot_be_injected(client, app):
    rows = [
        {**observations()[0], "ip": "8.8.8.8", "tag": ID},
        {**observations()[0], "hostname": "unrelated.com", "ip": "1.1.1.1", "tag": OTHER},
    ]
    import_rows(client, app, rows)
    leads = client.get("/api/leads").json()
    first = client.get(
        "/api/leads/"
        + next(lead_item["id"] for lead_item in leads if lead_item["domain"] == "example.com")
    ).json()
    second = client.get(
        "/api/leads/"
        + next(lead_item["id"] for lead_item in leads if lead_item["domain"] == "unrelated.com")
    ).json()
    first = adopt_source(client, app, first, source_record(ID))
    second = adopt_source(client, app, second, source_record(OTHER))
    fields = deepcopy(first["draft"])
    fields["cve_records"].extend(second["draft"]["cve_records"])
    assert save(client, first, fields).status_code == 422
    fields = deepcopy(first["draft"])
    fields["selected_ssvc_assessments"] = {
        OTHER: second["draft"]["cve_records"][0]["ssvc_assessments"][0]["id"]
    }
    assert save(client, first, fields).status_code == 422


@pytest.mark.parametrize("state", ["reserved", "rejected"])
def test_known_unpublished_record_cannot_be_omitted_to_enable_fallback(client, app, state):
    lead = lead_with_cve(client, app)
    lead = adopt_source(client, app, lead, source_record(state=state))
    fields = deepcopy(lead["draft"])
    fields["cve_records"] = []
    fields["cve_dispositions"] = {
        ID: {
            "action": "fallback",
            "reason": "Manual replacement",
            "description": "Claimed published wording",
            "publisher": "Example vendor",
            "source_url": "https://vendor.example/advisory",
            "retrieved_at": now(),
            "evidence_text": "Claimed evidence",
        }
    }
    result = save(client, lead, fields)
    assert result.status_code == 422 and "Reserved or rejected" in result.text


def test_fresh_authoritative_published_revision_can_replace_reserved_state(client, app):
    lead = lead_with_cve(client, app)
    lead = adopt_source(client, app, lead, source_record(state="reserved"))
    lead = adopt_source(
        client,
        app,
        lead,
        source_record(revision="published-later", captured_at="2026-11-07T11:00:00Z"),
    )
    assert lead["draft"]["cve_records"][0]["verification_status"] == "published"


def test_older_published_selection_cannot_reverse_newer_rejection(client, app):
    lead = lead_with_cve(client, app)
    old = source_record(revision="old-published", captured_at="2026-11-07T09:00:00Z")
    app.state.source_control["record"] = old
    old = client.post("/api/cves/" + ID + "/retrieve").json()
    lead = adopt_source(client, app, lead, source_record(state="rejected", revision="new-rejected"))
    fields = deepcopy(lead["draft"])
    fields["cve_records"] = [old]
    result = save(client, lead, fields)
    assert result.status_code == 422 and "captured after" in result.text


def test_state_history_prevents_two_step_omission_bypass(client, app):
    lead = lead_with_cve(client, app)
    lead = adopt_source(client, app, lead, source_record(state="rejected"))
    fields = deepcopy(lead["draft"])
    fields["cve_records"] = []
    omitted = save(client, lead, fields)
    assert omitted.status_code == 200, omitted.text
    lead = omitted.json()
    assert any(item["state"] == "rejected" for item in lead["draft"]["cve_state_history"])
    fields = deepcopy(lead["draft"])
    fields["cve_dispositions"] = {
        ID: {
            "action": "fallback",
            "reason": "Manual replacement",
            "description": "Claimed published wording",
            "publisher": "Example vendor",
            "source_url": "https://vendor.example/advisory",
            "retrieved_at": now(),
            "evidence_text": "Claimed evidence",
        }
    }
    result = save(client, lead, fields)
    assert result.status_code == 422 and "Reserved or rejected" in result.text


def test_browser_cannot_remove_server_pinned_state_history(client, app):
    lead = lead_with_cve(client, app)
    lead = adopt_source(client, app, lead, source_record(state="reserved"))
    fields = deepcopy(lead["draft"])
    fields["cve_state_history"] = []
    result = save(client, lead, fields)
    assert result.status_code == 422


def test_bank_index_retains_simultaneous_ransomware_and_kev_flags(app):
    store = app.state.store
    record = source_record()
    with store.transaction() as db:
        from modules.library.components.repositories.sources import SourceRepository

        SourceRepository.put(db, "intelligence-version:intelligence-one", record)
        db.execute(
            "INSERT INTO cache VALUES(?,?,?)",
            ("intelligence-latest:" + ID, dump({"revision_id": "intelligence-one"}), now()),
        )
    index = bank_index(store)
    assert index[ID]["ransomware"]["status"] == "known"
    assert flags(index.values())["ransomware_known"] is True
    assert flags(index.values())["kev"] is True
    assert flags([{"kev": None, "ransomware": {"status": "unknown"}}])["ransomware_known"] is None
