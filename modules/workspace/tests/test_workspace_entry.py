"""Workspace shows ready work, and browser icons resolve at every supported size."""

from tests.support.qualification import registry_factory, capture_website

import io

from PIL import Image

from tests.support.workbench import FakeRegistry, app, client, import_rows, observations
from modules.investigations.components.cases import Cases
from modules.leads.components.lead_queue import LeadQueue


def test_workspace_ready_leads_match_queue_and_exclude_work_already_started(client, app):
    import_rows(client, app, start_notifications=False)
    queue = LeadQueue(app.state.store)
    pending = queue.list()
    assert len(pending) == 1
    brief = client.get("/api/workspace/brief").json()
    assert brief["counts"]["leads"] == 1
    assert [row["id"] for row in brief["leads"]] == [pending[0]["id"]]
    assert not {"payload", "entries", "source_observations"} & brief["leads"][0].keys()
    deferred = queue.disposition(pending[0]["id"], pending[0]["revision"], "deferred")
    assert client.get("/api/workspace/brief").json()["counts"]["leads"] == 0
    queue.disposition(deferred["id"], deferred["revision"], "pending")
    assert client.get("/api/workspace/brief").json()["counts"]["leads"] == 1
    # Legacy/direct case creation does not update the stored queue status. The
    # overview must still recognize that its observations already belong to work.
    Cases(app.state.store).create(pending[0]["entity_id"])
    assert app.state.store.one("SELECT status FROM lead_queue")["status"] == "pending"
    assert queue.list() == []
    assert client.get("/api/workspace/brief").json()["counts"]["leads"] == 0


def test_workspace_lead_preview_is_bounded_without_truncating_total(client, app):
    class Registry(FakeRegistry):
        def lookup(self, ip):
            record = super().lookup(ip)
            return type(record)(
                record.ip,
                record.registry,
                record.source_url,
                record.retrieved_at,
                {"contact": f"abuse@case{ip.rsplit('.', 1)[-1]}.org"},
            )

    app.state.intake.attribution_factory = registry_factory(Registry)
    import_rows(
        client,
        app,
        [
            {**observations()[0], "hostname": f"mail.case{i}.org", "ip": f"8.8.8.{i}"}
            for i in range(1, 7)
        ],
        start_notifications=False,
    )
    queued = client.get("/api/pending-leads").json()
    assert len(queued) == 6
    brief = client.get("/api/workspace/brief").json()
    assert brief["counts"]["leads"] == 6
    assert [row["id"] for row in brief["leads"]] == [row["id"] for row in queued[:4]]


def test_eclipse_favicon_has_svg_png_and_conventional_ico_fallback(client):
    page = client.get("/")
    assert page.status_code == 200
    for path in ("favicon.svg", "favicon.png", "favicon.ico"):
        assert f"/modules/ui/static/{path}?v=eclipse-1" in page.text
        assert client.get("/modules/ui/static/" + path).status_code == 200
    ico = client.get("/favicon.ico")
    assert ico.status_code == 200
    assert ico.content == client.get("/modules/ui/static/favicon.ico").content
    with Image.open(io.BytesIO(ico.content)) as icon:
        assert icon.format == "ICO"
        assert icon.ico.sizes() == {(16, 16), (32, 32), (48, 48), (64, 64)}
    with Image.open(io.BytesIO(client.get("/modules/ui/static/favicon.png").content)) as png:
        assert png.size == (64, 64)
