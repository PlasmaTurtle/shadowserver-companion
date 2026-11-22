"""Schedules preserve full-intake completion, catchup and workspace boundaries."""

from tests.support.qualification import capture_website, registry_factory

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import json
import threading
import xml.etree.ElementTree as ET

import pytest

from modules.workspace.components.store import Store
from modules.accretion.components.scheduling import (
    AcquisitionSchedule,
    DEFAULTS,
    checked,
    next_due,
    window,
)
from modules.accretion.components.windows_schedule import task_xml, task_name
from tests.support.workbench import app, client

from modules.accretion.tests.support.scheduling import (
    Acquisition,
    NOW,
    scheduler,
)


def test_download_is_not_success_until_full_intake_finishes(tmp_path):
    schedule, network, store = scheduler(tmp_path)
    schedule.tick()
    assert schedule.status()["run"]["status"] == "importing"
    assert schedule.status().get("last_success_at") is None
    assert len(network.calls) == 1
    schedule.tick()
    assert len(network.calls) == 1  # No overlapping retrieval while intake is pending.
    with store.transaction() as db:
        db.execute("UPDATE imports SET status='done'")
    schedule.tick()
    status = schedule.status()
    assert status["run"]["status"] == "complete"
    assert status["run"]["intake_completed"] == 1
    assert status["cursor"] == "2026-11-13"
    schedule.tick()
    assert len(network.calls) == 1


def test_failed_intake_does_not_advance_cursor(tmp_path):
    schedule, network, store = scheduler(tmp_path)
    schedule.tick()
    with store.transaction() as db:
        db.execute("UPDATE imports SET status='needs_retry'")
    schedule.tick()
    status = schedule.status()
    assert status["run"]["status"] == "partial"
    assert "cursor" not in status
    assert status["run"]["intake_failed"] == 1


def test_interrupted_run_resumes_import_completion_without_claiming_success(tmp_path):
    schedule, network, store = scheduler(tmp_path)
    state = schedule._read()
    state["run"] = {
        "id": "old",
        "status": "retrieving",
        "imports": [],
        "start": "2026-11-06",
        "end": "2026-11-13",
    }
    schedule._write(state)
    resumed = AcquisitionSchedule(store, network, schedule.catalog, clock=lambda: NOW)
    resumed.tick()
    assert resumed.status()["run"]["status"] == "failed"
    assert "cursor" not in resumed.status()
    assert not network.calls


def test_long_absence_is_chunked_without_skipping_dates_and_late_days_overlap():
    cfg = dict(DEFAULTS)
    assert window(cfg, {"cursor": "2026-08-01"}, date(2026, 11, 13)) == (
        date(2026, 8, 2),
        date(2026, 9, 1),
    )
    assert window(cfg, {"cursor": "2026-11-12"}, date(2026, 11, 13)) == (
        date(2026, 11, 7),
        date(2026, 11, 13),
    )
    assert next_due(cfg, NOW) == datetime(2026, 11, 13, 10, tzinfo=timezone.utc)


def test_unready_catalog_blocks_scheduled_qualification(tmp_path):
    schedule, network, store = scheduler(tmp_path)
    schedule.catalog = SimpleNamespace(status=lambda: {"bootstrap_complete": False})
    schedule.tick()
    assert not network.calls
    assert schedule.status()["run"]["status"] == "failed"
    assert "catalog" in schedule.status()["run"]["message"]


def test_manual_api_operation_prevents_scheduled_overlap(tmp_path):
    schedule, network, store = scheduler(tmp_path)
    network.active = True
    schedule.tick()
    assert not network.calls


def test_schedule_scope_change_resets_checkpoint(tmp_path):
    schedule, network, store = scheduler(tmp_path)
    state = schedule._read()
    state["cursor"] = "2026-11-12"
    schedule._write(state)
    schedule.configure({**state["config"], "report_types": ["scan_exchange"]})
    assert "cursor" not in schedule.status()


def test_task_xml_uses_current_user_without_secrets_or_privilege_escalation(tmp_path):
    root = tmp_path / "workspace & records"
    raw = task_xml(
        root,
        Path(r"C:\Program Files\Python\pythonw.exe"),
        tmp_path / "app" / "tools" / "run_scheduled.py",
        "S-1-5-21-123-456",
        current=NOW.replace(tzinfo=None),
    )
    tree = ET.fromstring(raw)
    ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    assert tree.find(".//t:LogonType", ns).text == "InteractiveToken"
    assert tree.find(".//t:RunLevel", ns).text == "LeastPrivilege"
    assert tree.find(".//t:StartWhenAvailable", ns).text == "true"
    assert tree.find(".//t:MultipleInstancesPolicy", ns).text == "IgnoreNew"
    assert "--data-dir" in tree.find(".//t:Arguments", ns).text
    assert task_name(root) != task_name(tmp_path / "other")
    assert "Password" not in raw.decode("utf-16")


def test_schedule_routes_and_sensitive_fields_are_rejected(client, app):
    response = client.put(
        "/api/schedule", json={**DEFAULTS, "enabled": True, "shadowserver": False}
    )
    assert response.status_code == 200
    assert client.get("/api/shadowserver/status").json()["schedule"]["config"]["enabled"]
    assert client.post("/api/schedule/run").status_code == 200
    bad = client.put("/api/schedule", json={**DEFAULTS, "api_key": "do-not-save"})
    assert bad.status_code == 422
    assert "do-not-save" not in app.state.store.db.read_bytes().decode(errors="ignore")


@pytest.mark.parametrize(
    "values",
    [
        {"hour": 24},
        {"interval_hours": 0},
        {"enabled": True},
        {"lookback_days": 90},
        {"reference": 1},
    ],
)
def test_invalid_schedule_settings(values):
    with pytest.raises(ValueError):
        checked(values)


def test_foreground_handoff_waits_for_workspace_lock_release(tmp_path):
    from modules.accretion.components.schedule_handoff import scheduled_ownership, request_handoff
    from modules.workspace.components.workspace_session import workspace_session
    import time

    root = tmp_path / "handoff"
    ready = threading.Event()
    stop = threading.Event()

    def owner():
        with workspace_session(root):
            with scheduled_ownership(root, stop):
                ready.set()
                assert stop.wait(5)
            # Marker can disappear before the workspace context releases its lock.
            time.sleep(0.15)

    worker = threading.Thread(target=owner)
    worker.start()
    assert ready.wait(5)
    assert request_handoff(root, timeout=5)
    with workspace_session(root):
        pass
    worker.join(timeout=2)
    assert not worker.is_alive()


def test_handoff_ignores_unrelated_or_linked_markers(tmp_path):
    from modules.accretion.components.schedule_handoff import request_handoff, _paths

    root = tmp_path / "handoff"
    marker, _ = _paths(root)
    marker.write_text(json.dumps({"pid": 1, "nonce": "a" * 32, "workspace": "another"}))
    assert request_handoff(root, timeout=0) is False


def test_signed_scheduled_download_runs_real_intake_and_repeat_is_idempotent(tmp_path):
    from modules.accretion.components.api_acquisition import APIAcquisition
    from modules.accretion.components.intake_service import IntakeService
    from modules.accretion.components.shadowserver_reports import ReportDownloader, SignedTransport
    from modules.accretion.components.shadowserver_reports.demo import (
        _Opener,
        _SyntheticService,
        _Response,
    )
    from tests.support.workbench import FakeRegistry, csv_bytes, observations
    import hashlib

    store = Store(tmp_path / "full-pipeline")
    intake = IntakeService(
        store, attribution_factory=registry_factory(FakeRegistry), capture=capture_website
    )
    remote = _SyntheticService()
    content = csv_bytes([{**observations()[0], "ip": "8.8.8.8"}])
    acquisition = APIAcquisition(
        store,
        intake,
        transport_factory=lambda provider: SignedTransport(
            provider, backend=_Opener(remote.api_open)
        ),
        downloader_factory=lambda root: ReportDownloader(
            root, opener=_Opener(lambda *_args, **_kwargs: _Response(content, "text/csv"))
        ),
    )
    acquisition.configure(remote.credentials.api_key, remote.credentials.secret)
    schedule = AcquisitionSchedule(
        store,
        acquisition,
        SimpleNamespace(status=lambda: {"bootstrap_complete": True}),
        clock=lambda: datetime(2026, 11, 6, 7, tzinfo=timezone.utc),
    )
    schedule.configure(
        {
            **DEFAULTS,
            "enabled": True,
            "reference": False,
            "subscription": "synthetic-example",
            "report_types": ["scan_http_vulnerable"],
        }
    )
    try:
        schedule.tick()
        identity = schedule.status()["run"]["imports"][0]
        assert schedule.status()["run"]["status"] == "importing"
        intake.process(identity)
        schedule.tick()
        assert schedule.status()["run"]["status"] == "complete"
        stored = store.one("SELECT * FROM imports WHERE id=?", (identity,))
        assert stored["status"] == "done"
        assert (
            hashlib.sha256(store.path(stored["path"]).read_bytes()).hexdigest() == stored["sha256"]
        )
        schedule.request_run()
        schedule.tick()
        assert schedule.status()["run"]["status"] == "complete"
        assert store.one("SELECT count(*) AS n FROM imports")["n"] == 1
    finally:
        schedule.close()
        acquisition.close()
        intake.close()


def test_schedule_endpoints_require_session_and_csrf(client):
    token = client.headers.pop("X-Workbench-Token")
    assert client.put("/api/schedule", json=DEFAULTS).status_code == 403
    client.headers["X-Workbench-Token"] = token
    client.cookies.clear()
    assert client.get("/api/schedule").status_code == 401
    assert client.post("/api/schedule/run").status_code == 401
    assert client.put("/api/schedule/background", json={"enabled": True}).status_code == 401


def test_scheduled_reference_check_starts_idle_risk_refresh(tmp_path):
    schedule, network, store = scheduler(tmp_path)

    class Risk:
        def __init__(self):
            self.calls = 0

        def status(self):
            return {
                "running": False,
                "job": {"status": "complete" if self.calls else "idle"},
                "epss": {"last_success_at": NOW.isoformat() if self.calls else None},
                "kev": {"last_success_at": NOW.isoformat() if self.calls else None},
            }

        def sync(self):
            self.calls += 1

    risk = Risk()
    schedule.catalog = SimpleNamespace(
        status=lambda: {"running": False, "job": {"status": "complete"}, "total": 100},
        sync=lambda: None,
        risk=risk,
    )
    run = {}
    schedule._references(run)
    assert risk.calls == 1
    assert run["reference"]["risk"] == "complete"


def test_reference_outage_does_not_block_reports_with_existing_complete_catalog(tmp_path):
    schedule, network, store = scheduler(tmp_path, reference=True)

    def unavailable():
        raise ValueError("Reference transport unavailable")

    schedule.catalog = SimpleNamespace(
        status=lambda: {"bootstrap_complete": True}, sync=unavailable
    )
    schedule.tick()
    assert len(network.calls) == 1
    assert schedule.status()["run"]["reference_error"]
    with store.transaction() as db:
        db.execute("UPDATE imports SET status='done'")
    schedule.tick()
    result = schedule.status()
    assert result["run"]["status"] == "partial"
    assert result["cursor"] == "2026-11-13"
    assert "last_success_at" not in result


@pytest.mark.parametrize(
    "invalid",
    [
        None,
        [],
        {"config": {"enabled": True}},
        {"config": DEFAULTS, "next_run_at": "bad"},
        {"config": DEFAULTS, "run": {"status": "importing", "imports": "bad"}},
    ],
)
def test_corrupt_optional_schedule_does_not_block_workspace(tmp_path, invalid):
    store = Store(tmp_path / "data")
    with store.transaction() as db:
        db.execute("INSERT INTO settings VALUES('scheduled_acquisition',?)", (json.dumps(invalid),))
    schedule = AcquisitionSchedule(store, Acquisition(store), None)
    result = schedule.status()
    assert not result["config"]["enabled"]
    assert result["configuration_error"]


def test_finished_but_old_risk_job_is_refreshed(tmp_path):
    schedule, _, _ = scheduler(tmp_path)

    class Risk:
        calls = 0

        def status(self):
            when = NOW if self.calls else NOW - timedelta(days=2)
            return {
                "running": False,
                "job": {"status": "complete"},
                "epss": {"last_success_at": when.isoformat()},
                "kev": {"last_success_at": when.isoformat()},
            }

        def sync(self):
            self.calls += 1

    risk = Risk()
    schedule.catalog = SimpleNamespace(
        status=lambda: {"running": False, "job": {"status": "complete"}, "total": 100},
        sync=lambda: None,
        risk=risk,
    )
    schedule._references({})
    assert risk.calls == 1


def test_recent_risk_check_preserves_oldest_provider_time(tmp_path):
    schedule, _, _ = scheduler(tmp_path)
    old = NOW - timedelta(hours=19)

    def unexpected():
        raise AssertionError("Fresh feeds should not download again")

    risk = SimpleNamespace(
        status=lambda: {
            "running": False,
            "epss": {"last_success_at": old.isoformat()},
            "kev": {"last_success_at": NOW.isoformat()},
        },
        sync=unexpected,
    )
    schedule.catalog = SimpleNamespace(
        status=lambda: {"running": False, "job": {"status": "complete"}, "total": 100},
        sync=lambda: None,
        risk=risk,
    )
    run = {}
    schedule._references(run)
    assert run["reference"]["checked_at"] == old.isoformat()


@pytest.mark.parametrize("code,expected", [(2, False), (3, None)])
def test_windows_query_distinguishes_missing_task_from_permission_failure(code, expected, tmp_path):
    from modules.accretion.components.windows_schedule import _task_exists

    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=1 if len(calls) == 1 else code)

    if expected is None:
        with pytest.raises(ValueError, match="verify"):
            _task_exists(tmp_path, "ShadowserverCompanion-Schedule-abc", runner, {})
    else:
        assert _task_exists(tmp_path, "ShadowserverCompanion-Schedule-abc", runner, {}) is expected
    assert len(calls) == 2
    assert "-EncodedCommand" in calls[1]
