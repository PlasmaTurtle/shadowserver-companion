"""Reusable synthetic lead queue fixtures and builders."""

from tests.support.workbench import FakeRegistry, import_rows, observations


def queue_import(client, app, rows=None, name="report.csv"):
    return import_rows(client, app, rows, name, start_notifications=False)


class OtherRegistry(FakeRegistry):
    def lookup(self, ip):
        r = super().lookup(ip)
        return type(r)(
            r.ip, r.registry, r.source_url, r.retrieved_at, {"contact": "it@another.com"}
        )


class SharedRegistry(FakeRegistry):
    """One immutable shared-address record supports both independent roots.

    Changing a fixture's later response cannot change an already cached RDAP
    record. These association tests provide both observed relationships in the
    initial response instead of relying on a cache bypass.
    """

    def lookup(self, ip):
        result = super().lookup(ip)
        return type(result)(
            result.ip,
            result.registry,
            result.source_url,
            result.retrieved_at,
            {**result.record, "contact": "security@example.com, it@another.com"},
        )


def ingest(client, app, day="2026-11-12", **fields):
    row = {**observations()[2], "timestamp": day + " 01:02:03", **fields}
    result, _ = queue_import(client, app, [row], "scan_http_vulnerable.csv")
    saved = app.state.store.one("SELECT * FROM imports WHERE id=?", (result["id"],))
    assert saved["status"] == "done", saved
    return app.state.store.one("SELECT * FROM lead_queue WHERE import_id=?", (result["id"],))
