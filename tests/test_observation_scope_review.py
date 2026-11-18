"""Adversarial recipient-scope review, source retention and immutable history."""

from copy import deepcopy
import json

import pytest

from test_workbench import app, client, import_rows, observations, ready, validate_sections
from workbench.observation_scope import (
    address_issue,
    apply_scope,
    legacy_scope_warning,
    scope_checks,
    validate_saved_scope,
)
from workbench.report_snapshot import snapshot


def opened(client, app, rows=None):
    import_rows(client, app, rows)
    return client.get("/api/cases/" + client.get("/api/cases").json()[0]["id"]).json()


def change(client, lead, ids, decision="exclude", **extra):
    return client.post(
        "/api/cases/" + lead["case_id"] + "/observation-scope",
        json={
            "expected_version": lead["case"]["version"],
            "expected_revision": lead["draft_revision"],
            "entry_ids": ids,
            "decision": decision,
            "reason": "Synthetic analyst review: source observation does not belong in this notification.",
            **extra,
        },
    )


@pytest.mark.parametrize(
    "ip",
    [
        "10.1.2.3",
        "127.0.0.1",
        "100.64.0.1",
        "192.0.2.1",
        "224.0.0.1",
        "::1",
        "fc00::1",
        "fe80::1",
        "2001:db8::1",
        "::ffff:10.1.2.3",
        "fe80::1%eth0",
        "bad",
        "",
    ],
)
def test_address_anomalies_cannot_be_claimed_as_public(ip):
    assert address_issue({"ip": ip})


@pytest.mark.parametrize("ip", ["1.1.1.1", "8.8.8.8", "2606:4700:4700::1111", "::ffff:8.8.8.8"])
def test_supported_public_addresses(ip):
    assert not address_issue({"ip": ip})


@pytest.mark.parametrize(
    "stage,action",
    [
        (
            "pending_notification",
            "Revise this report, review its scope, and recertify before further outreach.",
        ),
        (
            "notification_completed",
            "Start a new notification and review its scope before further outreach.",
        ),
        ("closed", "Start a new notification and review its scope before further outreach."),
    ],
)
def test_certified_scope_warning_names_the_available_next_action(stage, action):
    lead = {
        "case": {"stage": stage, "certified_report_id": "saved"},
        "entries": [{"ip": "10.1.2.3"}],
    }
    assert legacy_scope_warning(lead)["message"] == (
        "This certified report retains 1 nonpublic or invalid source observation(s): 10.1.2.3. "
        + action
        + " Its original certified files and recorded delivery history remain unchanged."
    )
    lead["case"]["stage"] = "in_progress"
    assert legacy_scope_warning(lead) is None


def test_supporting_attribution_alone_does_not_create_a_notifiable_finding():
    lead = apply_scope(
        {
            "entries": [
                {
                    "id": "proof",
                    "ip": "8.8.8.8",
                    "normalized": {"case_condition_scope": True, "active_conditions": []},
                }
            ]
        }
    )
    assert lead["observation_scope"]["included"] == 1
    assert lead["observation_scope"]["finding_observations"] == 0
    assert not next(
        row for row in scope_checks(lead) if row["key"] == "observation_scope_nonempty"
    )["ok"]


def test_private_row_blocks_freeze_then_exclusion_retains_source_and_survives_save(client, app):
    lead = opened(client, app)
    private = next(row for row in lead["observation_scope"]["rows"] if row["requires_review"])
    source_before = app.state.store.all("SELECT id,payload FROM entries ORDER BY id")
    check = next(row for row in lead["readiness"] if row["key"] == "observation_scope")
    assert not check["ok"]
    blocked = client.post(
        "/api/cases/" + lead["case_id"] + "/sections/introduction/validate",
        json={"expected_revision": lead["draft_revision"]},
    )
    assert blocked.status_code == 422 and "nonpublic" in blocked.text
    saved = change(client, lead, [private["entry_id"]])
    assert saved.status_code == 200, saved.text
    scoped = saved.json()
    assert scoped["observation_scope"]["included"] == 3
    assert scoped["observation_scope"]["excluded"] == 1
    assert scoped["observation_scope"]["unresolved"] == 0
    listed = next(row for row in client.get("/api/cases").json() if row["id"] == lead["case_id"])
    assert (listed["observations"], listed["assets"], listed["source_observations"]) == (3, 3, 4)
    assert len(scoped["scope_source_entries"]) == 4
    assert "10.1.2.3" not in scoped["draft"]["narrative"]
    assert source_before == app.state.store.all("SELECT id,payload FROM entries ORDER BY id")
    data = snapshot(app.state.store, scoped["id"], scoped["case_id"], capture_sections=())
    assert {asset["ip"] for asset in data["assets"]} == {"1.1.1.1", "8.8.8.8", "9.9.9.9"}
    assert "10.1.2.3" not in json.dumps(data["composition"])
    assert "10.1.2.3" in json.dumps(data["scope_source_entries"])
    assert data["draft"]["observation_scope"][private["entry_id"]]["actor"] == "Test Analyst"
    response = client.put(
        "/api/leads/" + scoped["id"] + "/draft",
        params={"case_id": scoped["case_id"]},
        json={"expected_revision": scoped["draft_revision"], "fields": scoped["draft"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["observation_scope"]["excluded"] == 1
    assert change(client, lead, [private["entry_id"]]).status_code == 422
    assert change(client, response.json(), [private["entry_id"]], "include").status_code == 422


def test_decisions_cannot_be_forged_through_draft_or_other_case(client, app):
    lead = opened(client, app, [observations()[2]])
    assert change(client, lead, ["foreign-observation"]).status_code == 422
    assert change(client, lead, [lead["entries"][0]["id"]], reason="  ").status_code == 422
    draft = deepcopy(lead["draft"])
    draft["observation_scope"] = {
        lead["entries"][0]["id"]: {"decision": "exclude", "reason": "forged"}
    }
    result = client.put(
        "/api/leads/" + lead["id"] + "/draft",
        json={"expected_revision": lead["draft_revision"], "fields": draft},
    )
    assert result.status_code == 422 and "read-only" in result.text
    with pytest.raises(ValueError, match="outside"):
        validate_saved_scope({"observation_scope": {"foreign": {}}}, {"local"})


def test_excluded_attribution_anchor_is_proof_only_not_a_reported_asset(client, app):
    lead = opened(client, app, [observations()[0], observations()[2]])
    anchor = lead["attribution_entry_id"]
    saved = change(client, lead, [anchor])
    assert saved.status_code == 200, saved.text
    scoped = saved.json()
    assert [entry["ip"] for entry in scoped["entries"]] == ["1.1.1.1"]
    data = snapshot(app.state.store, scoped["id"], scoped["case_id"], capture_sections=())
    assert [asset["ip"] for asset in data["assets"]] == ["1.1.1.1"]
    group = data["qualified_lead"]["validated_leads"][0]
    assert group["supporting_observation"]["id"] == anchor
    assert all(entry["id"] != anchor for entry in group["entries"])
    assert next(row for row in scoped["readiness"] if row["key"] == "attribution_exhibit")["ok"]


def test_attribution_support_row_remains_proof_without_becoming_a_new_reported_asset(client, app):
    lead = opened(client, app, [observations()[0], observations()[2]])
    anchor = lead["attribution_entry_id"]
    with app.state.store.transaction() as db:
        db.execute(
            "INSERT OR REPLACE INTO case_entry_conditions VALUES(?,?,?)",
            (lead["case_id"], anchor, "[]"),
        )
    scoped = client.get("/api/cases/" + lead["case_id"]).json()
    assert scoped["observation_scope"]["included"] == 2
    assert scoped["observation_scope"]["finding_observations"] == 1
    listed = next(row for row in client.get("/api/cases").json() if row["id"] == lead["case_id"])
    assert (listed["assets"], listed["observations"], listed["included_source_observations"]) == (
        1,
        1,
        2,
    )
    data = snapshot(app.state.store, scoped["id"], scoped["case_id"], capture_sections=())
    assert [asset["ip"] for asset in data["assets"]] == ["1.1.1.1"]
    group = data["qualified_lead"]["validated_leads"][0]
    assert group["supporting_observation"]["id"] == anchor
    assert [entry["ip"] for entry in group["entries"]] == ["1.1.1.1"]
    assert len(data["scope_source_entries"]) == 2
    recipient_rows = [
        entry for entry in data["composition"]["appendix"]["entries"] if entry["partition"] == "A"
    ]
    assert "8.8.8.8" not in json.dumps(recipient_rows)
    assert next(row for row in scoped["readiness"] if row["key"] == "attribution_exhibit")["ok"]


def test_shared_ip_rows_are_independent_and_all_excluded_can_close_without_notification(
    client, app
):
    base = observations()[2]
    lead = opened(
        client,
        app,
        [base, {**base, "hostname": "other.example.com", "timestamp": "2026-11-05 01:02:03"}],
    )
    one = change(client, lead, [lead["entries"][0]["id"]]).json()
    assert len(one["entries"]) == 1 and one["entries"][0]["ip"] == "8.8.8.8"
    empty = change(client, one, [one["entries"][0]["id"]])
    assert empty.status_code == 200, empty.text
    empty = empty.json()
    assert empty["entries"] == []
    assert not next(
        row for row in empty["readiness"] if row["key"] == "observation_scope_nonempty"
    )["ok"]
    assert client.post("/api/leads/" + empty["id"] + "/finalize").status_code == 422
    closed = client.post(
        "/api/cases/" + empty["case_id"] + "/close",
        json={
            "expected_version": empty["case"]["version"],
            "disposition": "out_of_scope",
            "conclusion": "Synthetic exercise: all source observations excluded after review.",
            "closed_by": "Test Analyst",
            "reviewed": True,
        },
    )
    assert closed.status_code == 200, closed.text
    current = client.get("/api/cases/" + empty["case_id"]).json()
    assert change(client, current, [lead["entries"][0]["id"]], "include").status_code == 422


def test_scope_change_reopens_only_changed_locks_and_preserves_old_reviews(client, app):
    lead = opened(client, app, [observations()[0], observations()[2]])
    lead = ready(client, lead["id"])
    locked = {row["key"]: row["validation_id"] for row in lead["section_reviews"]}
    selected = next(entry["id"] for entry in lead["entries"] if entry["ip"] == "1.1.1.1")
    denied = change(client, lead, [selected])
    assert denied.status_code == 422 and "reopening" in denied.text
    unchanged = client.get("/api/cases/" + lead["case_id"]).json()
    assert unchanged["draft_revision"] == lead["draft_revision"]
    response = change(client, lead, [selected], reopen_affected=True)
    assert response.status_code == 200, response.text
    updated = response.json()
    reopened = set(updated["scope_reopened_sections"])
    assert {"introduction", "vulnerabilities"} <= reopened
    assert "closing" not in reopened
    for row in updated["section_reviews"]:
        assert row["status"] == ("draft" if row["key"] in reopened else "validated")
        if row["key"] not in reopened:
            assert row["validation_id"] == locked[row["key"]]
    assert len(app.state.store.all("SELECT id FROM section_validations")) == 5
    assert any(
        event["reason"].startswith("Observation scope: ") for event in updated["section_history"]
    )


def test_excluding_last_cve_row_restores_exact_pinned_selection_without_fetch(
    client, app, monkeypatch
):
    rows = [
        {**observations()[2], "tag": "CVE-2099-10001", "hostname": "mail.example.com"},
        {**observations()[2], "tag": "CVE-2099-10002", "hostname": "vpn.example.com"},
    ]
    lead = opened(client, app, rows)
    from test_notification_narrative import inputs

    reference = inputs()[1]["cve_records"][0]
    original = deepcopy(reference)
    original.update(id="CVE-2099-10001", source="Synthetic pinned source")
    other = deepcopy(reference)
    other.update(id="CVE-2099-10002")
    draft = deepcopy(lead["draft"])
    draft["cve_records"] = [original, other]
    with app.state.store.transaction() as db:
        db.execute("UPDATE cases SET draft=? WHERE id=?", (json.dumps(draft), lead["case_id"]))
    lead = client.get("/api/cases/" + lead["case_id"]).json()
    entry = next(entry for entry in lead["entries"] if "10001" in entry["source"]["fields"]["tag"])
    monkeypatch.setattr(
        "workbench.intelligence.acquisition._response_get",
        lambda *args, **kwargs: pytest.fail("Scope changes fetched external intelligence"),
    )
    excluded = change(client, lead, [entry["id"]])
    assert excluded.status_code == 200, excluded.text
    excluded = excluded.json()
    assert [record["id"] for record in excluded["draft"]["cve_records"]] == ["CVE-2099-10002"]
    assert "CVE-2099-10001" not in excluded["draft"]["narrative"]
    assert (
        excluded["draft"]["observation_scope_archive"]["cve_records"]["CVE-2099-10001"] == original
    )
    restored = change(client, excluded, [entry["id"]], "include")
    assert restored.status_code == 200, restored.text
    restored = restored.json()
    assert (
        next(
            record
            for record in restored["draft"]["cve_records"]
            if record["id"] == "CVE-2099-10001"
        )
        == original
    )


def test_certified_scope_is_immutable_and_excluded_observation_not_marked_notified(client, app):
    lead = opened(client, app)
    lead = ready(client, lead["id"])
    result = client.post("/api/leads/" + lead["id"] + "/finalize")
    assert result.status_code == 200, result.text
    report = result.json()
    lead = client.get("/api/cases/" + lead["case_id"]).json()
    assert change(client, lead, [lead["entries"][0]["id"]]).status_code == 422
    from test_cases import attempt

    response = client.post(
        "/api/cases/" + lead["case_id"] + "/attempts", json=attempt(lead, report)
    )
    assert response.status_code == 200, response.text
    delivered = client.get("/api/cases/" + lead["case_id"]).json()
    assert change(client, delivered, [lead["entries"][0]["id"]]).status_code == 422
    assert all(
        item["ip"] != "10.1.2.3" or not item["notifications"]
        for item in delivered["finding_history"]["items"]
    )
    before = (app.state.store.path(report["path"]) / "notification.pdf").read_bytes()
    import_rows(client, app, name="same-source.csv")
    assert before == (app.state.store.path(report["path"]) / "notification.pdf").read_bytes()
    from workbench.store import Store
    from workbench.cases import Cases

    reopened = Cases(Store(app.state.store.root)).view(lead["case_id"])
    assert reopened["observation_scope"]["excluded"] == 1


def test_legacy_certified_anomaly_blocks_new_outreach_until_revised_without_rewriting_history(
    client, app, monkeypatch
):
    lead = opened(client, app)
    lead = ready(client, lead["id"], validate=False)
    # Simulate the earlier release's certification behavior. The new gate is
    # restored before reading or preparing outreach from this historical packet.
    with monkeypatch.context() as earlier_release:
        earlier_release.setattr(
            "workbench.observation_scope.scope_checks",
            lambda lead: [
                {"key": key, "label": "Earlier release review", "ok": True}
                for key in ("observation_scope", "observation_scope_nonempty")
            ],
        )
        for key in ("introduction", "vulnerabilities", "attribution", "information", "closing"):
            response = client.post(
                f"/api/cases/{lead['case_id']}/sections/{key}/validate",
                json={"expected_revision": lead["draft_revision"]},
            )
            assert response.status_code == 200, response.text
            lead = response.json()
        result = client.post("/api/leads/" + lead["id"] + "/finalize")
        assert result.status_code == 200, result.text
    folder = app.state.store.path(result.json()["path"])
    files = {path.name: path.read_bytes() for path in folder.iterdir() if path.is_file()}
    current = client.get("/api/cases/" + lead["case_id"]).json()
    assert current["scope_warning"]["count"] == 1
    assert current["scope_warning"]["addresses"] == ["10.1.2.3"]
    assert all(row["ok"] for row in current["readiness"])
    handoff = client.get(f"/api/cases/{lead['case_id']}/outreach-handoff")
    assert handoff.status_code == 200, handoff.text
    assert handoff.json()["scope_warning"] == current["scope_warning"]
    assert current["scope_warning"]["message"] in handoff.json()["warnings"]
    assert not handoff.json()["ready"] and not handoff.json()["copy_allowed"]
    assert current["scope_warning"]["message"] in handoff.json()["blockers"]
    assert current["scope_warning"]["message"] in handoff.json()["copy_blockers"]
    assert files == {path.name: path.read_bytes() for path in folder.iterdir() if path.is_file()}
    revised = client.post(
        f"/api/cases/{lead['case_id']}/revise",
        json={
            "expected_version": current["case"]["version"],
            "reason": "Exclude retained nonpublic address before new outreach.",
        },
    )
    assert revised.status_code == 200, revised.text
    current = client.get("/api/cases/" + lead["case_id"]).json()
    private = next(row for row in current["observation_scope"]["rows"] if row["requires_review"])
    excluded = change(client, current, [private["entry_id"]], reopen_affected=True)
    assert excluded.status_code == 200, excluded.text
    validate_sections(client, excluded.json())
    replacement = client.post("/api/leads/" + lead["id"] + "/finalize")
    assert replacement.status_code == 200, replacement.text
    handoff = client.get(f"/api/cases/{lead['case_id']}/outreach-handoff").json()
    assert handoff["scope_warning"] is None
    assert not any("nonpublic" in value for value in handoff["copy_blockers"])
    assert handoff["report"]["id"] == replacement.json()["id"]
    from test_cases import attempt, closing_values

    current = client.get("/api/cases/" + lead["case_id"]).json()
    delivered = client.post(
        f"/api/cases/{lead['case_id']}/attempts", json=attempt(current, replacement.json())
    )
    assert delivered.status_code == 200, delivered.text
    closed = client.post(
        f"/api/cases/{lead['case_id']}/close", json=closing_values(delivered.json())
    )
    assert closed.status_code == 200, closed.text
    current = client.get("/api/cases/" + lead["case_id"]).json()
    assert current["case"]["stage"] == "closed" and current["case"]["delivered_at"]
    assert len(current["reports"]) == 2 and len(current["attempts"]) == 1
    assert files == {path.name: path.read_bytes() for path in folder.iterdir() if path.is_file()}


def test_scope_backup_restore_retains_decisions_and_original_rows(client, app, tmp_path):
    from workbench.cases import Cases
    from workbench.store import Store
    from workbench.workspace_data import WorkspaceData, apply_pending_workspace, export_workspace

    lead = opened(client, app)
    private = next(row for row in lead["observation_scope"]["rows"] if row["requires_review"])
    saved = change(client, lead, [private["entry_id"]]).json()
    rows = app.state.store.all("SELECT id,payload FROM entries ORDER BY id")
    archive = export_workspace(app.state.store)
    try:
        destination = Store(tmp_path / "restored-scope")
        assert WorkspaceData(app, destination).stage("import", archive)["pending"] == "import"
        apply_pending_workspace(destination.root)
        restored = Store(destination.root)
        current = Cases(restored).view(lead["case_id"])
        assert current["draft"]["observation_scope"] == saved["draft"]["observation_scope"]
        assert current["observation_scope"]["excluded"] == 1
        assert len(current["scope_source_entries"]) == 4
        assert restored.all("SELECT id,payload FROM entries ORDER BY id") == rows
        assert restored.all("PRAGMA foreign_key_check") == []
    finally:
        archive.unlink(missing_ok=True)


@pytest.mark.parametrize(
    "archive",
    [
        [],
        {"unknown": {}},
        {"cve_records": {"CVE-1": {"id": "CVE-2"}}},
        {"selected_ssvc_assessments": {"CVE-1": []}},
    ],
)
def test_scope_archive_validation_rejects_corrupt_restored_metadata(archive):
    with pytest.raises(ValueError, match="scope source"):
        validate_saved_scope({"observation_scope_archive": archive}, set())
