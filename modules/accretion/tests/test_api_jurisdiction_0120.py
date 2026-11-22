"""Jurisdiction choices stop stale requests before retrieval or Accretion."""

from dataclasses import replace
from datetime import date
import json
import threading

import pytest

from modules.accretion.components.api_jurisdiction import available_subscriptions, state_scope
from modules.accretion.components.scheduling import DEFAULTS
from modules.accretion.components.shadowserver_reports.errors import ConfigurationError
from modules.accretion.tests.support.api_acquisition import (
    acquisition,
    catalog,
    connected,
    finished,
)
from modules.accretion.tests.support.api_acquisition import api_app
from modules.accretion.tests.support.scheduling import scheduler


def regions(store, *names):
    profile = {**store.settings(), "regions": list(names)}
    with store.transaction() as db:
        db.execute("UPDATE settings SET value=? WHERE key='profile'", (json.dumps(profile),))


@pytest.mark.parametrize(
    "name", ["NC", "North Carolina", "north-carolina", "US-NC", "geo-US-NC", "state_north_carolina"]
)
def test_only_whole_states_or_explicit_geographic_forms_are_matched(name):
    assert state_scope(name) == "NC"


@pytest.mark.parametrize(
    "name",
    [
        "acme-ca-security",
        "California Research Institute",
        "NCIS",
        "nc-business",
        "canada",
        "us-custom-nc",
    ],
)
def test_organization_names_are_not_inferred_from_state_fragments(name):
    assert state_scope(name) is None


def test_account_scope_filter_retains_national_and_custom_with_explanation():
    available, scope = available_subscriptions(
        ["US-NC", "US-SC", "california", "united-states", "agency-custom"], ["North Carolina"]
    )
    assert available == ["US-NC", "united-states", "agency-custom"]
    assert scope["hidden_subscriptions"] == 2
    assert scope["matched_subscriptions"] == ["US-NC"]
    assert scope["unclassified_subscriptions"] == ["agency-custom"]
    assert scope["national_subscriptions"] == ["united-states"]
    assert "individual observations still pass" in scope["notice"]


def test_multiple_states_match_and_custom_regions_do_not_assume_nationwide_scope():
    available, scope = available_subscriptions(["NC", "SC", "VA"], ["North Carolina", "SC"])
    assert available == ["NC", "SC"]
    available, scope = available_subscriptions(["NC", "London", "united-states"], ["London"])
    assert available == ["London", "united-states"]
    assert scope["matched_subscriptions"] == ["London"]


def test_connection_status_filters_choices_without_hiding_accountwide_report_types(acquisition):
    service, remote, store = acquisition
    connected(service, remote)
    service.subscriptions = ["US-SC", "US-NC", "united-states", "agency-custom"]
    before = list(service.types)
    status = service.status()
    assert status["subscriptions"] == ["US-NC", "united-states", "agency-custom"]
    assert status["types"] == before
    assert status["selection_defaults"]["subscription"] == "US-NC"
    regions(store, "Virginia")
    assert service.status()["selection_defaults"]["subscription"] == ""
    assert service.status()["subscriptions"] == ["united-states", "agency-custom"]


def test_catalog_rejects_other_state_before_making_requests(acquisition):
    service, remote, _ = acquisition
    connected(service, remote)
    service.subscriptions += ["US-SC"]
    calls = remote.api_calls
    with pytest.raises(ConfigurationError, match="outside your configured jurisdiction"):
        service.start(
            "catalog",
            selection={
                "start": "2026-11-06",
                "end": "2026-11-06",
                "subscription": "US-SC",
                "report_type": "scan_http_vulnerable",
            },
        )
    assert remote.api_calls == calls


def state_catalog(service, remote):
    ids = catalog(service, remote)
    service.subscriptions = ["US-NC", "US-SC"]
    service.catalog = {
        key: replace(report, subscription="US-NC") for key, report in service.catalog.items()
    }
    return ids


def test_changed_regions_hide_old_reports_and_reject_stale_import_ids(acquisition):
    service, remote, store = acquisition
    ids = state_catalog(service, remote)
    assert service.status()["reports"]
    regions(store, "South Carolina")
    assert service.status()["reports"] == []
    with pytest.raises(ConfigurationError, match="outside your configured jurisdiction"):
        service.start("import", report_ids=ids)
    assert remote.download_calls == 0
    assert store.one("SELECT COUNT(*) n FROM imports")["n"] == 0
    service.scope_changed()
    assert service.status()["completeness"] is None
    assert service.status()["subscriptions"] == ["US-SC"]


def test_region_change_during_download_cannot_enqueue_old_scope(acquisition):
    service, remote, store = acquisition
    ids = state_catalog(service, remote)
    original = service.downloader_factory

    class ChangeScopeDownloader:
        def __init__(self, root):
            self.downloader = original(root)

        def download_report(self, report, *, operation):
            receipt = self.downloader.download_report(report, operation=operation)
            regions(store, "South Carolina")
            return receipt

    service.downloader_factory = ChangeScopeDownloader
    job = finished(service, service.start("import", report_ids=ids))
    assert job["status"] == "failed"
    assert "outside your configured jurisdiction" in job["message"]
    assert store.one("SELECT COUNT(*) n FROM imports")["n"] == 0


def test_scheduled_retrieval_rechecks_scope_even_without_browser_connection(acquisition):
    service, remote, _ = acquisition
    service.configure(remote.credentials.api_key, remote.credentials.secret)
    with pytest.raises(ConfigurationError, match="outside your configured jurisdiction"):
        service.scheduled(
            {
                "shadowserver": True,
                "subscription": "US-SC",
                "report_types": ["scan_http_vulnerable"],
            },
            date(2026, 11, 6),
            date(2026, 11, 6),
            cancel_event=threading.Event(),
            queued=lambda _: None,
        )
    assert remote.api_calls == remote.download_calls == 0


def test_schedule_pauses_after_jurisdiction_change_and_keeps_explicit_selection(tmp_path):
    schedule, network, store = scheduler(tmp_path, subscription="US-NC")
    regions(store, "South Carolina")
    status = schedule.status()
    assert "outside your configured jurisdiction" in status["scope_error"]
    assert status["config"]["subscription"] == "US-NC"
    with pytest.raises(ConfigurationError):
        schedule.request_run()
    schedule.tick()
    assert not network.calls
    with pytest.raises(ConfigurationError):
        schedule.configure(status["config"])
    # Disabling an invalid schedule remains possible.
    schedule.configure({**status["config"], "enabled": False})
    assert schedule.status()["config"]["enabled"] is False


def test_routes_reject_direct_other_state_catalog_and_schedule_requests(api_app):
    app, client, remote = api_app
    service = app.state.api_acquisition
    connected(service, remote)
    service.subscriptions += ["US-SC"]
    calls = remote.api_calls
    body = {
        "start": "2026-11-06",
        "end": "2026-11-06",
        "subscription": "US-SC",
        "report_type": "scan_http_vulnerable",
    }
    assert client.post("/api/shadowserver/catalog", json=body).status_code == 400
    response = client.put(
        "/api/schedule",
        json={
            **DEFAULTS,
            "enabled": True,
            "reference": False,
            "subscription": "US-SC",
            "report_types": ["scan_http_vulnerable"],
        },
    )
    assert response.status_code == 400
    assert "outside your configured jurisdiction" in response.json()["detail"]
    assert remote.api_calls == calls


def test_scope_change_during_empty_scheduled_listing_is_not_reported_as_success(acquisition):
    from modules.accretion.components.shadowserver_reports import SignedTransport
    from modules.accretion.components.shadowserver_reports.demo import _Opener

    service, remote, store = acquisition
    service.configure(remote.credentials.api_key, remote.credentials.secret)

    def changed_scope(request, timeout):
        response = remote.api_open(request, timeout)
        if request.full_url.endswith("/reports/list"):
            regions(store, "South Carolina")
        return response

    service.transport_factory = lambda provider: SignedTransport(
        provider, backend=_Opener(changed_scope)
    )
    queued = []
    with pytest.raises(ConfigurationError, match="outside your configured jurisdiction"):
        service.scheduled(
            {
                "shadowserver": True,
                "subscription": "US-NC",
                "report_types": ["scan_http_vulnerable"],
            },
            date(2026, 11, 7),
            date(2026, 11, 7),
            cancel_event=threading.Event(),
            queued=queued.append,
        )
    assert queued == []
    assert remote.download_calls == 0
    assert not service.busy()


@pytest.mark.parametrize(
    "region,subscription",
    [
        ("U.S. Virgin Islands", "US-VI"),
        ("American Samoa", "US-AS"),
        ("Guam", "US-GU"),
        ("Northern Mariana Islands", "US-MP"),
        ("Puerto Rico", "US-PR"),
    ],
)
def test_setup_territory_names_match_their_geographic_subscriptions(region, subscription):
    from modules.settings.components.onboarding import REGIONS

    assert region in REGIONS
    available, scope = available_subscriptions([subscription, "US-NC"], [region])
    assert available == [subscription]
    assert scope["matched_subscriptions"] == [subscription]
    assert scope["hidden_subscriptions"] == 1
