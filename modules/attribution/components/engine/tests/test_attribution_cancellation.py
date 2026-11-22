"""Shutdown reaches RDAP waits and prevents a late response becoming a match."""

from concurrent.futures import ThreadPoolExecutor
import threading
import time

import pytest

from attribution import AttributionModule, CandidateIP, EvidenceStore, Settings
from attribution.bounded_http import CaptureCancelled
from attribution.http import RegistryHttpClient, RequestContext
from attribution.models import LookupFailure, ProviderResult


def test_module_propagates_cancellation_to_both_default_providers(tmp_path):
    cancel = threading.Event()
    with AttributionModule.open(tmp_path / "attribution.sqlite3", cancel_event=cancel) as module:
        assert module.providers[0].cancel_event is cancel
        assert all(provider.cancel_event is cancel for provider in module.providers[1].providers)


def test_rdap_native_capture_receives_cancellation_and_preserves_outcome(tmp_path, monkeypatch):
    import attribution.http as http

    cancel = threading.Event()
    received = []

    def capture(url, **kwargs):
        received.append(kwargs["cancel_event"])
        raise CaptureCancelled("Cancelled")

    monkeypatch.setattr(http, "capture_response", capture)
    with EvidenceStore(tmp_path / "attribution.sqlite3") as evidence:
        client = RegistryHttpClient(evidence, Settings(interval=0))
        with pytest.raises(LookupFailure) as error:
            client.fetch(
                "https://rdap.arin.net/ip/8.8.8.8",
                {"rdap.arin.net"},
                lambda data: None,
                RequestContext(time.monotonic() + 30, cancel_event=cancel),
            )
        assert error.value.reason == "cancelled"
        assert received == [cancel]
        client.close()


@pytest.mark.parametrize("waiting", ["pacing", "queue"])
def test_cancellation_interrupts_existing_waits(waiting):
    cancel, entered = threading.Event(), threading.Event()
    context = RequestContext(time.monotonic() + 30, cancel_event=cancel)
    lock = threading.Lock()
    lock.acquire()

    def operation():
        entered.set()
        if waiting == "pacing":
            context.wait(20)
        else:
            context.acquire(lock)

    with ThreadPoolExecutor(max_workers=1) as executor:
        task = executor.submit(operation)
        assert entered.wait(1)
        cancel.set()
        with pytest.raises(LookupFailure) as error:
            task.result(timeout=1)
        assert error.value.reason == "cancelled"
    lock.release()


def test_cancellation_after_provider_return_never_qualifies_or_starts_dns(tmp_path):
    cancel = threading.Event()
    calls = []

    class Provider:
        def __init__(self, name):
            self.name = name

        def collect(self, *args, **kwargs):
            calls.append(self.name)
            cancel.set()
            return ProviderResult("no_match")

    with EvidenceStore(tmp_path / "attribution.sqlite3") as evidence:
        module = AttributionModule(
            evidence, providers=[Provider("rdap"), Provider("dns")], cancel_event=cancel
        )
        with pytest.raises(LookupFailure) as error:
            module.attribute(
                "example.com", [CandidateIP("original", "8.8.8.8", "login.example.com")]
            )
        assert error.value.reason == "cancelled"
        assert calls == ["rdap"]
        assert evidence._db.execute("SELECT count(*) FROM results").fetchone()[0] == 0
