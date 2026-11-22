"""Repeat-heavy outreach intake, without network calls or production data."""

from tests.support.qualification import registry_factory

from datetime import date, timedelta

import pytest
from tests.support.workbench import app, client, observations
from modules.leads.tests.support.lead_queue import queue_import, SharedRegistry
from modules.entities.tests.support.contacts_api import FixtureCore, finished
from modules.leads.components.lead_queue import LeadQueue
from modules.entities.components.contact_records import ContactRecords
from modules.observatory.components.eclipse import Eclipse
from modules.leads.components.provider_policy import is_provider
from modules.accretion.components.report_profiles import (
    notification_eligibility,
    resolve_profile,
)

from modules.leads.tests.support.lead_queue import ingest


def test_sixty_repeat_days_keep_one_current_lead_and_one_signal(client, app):
    for day in range(60):
        latest = ingest(client, app, (date(2026, 9, 1) + timedelta(days=day)).isoformat())
    store = app.state.store
    queue = LeadQueue(store).list()
    assert len(queue) == 1 and queue[0]["id"] == latest["id"]
    assert queue[0]["observations"] == 60 and queue[0]["finding_count"] == 1
    signals = store.all("SELECT * FROM awareness_findings WHERE admitted=1")
    assert len(signals) == 1
    assert signals[0]["first_seen"].startswith("2026-09-01")
    assert signals[0]["last_seen"].startswith("2026-10-30")
    assert len(store.all("SELECT * FROM entries")) == 1
    assert len(store.all("SELECT * FROM lead_queue WHERE payload<>'[]'")) == 1
    assert len(store.all("SELECT * FROM jobs WHERE payload<>'[]'")) == 1
    assert len(store.all("SELECT * FROM imports")) == 60
    assert not store.all("PRAGMA foreign_key_check")
    field = Eclipse(store).snapshot()
    assert len(field["observations"]) == 60
    assert len(field["findings"]) == 1 and field["findings"][0]["sightings"] == 60
    assert field["findings"][0]["observation_count"] == 60


def test_complementary_same_day_reports_share_one_scope_and_source_ids(client, app):
    first = ingest(client, app)
    second = ingest(client, app, hostname="web.example.com", unknown_extension="another report")
    queue = LeadQueue(app.state.store)
    row = queue.list()[0]
    assert len(queue.list()) == 1 and row["observations"] == 2
    detail = queue.detail(row["id"])
    ids = {e["id"] for e in detail["entries"]}
    assert len(ids) == 2
    result = queue.start(row["id"], row["revision"])
    scope = app.state.store.all("SELECT * FROM case_entries WHERE case_id=?", (result["case_id"],))
    assert {r["entry_id"] for r in scope} == ids
    assert not queue.detail(first["id"])["can_start"]
    assert second["id"] == row["id"]


def test_new_day_retires_unworked_findings_and_late_reports_cannot_replace_it(client, app):
    old = ingest(client, app, "2026-11-10", version="7.3.24")
    latest = ingest(client, app, "2026-11-12", version="7.3.25")
    late = ingest(client, app, "2026-11-11", version="7.3.23")
    queue = LeadQueue(app.state.store)
    assert [r["id"] for r in queue.list()] == [latest["id"]]
    assert queue.detail(old["id"])["superseded_by"] == latest["id"]
    assert queue.detail(late["id"])["superseded_by"] == latest["id"]
    assert app.state.store.dark_matter.query()["total"] == 0
    assert (
        app.state.store.one("SELECT count(*) total FROM awareness_observations WHERE admitted=1")[
            "total"
        ]
        == 3
    )
    assert len(app.state.store.all("SELECT * FROM entries")) == 1
    assert app.state.store.one("SELECT observed_at FROM entries")["observed_at"].startswith(
        "2026-11-12"
    )
    with pytest.raises(ValueError):
        queue.start(old["id"], queue.detail(old["id"])["revision"])


def test_handled_repeat_and_patch_change_stop_before_fresh_qualification(client, app):
    ingest(client, app, "2026-11-10")
    store, queue = app.state.store, LeadQueue(app.state.store)
    row = queue.list()[0]
    case = queue.start(row["id"], row["revision"])["case_id"]
    before = store.one("SELECT * FROM cases WHERE id=?", (case,))
    scope = store.all("SELECT * FROM case_entries WHERE case_id=?", (case,))
    ingest(client, app, "2026-11-11")
    assert queue.list() == []
    archived = store.dark_matter.query()
    assert archived["total"] == 1
    assert archived["items"][0]["reason"] == "no_actionable_findings"
    ingest(client, app, "2026-11-12", version="7.3.26")
    assert queue.list() == []
    assert store.dark_matter.query()["total"] == 2
    assert store.one("SELECT admitted,workflow FROM awareness_findings") == {
        "admitted": 1,
        "workflow": "handled",
    }
    assert store.one("SELECT * FROM cases WHERE id=?", (case,)) == before
    assert store.all("SELECT * FROM case_entries WHERE case_id=?", (case,)) == scope
    assert not store.all("PRAGMA foreign_key_check")


def test_ignore_suppresses_unchanged_repeats_but_accepts_new_findings(client, app):
    ingest(client, app, "2026-11-10")
    queue = LeadQueue(app.state.store)
    row = queue.list()[0]
    queue.disposition(row["id"], row["revision"], "dismissed")
    ingest(client, app, "2026-11-11")
    assert queue.list() == []
    ingest(client, app, "2026-11-12", version="8.0.1")
    assert len(queue.list()) == 1


def test_failed_attribution_is_hidden_until_qualification_finishes(client, app):
    app.state.fake.fail = True
    queue_import(client, app)
    assert LeadQueue(app.state.store).list("all") == []
    job = app.state.store.one("SELECT * FROM jobs")
    app.state.fake.fail = False
    app.state.intake.retry(job["import_id"])
    app.state.intake.process(job["import_id"])
    assert len(LeadQueue(app.state.store).list()) == 1


def test_shared_ip_keeps_separate_entities_without_review(client, app):
    app.state.intake.attribution_factory = registry_factory(SharedRegistry)
    ingest(client, app)
    ingest(client, app, hostname="mail.another.com")
    rows = LeadQueue(app.state.store).list()
    assert len(rows) == 2 and len({r["entity_id"] for r in rows}) == 2
    assert all(r["can_start"] and r["association_state"] == "new" for r in rows)
    for row in rows:
        related = LeadQueue(app.state.store).detail(row["id"])["shared_ip_associations"]
        assert len(related) == 1 and related[0]["ip"] == "8.8.8.8"
        assert related[0]["first_seen"].startswith("2026-11-12")
        entity = app.state.store.entities.lead(row["entity_id"])
        assert entity["shared_ip_associations"] == related


@pytest.mark.parametrize(
    "host",
    [
        "mail.spectrum.com",
        "static.charter.net",
        "att.net",
        "verizon.com",
        "business.brightspeed.com",
        "ip.comcast.net",
    ],
)
def test_provider_domains_are_admitted_for_priority_penalty(host):
    fields = {**observations()[0], "hostname": host}
    result = notification_eligibility(
        fields, resolve_profile(fields, "scan_http_vulnerable.csv"), {}
    )
    assert result["eligible"]
    assert not is_provider("spectrum.com.example.com")


def test_provider_asn_does_not_exclude_a_customer(client, app):
    ingest(client, app, asn="20115")
    assert len(LeadQueue(app.state.store).list()) == 1


def test_contact_discovery_automatically_saves_default_pending_confirmation(client, app):
    row = ingest(client, app)
    jobs, calls = app.state.contact_discovery_jobs, []
    jobs.core_factory = lambda: FixtureCore(calls)
    assert jobs.automatic_thread is None  # worker=False keeps tests offline.
    job = jobs.automatic_once()
    done = finished(jobs, job["id"])
    assert done["state"] == "completed", done
    state = ContactRecords(app.state.store).state(row["entity_id"])
    candidate = state["candidates"][0]
    assert candidate["preferred"] and candidate["decision"] == "pending"
    assert not candidate["reviewed_by"] and not candidate["review_required"]
    assert (
        app.state.store.entities.lead(row["entity_id"])["entity_profile"]["contact_email"]
        == "security@example.com"
    )
    assert len(calls) == 1 and jobs.automatic_once() is None
    assert not app.state.store.all("SELECT * FROM cases")


def test_auto_contact_does_not_replace_manual_contact(client, app):
    row = ingest(client, app)
    with app.state.store.transaction() as db:
        app.state.store.entities.save_profile(
            db, row["entity_id"], {"contact_email": "known@example.com"}
        )
    jobs = app.state.contact_discovery_jobs
    jobs.core_factory = lambda: FixtureCore([])
    done = finished(jobs, jobs.automatic_once()["id"])
    assert done["state"] == "completed", done
    profile = app.state.store.entities.lead(row["entity_id"])["entity_profile"]
    assert profile["contact_email"] == "known@example.com"
    assert not ContactRecords(app.state.store).state(row["entity_id"])["candidates"][0]["preferred"]


def test_associating_two_roots_consolidates_scope_and_retains_each_source(client, app):
    app.state.intake.attribution_factory = registry_factory(SharedRegistry)
    first = ingest(client, app)
    second = ingest(client, app, hostname="mail.another.com")
    queue = LeadQueue(app.state.store)
    associated = queue.associate(second["id"], second["revision"], first["entity_id"])
    assert len(queue.list()) == 1 and associated["observations"] == 2
    result = queue.start(associated["id"], associated["revision"])
    assert (
        len(app.state.store.all("SELECT * FROM case_groups WHERE case_id=?", (result["case_id"],)))
        == 2
    )
    assert not app.state.store.all("PRAGMA foreign_key_check")


def test_automatic_contact_failure_does_not_retry_or_block_leads(client, app):
    row = ingest(client, app)
    jobs = app.state.contact_discovery_jobs

    class Failed:
        def discover(self, *args, **kwargs):
            raise ValueError("synthetic failure")

    jobs.core_factory = Failed
    done = finished(jobs, jobs.automatic_once()["id"])
    assert done["state"] == "failed"
    assert jobs.automatic_once() is None
    assert LeadQueue(app.state.store).list()[0]["entity_id"] == row["entity_id"]


def test_ignored_attribution_support_does_not_offer_new_work(client, app):
    ingest(client, app)
    queue = LeadQueue(app.state.store)
    row = queue.list()[0]
    queue.disposition(row["id"], row["revision"], "dismissed")
    assert queue.list() == []
    entity = client.get("/api/leads").json()[0]
    assert entity["unassigned_observations"] == 0
    assert entity["new_observations"] == 0


def test_numeric_finding_name_and_explicit_protocol_fields():
    from modules.accretion.components.intake.findings import finding_rejection_reason
    from modules.accretion.components.intake.versions import selected_version

    assert finding_rejection_reason("21nails;smtp") is None
    assert finding_rejection_reason("12345") == "unsupported_finding"
    profile = resolve_profile({}, configured_type="population_ntrip")
    selected = selected_version({"version": "", "ntrip_version": "Ntrip/2.0"}, profile)
    assert selected == {"source_field": "ntrip_version", "raw_version": "Ntrip/2.0"}
    assert profile["version_semantics"] == "protocol"
