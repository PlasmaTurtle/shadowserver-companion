"""Runtime replacement reserves the workspace and recovers if handoff fails."""

from types import SimpleNamespace

import pytest

from workbench.store import Store
from workbench.workspace_data import WorkspaceData


def manager(tmp_path):
    store = Store(tmp_path)
    app = SimpleNamespace(state=SimpleNamespace())
    return WorkspaceData(app, store)


def test_update_reserves_admission_and_failed_launch_can_restore_work(tmp_path):
    data = manager(tmp_path)
    assert data.enter_request("/api/software/install", "POST") is None
    assert data.begin_update() is None
    assert data.store.maintenance.is_set()
    assert data.enter_request("/api/settings", "PUT")
    assert data.enter_request("/api/overview", "GET")
    assert data.enter_request("/api/software/status", "GET") is None
    data.exit_request("/api/software/status")
    data.exit_request("/api/software/install")
    with pytest.raises(ValueError):
        with data.operation():
            pytest.fail("data replacement entered while an update owns the workspace")
    data.cancel_update()
    assert not data.store.maintenance.is_set()
    assert data.active_requests == 0
    assert data.enter_request("/api/settings", "PUT") is None


def test_update_cannot_interrupt_another_request_or_background_job(tmp_path):
    data = manager(tmp_path)
    data.enter_request("/api/software/install", "POST")
    data.enter_request("/api/settings", "PUT")
    assert data.begin_update()
    assert not data.updating
    data.exit_request("/api/settings")
    data.app.state.report_operations = SimpleNamespace(busy=lambda: True)
    assert "active reports" in data.begin_update()
    assert not data.updating
    assert not data.store.maintenance.is_set()


def test_failed_reservation_preserves_staged_data_maintenance(tmp_path):
    data = manager(tmp_path)
    data.pending = {"operation": "import"}
    data.store.maintenance.set()
    assert data.begin_update()
    data.cancel_update()
    assert data.store.maintenance.is_set()


def reference_manager(tmp_path, *, factory=None):
    from workbench.cve_catalog.manager import CatalogManager
    from workbench.cve_catalog.risk_manager import RiskManager
    from workbench.routes.cve_catalog import CatalogAccess

    store = Store(tmp_path)
    risk = RiskManager(SimpleNamespace())
    catalog = CatalogManager(SimpleNamespace(), risk=risk)
    access = CatalogAccess(factory or (lambda: catalog))
    data = WorkspaceData(SimpleNamespace(state=SimpleNamespace(cve_catalog=access)), store)
    return data, catalog, risk, access


@pytest.mark.parametrize("kind", ["catalog", "index", "risk"])
def test_update_waits_for_each_independent_reference_worker(tmp_path, kind):
    data, catalog, risk, _ = reference_manager(tmp_path)
    alive = SimpleNamespace(is_alive=lambda: True)
    if kind == "catalog":
        catalog.worker = alive
    elif kind == "index":
        catalog.index_worker = alive
    else:
        risk.worker = alive
    message = data.begin_update()
    assert "CVE catalog, risk feed and product index" in message
    assert not data.updating
    assert not data.store.maintenance.is_set()


@pytest.mark.parametrize("status", ["queued", "running"])
def test_update_waits_for_queued_and_running_entity_dns(tmp_path, status):
    from workbench.entity_dns import EntityDNS

    data = manager(tmp_path)
    dns = EntityDNS(data.store)
    data.app.state.entity_dns = dns
    dns.jobs["fixture"] = {"status": status}
    assert "lookups" in data.begin_update()
    assert not data.updating
    assert not data.store.maintenance.is_set()
    dns.jobs["fixture"]["status"] = "complete"
    assert data.begin_update() is None
    with pytest.raises(ValueError, match="operation or update"):
        dns.start({"id": "new", "domain": "example.com"})
    assert "new" not in dns.jobs
    data.cancel_update()


@pytest.mark.parametrize("kind", ["catalog", "risk"])
def test_independent_schedule_cannot_start_while_update_checks_its_lock(tmp_path, kind):
    import threading

    data, catalog, risk, _ = reference_manager(tmp_path)
    owner = catalog if kind == "catalog" else risk
    outcomes = []
    started = []
    # If the maintenance check is absent this replaces the worker body, keeping
    # the regression bounded and proving that an unauthorized start occurred.
    owner._run = lambda *args: started.append(kind)
    if kind == "catalog":
        from datetime import datetime, timezone

        owner.catalog = SimpleNamespace(clock=lambda: datetime.now(timezone.utc))
    else:
        from datetime import datetime, timezone

        owner.store.clock = lambda: datetime.now(timezone.utc)
    start = owner._start_job if kind == "catalog" else lambda: owner._start_job(["epss", "kev"])
    with owner.lock:
        updater = threading.Thread(target=lambda: outcomes.append(data.begin_update()), daemon=True)
        updater.start()
        assert data.store.maintenance.wait(2)
        timer = threading.Thread(target=start, daemon=True)
        timer.start()
    updater.join(2)
    timer.join(2)
    assert not updater.is_alive() and not timer.is_alive()
    assert outcomes == [None]
    assert started == []
    assert owner.worker is None
    data.cancel_update()
    assert not owner.maintenance.is_set()


def test_update_reservation_blocks_explicit_reference_starts_without_side_effects(tmp_path):
    data, catalog, risk, _ = reference_manager(tmp_path)
    assert data.begin_update() is None
    for start in (catalog.sync, risk.sync):
        with pytest.raises(ValueError, match="operation or update"):
            start()
    catalog.status = lambda: {"index_running": False}
    assert catalog.index() == {"index_running": False}
    assert catalog.worker is catalog.index_worker is risk.worker is None
    data.cancel_update()
    assert not catalog.maintenance.is_set()
    assert not risk.maintenance.is_set()


def test_optional_catalog_stays_lazy_and_recovery_inherits_maintenance(tmp_path):
    calls = []

    def unavailable():
        calls.append("attempt")
        raise ValueError("synthetic unavailable reference data")

    data, catalog, risk, access = reference_manager(tmp_path, factory=unavailable)
    assert calls == ["attempt"]
    assert access.manager is None
    assert data.begin_update() is None
    assert calls == ["attempt"]
    data.cancel_update()
    access.factory = lambda: catalog
    access._initialize()
    assert catalog.maintenance is data.store.maintenance
    assert risk.maintenance is data.store.maintenance


def test_update_does_not_hold_store_lock_while_waiting_for_worker_lock(tmp_path):
    import threading

    data = manager(tmp_path)
    worker_ready, inspected = threading.Event(), threading.Event()
    service_lock = threading.Lock()
    outcomes = []

    def busy():
        inspected.set()
        with service_lock:
            return False

    data.app.state.source_jobs = SimpleNamespace(busy=busy)

    def finish_worker():
        with service_lock:
            worker_ready.set()
            assert inspected.wait(2)
            with data.store.transaction() as db:
                db.execute("INSERT OR REPLACE INTO settings VALUES('update-lock-test', '{}')")

    worker = threading.Thread(target=finish_worker, daemon=True)
    worker.start()
    assert worker_ready.wait(2)
    updater = threading.Thread(target=lambda: outcomes.append(data.begin_update()), daemon=True)
    updater.start()
    worker.join(2)
    updater.join(2)
    assert not worker.is_alive() and not updater.is_alive(), "service/store lock inversion"
    assert outcomes == [None]
    assert data.store.one("SELECT value FROM settings WHERE key='update-lock-test'")
    data.cancel_update()


@pytest.mark.parametrize("kind", ["catalog", "index", "risk", "dns"])
def test_data_operations_wait_for_independent_reference_and_dns_jobs(tmp_path, kind):
    from workbench.entity_dns import EntityDNS

    data, catalog, risk, _ = reference_manager(tmp_path)
    alive = SimpleNamespace(is_alive=lambda: True)
    if kind == "catalog":
        catalog.worker = alive
    elif kind == "index":
        catalog.index_worker = alive
    elif kind == "risk":
        risk.worker = alive
    else:
        dns = EntityDNS(data.store)
        dns.jobs["fixture"] = {"status": "queued"}
        data.app.state.entity_dns = dns
    with pytest.raises(ValueError, match="before managing data"):
        with data.operation():
            pytest.fail("data replacement entered during background work")
    assert not data.preparing
    assert not data.store.maintenance.is_set()


def test_data_operation_avoids_service_lock_inversion_and_holds_writer_during_yield(tmp_path):
    import threading

    data = manager(tmp_path)
    worker_ready, inspected = threading.Event(), threading.Event()
    service_lock = threading.Lock()
    outcomes, writer_acquired = [], []

    def busy():
        inspected.set()
        with service_lock:
            return False

    data.app.state.source_jobs = SimpleNamespace(busy=busy)

    def finish_worker():
        with service_lock:
            worker_ready.set()
            assert inspected.wait(2)
            with data.store.transaction() as db:
                db.execute("INSERT OR REPLACE INTO settings VALUES('data-lock-test', '{}')")

    def writer_probe():
        acquired = data.store.lock.acquire(blocking=False)
        writer_acquired.append(acquired)
        if acquired:
            data.store.lock.release()

    def operation():
        with data.operation():
            assert data.store.maintenance.is_set()
            assert data.store.one("SELECT value FROM settings WHERE key='data-lock-test'")
            probe = threading.Thread(target=writer_probe, daemon=True)
            probe.start()
            probe.join(2)
            assert not probe.is_alive()
            outcomes.append("entered")

    worker = threading.Thread(target=finish_worker, daemon=True)
    worker.start()
    assert worker_ready.wait(2)
    manager_thread = threading.Thread(target=operation, daemon=True)
    manager_thread.start()
    worker.join(2)
    manager_thread.join(2)
    assert not worker.is_alive() and not manager_thread.is_alive(), "service/store lock inversion"
    assert outcomes == ["entered"]
    assert writer_acquired == [False], "backup/staging lost its writer reservation"
    assert not data.preparing
    assert not data.store.maintenance.is_set()
