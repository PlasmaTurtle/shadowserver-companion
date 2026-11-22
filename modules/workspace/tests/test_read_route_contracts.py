"""Ordinary navigation must not mutate retained work or initiate casework."""

from contextlib import closing
import hashlib

from tests.support.workbench import app as app, client as client, import_rows, observations


def retained_state(store):
    with closing(store.connect()) as db:
        database = "\n".join(db.iterdump())
    files = {}
    for folder in ("originals", "evidence", "reports", "closures"):
        for path in sorted((store.root / folder).rglob("*")):
            if path.is_file():
                files[path.relative_to(store.root).as_posix()] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
    return database, files


def test_navigation_reads_preserve_retained_work(app, client, monkeypatch, subtests):
    import_rows(client, app, observations(), start_notifications=False)
    store = app.state.store
    entity = store.one("SELECT id FROM leads WHERE merged_into IS NULL")["id"]
    assert store.one("SELECT COUNT(*) AS n FROM cases")["n"] == 0
    before = retained_state(store)
    connect = store.connect

    def read_connection():
        db = connect()
        db.execute("PRAGMA query_only=ON")
        return db

    # These are ordinary navigation/status projections. Working notification
    # refresh and generated exports have separate, explicit write contracts.
    paths = (
        "/api/bootstrap",
        "/api/dashboard",
        "/api/workspace/queue",
        "/api/workspace/brief",
        "/api/search?q=example",
        "/api/activity",
        "/api/entities",
        f"/api/entities/{entity}",
        f"/api/entities/{entity}/connections/dns",
        f"/api/entities/{entity}/contacts",
        "/api/navigation-counts",
        "/api/leads",
        "/api/cases",
        "/api/reports",
        "/api/report-operations",
        "/api/imports",
        "/api/intake/progress",
        "/api/intake/capabilities",
        "/api/explainers",
        "/api/setup",
        "/api/software/status",
        "/api/software/whats-new",
        "/api/cve-catalog/status",
        "/api/cve-catalog/search?q=example",
        "/api/cve-catalog/products",
        "/api/cve-catalog/fields",
        "/api/cve-catalog/changes",
        "/api/cve-catalog/index",
        "/api/data/status",
        "/api/data/health",
        "/api/data/maintenance",
        "/api/dark-matter",
        "/api/eclipse",
    )
    with monkeypatch.context() as guard:
        guard.setattr(store, "connect", read_connection)
        for path in paths:
            with subtests.test(path=path):
                response = client.get(path)
                assert response.status_code == 200, response.text
                assert retained_state(store) == before, path
    assert store.one("SELECT COUNT(*) AS n FROM cases")["n"] == 0
