"""No unit/integration test may quietly depend on public services."""

import pytest
import requests


@pytest.fixture(autouse=True)
def block_external_requests(monkeypatch):
    def blocked(*args, **kwargs):
        # A prohibited test request is not a transient network failure. Retry
        # tests install their own transport faults and controlled clocks.
        raise requests.RequestException("External networking disabled in tests")

    monkeypatch.setattr(requests, "get", blocked)
    from workbench.intelligence import acquisition

    monkeypatch.setattr(acquisition, "_response_get", blocked)
    # Offline source fixtures must not sleep on the cross-provider network gate.
    # Transport rate-limit tests exercise the original gate with a controlled clock.
    from workbench import cve_catalog

    monkeypatch.setattr(cve_catalog, "pace_nvd", lambda cancel_event=None, **kwargs: None)
